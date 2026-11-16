"""探测 /aweme/v1/play/?ratio=default 是否 302 到上传原片。

对照 jiji262/douyin-downloader 的 _probe_original_play_source 实现：
GET https://www.douyin.com/aweme/v1/play/?video_id=<vid>&ratio=default&line=0
     &is_play_url=1&watermark=0&source=PackSourceEnum_PUBLISH
头部 Range: bytes=0-0，跟随跳转，看落点 URL 与 Content-Range 总长度。

用法：
    python tools\probe_play_ratio.py <作品ID> <video_id> [<video_id> ...]
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

PLAY_URL = "https://www.douyin.com/aweme/v1/play/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _base_params(video_id: str, ratio: str) -> dict[str, str]:
    return {
        "video_id": video_id,
        "ratio": ratio,
        "line": "0",
        "is_play_url": "1",
        "watermark": "0",
        "source": "PackSourceEnum_PUBLISH",
    }


def _headers(referer: str) -> dict[str, str]:
    return {
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "*/*",
        "Range": "bytes=0-0",
    }


def probe(aweme_id: str, video_id: str, out: list[str]) -> None:
    referer = f"https://www.douyin.com/video/{aweme_id}"
    for ratio in ("default", "1080p", "720p"):
        params = _base_params(video_id, ratio)
        out.append(f"[{ratio}] GET {PLAY_URL}?{urlencode(params)}")
        try:
            resp = requests.get(
                PLAY_URL,
                params=params,
                headers=_headers(referer),
                allow_redirects=True,
                timeout=20,
            )
        except Exception as error:  # noqa: BLE001
            out.append(f"  !! {type(error).__name__}: {error}")
            continue
        out.append(f"  status={resp.status_code} content_type={resp.headers.get('Content-Type')}")
        out.append(f"  final={resp.url}")
        out.append(
            "  content_range={} content_length={}".format(
                resp.headers.get("Content-Range"), resp.headers.get("Content-Length")
            )
        )
        try:
            body = resp.content[:400]
            out.append(f"  body[:400]={body!r}")
        except Exception as error:  # noqa: BLE001
            out.append(f"  !! body read failed: {error}")
        out.append("")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    aweme_id = argv[1]
    lines: list[str] = [f"aweme_id={aweme_id}"]
    for video_id in argv[2:]:
        lines.append(f"--- video_id={video_id}")
        probe(aweme_id, video_id, lines)
    text = "\n".join(lines)
    print(text)
    root = Path(__file__).resolve().parent.parent / "output"
    root.mkdir(exist_ok=True)
    (root / f"play-ratio-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
