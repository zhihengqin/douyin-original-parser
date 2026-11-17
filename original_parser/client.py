"""作品链接 → 官方原画 → 可下载 URL → 实际媒体校验。"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import ssl
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests

from .codec import decode_url
from .guest import USER_AGENT, UIFID_NAMES, cached_guest, get_guest
from .media import inspect_file, inspect_mp4

DETAIL_URL = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
DETAIL_UA = USER_AGENT
MAX_JSON_BYTES = 8 * 1024 * 1024
logger = logging.getLogger(__name__)
GUEST_RETRY_CODES = frozenset(("credentials_required", "credentials_rejected",
                               "upstream_empty_response", "upstream_non_json"))
# 可信原片记录的来源标记。两种都必须已完成官方入口分发确认与 MP4 媒体校验：
#   official_fplay_and_mp4_probe          官方 fplay 直接下发 original/source 档位
#                                         （身份由平台自己给出，默认参与生产）
#   official_play_hash_from_verified_asset 外部资产哈希经官方分发重签并核对
#                                         （仅历史补救用，默认不参与，需显式开启；
#                                          它无法由作品 ID 自身推出，不属于首次发现）
OFFICIAL_PROVENANCE = "official_fplay_and_mp4_probe"
EXTERNAL_ASSET_PROVENANCE = "official_play_hash_from_verified_asset"
# 官方 /aweme/v1/play/ 的默认档（ratio=default）直接 302 到上传原片，
# 只需作品自己的 video_id，不需要任何整文件哈希。
PLAY_DEFAULT_PROVENANCE = "official_play_default_and_mp4_probe"
VERIFIED_PROVENANCE = frozenset((OFFICIAL_PROVENANCE, EXTERNAL_ASSET_PROVENANCE, PLAY_DEFAULT_PROVENANCE))
PLAY_URL = "https://www.douyin.com/aweme/v1/play/"

# requests normally wraps OpenSSL failures in ``requests.exceptions.SSLError``.
# A few response adapters expose the underlying ``ssl.SSLError`` directly,
# especially while reading a streamed body, so keep both in every transport
# boundary below.
_REQUEST_ERRORS = (requests.RequestException, ssl.SSLError)


def _external_asset_recovery_enabled(allow_external: bool | None = None) -> bool:
    """外部资产哈希恢复默认关闭，避免把非平台下发的身份当常规取址。

    allow_external 为 True/False 时按调用方显式选择；None 时跟随环境变量。
    """
    if allow_external is not None:
        return bool(allow_external)
    return os.environ.get("DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY", "").strip().lower() in (
        "1", "true", "yes")
_ORIGINAL_METADATA_LOCK = threading.Lock()
_DEFAULT_ORIGINAL_METADATA = Path(__file__).resolve().parents[1] / "original_metadata.json"
PLATFORM_HOSTS = ("douyin.com", "iesdouyin.com")
# 保留历史域名集合供离线研究工具使用，生产原画取址及下载不再按此集合筛选。
MEDIA_HOSTS = ("douyinvod.com", "douyin.com", "iesdouyin.com", "snssdk.com",
               "amemv.com", "ixigua.com", "365yg.com", "toutiaovod.com", "bytecdn.cn", "bytecdn.com",
               "bytedance.com", "bytedance.net", "bytednsdoc.com", "pstatp.com", "zjcdn.com")


class ParseError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _exception_chain(error: BaseException):
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _is_tls_error(error: BaseException) -> bool:
    """Recognize requests, OpenSSL, and wrapped adapter TLS exceptions."""
    for current in _exception_chain(error):
        if isinstance(current, (requests.exceptions.SSLError, ssl.SSLError)):
            return True
        # urllib3's SSLError can reach custom adapters without being converted
        # to requests.exceptions.SSLError. Avoid importing urllib3 just for a
        # type check; restrict the fallback to its SSL-named exception class.
        if (type(current).__name__ == "SSLError"
                and type(current).__module__.split(".", 1)[0] in {"urllib3", "ssl"}):
            return True
    return False


def _tls_failure_reason(error: BaseException) -> str:
    """Return a short, non-sensitive reason for an HTTPS failure.

    ``requests`` often wraps an urllib3/OpenSSL error in a message containing
    the complete request path.  Do not expose that text to callers or logs:
    signed query strings and cookies must never become part of a diagnostic.
    The small set of labels below is enough to distinguish deployment
    certificate/proxy problems from a peer abort without depending on a
    particular OpenSSL version or urllib3 exception layout.
    """
    parts: list[str] = []
    for current in _exception_chain(error):
        parts.append(str(current).lower())
    text = " ".join(parts)
    if "certificate verify failed" in text or "unable to get local issuer" in text \
            or "self signed certificate" in text:
        return "证书校验失败"
    if "hostname mismatch" in text or "doesn't match" in text:
        return "证书主机名不匹配"
    if "wrong version number" in text or "unknown protocol" in text \
            or "wrong tls" in text or "protocol version" in text:
        return "TLS 协议与代理或对端不匹配"
    if "tlsv1 alert" in text or "sslv3 alert" in text or "alert" in text:
        return "对端中止了 TLS 握手"
    if "eof occurred" in text or "unexpected eof" in text or "connection reset" in text \
            or "connection closed" in text:
        return "TLS 连接被对端中止"
    return "TLS 握手失败"


def _request_parse_error(error: BaseException,
                         *, stage: str) -> ParseError:
    """Convert a transport exception without leaking URL or credential data."""
    if _is_tls_error(error):
        reason = _tls_failure_reason(error)
        logger.warning("upstream_tls_error stage=%s reason=%s", stage, reason)
        return ParseError(
            "network_tls_error",
            f"{stage} HTTPS 请求失败（{reason}）；请检查解析节点的 CA 证书、"
            "系统时间和 HTTPS 代理配置",
        )
    return ParseError("network_error", f"{stage}请求失败：{type(error).__name__}")


def check_url(url: str, suffixes: tuple[str, ...] | None = None) -> str:
    """媒体地址只校验基本格式，作品入口和特定平台接口仍显式限定域名。"""
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        valid = (p.scheme in ("http", "https") and bool(host) and not p.username and not p.password
                 and p.port in (None, 80, 443)
                 and (suffixes is None
                      or any(host == s or host.endswith("." + s) for s in suffixes)))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        message = ("地址不属于支持的平台域名" if suffixes is not None
                   else "视频地址必须是有效的HTTP或HTTPS地址")
        raise ParseError("invalid_url", message)
    return url


def _original_metadata_path() -> Path:
    configured = os.environ.get("DOUYIN_ORIGINAL_METADATA_FILE", "").strip()
    return Path(configured).expanduser() if configured else _DEFAULT_ORIGINAL_METADATA


def _valid_original_record(record: object, allow_external: bool | None = None) -> bool:
    if not isinstance(record, dict):
        return False
    if not re.fullmatch(r"\d{15,22}", str(record.get("aweme_id") or "")):
        return False
    if not re.fullmatch(r"[a-zA-Z0-9_-]{10,128}", str(record.get("video_id") or "")):
        return False
    if not re.fullmatch(r"[a-fA-F0-9]{32}", str(record.get("file_hash") or "")):
        return False
    if not re.fullmatch(r"[a-zA-Z0-9_-]{10,128}", str(record.get("file_id") or "")):
        return False
    provenance = record.get("verified_by")
    if provenance not in VERIFIED_PROVENANCE:
        return False
    if provenance == EXTERNAL_ASSET_PROVENANCE and not _external_asset_recovery_enabled(allow_external):
        return False
    try:
        size = int(record.get("size") or 0)
        width = int(record.get("width") or 0)
        height = int(record.get("height") or 0)
        duration = float(record.get("duration_seconds") or 0)
    except (TypeError, ValueError, OverflowError):
        return False
    return size > 0 and width > 0 and height > 0 and duration > 0


def _read_original_records(path: Path | None = None,
                           allow_external: bool | None = None) -> dict[str, dict]:
    paths = [path] if path is not None else [_DEFAULT_ORIGINAL_METADATA]
    configured = _original_metadata_path()
    if configured not in paths:
        paths.append(configured)
    records = {}
    for source in paths:
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            continue
        rows = raw.get("records") if isinstance(raw, dict) else raw
        if isinstance(rows, list):
            records.update({str(row["aweme_id"]): dict(row)
                            for row in rows if _valid_original_record(row, allow_external)})
    return records


def _remember_original_record(record: dict, path: Path | None = None,
                              allow_external: bool | None = None) -> None:
    """保存已完成官方媒体校验的原画元数据，不保存临时签名 URL。"""
    if not _valid_original_record(record, allow_external):
        return
    path = path or _original_metadata_path()
    with _ORIGINAL_METADATA_LOCK:
        # 重写整个文件时必须把所有已存记录都读出来（含默认被策略挡住的外部来源记录），
        # 否则一次写入会把它们悄悄丢掉。
        rows = _read_original_records(path, allow_external=True)
        rows[str(record["aweme_id"])] = dict(record)
        payload = {"version": 1, "records": sorted(rows.values(), key=lambda row: row["aweme_id"])}
        temporary = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                             prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, path)
        except OSError as exc:
            logger.info("original_metadata_write_skipped reason=%s", type(exc).__name__)
            if temporary:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def id_from_url(url: str) -> str | None:
    p = urlsplit(check_url(url, PLATFORM_HOSTS))
    match = re.search(r"/(?:share/)?(?:video|note)/(\d{15,22})(?:/|$)", p.path)
    if match:
        return match.group(1)
    for key in ("modal_id", "aweme_id", "item_id"):
        value = parse_qs(p.query).get(key, [""])[0]
        if re.fullmatch(r"\d{15,22}", value):
            return value
    return None


def resolve_id_local(text: str) -> tuple[str | None, str]:
    """只提取并校验本地输入；短链接的跳转留给实际解析任务。"""
    text = text.strip()
    if re.fullmatch(r"\d{15,22}", text):
        return text, "https://www.douyin.com/video/" + text
    # 分享文案常在链接后直接接中文句号与提示语，不能把它们并入 URL。
    match = re.search(r'https?://[^\s<>"\]。，！；）】]+', text)
    if not match:
        raise ParseError("invalid_input", "请提供抖音视频链接、分享文案或作品 ID")
    url = match.group(0).rstrip("。，！；）)】,;'")
    return id_from_url(url), url


def load_credentials(path: Path) -> tuple[dict[str, str], str | None]:
    """读取普通 Cookie 文件或 dtk-parse 的 credentials.json。"""
    text = path.read_text(encoding="utf-8-sig").strip()
    if text.startswith(("{", "[")):
        data = json.loads(text)
        if isinstance(data, list):
            if not all(isinstance(c, dict) and isinstance(c.get("name"), str)
                       and isinstance(c.get("value"), str) for c in data):
                raise ValueError("Cookie 数组中的每项都需要字符串 name 和 value")
            return {c["name"]: c["value"] for c in data}, None
        if "cookies" in data:
            if not isinstance(data["cookies"], dict):
                raise ValueError("凭据文件的 cookies 必须是对象")
            user_agent = data.get("user_agent")
            return ({str(k): str(v) for k, v in data["cookies"].items()},
                    str(user_agent) if user_agent else None)
        return {str(k): str(v) for k, v in data.items()}, None
    text = ";".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return ({k.strip(): v.strip() for item in text.split(";") if "=" in item
             for k, v in [item.strip().removeprefix("Cookie:").partition("=")[::2]]}, None)


def load_cookies(path: Path) -> dict[str, str]:
    """兼容旧调用：只返回 Cookie 字典。"""
    return load_credentials(path)[0]


def _content_md5(headers) -> str | None:
    """读取官方 CDN 的 Content-MD5；不把 ETag 或 CRC 当作文件 MD5。"""
    value = headers.get("Content-MD5")
    if not isinstance(value, str):
        return None
    try:
        digest = base64.b64decode(value.strip(), validate=True)
    except (ValueError, TypeError):
        return None
    return digest.hex() if len(digest) == 16 else None


def signed_query(params: dict, cookies: dict) -> str | None:
    """使用平台下发的访客标识计算网页请求签名。"""
    uifid = next((cookies.get(k) for k in UIFID_NAMES if cookies.get(k)), None)
    if not uifid:
        return None
    stamp = str(int(time.time()))
    signed_params = dict(params)
    verify_fp = cookies.get("s_v_web_id")
    if verify_fp:
        signed_params.setdefault("verifyFp", verify_fp)
        signed_params.setdefault("fp", verify_fp)
    signed_params.update({"uifid": uifid, "timestamp": stamp})
    query = urlencode(signed_params, safe="*-._").replace("~", "%7E")
    signature = hashlib.md5(
        f"{uifid}_{stamp}_A96D855A08C0A9707F8BEF0D9A527E4E_{query}".encode()
    ).hexdigest()
    return query + "&x-secsdk-web-signature=" + signature


def signed_headers(query: str | None) -> dict[str, str]:
    """从同一条查询串提取签名头，保证时间戳不会在秒边界发生变化。"""
    if not query:
        return {}
    params = parse_qs(query)
    return {"uifid": params["uifid"][0], "x-secsdk-web-signature": params["x-secsdk-web-signature"][0],
            "x-secsdk-web-expire": params["timestamp"][0]}


class OriginalParser:
    def __init__(self, *, timeout: float = 20, cookies: dict | None = None,
                 user_agent: str | None = None, auto_guest: bool = True,
                 detail_mode: str = "http", browser_profile: str = "windows",
                 refresh_guest_on_rejection: bool = True,
                 allow_external_asset_recovery: bool | None = None):
        if detail_mode not in ("http", "browser"):
            raise ValueError("detail_mode 必须是 http 或 browser")
        if browser_profile not in ("current", "native", "windows"):
            raise ValueError("browser_profile 必须是 current、native 或 windows")
        if detail_mode == "browser" and (cookies is not None or not auto_guest):
            raise ValueError("浏览器页面解析模式仅支持自动访客，不能同时指定外部 Cookie 或关闭自动访客")
        self.allow_external_asset_recovery = allow_external_asset_recovery
        self.catalog_blocked_external = False
        self.play_default_note = ""
        self._signer = None
        self._signer_ua = None
        self.timeout = timeout
        self.detail_mode = detail_mode
        self.browser_profile = browser_profile
        self.refresh_guest_on_rejection = refresh_guest_on_rejection
        self.auto_guest = auto_guest and not cookies
        self.cookies = dict(cookies or {})
        self.user_agent = user_agent or DETAIL_UA
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent, "Referer": "https://www.douyin.com/"})
        if self.auto_guest and detail_mode == "http":
            guest = cached_guest()
            if guest:
                self.cookies, self.user_agent = guest
                self.session.headers["User-Agent"] = self.user_agent
        for name, value in self.cookies.items():
            self.session.cookies.set(name, value, domain=".douyin.com", path="/")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.session.close()

    def _get(self, url, *, hosts=None, headers=None):
        from urllib.parse import urljoin
        for _ in range(6):
            check_url(url, hosts)
            try:
                response = self.session.get(url, headers=headers, stream=True,
                                            allow_redirects=False, timeout=self.timeout)
            except _REQUEST_ERRORS as exc:
                raise _request_parse_error(exc, stage="平台") from exc
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise ParseError("upstream_error", "平台跳转缺少 Location")
                url = urljoin(url, location)
                continue
            return response
        raise ParseError("upstream_error", "平台跳转次数超过上限")

    def _json(self, url, *, headers=None, stage="平台接口") -> dict:
        with self._get(url, headers=headers) as response:
            if response.status_code == 403:
                try:
                    body = response.raw.read(1024, decode_content=True).decode("utf-8", errors="replace")
                except _REQUEST_ERRORS as exc:
                    raise _request_parse_error(exc, stage=f"{stage}响应读取") from exc
                if "Uifid Not Found" in body:
                    raise ParseError("credentials_required", "抖音详情接口缺少 UIFID 访客标识（HTTP 403）")
                if "Signature" in body and "ArgusSecurityPlugin" in body:
                    raise ParseError("credentials_rejected", "抖音拒绝了当前访客签名（HTTP 403），请更新访客凭据")
                raise ParseError("upstream_forbidden", "平台拒绝了请求（HTTP 403），请检查当前网络和凭据")
            if response.status_code == 429:
                raise ParseError("upstream_rate_limited", f"{stage}返回 HTTP 429，请稍后重试")
            if response.status_code == 444:
                raise ParseError("upstream_forbidden", f"{stage}拒绝了请求（HTTP 444）")
            if response.status_code != 200:
                raise ParseError("upstream_error", f"{stage}返回 HTTP {response.status_code}")
            chunks, size = [], 0
            try:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_JSON_BYTES:
                        raise ParseError("upstream_error", "平台 JSON 响应过大")
                    chunks.append(chunk)
            except _REQUEST_ERRORS as exc:
                # stream=True 时，HTTP 200 之后仍可能读取超时或连接中断。
                # 丢弃不完整正文；不把网络故障当作访客失效或原画缺失。
                raise _request_parse_error(exc, stage=f"{stage}响应读取") from exc
            raw = b"".join(chunks)
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                text = raw.decode("utf-8", errors="replace")
                # 仅输出类型和大小，不记录正文、Cookie 或带签名的请求地址。
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if not re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", content_type):
                    content_type = "unknown"
                diagnostic = f"HTTP 200，Content-Type={content_type}，响应 {len(raw)} 字节"
                logger.warning("upstream_invalid_json stage=%s status=200 content_type=%s bytes=%d",
                               stage, content_type, len(raw))
                if "wafchallenge" in text or "Please wait" in text or "Uifid" in text:
                    raise ParseError("credentials_required", "抖音返回了访客验证页面，需要先初始化 UIFID 访客标识") from exc
                if not raw.strip():
                    raise ParseError("upstream_empty_response", f"{stage}返回空内容（{diagnostic}）") from exc
                raise ParseError("upstream_non_json", f"{stage}返回非 JSON 内容（{diagnostic}）") from exc
            if not isinstance(data, dict):
                raise ParseError("upstream_error", "平台返回了不支持的 JSON 结构")
            return data

    def resolve_id(self, text: str) -> str:
        content_id, url = resolve_id_local(text)
        if content_id:
            return content_id
        with self._get(url, hosts=PLATFORM_HOSTS, headers={"User-Agent": self.user_agent}) as response:
            content_id = id_from_url(response.url)
            if content_id:
                return content_id
        raise ParseError("invalid_input", "链接中没有找到作品 ID")

    def detail(self, aweme_id: str) -> dict:
        if self.detail_mode == "browser":
            from .browser_detail import get_browser_detail
            detail, cookies, user_agent = get_browser_detail(
                aweme_id, timeout=self.timeout, profile=self.browser_profile)
            self._use_guest((cookies, user_agent))
            return detail
        if self.auto_guest and not self.cookies:
            self._use_guest(get_guest())
        try:
            return self._detail_once(aweme_id)
        except ParseError as exc:
            if (not self.auto_guest or not self.refresh_guest_on_rejection
                    or exc.code not in GUEST_RETRY_CODES):
                raise
            logger.warning("guest_refresh_requested aweme_id=%s reason=%s", aweme_id, exc.code)
        self._use_guest(get_guest(rejected=self.cookies))
        # 仅自动更新一次；再次失败时返回真实原因，不无休止重试。
        return self._detail_once(aweme_id)

    def _use_guest(self, guest: tuple[dict[str, str], str]):
        cookies, user_agent = guest
        self.cookies, self.user_agent = cookies, user_agent
        self.session.cookies.clear()
        self.session.headers["User-Agent"] = user_agent
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=".douyin.com", path="/")

    def _detail_once(self, aweme_id: str) -> dict:
        params = {"aweme_id": aweme_id, "aid": "392139", "device_platform": "webapp"}
        signed = signed_query(params, self.cookies)
        url = DETAIL_URL + "?" + (signed or urlencode(params))
        data = self._json(url, headers={"User-Agent": self.user_agent, **signed_headers(signed)},
                          stage="作品详情接口")
        detail = data.get("aweme_detail")
        if not isinstance(detail, dict) or str(detail.get("aweme_id")) != aweme_id:
            raise ParseError("detail_unavailable", "平台未返回该作品详情，作品可能不可见")
        return detail

    def _a_bogus_signer(self):
        """按当前 UA 取（并缓存）a_bogus 签名器；UA 变了必须重建。"""
        signer = self._signer
        if signer is None or self._signer_ua != self.user_agent:
            try:
                from .abogus import ABogus
            except ImportError as exc:
                raise ParseError(
                    "dependency_missing",
                    f"a_bogus 签名依赖加载失败（{exc.name or 'import_error'}）；"
                    f'请执行 "{sys.executable}" -m pip install -r '
                    f'"{Path(__file__).resolve().parents[1] / "requirements.txt"}"，'
                    "完成后重启解析服务") from exc
            signer = ABogus(user_agent=self.user_agent)
            self._signer, self._signer_ua = signer, self.user_agent
        return signer

    def _a_bogus_query(self, params: dict) -> str:
        """给 www.douyin.com 的 play 接口请求签名，返回完整查询串。"""
        query = urlencode(params)
        signed, _ab, _ua, _body = self._a_bogus_signer().generate_abogus(query, "")
        return signed

    @staticmethod
    def _video_rows(model: dict) -> list[dict]:
        """兼容详情 video_meta 包装和 fplay 平铺档位，保留外层地址与加密标记。"""
        rows = model.get("video_list")
        if isinstance(rows, dict):
            rows = list(rows.values())
        if not isinstance(rows, list):
            return []
        normalized = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            meta = row.get("video_meta")
            if not isinstance(meta, dict):
                normalized.append(dict(row))
                continue
            item = {**row, **meta}
            # 两处声明不一致时不把较宽松的声明当成原画证据。
            if (row.get("quality") and meta.get("quality") and
                    str(row["quality"]).lower() != str(meta["quality"]).lower()):
                item["quality"] = "conflicting"
            for key in ("encrypt", "spade_a", "encryption_method"):
                item[key] = row.get(key) or meta.get(key)
            normalized.append(item)
        return normalized

    @staticmethod
    def _transcode_sizes(video: dict) -> set[int]:
        """收集详情里已知的转码档位字节数，用于排除相同大小的 default 返回对象。"""
        sizes: set[int] = set()

        def add(value) -> None:
            try:
                size = int(value or 0)
            except (TypeError, ValueError, OverflowError):
                return
            if size > 0:
                sizes.add(size)

        rows = video.get("bit_rate")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                add(row.get("data_size"))
                add(row.get("size"))
                for key in ("play_addr", "play_addr_265", "play_addr_h264"):
                    addr = row.get(key)
                    if isinstance(addr, dict):
                        add(addr.get("data_size"))
        for key in ("play_addr", "play_addr_265", "play_addr_h264", "download_addr"):
            addr = video.get(key)
            if isinstance(addr, dict):
                add(addr.get("data_size"))
        model = video.get("video_model")
        if isinstance(model, str):
            try:
                model = json.loads(model)
            except ValueError:
                model = None
        if isinstance(model, dict):
            for row in OriginalParser._video_rows(model):
                if str(row.get("quality") or "").lower() not in ("original", "source"):
                    add(row.get("size"))
        return sizes

    def _play_default_candidate(self, detail: dict, video_id: str, *,
                                transcode_sizes: set[int] | None = None) -> dict | None:
        """请求官方 ratio=default 播放档，并排除已知转码大小的返回对象。

        返回 None 表示本次请求没有取得可用候选，观察结果写进 self.play_default_note。
        HTTP 404 不携带具体原因，不能据此推断未登记原片或原片已不存在。
        """
        self.play_default_note = ""
        video = detail.get("video") or {}
        transcode_sizes = self._transcode_sizes(video) | (transcode_sizes or set())
        if not transcode_sizes:
            # 详情没给任何转码档尺寸时无法判定 default 档是原片还是转码，不猜。
            self.play_default_note = "；平台默认档无法判定（详情未给出任何转码档位尺寸）"
            return None
        try:
            duration = int(video.get("duration") or 0) / 1000
        except (TypeError, ValueError, OverflowError):
            duration = 0.0
        if duration <= 0:
            self.play_default_note = "；平台默认档无法判定（详情未给出作品时长）"
            return None
        params = {"video_id": video_id, "ratio": "default", "line": "0",
                  "is_play_url": "1", "watermark": "0",
                  "source": "PackSourceEnum_PUBLISH"}
        url = PLAY_URL + "?" + self._a_bogus_query(params)
        headers = {"Range": "bytes=0-15", "Accept-Encoding": "identity",
                   "Referer": f"https://www.douyin.com/video/{detail.get('aweme_id', '')}"}
        try:
            with self._get(url, headers=headers) as response:
                status = response.status_code
                if status == 404:
                    self.play_default_note = "；平台默认档接口返回 HTTP 404（本次请求未取得媒体地址，原因未确定）"
                    return None
                if status == 403:
                    raise ParseError("upstream_forbidden", "官方播放接口拒绝了默认档请求（HTTP 403）")
                if status == 429:
                    raise ParseError("upstream_rate_limited", "官方播放接口返回 HTTP 429，请稍后重试")
                if status not in (200, 206):
                    raise ParseError("upstream_error", f"官方播放接口返回 HTTP {status}")
                match = re.fullmatch(r"bytes 0-15/(\d+)", response.headers.get("Content-Range", ""))
                try:
                    first = response.raw.read(16, decode_content=False)
                except _REQUEST_ERRORS as exc:
                    raise _request_parse_error(exc, stage="官方播放接口响应读取") from exc
                if status != 206 or not match or first[4:8] != b"ftyp":
                    self.play_default_note = "；平台默认档不是可校验的完整 MP4"
                    return None
                size = int(match.group(1))
                file_hash = _content_md5(response.headers)
                final_url = response.url
                check_url(final_url)
        except (requests.RequestException, OSError) as exc:
            raise _request_parse_error(exc, stage="官方播放接口") from exc
        if size in transcode_sizes:
            # 平台把某个转码档登记成了默认档：不能当原片。
            self.play_default_note = "；平台默认档与某个转码档字节数完全相同"
            return None
        query = parse_qs(urlsplit(final_url).query)
        expires_at = next((query.get(key, [None])[0] for key in
                           ("x-expires", "expires", "x-tos-expires", "url_expire", "expire", "dy_q")
                           if query.get(key, [None])[0]), None)
        return {
            "url": final_url, "urls": [final_url],
            "quality": "source", "level": "原画（官方默认档）",
            "official_quality": "original", "file_id": video_id,
            "size": size, "source_evidence": "official_play_default",
            # 原片分辨率不一定等于详情里转码档的分辨率，交给 probe 从 moov 回填。
            "width": 0, "height": 0, "bit_rate": 0,
            "codec": None, "fps": None, "file_hash": file_hash,
            "expires_at": expires_at, "duration_seconds": duration,
        }

    def source_streams(self, detail: dict) -> tuple[dict, list[dict]]:
        """返回首组明确原画候选；parse 会继续尝试后续组直到媒体校验通过。"""
        groups = self._source_stream_groups(detail)
        try:
            return next(groups)
        finally:
            groups.close()

    def _source_stream_groups(self, detail: dict):
        """按需尝试详情内嵌模型、官方两种选档和原片分发，不预先请求所有路线。"""
        self.play_default_note = ""
        self.catalog_blocked_external = False
        video = detail.get("video") or {}
        video_id = (video.get("play_addr") or {}).get("uri")
        if not video_id:
            raise ParseError("source_unavailable", "详情未下发视频标识")
        model = video.get("video_model")
        last_error = None
        issued_candidates = []

        def collect_group(payload):
            data, candidates = self._source_candidates(payload, video_id, allow_missing_urls=True)
            issued_candidates.extend(dict(candidate) for candidate in candidates)
            playable = [candidate for candidate in candidates if candidate["urls"]]
            if playable:
                return data, playable
            # 复用严格选档器保留缺地址/解码失败等原诊断；只再次校验本地回包。
            return self._source_candidates(payload, video_id)

        try:
            model = json.loads(model) if isinstance(model, str) else model
        except ValueError:
            model = None
            last_error = ParseError("source_unavailable", "video_model 不是有效 JSON")
        if not isinstance(model, dict):
            model = {}
            last_error = last_error or ParseError("source_unavailable", "平台未下发 video_model")
        elif model.get("video_id") != video_id:
            raise ParseError("identity_mismatch", "详情与播放模型的视频标识不一致")
        # 网页详情已下发的完整模型也有独立原画/地址；不能只把它当作 fallback 容器。
        if model.get("video_list"):
            embedded = {"code": 0, "video_info": {"code": 0, "data": model}}
            try:
                group = collect_group(embedded)
            except ParseError as exc:
                if exc.code != "source_unavailable":
                    raise
                last_error = exc
            else:
                yield group
        try:
            request_urls = self._fallback_source_urls(model, video_id)
        except ParseError as exc:
            if exc.code != "source_unavailable":
                raise
            request_urls = []
            last_error = exc
        transcode_sizes = self._transcode_sizes(video)
        for request_url in request_urls:
            payload = self._json(request_url, stage="原画接口")
            try:
                group = collect_group(payload)
            except ParseError as exc:
                if exc.code != "source_unavailable":
                    raise
                last_error = exc
            else:
                yield group
            data = (payload.get("video_info") or {}).get("data") or {}
            if data.get("video_id") == video_id:
                for row in self._video_rows(data):
                    if str(row.get("quality") or "").lower() in ("original", "source"):
                        continue
                    try:
                        size = int(row.get("size") or 0)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if size > 0:
                        transcode_sizes.add(size)
        # 当前官方回包的原画身份可以直接重新分发，首次解析也不必依赖历史 catalog。
        # 到达这里意味着地址缺失/无法解码，或先前已下发的地址均未通过媒体校验。
        refreshed_identities = set()
        for candidate in issued_candidates:
            identity = (candidate.get("file_id"), candidate.get("file_hash"))
            if identity in refreshed_identities:
                continue
            refreshed_identities.add(identity)
            refreshed = self._redispatch_source_candidate(detail, video_id, candidate)
            if refreshed is not None:
                yield ({"status": 10, "video_id": video_id,
                        "video_duration": refreshed["duration_seconds"]}, [refreshed])
        # 部分作品的 fplay 回包会暂时只列出转码，但官方分发入口仍接受
        # 该作品此前已验证过的原片 file_hash。只使用本地可信记录，且仍
        # 通过官方入口和后续 MP4 校验；没有记录时不猜测哈希。
        catalog_candidate = self._catalog_original_candidate(detail, video_id)
        if catalog_candidate is not None:
            catalog_data = {"status": 10, "video_id": video_id,
                            "video_duration": catalog_candidate["duration_seconds"]}
            yield catalog_data, [catalog_candidate]
        # 再按作品 VID 请求官方 play 默认档；失败响应不代表已经查明原片缺失原因。
        play_default = self._play_default_candidate(detail, video_id, transcode_sizes=transcode_sizes)
        if play_default is not None:
            yield ({"status": 10, "video_id": video_id,
                    "video_duration": play_default["duration_seconds"]}, [play_default])
        if last_error is None:
            last_error = ParseError("source_unavailable", "官方接口未返回可用原画")
        # 此字段是响应中的上下文标记，不能单独解释为何当前未取得原片。
        hdr_note = ("（详情标记 is_source_HDR=1；该标记不能单独确定原片取址失败的原因）"
                    if str(video.get("is_source_HDR")) in ("1", "True") else "")
        blocked_note = ("（本地已有该作品经官方重签与媒体校验的原片身份记录，"
                        "外部来源默认屏蔽；加 --allow-external 或设置 "
                        "DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY=1 即可取到原画）"
                        if self.catalog_blocked_external else "")
        raise ParseError("source_unavailable",
                         f"获取原画失败：{last_error}{hdr_note}{self.play_default_note}"
                         f"{blocked_note}") from last_error

    @staticmethod
    def _fallback_source_urls(model: dict, video_id: str) -> list[str]:
        fallback = model.get("fallback_api")
        url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
        if not isinstance(url, str):
            raise ParseError("source_unavailable", "平台未下发备用播放接口")
        p = urlsplit(check_url(url, ("snssdk.com",)))
        if not re.fullmatch(r"/video/fplay/1/[a-fA-F0-9]{32}/" + re.escape(video_id), p.path):
            raise ParseError("source_unavailable", "备用播放接口结构已变化")
        if parse_qs(p.query).get("aid", [""])[0] != "392139":
            raise ParseError("source_unavailable", "备用播放接口的应用标识不符合当前实现")
        # 保留官方签发的上下文，仅修改已验证的选择参数。
        original_params = parse_qs(p.query, keep_blank_values=True)
        original_params.pop("logo_type", None)
        original_params["force_fids"] = [base64.b64encode(b"original").decode("ascii")]
        original_params["codec_type"] = ["5"]
        source_params = parse_qs(p.query, keep_blank_values=True)
        source_params.pop("logo_type", None)
        source_params["stream_type"] = ["source"]
        return [urlunsplit((p.scheme, p.netloc, p.path, urlencode(params, doseq=True), ""))
                for params in (original_params, source_params)]

    def _redispatch_source_candidate(self, detail: dict, video_id: str, candidate: dict) -> dict | None:
        """只使用本次官方 original/source 回包的身份刷新过期地址，仍须后续 probe。"""
        record = {
            "aweme_id": str(detail.get("aweme_id") or ""), "video_id": video_id,
            "file_id": candidate.get("file_id") or video_id,
            "file_hash": candidate.get("file_hash"), "size": candidate.get("size"),
            "width": candidate.get("width"), "height": candidate.get("height"),
            "duration_seconds": candidate.get("duration_seconds"),
            "verified_by": OFFICIAL_PROVENANCE,
        }
        # 仅借用记录格式校验；这里还没有完成媒体核验，不写入任何可信记录。
        if not _valid_original_record(record):
            return None
        url = self._dispatch_official_original(record)
        if url is None:
            return None
        query = parse_qs(urlsplit(url).query)
        expires_at = next((query[key][0] for key in
                           ("x-expires", "expires", "x-tos-expires", "url_expire", "expire", "dy_q")
                           if query.get(key)), None)
        return {**candidate, "url": url, "urls": [url], "expires_at": expires_at,
                "level": "原画（官方重新分发）"}

    def _dispatch_official_original(self, record: dict) -> str | None:
        """用记录里的整文件 file_hash 打官方原片分发，返回通过大小校验的最终地址。

        返回 None 表示官方不认这个哈希（404、非 MP4 或大小对不上），调用方应继续失败。
        """
        video_id = str(record.get("video_id") or "")
        file_id = str(record.get("file_id") or video_id)
        params = {
            "video_id": video_id,
            "file_id": file_id,
            "line": "0",
            "is_play_url": "1",
            "source": "PackSourceEnum_AWEME_DETAIL",
            "sign": str(record["file_hash"]).lower(),
        }
        dispatch_url = "https://www.douyin.com/aweme/v1/play/?" + urlencode(params)
        try:
            with self._get(dispatch_url, headers={
                    "Range": "bytes=0-15", "Accept-Encoding": "identity"}) as response:
                if response.status_code == 403:
                    raise ParseError("upstream_forbidden", "官方原片分发接口拒绝了请求（HTTP 403）")
                if response.status_code == 429:
                    raise ParseError("upstream_rate_limited", "官方原片分发接口返回 HTTP 429，请稍后重试")
                if response.status_code == 444:
                    raise ParseError("upstream_forbidden", "官方原片分发接口拒绝了请求（HTTP 444）")
                if response.status_code == 404:
                    return None
                if response.status_code not in (200, 206):
                    raise ParseError("upstream_error",
                                     f"官方原片分发接口返回 HTTP {response.status_code}")
                match = re.fullmatch(r"bytes 0-15/(\d+)",
                                     response.headers.get("Content-Range", ""))
                try:
                    first = response.raw.read(16, decode_content=False)
                except _REQUEST_ERRORS as exc:
                    raise _request_parse_error(exc, stage="官方原片分发响应读取") from exc
                if response.status_code != 206 or not match or first[4:8] != b"ftyp":
                    return None
                size = int(match.group(1))
                if size != int(record["size"]):
                    logger.info("original_metadata_rejected aweme_id=%s reason=size_mismatch",
                                record.get("aweme_id"))
                    return None
                final_url = response.url
                check_url(final_url)
                return final_url
        except (requests.RequestException, OSError, ValueError) as exc:
            raise _request_parse_error(exc, stage="官方原片分发接口") from exc

    def _media_head(self, url: str) -> tuple[int, str, str | None]:
        """读媒体首 16 字节：返回（总字节数、最终地址、响应头里的 Content-MD5）。"""
        with self._get(url, headers={"Range": "bytes=0-15", "Accept-Encoding": "identity"}) as response:
            if response.status_code != 206:
                raise ParseError("probe_failed", "该地址不支持有效的范围读取")
            match = re.fullmatch(r"bytes 0-15/(\d+)", response.headers.get("Content-Range", ""))
            if not match:
                raise ParseError("probe_failed", "该地址的 Content-Range 不符合单文件语义")
            size = int(match.group(1))
            try:
                first = response.raw.read(16, decode_content=False)
            except _REQUEST_ERRORS as exc:
                raise _request_parse_error(exc, stage="媒体响应读取") from exc
            if first[4:8] != b"ftyp":
                raise ParseError("identity_mismatch", "该地址响应不是 MP4 文件")
            final_url = response.url
            check_url(final_url)
            return size, final_url, response.headers.get("Content-MD5")

    def _hash_media(self, url: str, size: int) -> str:
        """流式读完整文件计算 MD5，用于缺少 Content-MD5 响应的边缘。"""
        digest = hashlib.md5()
        received = 0
        with self._get(url, headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code != 200:
                raise ParseError("probe_failed", f"下载媒体返回 HTTP {response.status_code}")
            try:
                for chunk in response.iter_content(1 << 20):
                    digest.update(chunk)
                    received += len(chunk)
            except _REQUEST_ERRORS as exc:
                raise _request_parse_error(exc, stage="媒体哈希读取") from exc
        if received != size:
            raise ParseError("size_mismatch", "下载字节数与声明大小不一致")
        return digest.hexdigest()

    def register_external_original(self, text: str, media_url: str) -> dict:
        """把一条一次性原片直链核验后登记为本地原片身份记录。

        只做三件事：核验该地址是完整 MP4 且与作品详情对得上、取整文件 MD5、
        用该 MD5 打官方原片分发确认平台认可。登记后仍按外部来源对待，
        默认策略不参与取址（需要 --allow-external）。
        """
        aweme_id = self.resolve_id(text)
        check_url(media_url)
        detail = self.detail(aweme_id)
        video = detail.get("video") or {}
        addr = video.get("play_addr") or {}
        video_id = str(addr.get("uri") or "")
        if not video_id:
            raise ParseError("source_unavailable", "作品详情缺少视频标识，无法登记原片身份")
        expected_duration = int(video.get("duration") or 0) / 1000
        size, final_url, header_md5 = self._media_head(media_url)
        logger.info("register_original_head aweme_id=%s size=%d", aweme_id, size)

        def read_at(offset, count):
            with self._get(final_url, headers={"Range": f"bytes={offset}-{offset + count - 1}"}) as r:
                expected = f"bytes {offset}-{offset + count - 1}/{size}"
                if r.status_code != 206 or r.headers.get("Content-Range") != expected:
                    raise ParseError("probe_failed", "登记校验时范围读取响应不一致")
                try:
                    return r.raw.read(count, decode_content=False)
                except _REQUEST_ERRORS as exc:
                    raise _request_parse_error(exc, stage="媒体响应读取") from exc

        media = inspect_mp4(read_at, size)
        if not media["has_video"] or not media["has_audio"]:
            raise ParseError("incomplete_media", "该地址不是同时包含音视频轨道的完整 MP4")
        video_track = next(track for track in media["tracks"] if track.get("type") == "vide")
        if expected_duration and abs(media["duration_seconds"] - expected_duration) > 1:
            raise ParseError("identity_mismatch",
                             f"该地址时长 {media['duration_seconds']:.3f} 秒与作品详情 "
                             f"{expected_duration:.3f} 秒不一致")
        width, height = int(video_track["width"]), int(video_track["height"])

        # 防止把平台自己的转码档当原片登记：转码档尺寸在详情里都是已知的。
        declared = {int(addr.get("data_size") or 0)}
        for gear in (video.get("play_addr_h264"), video.get("play_addr_265")):
            declared.add(int((gear or {}).get("data_size") or 0))
        for gear in (video.get("bit_rate") or []):
            declared.add(int((gear.get("play_addr") or {}).get("data_size") or 0))
        declared.discard(0)
        if size in declared:
            raise ParseError("identity_mismatch",
                             f"{size:,} 字节正是详情里已有的转码档大小，该地址不是原片")

        if header_md5:
            try:
                md5_hex = base64.b64decode(header_md5).hex()
            except (ValueError, TypeError):
                md5_hex = self._hash_media(final_url, size)
        else:
            md5_hex = self._hash_media(final_url, size)
        if not re.fullmatch(r"[a-fA-F0-9]{32}", md5_hex):
            raise ParseError("probe_failed", "无法取得该媒体的整文件 MD5")

        record = {
            "aweme_id": aweme_id,
            "video_id": video_id,
            "file_id": video_id,
            "file_hash": md5_hex.lower(),
            "size": size,
            "width": width,
            "height": height,
            "duration_seconds": round(float(media["duration_seconds"]), 3),
            "bit_rate": round(size * 8 / media["duration_seconds"]),
            "codec": (video_track.get("codec") or "").lower() or None,
            "fps": None,
            "verified_by": EXTERNAL_ASSET_PROVENANCE,
            "registered_from": urlsplit(final_url).netloc,
            "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        relay_url = self._dispatch_official_original(record)
        if relay_url is None:
            raise ParseError("source_unavailable",
                             "官方原片分发接口不认这个整文件 MD5（未返回同大小 MP4）；"
                             "该地址不是平台可重签的原片对象")
        record["relay_verified"] = True
        _remember_original_record(record, allow_external=True)
        logger.info("register_original_saved aweme_id=%s size=%d", aweme_id, size)
        return {"record": record, "relay_url": relay_url, "media": media}

    def _catalog_original_candidate(self, detail: dict, video_id: str) -> dict | None:
        aweme_id = str(detail.get("aweme_id") or "")
        self.catalog_blocked_external = False
        record = _read_original_records(
            allow_external=self.allow_external_asset_recovery).get(aweme_id)
        if record is None:
            # 只在策略把已有记录挡掉时才多读一次，用于给调用方可执行的提示；
            # 诊断/对照流程重写本方法后不会触碰 catalog。
            if not _external_asset_recovery_enabled(self.allow_external_asset_recovery):
                blocked = _read_original_records(allow_external=True).get(aweme_id)
                self.catalog_blocked_external = bool(
                    blocked is not None and blocked.get("video_id") == video_id)
            return None
        if record is None or record.get("video_id") != video_id:
            return None
        file_id = str(record.get("file_id") or video_id)
        final_url = self._dispatch_official_original(record)
        if final_url is None:
            return None
        query = parse_qs(urlsplit(final_url).query)
        expires_at = next((query.get(key, [None])[0] for key in
                           ("x-expires", "expires", "url_expire", "dy_q")
                           if query.get(key, [None])[0]), None)
        return {
            "url": final_url,
            "urls": [final_url],
            "quality": "source",
            "level": "原画（官方原片分发）",
            "official_quality": "original",
            "file_id": file_id,
            "size": int(record["size"]),
            "source_evidence": "official_play_hash",
            "width": int(record["width"]),
            "height": int(record["height"]),
            "bit_rate": int(record.get("bit_rate") or 0),
            "codec": record.get("codec"),
            "fps": record.get("fps"),
            "file_hash": str(record["file_hash"]).lower(),
            "expires_at": expires_at,
            "duration_seconds": float(record["duration_seconds"]),
        }

    @staticmethod
    def _candidate_rank(candidate: dict) -> tuple:
        return (candidate["official_quality"] in ("original", "source"),
                candidate["width"] * candidate["height"], candidate["bit_rate"], candidate["size"])

    def _source_candidates(self, payload: dict, video_id: str, *,
                           allow_missing_urls: bool = False) -> tuple[dict, list[dict]]:
        """筛选原画；内部重签可保留无可用地址的已验证原画元数据。"""
        info = payload.get("video_info") or {}
        data = info.get("data") or {}
        if payload.get("code") != 0 or info.get("code") != 0 or data.get("status") != 10:
            raise ParseError("source_unavailable", "官方备用接口没有返回可用原画")
        if data.get("video_id") != video_id:
            raise ParseError("identity_mismatch", "原画接口返回了另一个视频")
        rows = data.get("video_list")
        if rows is None:
            rows = []
        elif isinstance(rows, dict):
            rows = list(rows.values())
        elif not isinstance(rows, list):
            raise ParseError("source_unavailable", "原画接口返回的视频档位列表格式异常")
        rows = self._video_rows(data)
        if not rows:
            raise ParseError("source_unavailable", "原画接口未返回有效的视频档位")
        candidates = []
        source_count = normal_count = 0
        # 只汇总固定原因与数量，不把上游地址、密钥或任意响应文本放入错误消息。
        rejected = {"档位标识异常": 0, "视频元数据异常": 0,
                    "非 MP4 格式": 0, "带媒体加密标记": 0, "缺少播放地址": 0,
                    "地址解码失败": 0, "地址校验未通过": 0}
        for row in rows:
            quality = str(row.get("quality") or "").lower()
            if quality == "normal":
                normal_count += 1
            api_source = quality in ("original", "source")
            source_count += int(api_source)
            if not api_source:
                continue
            if not re.fullmatch(r"[a-z0-9_-]{1,32}", quality):
                rejected["档位标识异常"] += 1
                continue
            if row.get("vtype") != "mp4":
                rejected["非 MP4 格式"] += 1
                continue
            if row.get("encrypt") or row.get("spade_a") or row.get("encryption_method"):
                rejected["带媒体加密标记"] += 1
                continue
            try:
                width, height = int(row.get("vwidth") or 0), int(row.get("vheight") or 0)
                size, bit_rate = int(row.get("size") or 0), int(row.get("bitrate") or 0)
                if min(width, height, size) <= 0 or bit_rate < 0:
                    raise ValueError("invalid_metadata")
            except (TypeError, ValueError, OverflowError):
                rejected["视频元数据异常"] += 1
                continue
            urls = []
            has_address = False
            for key in ("main_url", "backup_url_1", "backup_url_2", "backup_url_3", "backup_url"):
                if not row.get(key):
                    continue
                has_address = True
                try:
                    url = decode_url(row[key], data.get("key_seed", ""))
                except (ValueError, TypeError, UnicodeError):
                    rejected["地址解码失败"] += 1
                    continue
                try:
                    url = check_url(url)
                except ParseError:
                    rejected["地址校验未通过"] += 1
                    continue
                if url not in urls:
                    urls.append(url)
            if not has_address:
                rejected["缺少播放地址"] += 1
            if urls or allow_missing_urls:
                candidates.append({
                    "url": urls[0] if urls else None, "urls": urls, "quality": "source",
                    "level": "原画",
                    "official_quality": quality, "size": size,
                    "source_evidence": "official_quality",
                    "width": width, "height": height,
                    "bit_rate": bit_rate, "codec": row.get("codec_type"),
                    "fps": row.get("float_fps") or row.get("fps"),
                    "file_hash": row.get("file_hash"),
                    "file_id": row.get("file_id"),
                    "expires_at": row.get("url_expire") or data.get("url_expire"),
                    "duration_seconds": data.get("video_duration"),
                })
        if not candidates:
            reasons = "、".join(f"{reason} {count} 项" for reason, count in rejected.items() if count)
            if not source_count:
                message = (f"原画接口仅返回普通转码档（{normal_count} 个），未返回 original/source 原画档位"
                           if normal_count == len(rows) else
                           f"原画接口返回了 {len(rows)} 个视频档位，但未返回 original/source 原画档位")
            else:
                message = f"原画接口返回了 {source_count} 个原画档位，但没有可用的完整 MP4 地址：{reasons}"
            raise ParseError("source_unavailable", message)
        candidates.sort(key=self._candidate_rank, reverse=True)
        return data, candidates

    def probe(self, candidate: dict) -> dict:
        last = None
        for url in candidate["urls"]:
            try:
                with self._get(url, headers={"Range": "bytes=0-15"}) as response:
                    if response.status_code == 444:
                        raise ParseError("upstream_forbidden", "媒体接口拒绝了请求")
                    if response.status_code == 429:
                        raise ParseError("upstream_rate_limited", "媒体接口返回 HTTP 429，请稍后重试")
                    match = re.fullmatch(r"bytes 0-15/(\d+)", response.headers.get("Content-Range", ""))
                    if response.status_code != 206 or not match:
                        raise ParseError("probe_failed", "CDN 不支持有效的范围读取")
                    size = int(match.group(1))
                    try:
                        first = response.raw.read(16, decode_content=True)
                    except _REQUEST_ERRORS as exc:
                        raise _request_parse_error(exc, stage="媒体响应读取") from exc
                    final_url = response.url
                    if first[4:8] != b"ftyp":
                        raise ParseError("probe_failed", "下载响应不是 MP4 文件")
                if candidate["size"] and size != candidate["size"]:
                    raise ParseError("size_mismatch", "CDN 实际大小与视频元数据不一致")

                def read_at(offset, count, media_url=final_url, media_size=size):
                    with self._get(media_url, headers={"Range": f"bytes={offset}-{offset + count - 1}"}) as r:
                        if r.status_code == 444:
                            raise ParseError("upstream_forbidden", "媒体接口拒绝了范围读取")
                        if r.status_code == 429:
                            raise ParseError("upstream_rate_limited", "媒体接口返回 HTTP 429，请稍后重试")
                        expected = f"bytes {offset}-{offset + count - 1}/{media_size}"
                        if r.status_code != 206 or r.headers.get("Content-Range") != expected:
                            raise ParseError("probe_failed", "CDN 范围读取响应不一致")
                        try:
                            return r.raw.read(count, decode_content=True)
                        except _REQUEST_ERRORS as exc:
                            raise _request_parse_error(exc, stage="媒体响应读取") from exc

                media = inspect_mp4(read_at, size)
                if not media["has_video"] or not media["has_audio"]:
                    raise ParseError("incomplete_media", "视频候选不是同时包含音视频轨道的完整 MP4")
                expected_duration = float(candidate.get("duration_seconds") or 0)
                if not media["duration_seconds"] or (expected_duration and
                        abs(media["duration_seconds"] - expected_duration) > 1):
                    raise ParseError("identity_mismatch", "实际 MP4 时长与视频元数据不一致")
                video_track = next(t for t in media["tracks"] if t.get("type") == "vide")
                declared = (candidate.get("width"), candidate.get("height"))
                if declared[0] and declared[1]:
                    if (video_track.get("width"), video_track.get("height")) != declared:
                        raise ParseError("identity_mismatch", "实际 MP4 分辨率与视频元数据不一致")
                else:
                    # 未声明的分辨率从真实容器回填；分辨率本身不是原画身份证据。
                    candidate["width"] = int(video_track.get("width") or 0)
                    candidate["height"] = int(video_track.get("height") or 0)
                candidate["url"] = final_url
                return {"ok": True, "actual_size": size, **media}
            except (ParseError, ValueError, requests.RequestException, OSError) as exc:
                if _is_tls_error(exc):
                    raise _request_parse_error(exc, stage="媒体响应") from exc
                if isinstance(exc, ParseError) and exc.code in (
                        "upstream_forbidden", "upstream_rate_limited", "network_tls_error"):
                    # A TLS validation/handshake failure is a node configuration
                    # problem; trying every CDN mirror only repeats the same
                    # failure and would hide the actionable diagnosis.
                    raise
                last = exc
        raise ParseError("probe_failed", f"所有视频地址校验失败：{last}")

    def parse(self, text: str, *, with_probe: bool = True) -> dict:
        started = time.monotonic()
        aweme_id = self.resolve_id(text)
        detail = self.detail(aweme_id)
        selected = None
        probe = None
        errors = []
        attempted_urls: set[str] = set()
        groups = self._source_stream_groups(detail)
        try:
            for _, candidates in groups:
                for candidate in candidates:
                    if with_probe:
                        fresh_urls = [url for url in candidate["urls"] if url not in attempted_urls]
                        if not fresh_urls:
                            continue
                        candidate["urls"] = fresh_urls
                        attempted_urls.update(fresh_urls)
                        try:
                            probe = self.probe(candidate)
                        except ParseError as exc:
                            if exc.code != "probe_failed":
                                raise
                            errors.append(str(exc))
                            continue
                    selected = candidate
                    break
                if selected is not None:
                    break
        except ParseError as exc:
            if exc.code != "source_unavailable" or not errors:
                raise
        finally:
            groups.close()
        if selected is None:
            raise ParseError("probe_failed", "获取原画失败：所有官方原画地址均未通过媒体校验：" + "; ".join(errors))
        if (with_probe and probe and probe.get("ok") and
                selected.get("source_evidence") == "official_quality"):
            _remember_original_record({
                "aweme_id": aweme_id,
                "video_id": detail["video"]["play_addr"]["uri"],
                "file_id": selected.get("file_id") or detail["video"]["play_addr"]["uri"],
                "file_hash": selected.get("file_hash"),
                "size": selected.get("size"),
                "width": selected.get("width"),
                "height": selected.get("height"),
                "duration_seconds": probe.get("duration_seconds") or selected.get("duration_seconds"),
                "bit_rate": selected.get("bit_rate"),
                "codec": selected.get("codec"),
                "fps": selected.get("fps"),
                "verified_by": "official_fplay_and_mp4_probe",
            })
        ordered = [selected] + [c for c in candidates if c is not selected]
        evidence = selected.get("source_evidence") or ""
        message = ("原画解析成功" if evidence in ("official_quality", "official_play_hash",
                                                 "official_play_default") else
                   f"按原片桶识别为原画：{selected['level']}")
        return {"code": 0, "msg": message, "data": {
            "aweme_id": aweme_id, "desc": detail.get("desc", ""),
            "author": (detail.get("author") or {}).get("nickname", ""),
            "share_url": f"https://www.douyin.com/video/{aweme_id}",
            "provider": "douyin-official-source", "url": selected["url"],
            "size_bytes": selected["size"], "width": selected["width"], "height": selected["height"],
            "duration_seconds": probe["duration_seconds"] if probe else selected["duration_seconds"],
            "expires_at": selected["expires_at"],
            "source_selected": True, "fallback_used": False, "fallback_reason": None,
            "quality": selected["quality"], "official_quality": selected["official_quality"],
            "source_evidence": selected.get("source_evidence"),
            "level": selected["level"], "reference_match": None,
            "video_list": ordered, "probe": probe,
            "cost_ms": round((time.monotonic() - started) * 1000),
        }}

    def download(self, result: dict, destination: Path, *, reference: Path | None = None,
                 max_bytes: int = 2 * 1024**3) -> dict:
        """地址过期或全部镜像下载失败时重新解析一次，不永久缓存 CDN 地址。"""
        if destination.exists():
            raise ParseError("file_exists", "目标文件已存在，请使用另一个输出文件名")
        expires = result["data"].get("expires_at")
        refreshed = False
        if expires and int(expires) <= time.time() + 5:
            fresh = self.parse(result["data"]["aweme_id"])
            result.clear()
            result.update(fresh)
            refreshed = True
        try:
            return self._download_once(result, destination, reference=reference, max_bytes=max_bytes)
        except ParseError as exc:
            if refreshed or exc.code != "download_failed":
                raise
            fresh = self.parse(result["data"]["aweme_id"])
            result.clear()
            result.update(fresh)
            return self._download_once(result, destination, reference=reference, max_bytes=max_bytes)

    def _download_once(self, result: dict, destination: Path, *, reference: Path | None = None,
                       max_bytes: int = 2 * 1024**3) -> dict:
        if destination.exists():
            raise ParseError("file_exists", "目标文件已存在，请使用另一个输出文件名")
        candidate = result["data"]["video_list"][0]
        destination.parent.mkdir(parents=True, exist_ok=True)
        urls = list(dict.fromkeys([result["data"]["url"], *candidate["urls"]]))
        errors = []
        for url in urls:
            temporary = None
            try:
                sha, md5, total = hashlib.sha256(), hashlib.md5(), 0
                with self._get(url) as response:
                    if response.status_code != 200:
                        raise ParseError("download_failed", f"CDN 返回 HTTP {response.status_code}")
                    header_md5 = _content_md5(response.headers)
                    official_md5 = candidate.get("file_hash") or header_md5
                    if ((official_md5 and (not isinstance(official_md5, str) or
                            not re.fullmatch(r"[0-9a-fA-F]{32}", official_md5))) or
                            (response.headers.get("Content-MD5") and header_md5 is None)):
                        raise ParseError("hash_mismatch", "官方文件 MD5 格式异常")
                    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=destination.name + ".",
                                                     suffix=".part", delete=False) as stream:
                        temporary = Path(stream.name)
                        try:
                            for chunk in response.iter_content(256 * 1024):
                                total += len(chunk)
                                if total > max_bytes or (candidate["size"] and total > candidate["size"]):
                                    raise ParseError("size_mismatch", "下载超过声明大小或设置上限")
                                stream.write(chunk)
                                sha.update(chunk)
                                md5.update(chunk)
                        except _REQUEST_ERRORS as exc:
                            raise _request_parse_error(exc, stage="媒体下载读取") from exc
                if total != candidate["size"]:
                    raise ParseError("size_mismatch", "下载文件大小与官方视频大小不一致")
                if official_md5 and md5.hexdigest() != official_md5.lower():
                    raise ParseError("hash_mismatch", "下载文件 MD5 与官方视频哈希不一致")
                media = inspect_file(temporary)
                if not media["has_audio"] or not media["has_video"]:
                    raise ParseError("incomplete_media", "完整文件缺少音频或视频轨道")
                expected_duration = float(candidate.get("duration_seconds") or 0)
                if expected_duration and (not media.get("duration_seconds") or
                        abs(media["duration_seconds"] - expected_duration) > 1):
                    raise ParseError("identity_mismatch", "完整文件时长与视频元数据不一致")
                video_track = next((track for track in media.get("tracks", []) if track.get("type") == "vide"), {})
                if candidate.get("width") and candidate.get("height"):
                    if (video_track.get("width"), video_track.get("height")) != (candidate["width"], candidate["height"]):
                        raise ParseError("identity_mismatch", "完整文件分辨率与视频元数据不一致")
                reference_match, reference_sha = None, None
                if reference:
                    with reference.open("rb") as stream:
                        h = hashlib.sha256()
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            h.update(block)
                    reference_sha = h.hexdigest()
                    reference_match = total == reference.stat().st_size and sha.hexdigest() == reference_sha
                # 使用排他创建，避免覆盖用户文件；同目录临时文件校验完成后才复制到目标。
                import shutil
                with destination.open("xb") as stream, temporary.open("rb") as source:
                    try:
                        shutil.copyfileobj(source, stream, 1024 * 1024)
                    except BaseException:
                        stream.close()
                        destination.unlink(missing_ok=True)
                        raise
                record = {"path": str(destination.resolve()), "bytes": total, "md5": md5.hexdigest(),
                          "sha256": sha.hexdigest(), "official_hash_match": True if official_md5 else None,
                          "reference_match": reference_match, "reference_sha256": reference_sha, "media": media}
                result["data"]["reference_match"] = reference_match
                result["data"]["download"] = record
                return record
            except (_REQUEST_ERRORS + (ParseError,)) as exc:
                if _is_tls_error(exc):
                    raise _request_parse_error(exc, stage="媒体下载") from exc
                if isinstance(exc, ParseError) and exc.code == "network_tls_error":
                    raise
                errors.append(str(exc))
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
        raise ParseError("download_failed", "所有下载地址失败：" + "; ".join(errors))
