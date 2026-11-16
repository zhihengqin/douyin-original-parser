"""探针：看详情里 video.token_auth 的结构（VOD 播放授权签发 query）。"""

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

A = "7707993970332290314"

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
    token = (detail.get("video") or {}).get("token_auth") or {}
    print("token_auth keys:", sorted(token))
    for key, value in token.items():
        if isinstance(value, str) and len(value) > 8:
            print(f"  {key}: len={len(value)} head={value[:60]}")
            if "=" in value and "&" in value:
                query = parse_qs(urlsplit(value).query or value, keep_blank_values=True)
                print("     as-query keys:", sorted(query))
        else:
            print(f"  {key}: {value!r}")
    Path("output/token.txt").write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")
