"""验证 /aweme/v1/play/ 的 sign 参数语义：是"原片 MD5 指纹"还是"任意占位串"。

对 HDR 作品（其原片 140,778,272 字节）逐组替换 sign/file_id，看总长度是否变化：
  - sign=<真 MD5> + file_id      （已知可行，基线）
  - sign=<随机 32 位 hex> + file_id
  - sign=<随机 32 位 hex>（无 file_id）
  - sign=<真 MD5>（无 file_id）
  - 无 sign / 无 file_id（对照组，已知 404）
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _abogus_ref import ABogus  # noqa: E402

PLAY_URL = "https://www.douyin.com/aweme/v1/play/"


def probe(tag: str, params: dict[str, str], cookies: dict[str, str], ua: str, out: list[str]) -> None:
    signer = ABogus(user_agent=ua)
    signed_query, _ab, signer_ua, _ = signer.generate_abogus(urlencode(params), "")
    try:
        resp = requests.get(
            f"{PLAY_URL}?{signed_query}",
            headers={
                "User-Agent": signer_ua,
                "Accept": "*/*",
                "Range": "bytes=0-0",
                "Referer": "https://www.douyin.com/",
                "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
            },
            allow_redirects=True,
            timeout=25,
        )
    except Exception as error:  # noqa: BLE001
        out.append(f"[{tag}] !! {type(error).__name__}: {error}")
        out.append("")
        return
    total = (resp.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
    out.append(f"[{tag}] status={resp.status_code} ct={resp.headers.get('Content-Type')} total={total}")
    out.append(f"  final={resp.url[:180]}")
    out.append("")


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    aweme_id, video_id, real_md5 = argv[1], argv[2], argv[3]
    fake = secrets.token_hex(16)

    lines = [f"aweme_id={aweme_id} video_id={video_id} real_md5={real_md5} fake={fake}"]
    cookies: dict[str, str] = {}
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    try:
        from original_parser.guest import get_guest

        cookies, ua = get_guest()
    except Exception as error:  # noqa: BLE001
        lines.append(f"!! guest failed: {type(error).__name__}: {error}")

    def params(**extra: str) -> dict[str, str]:
        base = {
            "video_id": video_id,
            "ratio": "default",
            "line": "0",
            "is_play_url": "1",
            "watermark": "0",
            "source": "PackSourceEnum_PUBLISH",
        }
        base.update(extra)
        return base

    cases = [
        ("sign=real+file_id", params(sign=real_md5, file_id=video_id)),
        ("sign=fake+file_id", params(sign=fake, file_id=video_id)),
        ("sign=fake only", params(sign=fake)),
        ("sign=real only", params(sign=real_md5)),
        ("file_id only", params(file_id=video_id)),
        ("bare", params()),
    ]
    for tag, p in cases:
        probe(tag, p, cookies, ua, lines)

    text = "\n".join(lines)
    print(text)
    root = Path(__file__).resolve().parent.parent / "output"
    root.mkdir(exist_ok=True)
    (root / f"play-sign-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
