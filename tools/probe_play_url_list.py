"""检查 web/app 详情里 play_addr.url_list 的真实 CDN 路径，比对是否出现原片对象键。

用法：python tools/probe_play_url_list.py <aweme_id> [credentials.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from original_parser.client import OriginalParser  # noqa: E402


def dump_addr(label: str, addr: dict) -> list[str]:
    out = [f"{label}: uri={addr.get('uri')} size={addr.get('data_size')} "
           f"wh={addr.get('width')}x{addr.get('height')}"]
    urls = addr.get("url_list") or []
    out.append(f"  url_list 条数={len(urls)}")
    for url in urls[:3]:
        split = urlsplit(url)
        keys = sorted(parse_qs(split.query))
        out.append(f"  host={split.netloc} path={split.path[:150]}")
        out.append(f"  query keys={keys[:14]}")
    return out


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    blob = json.loads(credentials.read_text(encoding="utf-8"))
    lines = [f"aweme_id={aweme_id}"]
    original_key = "ogAAMdqlAbNZiScDirADwEEB1gsDeA8BdWfGq8"
    markers = (original_key, "tos-cn-v-0051", "video/tos/cn")
    for mode, kwargs in (("网页详情", {"cookies": None, "auto_guest": True}),
                         ("登录网页详情", {"cookies": blob.get("cookies"),
                                          "user_agent": blob.get("user_agent"), "auto_guest": False})):
        lines.append(f"\n===== {mode} =====")
        try:
            with OriginalParser(**kwargs) as parser:
                detail = parser.detail(aweme_id)
        except Exception as error:  # noqa: BLE001
            lines.append(f"  详情失败 {type(error).__name__}")
            continue
        video = detail.get("video") or {}
        for label in ("play_addr", "play_addr_265", "play_addr_h264", "download_addr", "play_addr_lowbr"):
            addr = video.get(label)
            if isinstance(addr, dict):
                lines.extend(dump_addr(label, addr))
        text = json.dumps(detail, ensure_ascii=False)
        for marker in markers:
            lines.append(f"  详情内出现 {marker!r}: {text.count(marker)} 次")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"play-url-list-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
