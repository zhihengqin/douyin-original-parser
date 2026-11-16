"""探针：诊断一个作品的目录与档位（是否列举原片、落在哪个桶、有无 file_hash）。"""

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlencode, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

A = sys.argv[1] if len(sys.argv) > 1 else "7708052871413075238"

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
    video = detail.get("video") or {}
    addr = video.get("play_addr") or {}
    print("aweme_id:", detail.get("aweme_id"))
    print("desc:", (detail.get("desc") or "")[:60])
    print("author:", ((detail.get("author") or {}).get("nickname")))
    print("is_source_HDR:", video.get("is_source_HDR"), "| is_long_video:", video.get("is_long_video"))
    print("duration_ms:", video.get("duration"))
    print("ratio:", video.get("ratio"), "| VID:", addr.get("uri"))
    print("play_addr:", addr.get("width"), "x", addr.get("height"), addr.get("data_size"))
    print("token_auth:", bool((video.get("token_auth") or {}).get("play_auth_token")))
    print("bit_rate:")
    for gear in (video.get("bit_rate") or []):
        play = gear.get("play_addr") or {}
        print("   ", gear.get("gear_name"), "q=", gear.get("quality_type"), "br=", gear.get("bit_rate"),
              "size=", play.get("data_size"), "wh=", play.get("width"), play.get("height"),
              "hash=", str(gear.get("file_hash"))[:8])

    model = json.loads(video["video_model"]) if isinstance(video.get("video_model"), str) else None
    marked = model.get("video_id") if isinstance(model, dict) else None
    print("video_model video_id:", marked)
    fallback = (model or {}).get("fallback_api")
    url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
    if isinstance(url, str):
        p = urlsplit(url)
        print("fplay path:", p.path)
        print("fplay params:", {k: v[0][:26] for k, v in parse_qs(p.query).items()})
        params = parse_qs(p.query, keep_blank_values=True)
        params.pop("logo_type", None)
        import base64
        params["force_fids"] = [base64.b64encode(b"original").decode("ascii")]
        params["codec_type"] = ["5"]
        probe = urlunsplit((p.scheme, p.netloc, p.path, urlencode(params, doseq=True), ""))
        payload = parser._json(probe, stage="原画接口")
        data = ((payload.get("video_info") or {}).get("data") or {})
        print("status:", data.get("status"), "| key_seed:", bool(data.get("key_seed")))
        rows = data.get("video_list") or {}
        rows = list(rows.values()) if isinstance(rows, dict) else rows
        print("rows:", len(rows))
        for row in rows:
            main = row.get("main_url") or ""
            bucket = next((seg for seg in urlsplit(main).path.split("/") if seg.startswith("tos-cn-")), "-")
            print(f"    q={row.get('quality'):16} geardes={row.get('gear_des_key','')[:26]:26} "
                  f"size={row.get('size')} wh={row.get('vwidth')}x{row.get('vheight')} "
                  f"hash={str(row.get('file_hash'))[:8]} bucket={bucket}")
