"""HDR 作品补测：默认档接口换 video_id（download_addr 的 uri / 详情其它 uri）。

用法：python tools/probe_play_default_alt_vid.py <aweme_id>
"""
from __future__ import annotations

import sys
from pathlib import Path

from urllib.parse import parse_qs, urlencode, urlsplit

from original_parser.client import OriginalParser, ParseError


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    lines = []
    with OriginalParser() as parser:
        detail = parser.detail(aweme_id)
        video = detail.get("video") or {}
        ids = []
        for key in ("play_addr", "play_addr_h264", "play_addr_265", "download_addr"):
            addr = video.get(key)
            uri = (addr or {}).get("uri") if isinstance(addr, dict) else None
            if uri and uri not in ids:
                ids.append((key, uri))
        lines.append(f"aweme_id={aweme_id} uri={ids}")
        for key, uri in ids:
            for ratio in ("default",):
                params = {"video_id": uri, "ratio": ratio, "line": "0",
                          "is_play_url": "1", "watermark": "0",
                          "source": "PackSourceEnum_PUBLISH"}
                url = "https://www.douyin.com/aweme/v1/play/?" + parser._a_bogus_query(params)
                try:
                    with parser._get(url, headers={"Range": "bytes=0-15",
                                                   "Accept-Encoding": "identity",
                                                   "Referer": f"https://www.douyin.com/video/{aweme_id}"}) as r:
                        total = (r.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
                        lines.append(f"{key} {ratio}: status={r.status_code} ct={r.headers.get('Content-Type')} total={total}")
                        lines.append(f"  final={r.url[:170]}")
                except ParseError as error:
                    lines.append(f"{key} {ratio}: !! [{error.code}] {error}")
    text = "\n".join(lines)
    print(text)
    root = Path(__file__).resolve().parent.parent / "output"
    root.mkdir(exist_ok=True)
    (root / f"play-altvid-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
