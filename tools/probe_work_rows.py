"""探针：看 fplay 单行的完整字段与详情各 addr 的地址（含桶名）。"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

A = sys.argv[1] if len(sys.argv) > 1 else "7708052871413075238"


def bucket(url):
    try:
        return next((seg for seg in urlsplit(url).path.split("/") if seg.startswith("tos-cn-")), "-")
    except ValueError:
        return "-"


with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
    video = detail.get("video") or {}

    print("== detail addrs ==")
    for key, value in video.items():
        if isinstance(value, dict) and value.get("url_list"):
            urls = value["url_list"]
            print(f"{key}: data_size={value.get('data_size')} wh={value.get('width')}x{value.get('height')}")
            for url in urls:
                print("   ", urlsplit(url).netloc[:34], bucket(url), url[:60])

    model = json.loads(video["video_model"]) if isinstance(video.get("video_model"), str) else {}
    raw = (model.get("fallback_api") or {})
    url = raw.get("fallback_api") if isinstance(raw, dict) else raw
    p = urlsplit(url)
    params = parse_qs(p.query, keep_blank_values=True)
    params.pop("logo_type", None)
    params["force_fids"] = [base64.b64encode(b"original").decode("ascii")]
    params["codec_type"] = ["5"]
    probe = urlunsplit((p.scheme, p.netloc, p.path, urlencode(params, doseq=True), ""))
    payload = parser._json(probe, stage="原画接口")
    data = ((payload.get("video_info") or {}).get("data") or {})
    rows = data.get("video_list") or {}
    rows = list(rows.values()) if isinstance(rows, dict) else rows

    print("\n== fplay row keys ==", sorted(rows[0]) if rows else "none")
    print("\n== first row ==")
    for key, value in (rows[0] if rows else {}).items():
        text = json.dumps(value, ensure_ascii=False)[:120] if not isinstance(value, str) else value[:120]
        print(f"   {key} = {text}")

    print("\n== all rows buckets ==")
    for row in rows:
        mains = [row.get("main_url")] if row.get("main_url") else []
        mains += row.get("url_list") or []
        main = mains[0] if mains else ""
        print(f"   q={row.get('quality'):14} size={row.get('size')} "
              f"wh={row.get('vwidth')}x{row.get('vheight')} bucket={bucket(main)} "
              f"keyseed={bool(row.get('file_hash'))} urls={len(mains)}")
