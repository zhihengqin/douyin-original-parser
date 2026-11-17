"""保存 App 侧详情原始 JSON，并检索是否含西瓜/头条侧关联标识。

用法：python tools/dump_app_raw.py <aweme_id> [credentials.json]
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

UA_APP = ("com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN; SM-G988N; "
          "Build/TP1A.220624.014; Cronet/TTNetVersion:4c4dc92c/1.0.9.102)")
PATTERNS = ("ixigua", "toutiao", "365yg", "xigua", "视频号", "item_id", "vids")


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
    text = requests.get(url, headers={"User-Agent": UA_APP, "Accept": "*/*"},
                        cookies=cookies, timeout=25).text
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"app-detail-raw-{aweme_id}.json").write_text(text, encoding="utf-8")
    lines = [f"aweme_id={aweme_id} 长度={len(text)}"]
    for pattern in PATTERNS:
        hits = [match.start() for match in re.finditer(pattern, text)]
        lines.append(f"{pattern}: {len(hits)} 处")
        for start in hits[:3]:
            lines.append("  …" + text[max(0, start - 90):start + 110].replace("\n", " ") + "…")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
