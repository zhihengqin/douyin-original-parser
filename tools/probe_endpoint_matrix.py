"""探针：枚举若干官方入口，检查哪一个会返回原片桶（tos-cn-v-…）或 ixigua 主机地址。

只读，只发官方域名请求；不打印完整签名地址，只打印主机与桶名。
"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlunsplit, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, ParseError, check_url, signed_query  # noqa: E402

AWEME = sys.argv[1] if len(sys.argv) > 1 else "7707993970332290314"
VID = sys.argv[2] if len(sys.argv) > 2 else ""

ORIGINAL_BUCKETS = ("tos-cn-v-0051", "tos-cn-v-", "ixigua")


def _walk(node):
    """递归取出 JSON 里的 (路径, 值)。"""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)
    else:
        yield "", node


def scan(label: str, payload_text: str) -> str:
    hits = []
    for key in ("tos-cn-v-0051-ce", "tos-cn-v-0051", "tos-cn-v-", "ixigua.com"):
        if key in payload_text:
            hits.append(f"{key}x{payload_text.count(key)}")
    return f"命中: {', '.join(hits)}" if hits else "命中: 无"


with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(AWEME)
    video = detail.get("video") or {}
    vid = VID or (video.get("play_addr") or {}).get("uri")
    model = video.get("video_model")
    if isinstance(model, str):
        model = json.loads(model)
    fallback = model.get("fallback_api")
    fplay_url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
    fp = urlsplit(check_url(fplay_url, ("snssdk.com",)))

    def fplay_url_with(extra: dict) -> str:
        params = parse_qs(fp.query, keep_blank_values=True)
        params.pop("logo_type", None)
        for key, value in extra.items():
            params[key] = [value]
        return urlunsplit((fp.scheme, fp.netloc, fp.path, urlencode(params, doseq=True), ""))

    tests = [
        ("iteminfo(iesdouyin)",
         f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={AWEME}"),
        ("web-detail aid=6383",
         f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={AWEME}&aid=6383"
         "&device_platform=webapp&version_code=170400"),
        ("app-detail aid=1128",
         f"https://aweme.snssdk.com/aweme/v1/aweme/detail/?aweme_id={AWEME}&aid=1128"
         "&device_platform=android&version_code=410000"),
        ("fplay ratio=original", fplay_url_with({"ratio": "original"})),
        ("fplay vquality=original", fplay_url_with({"vquality": "original"})),
        ("fplay force_fids=source",
         fplay_url_with({"force_fids": base64.b64encode(b"source").decode("ascii"),
                         "codec_type": "5"})),
        ("fplay ratio=1080p", fplay_url_with({"ratio": "1080p"})),
        ("play no-sign ratio=original",
         f"https://www.douyin.com/aweme/v1/play/?video_id={vid}&file_id={vid}"
         "&line=0&is_play_url=1&ratio=original"),
    ]

    for label, url in tests:
        if label.startswith("web-detail"):
            signed = signed_query(parse_qs(urlsplit(url).query), parser.cookies or {})
            if signed:
                url = url + "&" + signed
        try:
            response = parser.session.get(url, timeout=15,
                                          headers={"User-Agent": parser.user_agent})
        except Exception as exc:  # noqa: BLE001
            print(f"{label:28} exception {type(exc).__name__}")
            continue
        body = response.content or b""
        text = body.decode("utf-8", "ignore")
        size = f"{len(body)}B"
        extra = ""
        if body.startswith(b"\x00\x00"):
            extra = f" mp4-ftyp={body[4:8]!r}"
        print(f"{label:28} HTTP {response.status_code} {size} {scan(label, text)}{extra}")
        if not text.startswith("{"):
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        # 统计所有 url 列表里的主机与桶
        hosts = {}
        for key, value in _walk(data):
            if isinstance(value, str) and value.startswith("http"):
                q = urlsplit(value)
                bucket = next((x for x in q.path.split("/") if x.startswith("tos-cn-")), "-")
                hosts[(q.netloc, bucket)] = hosts.get((q.netloc, bucket), 0) + 1
        for (host, bucket), count in sorted(hosts.items(), key=lambda kv: -kv[1])[:6]:
            print(f"    url host={host} bucket={bucket} x{count}")
