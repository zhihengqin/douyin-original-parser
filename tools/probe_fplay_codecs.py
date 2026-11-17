"""扫描 fplay 在不同 codec_type / force_fids 组合下暴露的档位清单，找原片 file_id。

用法：python tools/probe_fplay_codecs.py <aweme_id> [credentials.json]
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from original_parser.client import OriginalParser  # noqa: E402

FIDS = ("original", "source", "adapt", "normal", "low", "high", "origin", "hdr")


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    blob = json.loads(credentials.read_text(encoding="utf-8"))
    lines = [f"aweme_id={aweme_id}"]
    with OriginalParser(cookies=blob.get("cookies"), user_agent=blob.get("user_agent"),
                        auto_guest=False) as parser:
        detail = parser.detail(aweme_id)
        video = detail.get("video") or {}
        model = video.get("video_model")
        model = json.loads(model) if isinstance(model, str) else model
        fallback = model.get("fallback_api")
        url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
        parts = urlsplit(url)
        base = {k: v for k, v in parse_qs(parts.query, keep_blank_values=True).items()
                if k != "logo_type"}
        seen: dict[str, tuple] = {}
        combos = []
        for fids in FIDS:
            for codec in (None, "0", "1", "2", "3", "4", "5", "6", "7"):
                combos.append((fids, codec))
        for fids, codec in combos:
            params = dict(base)
            params["force_fids"] = [base64.b64encode(fids.encode()).decode("ascii")]
            if codec is not None:
                params["codec_type"] = [codec]
            request_url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                      urlencode(params, doseq=True), ""))
            try:
                payload = parser._json(request_url, stage="档位扫描")
            except Exception as error:  # noqa: BLE001
                lines.append(f"fids={fids} codec={codec} !! {type(error).__name__}")
                continue
            data = ((payload.get("video_info") or {}).get("data") or {})
            rows = data.get("video_list") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = str(row.get("file_id"))
                if key and key not in seen:
                    seen[key] = (row.get("quality"), row.get("size"), row.get("vwidth"),
                                 row.get("vheight"), row.get("codec_type"), fids, codec)
            top = max((int(row.get("size") or 0) for row in rows if isinstance(row, dict)), default=0)
            lines.append(f"fids={fids} codec={codec} 档位={len(rows)} 最大={top}")
    lines.append(f"\n去重后所有 file_id {len(seen)} 个（按 size 降序）：")
    for key, meta in sorted(seen.items(), key=lambda item: -(item[1][1] or 0)):
        lines.append(f"  file_id={key} quality={meta[0]} size={meta[1]} "
                     f"wh={meta[2]}x{meta[3]} codec={meta[4]} 首次来自 fids={meta[5]} codec={meta[6]}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"fplay-codecs-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
