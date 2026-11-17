"""打印 fplay 档位接口的实际回包清单（不做档位过滤），用于看清 HDR 作品注册了哪些档位。

用法：python tools/dump_fplay_gears.py <aweme_id> [credentials.json]
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


def variants(url: str) -> dict[str, str]:
    parts = urlsplit(url)
    base = parse_qs(parts.query, keep_blank_values=True)
    made = {}
    plain = {k: v for k, v in base.items() if k != "logo_type"}
    made["原样（仅去 logo_type）"] = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                                 urlencode(plain, doseq=True), ""))
    original = dict(plain)
    original["force_fids"] = [base64.b64encode(b"original").decode("ascii")]
    original["codec_type"] = ["5"]
    made["force_fids=original+codec5"] = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                                     urlencode(original, doseq=True), ""))
    source = dict(plain)
    source["stream_type"] = ["source"]
    made["stream_type=source"] = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                            urlencode(source, doseq=True), ""))
    no_codec = {k: v for k, v in plain.items() if k != "codec_type"}
    made["去 codec_type"] = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                       urlencode(no_codec, doseq=True), ""))
    return made


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    cookies = json.loads(credentials.read_text(encoding="utf-8")).get("cookies", {})
    user_agent = json.loads(credentials.read_text(encoding="utf-8")).get("user_agent")
    lines = [f"aweme_id={aweme_id}"]
    with OriginalParser(cookies=cookies, user_agent=user_agent, auto_guest=False) as parser:
        detail = parser.detail(aweme_id)
        video = detail.get("video") or {}
        model = video.get("video_model")
        model = json.loads(model) if isinstance(model, str) else model
        fallback = model.get("fallback_api")
        url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
        lines.append(f"video_id={(video.get('play_addr') or {}).get('uri')} "
                     f"is_source_HDR={video.get('is_source_HDR')} duration={video.get('duration')}")
        for label, request_url in variants(url).items():
            try:
                payload = parser._json(request_url, stage="档位探查")
            except Exception as error:  # noqa: BLE001
                lines.append(f"\n[{label}] !! {type(error).__name__} {error}")
                continue
            data = ((payload.get("video_info") or {}).get("data") or {})
            rows = data.get("video_list") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
            lines.append(f"\n[{label}] code={payload.get('code')} status={data.get('status')} "
                         f"video_id={data.get('video_id')} 档位={len(rows)}")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"  quality={row.get('quality')!r} vtype={row.get('vtype')} "
                    f"size={row.get('size')} wh={row.get('vwidth')}x{row.get('vheight')} "
                    f"bitrate={row.get('bitrate')} codec_type={row.get('codec_type')} "
                    f"file_id={row.get('file_id')} file_hash={row.get('file_hash')} "
                    f"encrypt={row.get('encrypt')} 有地址={'main_url' in row}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"fplay-gears-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
