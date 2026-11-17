"""用不同抖音系客户端身份（aid/app_name）取详情，比较 token_auth 是否出现。

用法：python tools/probe_client_aids.py <aweme_id> [credentials.json]
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CLIENTS = (
    ("1128", "aweme", "320206", "32.2.6", "android",
     "com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN; SM-G988N; "
     "Build/TP1A.220624.014; Cronet/TTNetVersion:4c4dc92c/1.0.9.102)"),
    ("2329", "aweme_lite", "320206", "32.2.6", "android",
     "com.ss.android.ugc.aweme.lite/320206 (Linux; U; Android 13; zh_CN; SM-G988N; "
     "Build/TP1A.220624.014; Cronet/TTNetVersion:4c4dc92c/1.0.9.102)"),
    ("1112", "musical_ly", "110000", "11.0.0", "android",
     "com.ss.android.ugc.live/110000 (Linux; U; Android 13; zh_CN; SM-G988N; "
     "Build/TP1A.220624.014; Cronet/TTNetVersion:4c4dc92c/1.0.9.102)"),
    ("6383", "aweme", "320206", "32.2.6", "android",
     "com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN; SM-G988N; "
     "Build/TP1A.220624.014; Cronet/TTNetVersion:4c4dc92c/1.0.9.102)"),
)


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    cookies = json.loads(credentials.read_text(encoding="utf-8")).get("cookies", {})
    lines = []
    for aid, app_name, version_code, version_name, platform, ua in CLIENTS:
        params = {
            "aweme_id": aweme_id, "aid": aid, "device_platform": platform,
            "version_code": version_code, "version_name": version_name, "os": "android",
            "os_api": "33", "os_version": "13", "device_type": "SM-G988N",
            "device_brand": "samsung", "channel": "googleplay", "app_name": app_name,
            "device_id": str(random.randint(10 ** 18, 10 ** 19 - 1)),
            "resolution": "1080*1920", "dpi": "480", "ac": "wifi", "ssmix": "a",
            "language": "zh", "region": "CN",
        }
        url = "https://api.amemv.com/aweme/v1/aweme/detail/?" + urlencode(params)
        response = requests.get(url, headers={"User-Agent": ua, "Accept": "*/*"},
                                cookies=cookies, timeout=20)
        try:
            blob = response.json()
        except ValueError:
            lines.append(f"aid={aid} app={app_name} status={response.status_code} 非 JSON")
            continue
        detail = blob.get("aweme_detail") or {}
        video = detail.get("video") or {}
        token_auth = video.get("token_auth") or {}
        lines.append(
            f"aid={aid} app={app_name} status={response.status_code} 长度={len(response.text)} "
            f"detail={'有' if detail else '无'} need_set_token={video.get('need_set_token')} "
            f"token_auth 字段={sorted(token_auth) if isinstance(token_auth, dict) else token_auth} "
            f"video keys={sorted(video) if video else []}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"client-aids-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
