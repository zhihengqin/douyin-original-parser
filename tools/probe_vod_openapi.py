"""探针：按 APK 里的模板调用视频云 openapi GetPlayInfo。

模板来自 classes30.dex：
    %s/video/openapi/v1/?action=GetPlayInfo&video_id=%s&ptoken=%s&aid=%s%s
只使用详情里原样下发的 play_auth_token 作为 ptoken，不伪造签名字段。
"""

import json
import sys
from pathlib import Path
from urllib.parse import quote, urlencode

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser  # noqa: E402

A = "7707993970332290314"
HOSTS = ("https://vod.bytedanceapi.com", "https://vod-urls.bytedanceapi.com",
         "https://api-play.amemv.com", "https://vod-luna.douyin.com")
UA = "com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN)"

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(A)
video = detail.get("video") or {}
vid = (video.get("play_addr") or {}).get("uri")
token = (video.get("token_auth") or {}).get("play_auth_token") or ""

print("VID:", vid)

for host in HOSTS:
    for label, ptoken in (("token", token), ("empty", "")):
        query = {"action": "GetPlayInfo", "video_id": vid, "ptoken": ptoken, "aid": "392139"}
        url = f"{host}/video/openapi/v1/?" + urlencode(query)
        try:
            response = requests.get(url, timeout=20,
                                    headers={"Accept-Encoding": "identity", "User-Agent": UA})
            text = response.text.replace("\n", " ")
            print(f"{host.split('//')[1][:24]:26} ptoken={label:5} {response.status_code} {text[:220]}")
            if "PlayInfoList" in text or "mime_type" in text:
                Path(f"output/vodplay-{label}.txt").write_text(text, encoding="utf-8")
                print("    ★ 含播放信息，已存文件")
        except requests.RequestException as exc:
            print(f"{host} ptoken={label} ERR {type(exc).__name__}")

# 附加参数轮换：模板尾部还有一个 %s
extras = {"format": "&format_type=mp4&codec_type=0&stream_type=video", "none": ""}
for label, extra in extras.items():
    url = ("https://vod.bytedanceapi.com/video/openapi/v1/?action=GetPlayInfo"
           f"&video_id={vid}&ptoken={quote(token)}&aid=392139{extra}")
    try:
        response = requests.get(url, timeout=20,
                                headers={"Accept-Encoding": "identity", "User-Agent": UA})
        print(f"extra={label:6} {response.status_code} {response.text[:200]}")
    except requests.RequestException as exc:
        print(f"extra={label} ERR {type(exc).__name__}")
