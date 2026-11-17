"""尝试从 TOS 对象键推导 play 接口的 file_id，并用任意合法 sign 试探。

用法：python tools/probe_file_id_derive.py <aweme_id> <对象键> <原片字节数> [credentials.json]
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PLAY_URL = "https://www.douyin.com/aweme/v1/play/"
UA_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/139.0.0.0 Safari/537.36")


def candidates(key: str, vid: str) -> dict[str, str]:
    made: dict[str, str] = {}

    def md5(text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    made["md5(对象键)"] = md5(key)
    made["md5(对象键大写)"] = md5(key.upper())
    made["md5(vid+对象键)"] = md5(vid + key)
    made["md5(对象键+vid)"] = md5(key + vid)
    made["md5(桶+对象键)"] = md5("tos-cn-v-0051" + key)
    made["对象键原样"] = key
    padded = key + "=" * (-len(key) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded)
        made["键base64解码前32位字节作hex"] = binascii.hexlify(raw[:16]).decode()
        made["键base64解码后16字节作hex"] = binascii.hexlify(raw[-16:]).decode()
    except (binascii.Error, ValueError):
        pass
    return made


def probe(url: str, cookies: dict) -> tuple[int, str, int]:
    try:
        response = requests.get(url, headers={"User-Agent": UA_WEB, "Range": "bytes=0-15",
                                             "Referer": "https://www.douyin.com/"},
                                cookies=cookies, timeout=20, allow_redirects=True)
        total = 0
        ranged = response.headers.get("Content-Range", "")
        if "/" in ranged:
            try:
                total = int(ranged.split("/")[-1])
            except ValueError:
                total = 0
        return response.status_code, response.headers.get("Content-Type", ""), total
    except requests.RequestException as error:
        return 0, type(error).__name__, 0


def main(argv: list[str]) -> int:
    aweme_id, key, expected = argv[1], argv[2], int(argv[3])
    credentials = Path(argv[4]) if len(argv) > 4 else ROOT / "credentials.json"
    cookies = json.loads(credentials.read_text(encoding="utf-8")).get("cookies", {})
    from original_parser.client import OriginalParser

    with OriginalParser(cookies=cookies, auto_guest=False) as parser:
        detail = parser.detail(aweme_id)
    vid = (detail.get("video") or {}).get("play_addr", {}).get("uri")
    lines = [f"aweme_id={aweme_id} vid={vid} 期望原片={expected} 对象键={key}"]
    signs = {"sign=全0(32位)": "0" * 32}
    for derivation, value in candidates(key, vid).items():
        for sign_label, sign in signs.items():
            url = (f"{PLAY_URL}?video_id={vid}&ratio=default&line=0"
                   f"&sign={sign}&file_id={value}")
            status, content_type, total = probe(url, cookies)
            hit = "  <<< 命中期望长度" if total == expected else ""
            lines.append(f"file_id={derivation} -> {value} {sign_label} "
                         f"status={status} type={content_type} 总长={total}{hit}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"file-id-derive-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
