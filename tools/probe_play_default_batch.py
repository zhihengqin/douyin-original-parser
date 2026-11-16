"""批量验证 `/aweme/v1/play/?ratio=default`（无 sign）在已有记录上的命中率。

对 original_metadata.json 里每条记录：用其 video_id 发一次探测，
把返回的 total 与记录里的 size 比较，输出"命中/未命中"对照表。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _abogus_ref import ABogus  # noqa: E402

PLAY_URL = "https://www.douyin.com/aweme/v1/play/"
ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    records = json.loads((ROOT / "original_metadata.json").read_text(encoding="utf-8"))["records"]
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

    lines = ["aweme_id            record_size     total       status  match"]
    for record in records:
        aweme_id = str(record.get("aweme_id"))
        video_id = str(record.get("video_id"))
        expect = int(record.get("size") or 0)
        params = {
            "video_id": video_id,
            "ratio": "default",
            "line": "0",
            "is_play_url": "1",
            "watermark": "0",
            "source": "PackSourceEnum_PUBLISH",
        }
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
            lines.append(f"{aweme_id} {expect:>12} {'ERR':>10}  {type(error).__name__}")
            continue
        total_raw = (resp.headers.get("Content-Range") or "").rsplit("/", 1)[-1] or "0"
        try:
            total = int(total_raw)
        except ValueError:
            total = 0
        match = "YES" if total == expect and expect else ("no" if resp.status_code == 404 else f"size!={expect}")
        lines.append(f"{aweme_id} {expect:>12} {total:>10}  {resp.status_code:>6}  {match}")

    text = "\n".join(lines)
    print(text)
    (ROOT / "output" / "play-default-batch.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
