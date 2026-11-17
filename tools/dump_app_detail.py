"""实验性检查 App 视频字段和档位；仅输出结构，不据字段名称认定原画。

用法：python tools/dump_app_detail.py <aweme_id> [credentials.json]
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

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
    response = requests.get(url, headers={"User-Agent": UA_APP, "Accept": "*/*"},
                            cookies=cookies, timeout=25)
    blob = response.json()
    detail = blob["aweme_detail"]
    video = detail.get("video") or {}
    lines = [f"aweme_id={aweme_id} status={response.status_code}"]
    lines.append(f"video.need_set_token={video.get('need_set_token')}")
    for key in ("play_addr_lowbr", "download_addr", "play_addr", "play_addr_265", "play_addr_h264"):
        addr = video.get(key)
        if isinstance(addr, dict):
            lines.append(f"video.{key}: uri={addr.get('uri')} size={addr.get('data_size')} "
                         f"wh={addr.get('width')}x{addr.get('height')} keys={sorted(addr)}")
    meta = video.get("meta")
    if isinstance(meta, dict):
        lines.append(f"video.meta keys={sorted(meta)}")
    model = video.get("video_model")
    if isinstance(model, str):
        try:
            model = json.loads(model)
        except ValueError:
            pass
    if isinstance(model, dict):
        lines.append(f"video_model keys={sorted(model)}")
        for key in ("video_id", "fallback_api", "gear_name", "meta", "duration"):
            if key in model:
                value = model[key]
                if key in ("fallback_api", "meta"):
                    lines.append(f"  model.{key}存在={bool(value)} 类型={type(value).__name__}")
                else:
                    lines.append(f"  model.{key}={value}")
    rows = video.get("bit_rate")
    if isinstance(rows, list):
        lines.append(f"bit_rate 档位 {len(rows)} 个：")
        for row in rows:
            if not isinstance(row, dict):
                continue
            addr = row.get("play_addr") or {}
            lines.append(
                f"  gear={row.get('gear_name')} quality={row.get('quality_type')}/{(row.get('quality') or '')} "
                f"size={addr.get('data_size')} wh={addr.get('width')}x{addr.get('height')} "
                f"uri={addr.get('uri')} hdr={row.get('is_hdr')} keys={sorted(row)}")
    lines.append(f"detail keys={sorted(detail)}")
    for key in ("xigua_base_info", "xigua_task", "original", "video_control",
                "without_watermark", "prevent_download", "media_type", "packed_clips",
                "main_arch_common", "video_tag"):
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
    for row in (video.get("bit_rate") or []):
        if isinstance(row, dict) and (row.get("HDR_bit") or row.get("HDR_type")):
            lines.append(f"HDR 标记行 gear={row.get('gear_name')} HDR_bit={row.get('HDR_bit')} "
                         f"HDR_type={row.get('HDR_type')} 有video_extra={bool(row.get('video_extra'))}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"app-detail-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
