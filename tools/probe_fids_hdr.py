"""打印 force_fids=hdr（及其它 fid）的原始档位行，含被 size=0 过滤掉的空档。

用法：python tools/probe_fids_hdr.py <aweme_id> [credentials.json]
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
        for fids in ("hdr", "hdr_2160", "hdr_1080", "source_hdr", "original"):
            params = dict(base)
            params["force_fids"] = [base64.b64encode(fids.encode()).decode("ascii")]
            request_url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                      urlencode(params, doseq=True), ""))
            try:
                payload = parser._json(request_url, stage="fid 探查")
            except Exception as error:  # noqa: BLE001
                lines.append(f"\n[fids={fids}] !! {type(error).__name__} {error}")
                continue
            info = payload.get("video_info") or {}
            data = info.get("data") or {}
            rows = data.get("video_list") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
            lines.append(f"\n[fids={fids}] code={payload.get('code')} info_code={info.get('code')} "
                         f"status={data.get('status')} 档位={len(rows)} "
                         f"data keys={sorted(data)}")
            for row in rows:
                if not isinstance(row, dict):
                    lines.append(f"  (非 dict) {row}")
                    continue
                keys = {k: row.get(k) for k in ("quality", "vtype", "size", "vwidth", "vheight",
                                                "bitrate", "codec_type", "file_id", "file_hash",
                                                "encrypt", "url_expire")}
                has_main = bool(row.get("main_url"))
                lines.append(f"  {json.dumps(keys, ensure_ascii=False)} 有地址={has_main} "
                             f"全部字段={sorted(row)}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"fids-hdr-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
