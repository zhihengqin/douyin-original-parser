"""探针：fplay 的 stream_type 取值矩阵 + 分发接口路径矩阵（都只用官方域名）。"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlunsplit, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, check_url  # noqa: E402
from original_parser.codec import decode_url  # noqa: E402

A = "7707993970332290314"
VID = "v28033gi0000dbs4nevog65jrl6u1s10"

STREAM_TYPES = ["hdr", "origin", "original", "source", "high", "dash"]
PATHS = ["/aweme/v1/play/", "/aweme/v1/play/hd/", "/aweme/v1/play/hdr/",
         "/aweme/v1/play/source/", "/aweme/v1/play/original/", "/aweme/v1/play/hevc/",
         "/aweme/v1/play/h264/", "/aweme/v1/playwm/"]


def buckets(rows, seed):
    found = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        addr = row.get("main_url") or row.get("backup_url")
        if not isinstance(addr, str):
            continue
        try:
            decoded = decode_url(addr, seed)
        except Exception:  # noqa: BLE001
            continue
        found |= {x for x in urlsplit(decoded).path.split("/") if x.startswith("tos-cn-")}
    return sorted(found)


with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
    model = detail["video"]["video_model"]
    if isinstance(model, str):
        model = json.loads(model)
    fallback = model["fallback_api"]
    fplay = fallback["fallback_api"] if isinstance(fallback, dict) else fallback
    part = urlsplit(check_url(fplay, ("snssdk.com",)))
    base = parse_qs(part.query, keep_blank_values=True)

    print("=== fplay stream_type 矩阵 ===")
    for stream in STREAM_TYPES:
        params = {k: list(v) for k, v in base.items()}
        params.pop("logo_type", None)
        params["stream_type"] = [stream]
        req = urlunsplit((part.scheme, part.netloc, part.path, urlencode(params, doseq=True), ""))
        try:
            payload = parser._json(req, stage="原画接口")
        except Exception as exc:  # noqa: BLE001
            print(f"stream_type={stream:9} ERR {type(exc).__name__} {str(exc)[:50]}")
            continue
        data = (payload.get("video_info") or {}).get("data") or {}
        rows = data.get("video_list") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        found = buckets(rows, data.get("key_seed", ""))
        star = "★" if any(b.startswith("tos-cn-v-") for b in found) else ""
        print(f"stream_type={stream:9} status={data.get('status')} rows={len(rows)} "
              f"{found} {star} msg={data.get('message')}")

    print("\n=== 分发接口路径矩阵（无 sign） ===")
    params = {"video_id": VID, "file_id": VID, "line": "0", "is_play_url": "1",
              "source": "PackSourceEnum_AWEME_DETAIL"}
    for path in PATHS:
        url = "https://www.douyin.com" + path + "?" + urlencode(params)
        try:
            with parser._get(url, headers={"Range": "bytes=0-15",
                                           "Accept-Encoding": "identity"}) as response:
                host = urlsplit(response.url).netloc
                bucket = next((x for x in urlsplit(response.url).path.split("/")
                               if x.startswith("tos-cn-")), "-")
                print(f"{path:28} HTTP {response.status_code} host={host} bucket={bucket} "
                      f"range={response.headers.get('Content-Range', '-')}")
        except Exception as exc:  # noqa: BLE001
            print(f"{path:28} ERR {type(exc).__name__} {str(exc)[:60]}")
