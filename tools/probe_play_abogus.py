"""用 A_Bogus 给 /aweme/v1/play/ 签名后探测 ratio=default 是否落原片。

对照组：
  1) 裸请求（无签名，无 Cookie）——已知 404
  2) A_Bogus + 访客 Cookie（ttwid/UIFID）
  3) A_Bogus + ratio=default + 已知 file_hash 作为 sign
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _abogus_ref import ABogus  # noqa: E402

PLAY_URL = "https://www.douyin.com/aweme/v1/play/"


def build_params(video_id: str, ratio: str, sign: str | None = None) -> dict[str, str]:
    params = {
        "video_id": video_id,
        "ratio": ratio,
        "line": "0",
        "is_play_url": "1",
        "watermark": "0",
        "source": "PackSourceEnum_PUBLISH",
    }
    if sign:
        params["sign"] = sign
        params["file_id"] = video_id
    return params


def probe(tag: str, params: dict[str, str], cookies: dict[str, str], ua: str, out: list[str]) -> None:
    query = urlencode(params)
    signer = ABogus(user_agent=ua)
    signed_query, ab, signer_ua, _body = signer.generate_abogus(query, "")
    url = f"{PLAY_URL}?{signed_query}"
    out.append(f"[{tag}] ab={ab[:40]}... ua_matches={signer_ua == ua}")
    headers = {
        "User-Agent": signer_ua,
        "Accept": "*/*",
        "Range": "bytes=0-0",
        "Referer": "https://www.douyin.com/",
    }
    try:
        resp = requests.get(url, headers=headers, cookies=cookies, allow_redirects=True, timeout=25)
    except Exception as error:  # noqa: BLE001
        out.append(f"  !! {type(error).__name__}: {error}")
        out.append("")
        return
    out.append(f"  status={resp.status_code} ct={resp.headers.get('Content-Type')}")
    out.append(f"  final={resp.url}")
    out.append(
        "  content_range={} content_length={}".format(
            resp.headers.get("Content-Range"), resp.headers.get("Content-Length")
        )
    )
    out.append(f"  body[:300]={resp.content[:300]!r}")
    out.append("")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    aweme_id, video_id = argv[1], argv[2]
    file_hash = argv[3] if len(argv) > 3 else None

    lines = [f"aweme_id={aweme_id} video_id={video_id} file_hash={file_hash}"]
    cookies: dict[str, str] = {}
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    try:
        from original_parser.guest import get_guest

        cookies, ua = get_guest()
        lines.append(f"guest cookies={sorted(cookies)}")
        lines.append(f"guest ua={ua}")
    except Exception as error:  # noqa: BLE001
        lines.append(f"!! guest failed: {type(error).__name__}: {error}")

    for ratio in ("default", "1080p"):
        probe(f"abogus+{ratio}", build_params(video_id, ratio), cookies, ua, lines)
    if file_hash:
        probe("abogus+default+sign", build_params(video_id, "default", file_hash), cookies, ua, lines)

    text = "\n".join(lines)
    print(text)
    root = Path(__file__).resolve().parent.parent / "output"
    root.mkdir(exist_ok=True)
    (root / f"play-abogus-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
