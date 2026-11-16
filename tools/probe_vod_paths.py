"""探针：openapi 路径与 query 的组合（路径是否参与签名、资源从哪来）。"""

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

A = sys.argv[1] if len(sys.argv) > 1 else "7708052871413075238"
UA = "com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN)"

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
video = detail.get("video") or {}
vid = (video.get("play_addr") or {}).get("uri")
token = (video.get("token_auth") or {}).get("play_auth_token") or ""
print("work:", A, "VID:", vid)

variants = [
    ("path-openapi + token query", "/video/openapi/v1/", ""),
    ("path-openapi/<vid> + token", f"/video/openapi/v1/{vid}", ""),
    ("path / + token + Vid", "/", "&Vid=" + vid),
    ("path-openapi + token + Vid", "/video/openapi/v1/", "&Vid=" + vid),
]

for host in ("https://vod.bytedanceapi.com", "https://api-play.amemv.com"):
    for label, path, extra in variants:
        url = f"{host}{path}?{token}{extra}"
        try:
            response = requests.get(url, timeout=20, headers={
                "Accept-Encoding": "identity", "User-Agent": UA})
            text = response.text.replace("\n", " ")
            print(f"{host.split('//')[1][:22]:24} {label:30} {response.status_code} {text[:190]}")
            if "PlayInfoList" in text or "mime_type" in text:
                Path("output/vod-path-hit.txt").write_text(text, encoding="utf-8")
                print("    ★ 命中")
        except requests.RequestException as exc:
            print(f"{host} {label} ERR {type(exc).__name__}")
