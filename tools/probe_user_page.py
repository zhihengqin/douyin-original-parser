"""从作者主页 HTML 里扒作品 ID，用于检查同系列作品的官方档位。

用法：python tools/probe_user_page.py <sec_uid> [credentials.json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv: list[str]) -> int:
    sec_uid = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    blob = json.loads(credentials.read_text(encoding="utf-8"))
    cookies, ua = blob.get("cookies"), blob.get("user_agent")
    url = f"https://www.douyin.com/user/{sec_uid}"
    response = requests.get(url, headers={"User-Agent": ua, "Referer": "https://www.douyin.com/"},
                            cookies=cookies, timeout=25)
    ids = re.findall(r'"aweme_id":"(\d{15,20})"', response.text)
    uniq = list(dict.fromkeys(ids))
    lines = [f"sec_uid={sec_uid} status={response.status_code} 长度={len(response.text)}",
             f"作品 ID {len(uniq)} 个：{uniq[:20]}"]
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / "user-page.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
