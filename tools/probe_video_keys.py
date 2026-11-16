"""探针：列出详情 video 的全部字段，重点看 hdr/source/origin 相关键。"""

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

A = sys.argv[1] if len(sys.argv) > 1 else "7708052871413075238"

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
video = detail.get("video") or {}
print("work:", A)
print("video keys:", sorted(video))
for key in sorted(video):
    if any(word in key.lower() for word in ("hdr", "source", "origin", "raw", "master", "dash")):
        value = video[key]
        text = json.dumps(value, ensure_ascii=False)
        print(f"\n[{key}] = {text[:300]}")
for key, value in video.items():
    if isinstance(value, dict) and value.get("url_list"):
        host_bucket = next((seg for seg in urlsplit(value["url_list"][0]).path.split("/")
                            if seg.startswith("tos-cn-")), "-")
        print(f"{key:20} bucket={host_bucket} size={value.get('data_size')}")
