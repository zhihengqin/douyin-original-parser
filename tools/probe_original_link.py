"""探针：核验一条外部原片直链，并用它的整文件 MD5 去打官方重签接口。

参数：<直链> [作品 ID]
"""

import base64
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402
from original_parser.media import inspect_mp4  # noqa: E402

URL = sys.argv[1]
A = sys.argv[2] if len(sys.argv) > 2 else "7708052871413075238"

session = requests.Session()
session.headers.update({"Accept-Encoding": "identity",
                        "User-Agent": "com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN)"})

with session.get(URL, headers={"Range": "bytes=0-15"}, timeout=25, allow_redirects=True,
                 stream=True) as response:
    match = re.fullmatch(r"bytes 0-15/(\d+)", response.headers.get("Content-Range", ""))
    print("status:", response.status_code, "| Content-Range:", response.headers.get("Content-Range"))
    total = int(match.group(1)) if match else None
    first = response.raw.read(16, decode_content=True)
    print("total:", total, "| ftyp:", first[4:8] == b"ftyp", "| first16:", first[:16])
    content_md5 = response.headers.get("Content-MD5")
    print("Content-MD5 header:", content_md5)
    final = response.url
md5_hex = None
if content_md5:
    md5_hex = base64.b64decode(content_md5).hex()
    print("object md5:", md5_hex)


def read_at(offset, count):
    with session.get(final, headers={"Range": f"bytes={offset}-{offset + count - 1}"}, timeout=25,
                     stream=True) as r:
        expected = f"bytes {offset}-{offset + count - 1}/{total}"
        if r.status_code != 206 or r.headers.get("Content-Range") != expected:
            raise RuntimeError(f"range 不一致：{r.status_code} {r.headers.get('Content-Range')}")
        return r.raw.read(count, decode_content=True)


media = inspect_mp4(read_at, total)
print("duration:", media["duration_seconds"], "| has_video:", media["has_video"], "| has_audio:", media["has_audio"])
for track in media["tracks"]:
    print("  track:", track)

if total:
    print(f"estimate bitrate: {total * 8 / media['duration_seconds'] / 1000:.0f} kbps")

# 用对象 MD5 打官方重签
with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
video = detail.get("video") or {}
vid = (video.get("play_addr") or {}).get("uri")
print("\nwork VID:", vid, "| detail duration_ms:", video.get("duration"))

if md5_hex and vid:
    for host in ("https://api-play.amemv.com", "https://api.amemv.com"):
        url = f"{host}/aweme/v1/play/?video_id={vid}&file_id={vid}&sign={md5_hex}&is_play_url=1&source=PackSourceEnum_AWEME_DETAIL"
        try:
            response = session.get(url, timeout=25, allow_redirects=False, headers={"Range": "bytes=0-15"})
            print(f"{host.split('//')[1]:22} {response.status_code} -> {response.headers.get('Location', '')[:110]}")
            if response.status_code in (200, 206):
                print("   ★ 官方认可该对象，可直接分发")
        except requests.RequestException as exc:
            print(host, "ERR", type(exc).__name__)
