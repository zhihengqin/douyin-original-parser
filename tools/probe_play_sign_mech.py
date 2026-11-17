"""对照 /aweme/v1/play 的 sign 参数：使用当前官方档位的 file_id/file_hash。

用法：python tools/probe_play_sign_mech.py <aweme_id> [credentials.json] [--reference-md5 MD5]
参考 MD5 仅在显式提供时使用，结果不代表仅凭链接首次发现原片。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from original_parser.client import OriginalParser  # noqa: E402

PLAY_URL = "https://www.douyin.com/aweme/v1/play/"
UA_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/139.0.0.0 Safari/537.36")


def head(url: str, cookies: dict) -> tuple[int, str, int]:
    try:
        response = requests.get(url, headers={"User-Agent": UA_WEB,
                                             "Range": "bytes=0-15",
                                             "Referer": "https://www.douyin.com/"},
                                cookies=cookies, timeout=20, allow_redirects=True)
        total = ""
        match = response.headers.get("Content-Range", "")
        if "/" in match:
            total = match.split("/")[-1]
        return response.status_code, response.headers.get("Content-Type", ""), total or 0
    except requests.RequestException as error:
        return 0, type(error).__name__, 0


def main(argv: list[str]) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("aweme_id")
    cli.add_argument("credentials", nargs="?", type=Path, default=ROOT / "credentials.json")
    cli.add_argument("--reference-md5", help="该作品已有参考文件的 MD5")
    args = cli.parse_args(argv[1:])
    if args.reference_md5 and not re.fullmatch(r"[a-fA-F0-9]{32}", args.reference_md5):
        cli.error("--reference-md5 必须是 32 位十六进制 MD5")
    aweme_id = args.aweme_id
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    cookies, user_agent = credentials.get("cookies", {}), credentials.get("user_agent")
    lines = [f"aweme_id={aweme_id}"]
    with OriginalParser(cookies=cookies, user_agent=user_agent, auto_guest=False) as parser:
        detail = parser.detail(aweme_id)
        video = detail.get("video") or {}
        vid = (video.get("play_addr") or {}).get("uri")
        model = video.get("video_model")
        model = json.loads(model) if isinstance(model, str) else model
        if not isinstance(model, dict):
            print("本次详情未下发视频模型，未发起分发请求")
            return 2
        fallback = model.get("fallback_api")
        url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
        if not isinstance(url, str) or not url:
            print("本次模型未下发 fallback_api，未发起分发请求")
            return 2
        gears = parser._json(url, stage="档位")
        data = (gears.get("video_info") or {}).get("data") or {}
        if data.get("video_id") != vid or data.get("status") != 10:
            print("档位响应身份或状态不匹配，未发起分发请求")
            return 2
        rows = [row for row in parser._video_rows(data) if row.get("file_id") and
                re.fullmatch(r"[a-fA-F0-9]{32}", str(row.get("file_hash") or ""))]
    if not rows:
        print("没有下发完整文件身份，未发起分发请求")
        return 2
    biggest = max(rows, key=lambda row: int(row.get("size") or 0))
    lines.append(f"vid={vid} 最大档 size={biggest.get('size')} quality={biggest.get('quality')} "
                 f"file_id={biggest.get('file_id')} file_hash={biggest.get('file_hash')}")
    cases = {
        "最大档 sign=该档MD5 file_id=该档file_id ratio=normal":
            f"{PLAY_URL}?video_id={vid}&ratio=normal&line=0&sign={biggest.get('file_hash')}"
            f"&file_id={biggest.get('file_id')}",
        "最大档 ratio=default + 同 sign/file_id":
            f"{PLAY_URL}?video_id={vid}&ratio=default&line=0&sign={biggest.get('file_hash')}"
            f"&file_id={biggest.get('file_id')}",
        "无 sign 裸 ratio=normal":
            f"{PLAY_URL}?video_id={vid}&ratio=normal&line=0",
    }
    if args.reference_md5:
        cases["显式参考 MD5 + 该档 file_id ratio=default"] = PLAY_URL + "?" + urlencode({
            "video_id": vid, "ratio": "default", "line": "0",
            "sign": args.reference_md5.lower(), "file_id": biggest["file_id"],
        })
    for label, target in cases.items():
        status, content_type, total = head(target, cookies)
        lines.append(f"[{label}] status={status} type={content_type} 总长={total}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"play-sign-mech-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
