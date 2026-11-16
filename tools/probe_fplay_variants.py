"""探针：在官方 fplay 上尝试若干客户端能力/档位参数，看能否拿到原片桶行。

只读；只发官方域名；只打印档位与桶名，不打印签名地址。
"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlunsplit, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, check_url  # noqa: E402
from original_parser.codec import decode_url  # noqa: E402

AWEME = sys.argv[1] if len(sys.argv) > 1 else "7707993970332290314"

VARIANTS = [
    ("baseline vquality=8", {"vquality": "8"}),
    ("vquality=9", {"vquality": "9"}),
    ("vquality=5 source", {"vquality": "5", "stream_type": "source"}),
    ("aid=2329", {"aid": "2329"}),
    ("aid=1128", {"aid": "1128"}),
    ("codec_type=1 source", {"codec_type": "1", "stream_type": "source"}),
    ("codec_type=6 source", {"codec_type": "6", "stream_type": "source"}),
    ("force_fids=source", {"force_fids": base64.b64encode(b"source").decode("ascii"),
                           "stream_type": "source"}),
]

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(AWEME)
    video = detail.get("video") or {}
    model = video.get("video_model")
    if isinstance(model, str):
        model = json.loads(model)
    vid = (video.get("play_addr") or {}).get("uri")
    fallback = model.get("fallback_api")
    url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
    part = urlsplit(check_url(url, ("snssdk.com",)))
    base = parse_qs(part.query, keep_blank_values=True)
    base.pop("logo_type", None)
    print("vid:", vid)

    for label, extra in VARIANTS:
        params = {k: list(v) for k, v in base.items()}
        for key, value in extra.items():
            params[key] = [value]
        request_url = urlunsplit((part.scheme, part.netloc, part.path,
                                  urlencode(params, doseq=True), ""))
        try:
            payload = parser._json(request_url, stage="原画接口")
        except Exception as exc:  # noqa: BLE001
            print(f"{label:22} ERR {type(exc).__name__}: {str(exc)[:90]}")
            continue
        data = (payload.get("video_info") or {}).get("data") or {}
        rows = data.get("video_list") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        qualities = sorted({str(r.get("quality")) for r in rows if isinstance(r, dict)})
        buckets = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            addr = row.get("main_url") or row.get("backup_url")
            if not isinstance(addr, str):
                continue
            try:
                decoded = decode_url(addr, data.get("key_seed", ""))
            except Exception:  # noqa: BLE001
                continue
            q = urlsplit(decoded)
            buckets |= {x for x in q.path.split("/") if x.startswith("tos-cn-")}
            if "ixigua" in q.netloc:
                buckets.add("ixigua-host")
        flag = "★原片桶" if any(b.startswith("tos-cn-v-") for b in buckets) else ""
        print(f"{label:22} status={data.get('status')} rows={len(rows)} {qualities} "
              f"buckets={sorted(buckets)} {flag}")
