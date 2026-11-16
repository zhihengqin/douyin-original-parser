"""读取任意公网 MP4 的 moov（Range 方式，不下载整个文件）。"""

import sys
from urllib.parse import urlsplit

import requests

sys.path.insert(0, ".")
from original_parser.media import inspect_mp4  # noqa: E402

URL = sys.argv[1]
SIZE = int(sys.argv[2]) if len(sys.argv) > 2 else None

session = requests.Session()
session.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

if SIZE is None:
    head = session.get(URL, headers={"Range": "bytes=0-0"}, timeout=20)
    size_line = head.headers.get("Content-Range", "")
    SIZE = int(size_line.split("/")[-1])
print("total_size", SIZE, "host", urlsplit(URL).netloc)


def read_at(offset: int, count: int) -> bytes:
    response = session.get(URL, headers={"Range": f"bytes={offset}-{offset + count - 1}",
                                         "Accept-Encoding": "identity"}, timeout=30)
    response.raise_for_status()
    return response.content


info = inspect_mp4(read_at, SIZE)
print("duration_seconds", round(info["duration_seconds"] or 0, 3))
for track in info["tracks"]:
    print("  track", track)
print("has_video", info["has_video"], "has_audio", info["has_audio"])
