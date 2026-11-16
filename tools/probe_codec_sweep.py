"""探针：固定 force_fids=original，扫 codec_type 全值域，看是否有一条能列出原片。"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

WORKS = sys.argv[1:] or ["7708052871413075238"]

for work in WORKS:
    with OriginalParser(auto_guest=True) as parser:
        detail = parser.detail(work)
    video = detail.get("video") or {}
    vid = (video.get("play_addr") or {}).get("uri")
    model = json.loads(video["video_model"]) if isinstance(video.get("video_model"), str) else {}
    raw = model.get("fallback_api") or {}
    base = raw.get("fallback_api") if isinstance(raw, dict) else raw
    p = urlsplit(base)
    print(f"\n=== {work} VID={vid} ===")
    for codec in ("0", "1", "2", "3", "4", "5", "6", "7", "9"):
        for fid in ("original", "source", "hdr", "origin"):
            params = parse_qs(p.query, keep_blank_values=True)
            params.pop("logo_type", None)
            params["force_fids"] = [base64.b64encode(fid.encode()).decode("ascii")]
            params["codec_type"] = [codec]
            url = urlunsplit((p.scheme, p.netloc, p.path, urlencode(params, doseq=True), ""))
            try:
                payload = parser._json(url, stage="原画接口")
            except Exception as exc:  # noqa: BLE001
                print(f"  codec={codec} fid={fid:8} 异常 {type(exc).__name__}")
                continue
            data = ((payload.get("video_info") or {}).get("data") or {})
            rows = data.get("video_list") or {}
            rows = list(rows.values()) if isinstance(rows, dict) else rows
            names = sorted({str(row.get("quality")) for row in rows})
            sizes = sorted({int(row.get("size") or 0) for row in rows})
            hit = [q for q in names if q in ("original", "source")]
            flag = " ★原片档" if hit else ""
            print(f"  codec={codec} fid={fid:8} rows={len(rows):2} max={max(sizes) if sizes else 0:>12} "
                  f"q={names[:6]}{flag}")
