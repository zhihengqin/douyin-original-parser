"""探针：解析分享短链，看落地页里有没有播放结构（含原片桶）。"""

import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SHORT = sys.argv[1] if len(sys.argv) > 1 else "https://v.douyin.com/9odWMuc0J9Q/"

UAS = [
    ("iphone-safari", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                      "Mobile/15E148 Safari/604.1"),
    ("aweme-android", "com.ss.android.ugc.aweme/410000 (Linux; U; Android 13; zh_CN; SM-G981B)"),
    ("windows-chrome", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"),
]

for label, ua in UAS:
    session = requests.Session()
    session.headers.update({"User-Agent": ua, "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        response = session.get(SHORT, timeout=20, allow_redirects=True)
    except requests.RequestException as exc:
        print(label, "ERR", type(exc).__name__)
        continue
    text = response.text
    buckets = sorted(set(re.findall(r"tos-cn-[a-z0-9-]+", text)))
    print(label, response.status_code, "len=" + str(len(text)))
    print("   final:", response.url[:150])
    print("   buckets:", buckets[:6])
    print("   router_data:", "_ROUTER_DATA" in text, "play_addr:", text.count("play_addr"),
          "mp4 refs:", len(re.findall(r"\.mp4", text)))
    Path("output/sharepage-%s.html" % label).write_text(text, encoding="utf-8")
