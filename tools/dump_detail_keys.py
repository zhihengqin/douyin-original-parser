"""打印作品详情的一级键与嵌套结构里出现的域名，找原片/西瓜线索。"""

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

AWEME = sys.argv[1] if len(sys.argv) > 1 else "7707993970332290314"


def walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")
    else:
        yield path, node


with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(AWEME)

print("top-level keys:", sorted(detail.keys()))
hosts = {}
urls = []
for path, value in walk(detail):
    if isinstance(value, str) and "http" in value and ("://" in value):
        q = urlsplit(value)
        bucket = next((x for x in q.path.split("/") if x.startswith("tos-cn-")), "-")
        hosts[(q.netloc, bucket)] = hosts.get((q.netloc, bucket), 0) + 1
        urls.append((path, q.netloc, bucket))

print("\nurl hosts:")
for (host, bucket), count in sorted(hosts.items(), key=lambda kv: -kv[1]):
    print(f"  {host} {bucket} x{count}")

print("\n非媒体线索字段:")
for path, value in walk(detail):
    if any(tag in path.lower() for tag in ("long_video", "xigua", "item_id", "origin",
                                           "source", "forward", "mix", "series", "chapter")):
        if isinstance(value, (str, int, float, bool)) and not (isinstance(value, str) and len(value) > 120):
            print(f"  {path} = {value}")
