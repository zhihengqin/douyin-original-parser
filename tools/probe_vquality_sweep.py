"""探针：fplay 的 vquality 全值域扫描，看是否存在能取到原片桶的取值。"""

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlunsplit, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, check_url  # noqa: E402
from original_parser.codec import decode_url  # noqa: E402

A = "7707993970332290314"
VALUES = [str(v) for v in range(0, 14)] + ["hd", "sd", "source", "original", "origin", "hdr"]


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

    for value in VALUES:
        params = {k: list(v) for k, v in base.items()}
        params.pop("logo_type", None)
        params["vquality"] = [value]
        req = urlunsplit((part.scheme, part.netloc, part.path, urlencode(params, doseq=True), ""))
        try:
            payload = parser._json(req, stage="原画接口")
        except Exception as exc:  # noqa: BLE001
            print(f"vquality={value:9} ERR {type(exc).__name__} {str(exc)[:40]}")
            continue
        data = (payload.get("video_info") or {}).get("data") or {}
        rows = data.get("video_list") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        found = buckets(rows, data.get("key_seed", ""))
        sizes = sorted(int((r.get("size") or 0)) for r in rows if isinstance(r, dict))
        star = "  ★原片桶" if any(b.startswith("tos-cn-v-") for b in found) else ""
        print(f"vquality={value:9} status={data.get('status')} rows={len(rows)} "
              f"max_size={max(sizes) if sizes else 0} {found}{star}")
