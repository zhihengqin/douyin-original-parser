"""探针：用详情自带的 play_auth_token 调 VOD GetPlayInfo，确定资源标识怎么带。

只用链接详情里原样下发的签发 query，不改任何签名字段；
资源标识分别尝试 query 参数、POST JSON body 两种位置。
"""

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

A = "7707993970332290314"
HOSTS = ("https://vod.bytedanceapi.com/", "https://vod-luna.douyin.com/")
UA = "com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN)"


def show(label, response):
    text = response.text.replace("\n", " ")[:300]
    print(f"{label:34} {response.status_code} {text}")


with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
    token = (detail.get("video") or {}).get("token_auth", {}).get("play_auth_token")
    vid = (detail.get("video") or {}).get("play_addr", {}).get("uri")
if not token or not vid:
    print("detail 不含 play_auth_token 或 VID")
    raise SystemExit(1)
print("VID:", vid)
Path("output/vod-token.txt").write_text(token, encoding="utf-8")

bodies = [("body Vid", {"Vid": vid}), ("body Vids", {"Vids": [vid]}),
          ("body vid", {"vid": vid}), ("body empty", {})]

for host in HOSTS:
    for label, body in bodies:
        try:
            response = requests.post(host + "?" + token, json=body, timeout=15,
                                     headers={"Accept-Encoding": "identity", "User-Agent": UA})
            show(f"{host.split('//')[1][:16]} {label}", response)
        except requests.RequestException as exc:
            print(f"{host} {label} ERR {type(exc).__name__}")

# 对照：把资源放在 query 里再 POST
try:
    response = requests.post(HOSTS[0] + "?" + token + "&Vid=" + vid, timeout=15,
                             headers={"Accept-Encoding": "identity", "User-Agent": UA})
    show("query Vid + POST", response)
except requests.RequestException as exc:
    print("query Vid ERR", type(exc).__name__)
