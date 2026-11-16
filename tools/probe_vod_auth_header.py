"""历史实验：把详情里的 AWS4 查询字段重排成 Authorization 后发送请求。

这不是已经确认的播放协议。2026-11-16 按实际方法核对发现，原先引用的
AWS4 字符串属于上传 SDK，带空格的头字段属于 QoS；version 2 播放器明确
传入空 auth。详见 docs/original-investigation-2026-11-16-auth-consumer-audit.md。
保留本脚本用于解释历史失败请求，不能据此推断缺少 native 签名算法。
"""

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

A = "7707993970332290314"
UA = "com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN)"
HOSTS = ("https://vod.bytedanceapi.com", "https://api-play.amemv.com")

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
video = detail.get("video") or {}
vid = (video.get("play_addr") or {}).get("uri")
token = (video.get("token_auth") or {}).get("play_auth_token") or ""
fields = {key: values[0] for key, values in parse_qs(token, keep_blank_values=True).items()}
print("VID:", vid)
print("token fields:", sorted(fields))

credential = fields.get("X-Amz-Credential", "")
signature = fields.get("X-Amz-Signature", "")
signed_headers = fields.get("X-Amz-SignedHeaders", "")
signed_queries = fields.get("X-Amz-SignedQueries", "")

auth_variants = {
    "aws4-empty-headers": f"AWS4-HMAC-SHA256 Credential={credential}, SignedHeaders={signed_headers}, Signature={signature}",
    "aws4-host": f"AWS4-HMAC-SHA256 Credential={credential}, SignedHeaders=host, Signature={signature}",
    "raw-token": token,
}

for host in HOSTS:
    base = {"action": "GetPlayInfo", "video_id": vid, "ptoken": token, "aid": "392139"}
    url = f"{host}/video/openapi/v1/?" + urlencode(base)
    for label, value in auth_variants.items():
        try:
            response = requests.get(url, timeout=20, headers={
                "Accept-Encoding": "identity", "User-Agent": UA, "Authorization": value})
            text = response.text.replace("\n", " ")
            print(f"{host.split('//')[1][:22]:24} {label:20} {response.status_code} {text[:200]}")
            if "PlayInfoList" in text or "mime_type" in text:
                Path(f"output/vodauth-{label}.txt").write_text(text, encoding="utf-8")
                print("    ★ 含播放信息")
        except requests.RequestException as exc:
            print(f"{host} {label} ERR {type(exc).__name__}")

# 变体：把 token 的查询和 openapi 查询合并后走根路径，Authorization 只放签名
for host in HOSTS:
    merged = dict(fields)
    merged.update({"action": "GetPlayInfo", "video_id": vid, "ptoken": token, "aid": "392139"})
    url = f"{host}/video/openapi/v1/?" + urlencode(merged)
    try:
        response = requests.get(url, timeout=20, headers={
            "Accept-Encoding": "identity", "User-Agent": UA,
            "Authorization": f"AWS4-HMAC-SHA256 Credential={credential}, SignedHeaders={signed_headers}, Signature={signature}"})
        print(f"{host.split('//')[1][:22]:24} merged              {response.status_code} {response.text[:180]}")
    except requests.RequestException as exc:
        print(f"{host} merged ERR {type(exc).__name__}")

Path("output/vod-token-fields.json").write_text(json.dumps(fields, indent=2), encoding="utf-8")
