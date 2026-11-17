"""实验性检查普通详情中的剧集字段结构；不据字段名称认定原画。

用法：python tools/probe_series.py <aweme_id> [credentials.json]
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
        "language": "zh", "region": "CN", "carrier_region": "CN",
        "build_number": "32.2.6", "manifest_version_code": "320206",
    }


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    cookies = json.loads(credentials.read_text(encoding="utf-8")).get("cookies", {})
    url = "https://api.amemv.com/aweme/v1/aweme/detail/?" + urlencode(app_params(aweme_id))
    detail = requests.get(url, headers={"User-Agent": UA_APP, "Accept": "*/*"},
                          cookies=cookies, timeout=25).json()["aweme_detail"]
    lines = [f"aweme_id={aweme_id}"]
    for key in ("series_basic_info", "series_paid_info", "entertainment_product_info",
                "chapter_list", "long_video", "media_type", "aweme_type", "aweme_type_tags",
                "video_labels", "video_tag", "packed_clips"):
        if key in detail:
            value = detail[key]
            if isinstance(value, dict):
                lines.append(f"detail.{key}字段={sorted(value)}")
            elif isinstance(value, list):
                lines.append(f"detail.{key}条数={len(value)}")
            elif isinstance(value, (int, float, bool)) or value is None:
                lines.append(f"detail.{key}={value}")
            else:
                lines.append(f"detail.{key}存在={bool(value)}")
    video = detail.get("video") or {}
    for key in ("meta", "bit_rate_audio", "audio", "format", "ratio", "width", "height"):
        if key in video:
            value = video[key]
            if isinstance(value, dict):
                lines.append(f"video.{key}字段={sorted(value)}")
            elif isinstance(value, list):
                lines.append(f"video.{key}条数={len(value)}")
            elif isinstance(value, (int, float, bool)) or value is None:
                lines.append(f"video.{key}={value}")
            else:
                lines.append(f"video.{key}存在={bool(value)}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"series-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
