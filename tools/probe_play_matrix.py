"""HDR 作品上穷举 /aweme/v1/play/ 的业务参数组合，确认 404 是否与 source/format/stream 有关。

每个组合只发一次 Range:bytes=0-0 的探测；判定标准：206 + video/* + Content-Range 总长度。
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _abogus_ref import ABogus  # noqa: E402

PLAY_URL = "https://www.douyin.com/aweme/v1/play/"


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    aweme_id, video_id = argv[1], argv[2]

    cookies: dict[str, str] = {}
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    try:
        from original_parser.guest import get_guest

        cookies, ua = get_guest()
    except Exception as error:  # noqa: BLE001
        print(f"guest failed: {error}")

    lines = [f"aweme_id={aweme_id} video_id={video_id}"]
    sources = [
        "PackSourceEnum_PUBLISH",
        "PackSourceEnum_AWEME_DETAIL",
        "PackSourceEnum_FEED",
        "PackSourceEnum_SEARCH",
        "PackSourceEnum_PERSONAL_HOME",
    ]
    extras = [
        {},
        {"format_type": "mp4"},
        {"format_type": "dash"},
        {"stream_type": "video"},
        {"stream_type": "dash"},
        {"aid": "1128"},
        {"codec_type": "0"},
    ]
    ratios = ["default", "origin", "source"]

    seen = 0
    for source, extra, ratio in itertools.product(sources, extras, ratios):
        params = {
            "video_id": video_id,
            "ratio": ratio,
            "line": "0",
            "is_play_url": "1",
            "watermark": "0",
            "source": source,
        }
        params.update(extra)
        signer = ABogus(user_agent=ua)
        signed_query, _ab, signer_ua, _ = signer.generate_abogus(urlencode(params), "")
        try:
            resp = requests.get(
                f"{PLAY_URL}?{signed_query}",
                headers={
                    "User-Agent": signer_ua,
                    "Accept": "*/*",
                    "Range": "bytes=0-0",
                    "Referer": f"https://www.douyin.com/video/{aweme_id}",
                    "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
                },
                allow_redirects=True,
                timeout=20,
            )
        except Exception as error:  # noqa: BLE001
            lines.append(f"ERR {source} {extra} {ratio}: {type(error).__name__}")
            continue
        seen += 1
        total = (resp.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
        lines.append(
            f"{resp.status_code} ct={resp.headers.get('Content-Type')} total={total} "
            f"| source={source} ratio={ratio} extra={extra}"
        )

    lines.append(f"-- requests={seen}")
    text = "\n".join(lines)
    print(text)
    root = Path(__file__).resolve().parent.parent / "output"
    root.mkdir(exist_ok=True)
    (root / f"play-matrix-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
