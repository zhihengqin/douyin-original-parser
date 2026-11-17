"""历史实验：比较不同作品的 ratio=default 响应与实际存储桶。

404 不能证明原片未登记，桶名与 HDR 标记不能单独判断原画。

用法：python tools/probe_original_bucket.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PLAY = "https://www.douyin.com/aweme/v1/play/"
CASES = (
    ("7707264789998849307", "v0d00fg10000dbqr10vog65mqlbihb00", "已登记原片（4K 6.9G）"),
    ("7708052871413075238", "v03033g10000dbs82lnog65ls2l3ol5g", "此前默认档请求未成功的短剧"),
)


def main() -> int:
    credentials = ROOT / "credentials.json"
    blob = json.loads(credentials.read_text(encoding="utf-8"))
    cookies, ua = blob.get("cookies"), blob.get("user_agent")
    lines = []
    for aweme_id, vid, note in CASES:
        params = {"video_id": vid, "ratio": "default", "line": "0", "is_play_url": "1",
                  "watermark": "0", "source": "PackSourceEnum_PUBLISH"}
        response = requests.get(PLAY, params=params, allow_redirects=False, timeout=25,
                                headers={"User-Agent": ua, "Referer": "https://www.douyin.com/"},
                                cookies=cookies)
        lines.append(f"\n{aweme_id}（{note}）status={response.status_code}")
        location = response.headers.get("Location")
        if not location:
            lines.append(f"  无跳转，响应正文长度={len(response.content)}")
            continue
        split = urlsplit(location)
        bucket = re.search(r"/video/tos/cn/([^/]+)/([^/]+)/", split.path)
        query = parse_qs(split.query)
        lines.append(f"  host={split.netloc}")
        lines.append(f"  桶={bucket.group(1) if bucket else '?'} 对象键={bucket.group(2) if bucket else '?'}"
                     f"（键长 {len(bucket.group(2)) if bucket else 0}）")
        lines.append(f"  参数 keys={sorted(query)[:10]}")
        probe = requests.get(location, headers={"User-Agent": ua, "Range": "bytes=0-15"},
                             timeout=25)
        total = probe.headers.get("Content-Range", "").split("/")[-1]
        lines.append(f"  实测 status={probe.status_code} total={total} "
                     f"type={probe.headers.get('Content-Type')}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / "original-bucket.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
