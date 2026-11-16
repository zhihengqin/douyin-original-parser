"""打印 video_model 的完整结构（脱敏：只显示键、档位、桶名与尺寸）。"""

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402
from original_parser.codec import decode_url  # noqa: E402

AWEME = sys.argv[1] if len(sys.argv) > 1 else "7707993970332290314"

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(AWEME)
video = detail.get("video") or {}
model = video.get("video_model")
if isinstance(model, str):
    model = json.loads(model)

print("model keys:", sorted(model.keys()))
for key in sorted(model.keys()):
    value = model[key]
    if isinstance(value, (str, int, float, bool)) or value is None:
        shown = value
        if isinstance(value, str) and value.startswith("http"):
            shown = f"<url host={urlsplit(value).netloc}>"
        if isinstance(value, str) and len(value) > 80 and "http" not in value:
            shown = value[:60] + "…"
        print(f"  {key} = {shown}")

rows = model.get("video_list")
print("\nmodel.video_list:", type(rows).__name__)
seed = model.get("key_seed") or (model.get("video_model") or "") if False else ""
rows_list = rows if isinstance(rows, list) else (list(rows.values()) if isinstance(rows, dict) else [])
for index, row in enumerate(rows_list):
    if not isinstance(row, dict):
        print(index, type(row).__name__)
        continue
    keys = {k: v for k, v in row.items()
            if not (isinstance(v, str) and (v.startswith("http") or len(v) > 60))}
    print(f"  [{index}] {json.dumps(keys, ensure_ascii=False)}")
    for addr_key in ("main_url", "backup_url", "backup_url_1"):
        text = row.get(addr_key)
        if isinstance(text, str) and text:
            try:
                decoded = decode_url(text, model.get("key_seed", "") or "")
                q = urlsplit(decoded)
                bucket = next((x for x in q.path.split("/") if x.startswith("tos-cn-")), "-")
                print(f"      {addr_key}: host={q.netloc} bucket={bucket} path={q.path[:70]}")
            except Exception as exc:  # noqa: BLE001
                print(f"      {addr_key}: decode failed {type(exc).__name__}")
