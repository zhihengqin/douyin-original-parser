"""探针：官方下载类接口（对象级直读地址），看是否返回原片对象。"""

import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, ParseError  # noqa: E402

A = "7707993970332290314"
VID = "v28033gi0000dbs4nevog65jrl6u1s10"
TARGET = 38562411

CANDIDATES = [
    ("douyin download", "https://www.douyin.com/aweme/v1/aweme/download/",
     {"item_ids": A, "aid": "1128"}),
    ("amemv download", "https://api.amemv.com/aweme/v1/aweme/download/",
     {"item_ids": A, "aid": "1128"}),
    ("douyin web download", "https://www.douyin.com/aweme/v1/web/aweme/download/",
     {"aweme_id": A, "aid": "6383"}),
    ("iesdouyin iteminfo v2", "https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/",
     {"item_ids": A}),
    ("play ratio original", "https://api-play.amemv.com/aweme/v1/play/",
     {"video_id": VID, "ratio": "original", "line": "0"}),
    ("play ratio 1080p", "https://api.amemv.com/aweme/v1/play/",
     {"video_id": VID, "ratio": "1080p", "line": "0"}),
]

with OriginalParser(auto_guest=True) as parser:
    for label, base, params in CANDIDATES:
        url = base + "?" + urlencode(params)
        try:
            with parser._get(url, headers={"Accept-Encoding": "identity"}) as response:
                final = response.url
                body = response.text[:400]
                size = response.headers.get("Content-Range") or response.headers.get("Content-Length")
                print(f"{label:22} HTTP {response.status_code} len={size} final={final[:70]}")
                print(f"                       body={body.replace(chr(10), ' ')[:300]}")
                if str(TARGET) in final or str(TARGET) in body:
                    print("                       ★ 命中原片大小 38562411")
        except ParseError as exc:
            print(f"{label:22} {exc.code}: {str(exc)[:60]}")
        except Exception as exc:  # noqa: BLE001
            print(f"{label:22} ERR {type(exc).__name__} {str(exc)[:60]}")
