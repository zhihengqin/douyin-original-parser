"""作品链接 → 官方 source 档位 → 可下载 URL → 实际媒体校验。"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import tempfile
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
PLATFORM_HOSTS = ("douyin.com", "iesdouyin.com")
MEDIA_HOSTS = ("douyinvod.com", "douyin.com", "iesdouyin.com", "snssdk.com",
               "amemv.com", "ixigua.com", "365yg.com", "toutiaovod.com", "bytecdn.cn", "bytecdn.com",
               "bytedance.com", "bytedance.net", "bytednsdoc.com", "pstatp.com")


class ParseError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def check_url(url: str, suffixes: tuple[str, ...]) -> str:
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        valid = (p.scheme in ("http", "https") and not p.username and not p.password
                 and p.port in (None, 80, 443)
                 and any(host == s or host.endswith("." + s) for s in suffixes))
    except ValueError:
        valid = False
    if not valid:
        raise ParseError("invalid_url", "地址不属于支持的平台域名")
    return url


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
                 refresh_guest_on_rejection: bool = True):
        if detail_mode not in ("http", "browser"):
            raise ValueError("detail_mode 必须是 http 或 browser")
        if browser_profile not in ("current", "native", "windows"):
            raise ValueError("browser_profile 必须是 current、native 或 windows")
        if detail_mode == "browser" and (cookies is not None or not auto_guest):
            raise ValueError("浏览器页面解析模式仅支持自动访客，不能同时指定外部 Cookie 或关闭自动访客")
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

    def _get(self, url, *, hosts=MEDIA_HOSTS, headers=None):
        from urllib.parse import urljoin
        for _ in range(6):
            check_url(url, hosts)
            try:
                response = self.session.get(url, headers=headers, stream=True,
                                            allow_redirects=False, timeout=self.timeout)
            except requests.RequestException as exc:
                raise ParseError("network_error", "平台请求失败：" + type(exc).__name__) from exc
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
                body = response.raw.read(1024, decode_content=True).decode("utf-8", errors="replace")
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
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_JSON_BYTES:
                    raise ParseError("upstream_error", "平台 JSON 响应过大")
                chunks.append(chunk)
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

    def source_streams(self, detail: dict) -> tuple[dict, list[dict]]:
        video = detail.get("video") or {}
        model = video.get("video_model")
        try:
            model = json.loads(model) if isinstance(model, str) else model
        except ValueError as exc:
            raise ParseError("source_unavailable", "video_model 不是有效 JSON") from exc
        if not isinstance(model, dict):
            raise ParseError("source_unavailable", "平台未下发原画取址所需的 video_model")
        video_id = (video.get("play_addr") or {}).get("uri")
        if not video_id or model.get("video_id") != video_id:
            raise ParseError("identity_mismatch", "详情与播放模型的视频标识不一致")
        fallback = model.get("fallback_api")
        url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
        if not isinstance(url, str):
            raise ParseError("source_unavailable", "平台未下发备用播放接口")
        p = urlsplit(check_url(url, ("snssdk.com",)))
        if not re.fullmatch(r"/video/fplay/1/[a-fA-F0-9]{32}/" + re.escape(video_id), p.path):
            raise ParseError("source_unavailable", "备用播放接口结构已变化")
        aid = parse_qs(p.query).get("aid", [""])[0]
        if aid != "392139":
            raise ParseError("source_unavailable", "备用播放接口的应用标识不符合当前实现")
        # 原片选择依赖完整下发查询；仅切换 stream_type 会遗漏部分作品的原画。
        original_params = parse_qs(p.query, keep_blank_values=True)
        original_params.pop("logo_type", None)
        original_params["force_fids"] = [base64.b64encode(b"original").decode("ascii")]
        original_params["codec_type"] = ["5"]
        original_url = urlunsplit((p.scheme, p.netloc, p.path,
                                  urlencode(original_params, doseq=True), ""))
        source_url = urlunsplit((p.scheme, p.netloc, p.path,
                                urlencode({"aid": aid, "stream_type": "source"}), ""))
        try:
            return self._source_candidates(self._json(original_url, stage="原画接口"), video_id)
        except ParseError as exc:
            if exc.code != "source_unavailable":
                raise
        # 新选档无原画时兼容旧 source 入口；身份、网络及限制类错误直接返回。
        return self._source_candidates(self._json(source_url, stage="原画接口"), video_id)

    def _source_candidates(self, payload: dict, video_id: str) -> tuple[dict, list[dict]]:
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
        rows = [row for row in rows if isinstance(row, dict)]
        if not rows:
            raise ParseError("source_unavailable", "原画接口未返回有效的视频档位")
        candidates = []
        source_count = normal_count = 0
        # 只汇总固定原因与数量，不把上游地址、密钥或任意响应文本放入错误消息。
        rejected = {"非 MP4 格式": 0, "带媒体加密标记": 0, "缺少播放地址": 0,
                    "地址解码失败": 0, "地址校验未通过": 0}
        for row in rows:
            quality = str(row.get("quality") or "").lower()
            if quality == "normal":
                normal_count += 1
            if quality not in ("original", "source"):
                continue
            source_count += 1
            if row.get("vtype") != "mp4":
                rejected["非 MP4 格式"] += 1
                continue
            if row.get("encrypt") or row.get("spade_a") or row.get("encryption_method"):
                rejected["带媒体加密标记"] += 1
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
                    url = check_url(url, MEDIA_HOSTS)
                except ParseError:
                    rejected["地址校验未通过"] += 1
                    continue
                if url not in urls:
                    urls.append(url)
            if not has_address:
                rejected["缺少播放地址"] += 1
            if urls:
                candidates.append({
                    "url": urls[0], "urls": urls, "quality": "source", "level": "原画",
                    "official_quality": quality, "size": int(row.get("size") or 0),
                    "width": int(row.get("vwidth") or 0), "height": int(row.get("vheight") or 0),
                    "bit_rate": int(row.get("bitrate") or 0), "codec": row.get("codec_type"),
                    "fps": row.get("float_fps") or row.get("fps"),
                    "file_hash": row.get("file_hash"),
                    "expires_at": row.get("url_expire") or data.get("url_expire"),
                    "duration_seconds": data.get("video_duration"),
                })
        if not candidates:
            if not source_count:
                message = (f"原画接口仅返回普通转码档（{normal_count} 个），未返回 original/source 原画档位"
                           if normal_count == len(rows) else
                           f"原画接口返回了 {len(rows)} 个视频档位，但未返回 original/source 原画档位")
            else:
                reasons = "、".join(f"{reason} {count} 项" for reason, count in rejected.items() if count)
                message = f"原画接口返回了 {source_count} 个原画档位，但没有可用的完整 MP4 地址：{reasons}"
            raise ParseError("source_unavailable", message + "；不会降级为网页转码档")
        candidates.sort(key=lambda c: (c["width"] * c["height"], c["bit_rate"], c["size"]), reverse=True)
        return data, candidates

    def probe(self, candidate: dict) -> dict:
        last = None
        for url in candidate["urls"]:
            try:
                with self._get(url, headers={"Range": "bytes=0-15"}) as response:
                    match = re.fullmatch(r"bytes 0-15/(\d+)", response.headers.get("Content-Range", ""))
                    if response.status_code != 206 or not match:
                        raise ParseError("probe_failed", "CDN 不支持有效的范围读取")
                    size = int(match.group(1))
                    first = response.raw.read(16, decode_content=True)
                    final_url = response.url
                    if first[4:8] != b"ftyp":
                        raise ParseError("probe_failed", "下载响应不是 MP4 文件")
                if candidate["size"] and size != candidate["size"]:
                    raise ParseError("size_mismatch", "CDN 实际大小与原画元数据不一致")

                def read_at(offset, count, media_url=final_url, media_size=size):
                    with self._get(media_url, headers={"Range": f"bytes={offset}-{offset + count - 1}"}) as r:
                        expected = f"bytes {offset}-{offset + count - 1}/{media_size}"
                        if r.status_code != 206 or r.headers.get("Content-Range") != expected:
                            raise ParseError("probe_failed", "CDN 范围读取响应不一致")
                        return r.raw.read(count, decode_content=True)

                media = inspect_mp4(read_at, size)
                if not media["has_video"] or not media["has_audio"]:
                    raise ParseError("incomplete_media", "原画候选不是同时包含音视频轨道的完整 MP4")
                expected_duration = float(candidate.get("duration_seconds") or 0)
                if not media["duration_seconds"] or (expected_duration and
                        abs(media["duration_seconds"] - expected_duration) > 1):
                    raise ParseError("identity_mismatch", "实际 MP4 时长与原画元数据不一致")
                video_track = next(t for t in media["tracks"] if t.get("type") == "vide")
                if (video_track.get("width"), video_track.get("height")) != (candidate["width"], candidate["height"]):
                    raise ParseError("identity_mismatch", "实际 MP4 分辨率与原画元数据不一致")
                candidate["url"] = final_url
                return {"ok": True, "actual_size": size, **media}
            except (ParseError, ValueError, requests.RequestException, OSError) as exc:
                last = exc
        raise ParseError("probe_failed", f"所有原画地址校验失败：{last}")

    def parse(self, text: str, *, with_probe: bool = True) -> dict:
        started = time.monotonic()
        aweme_id = self.resolve_id(text)
        detail = self.detail(aweme_id)
        _, candidates = self.source_streams(detail)
        selected = None
        probe = None
        errors = []
        for candidate in candidates:
            if with_probe:
                try:
                    probe = self.probe(candidate)
                except ParseError as exc:
                    errors.append(str(exc))
                    continue
            selected = candidate
            break
        if selected is None:
            raise ParseError("probe_failed", "; ".join(errors))
        ordered = [selected] + [c for c in candidates if c is not selected]
        return {"code": 0, "msg": "原画解析成功", "data": {
            "aweme_id": aweme_id, "desc": detail.get("desc", ""),
            "author": (detail.get("author") or {}).get("nickname", ""),
            "share_url": f"https://www.douyin.com/video/{aweme_id}",
            "provider": "douyin-official-source", "url": selected["url"],
            "size_bytes": selected["size"], "width": selected["width"], "height": selected["height"],
            "duration_seconds": probe["duration_seconds"] if probe else selected["duration_seconds"],
            "expires_at": selected["expires_at"],
            "source_selected": True, "reference_match": None,
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
                    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=destination.name + ".",
                                                     suffix=".part", delete=False) as stream:
                        temporary = Path(stream.name)
                        for chunk in response.iter_content(256 * 1024):
                            total += len(chunk)
                            if total > max_bytes or (candidate["size"] and total > candidate["size"]):
                                raise ParseError("size_mismatch", "下载超过声明大小或设置上限")
                            stream.write(chunk)
                            sha.update(chunk)
                            md5.update(chunk)
                if total != candidate["size"]:
                    raise ParseError("size_mismatch", "下载文件大小与官方原画大小不一致")
                official_md5 = candidate.get("file_hash") or ""
                if not re.fullmatch(r"[0-9a-fA-F]{32}", official_md5) or md5.hexdigest() != official_md5.lower():
                    raise ParseError("hash_mismatch", "下载文件 MD5 与官方原画哈希不一致")
                media = inspect_file(temporary)
                if not media["has_audio"] or not media["has_video"]:
                    raise ParseError("incomplete_media", "完整文件缺少音频或视频轨道")
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
                          "sha256": sha.hexdigest(), "official_hash_match": True,
                          "reference_match": reference_match, "reference_sha256": reference_sha, "media": media}
                result["data"]["reference_match"] = reference_match
                result["data"]["download"] = record
                return record
            except (requests.RequestException, ParseError) as exc:
                errors.append(str(exc))
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
        raise ParseError("download_failed", "所有下载地址失败：" + "; ".join(errors))
