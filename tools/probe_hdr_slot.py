"""实验性检查 fids=hdr 档位和实际字节长度；不据档位名称认定原画。

用法：python tools/probe_hdr_slot.py <aweme_id> [credentials.json]
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from original_parser.client import OriginalParser, decode_url  # noqa: E402


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
        params = dict(base)
        params["force_fids"] = [base64.b64encode(b"hdr").decode("ascii")]
        request_url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                  urlencode(params, doseq=True), ""))
        payload = parser._json(request_url, stage="hdr 槽")
        data = ((payload.get("video_info") or {}).get("data") or {})
        rows = data.get("video_list") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        seed = data.get("key_seed", "")
        lines.append(f"status={data.get('status')} 档位={len(rows)} duration={data.get('video_duration')}")
        for row in rows:
            if not isinstance(row, dict):
                continue
            lines.append(f"  definition={row.get('definition')!r} quality={row.get('quality')!r} "
                         f"size={row.get('size')} codec={row.get('codec_type')} "
                         f"有kid={bool(row.get('kid'))} 有spade_a={bool(row.get('spade_a'))} "
                         f"encrypt={bool(row.get('encrypt'))}")
            for key in ("main_url", "backup_url_1", "backup_url_2"):
                if not row.get(key):
                    continue
                try:
                    decoded = decode_url(row[key], seed)
                except Exception as error:  # noqa: BLE001
                    lines.append(f"  {key} 解码失败 {type(error).__name__}")
                    continue
                split = urlsplit(decoded)
                marker = "/video/tos/cn/"
                object_path = split.path.split(marker, 1)[1] if marker in split.path else "未识别稳定对象"
                lines.append(f"  {key} host={split.hostname} object={object_path}")
                lines.append(f"  {key} query keys={sorted(parse_qs(split.query))}")
                try:
                    response = requests.get(decoded, headers={"Range": "bytes=0-15",
                                                              "User-Agent": parser._signer_ua},
                                            timeout=25, allow_redirects=True)
                    total = response.headers.get("Content-Range", "")
                    lines.append(f"  {key} 实测 status={response.status_code} "
                                 f"type={response.headers.get('Content-Type')} Content-Range={total} "
                                 f"Content-Length={response.headers.get('Content-Length')} "
                                 f"final_host={urlsplit(response.url).netloc}")
                except requests.RequestException as error:
                    lines.append(f"  {key} 请求失败 {type(error).__name__}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"hdr-slot-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
