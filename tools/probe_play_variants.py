"""多组对照：/aweme/v1/play/ 的 ratio=default 在什么条件下才落原片。

变量：签名方式（a_bogus / X-Bogus / 无）、msToken、verifyFp/fp、host。
对 HDR 作品与普通作品各跑一遍，用来判断 404 是"签名不足"还是"该作品没有 default 档"。
"""
from __future__ import annotations

import random
import string
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _abogus_ref import ABogus  # noqa: E402
from _xbogus_ref import XBogus  # noqa: E402

HOSTS = ["https://www.douyin.com", "https://www.iesdouyin.com"]
PLAY_PATH = "/aweme/v1/play/"


def rand_ms_token() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(107))


def base_params(video_id: str, ratio: str) -> dict[str, str]:
    return {
        "video_id": video_id,
        "ratio": ratio,
        "line": "0",
        "is_play_url": "1",
        "watermark": "0",
        "source": "PackSourceEnum_PUBLISH",
    }


def run(tag: str, url: str, headers: dict, cookies: dict, out: list[str]) -> None:
    try:
        resp = requests.get(url, headers=headers, cookies=cookies, allow_redirects=True, timeout=25)
    except Exception as error:  # noqa: BLE001
        out.append(f"[{tag}] !! {type(error).__name__}: {error}")
        out.append("")
        return
    out.append(f"[{tag}] status={resp.status_code} ct={resp.headers.get('Content-Type')}")
    out.append(f"  final={resp.url[:220]}")
    out.append(
        "  total={} range={}".format(
            (resp.headers.get("Content-Range") or "").rsplit("/", 1)[-1] or resp.headers.get("Content-Length"),
            resp.headers.get("Content-Range"),
        )
    )
    out.append(f"  body[:120]={resp.content[:120]!r}")
    out.append("")


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    aweme_id, video_id = argv[1], argv[2]
    tag_prefix = argv[3]

    lines = [f"aweme_id={aweme_id} video_id={video_id}"]
    cookies: dict[str, str] = {}
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    try:
        from original_parser.guest import get_guest

        cookies, ua = get_guest()
        lines.append(f"guest cookies={sorted(cookies)}")
    except Exception as error:  # noqa: BLE001
        lines.append(f"!! guest failed: {type(error).__name__}: {error}")

    ms_token = rand_ms_token()
    headers = {
        "User-Agent": ua,
        "Accept": "*/*",
        "Range": "bytes=0-0",
        "Referer": f"https://www.douyin.com/video/{aweme_id}",
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()) + f"; msToken={ms_token}",
    }

    for host in HOSTS:
        # 1) X-Bogus，不带 sign
        params = base_params(video_id, "default")
        query = urlencode(params)
        url = f"{host}{PLAY_PATH}?{query}"
        signed_url, _xb, _ua = XBogus(ua).build(url)
        run(f"{tag_prefix} xbogus {host}", signed_url, headers, {}, lines)

        # 2) X-Bogus + msToken + verifyFp
        params2 = dict(params)
        params2["msToken"] = ms_token
        params2["verifyFp"] = cookies.get("s_v_web_id", "")
        params2["fp"] = cookies.get("s_v_web_id", "")
        url2 = f"{host}{PLAY_PATH}?{urlencode(params2)}"
        signed_url2, _xb2, _ua2 = XBogus(ua).build(url2)
        run(f"{tag_prefix} xbogus+msToken {host}", signed_url2, headers, {}, lines)

        # 3) a_bogus + msToken + verifyFp
        signer = ABogus(user_agent=ua)
        signed_query, _ab, signer_ua, _body = signer.generate_abogus(urlencode(params2), "")
        run(
            f"{tag_prefix} abogus+msToken {host}",
            f"{host}{PLAY_PATH}?{signed_query}",
            {**headers, "User-Agent": signer_ua},
            {},
            lines,
        )

        # 4) a_bogus 裸（无 msToken/verifyFp）
        signed_query4, _ab4, ua4, _ = signer.generate_abogus(urlencode(params), "")
        run(
            f"{tag_prefix} abogus {host}",
            f"{host}{PLAY_PATH}?{signed_query4}",
            {**headers, "User-Agent": ua4},
            {},
            lines,
        )

    text = "\n".join(lines)
    print(text)
    root = Path(__file__).resolve().parent.parent / "output"
    root.mkdir(exist_ok=True)
    (root / f"play-variants-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
