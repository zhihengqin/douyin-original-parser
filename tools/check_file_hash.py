"""对比 App 详情自带的 file_hash / file_cs 与已知原片 MD5。

用法：python tools/check_file_hash.py <aweme_id> [credentials.json] [已知MD5...]
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

UA_APP = ("com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN; SM-G988N; "
          "Build/TP1A.220624.014; Cronet/TTNetVersion:4c4dc92c/1.0.9.102)")


def app_params(aweme_id: str) -> dict:
    return {
        "aweme_id": aweme_id, "aid": "1128", "device_platform": "android",
        "version_code": "320206", "version_name": "32.2.6", "os": "android",
        "os_api": "33", "os_version": "13", "device_type": "SM-G988N",
        "device_brand": "samsung", "channel": "googleplay", "app_name": "aweme",
        "device_id": str(random.randint(10 ** 18, 10 ** 19 - 1)),
        "resolution": "1080*1920", "dpi": "480", "ac": "wifi", "ssmix": "a",
        "language": "zh", "region": "CN",
    }


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    known = [item.lower() for item in argv[3:]]
    cookies = json.loads(credentials.read_text(encoding="utf-8")).get("cookies", {})
    url = "https://api.amemv.com/aweme/v1/aweme/detail/?" + urlencode(app_params(aweme_id))
    detail = requests.get(url, headers={"User-Agent": UA_APP, "Accept": "*/*"},
                          cookies=cookies, timeout=25).json()["aweme_detail"]
    video = detail.get("video") or {}
    lines = [f"aweme_id={aweme_id} 已知 MD5={known or '未提供'}"]
    rows = [("play_addr", video.get("play_addr")), ("play_addr_265", video.get("play_addr_265")),
            ("play_addr_h264", video.get("play_addr_h264")),
            ("play_addr_lowbr", video.get("play_addr_lowbr")),
            ("download_addr", video.get("download_addr"))]
    for label, addr in rows:
        if not isinstance(addr, dict):
            continue
        lines.append(f"{label}: size={addr.get('data_size')} wh={addr.get('width')}x{addr.get('height')} "
                     f"file_hash={addr.get('file_hash')} file_cs={addr.get('file_cs')} uri={addr.get('uri')}")
    for row in (video.get("bit_rate") or []):
        addr = row.get("play_addr") or {}
        lines.append(f"gear={row.get('gear_name')} size={addr.get('data_size')} "
                     f"file_hash={addr.get('file_hash')} file_cs={addr.get('file_cs')} "
                     f"url_key={str(addr.get('url_key'))[:60]}")
    for value in (video.get("play_addr") or {},):
        for key in ("url_key",):
            if value.get(key):
                lines.append(f"play_addr.{key}={value[key]}")
    hits = [line for line in lines if any(md5 in line.lower() for md5 in known)]
    lines.append("命中已知 MD5 的字段：" + ("无" if not hits else str(hits)))
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"file-hash-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
