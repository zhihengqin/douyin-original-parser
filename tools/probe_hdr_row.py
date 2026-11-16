"""探针：取 force_fids=hdr 返回的那一行，解码地址并实测大小/轨道。"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402
from original_parser.codec import decode_url  # noqa: E402

WORK = sys.argv[1] if len(sys.argv) > 1 else "7708052871413075238"

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(WORK)
    video = detail.get("video") or {}
    vid = (video.get("play_addr") or {}).get("uri")
    model = json.loads(video["video_model"]) if isinstance(video.get("video_model"), str) else {}
    raw = model.get("fallback_api") or {}
    base = raw.get("fallback_api") if isinstance(raw, dict) else raw
    p = urlsplit(base)
    for codec in ("0", "5"):
        params = parse_qs(p.query, keep_blank_values=True)
        params.pop("logo_type", None)
        params["force_fids"] = [base64.b64encode(b"hdr").decode("ascii")]
        params["codec_type"] = [codec]
        url = urlunsplit((p.scheme, p.netloc, p.path, urlencode(params, doseq=True), ""))
        payload = parser._json(url, stage="原画接口")
        data = ((payload.get("video_info") or {}).get("data") or {})
        seed = data.get("key_seed")
        rows = data.get("video_list") or {}
        rows = list(rows.values()) if isinstance(rows, dict) else rows
        print(f"\n=== {WORK} codec={codec} fid=hdr rows={len(rows)} seed={bool(seed)} ===")
        for row in rows:
            print(json.dumps({k: (v[:60] if isinstance(v, str) else v) for k, v in row.items()},
                             ensure_ascii=False, indent=2))
            for key in ("main_url", "backup_url_1"):
                encoded = row.get(key)
                if not encoded:
                    continue
                try:
                    decoded = decode_url(encoded, seed)
                except ValueError as exc:
                    print(f"  {key} 解码失败：{exc}")
                    continue
                print(f"  {key} 解码：{decoded[:120]}")
                try:
                    with parser._get(decoded, headers={"Range": "bytes=0-15"}) as response:
                        print("     Range:", response.status_code, response.headers.get("Content-Range"))
                        head = response.raw.read(16, decode_content=False)
                        print("     首16字节:", head[:16], "| ftyp:", head[4:8] == b"ftyp")
                except Exception as exc:  # noqa: BLE001
                    print("     读取失败:", type(exc).__name__, exc)
