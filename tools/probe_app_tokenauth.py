"""实验性检查 App 详情授权字段及明确下发的完整 VOD URL，不认定原画。

目的：确认 App 侧详情是否下发 video.token_auth / video.meta.token_auth（含 vod vid、
token、hosts、version）。Web 侧 play_auth_token 是 video 的独立字段；
若没有完整官方 URL，不猜测 host 或将 token 拼到其他接口。

用法：python tools/probe_app_tokenauth.py <aweme_id> [credentials.json]
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
DETAIL_HOSTS = ("https://api.amemv.com", "https://aweme.snssdk.com",
                "https://api5-normal-c-lf.amemv.com")


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


def summarize(blob: dict) -> list[str]:
    notes = []
    detail = blob.get("aweme_detail")
    if not isinstance(detail, dict):
        notes.append(f"无 aweme_detail（status_code={blob.get('status_code')} "
                     f"有状态消息={bool(blob.get('status_msg'))}）")
        return notes
    video = detail.get("video") or {}
    notes.append(f"video keys={sorted(video)}")
    for key, label in (("token_auth", "video.token_auth"),
                       ("play_auth_token", "video.play_auth_token")):
        value = video.get(key)
        if isinstance(value, dict):
            notes.append(f"{label} 字段={sorted(value)}")
            for field in ("vid", "version", "hosts"):
                if field in value:
                    if field == "hosts":
                        notes.append(f"  {label}.hosts 存在={bool(value[field])}")
                    else:
                        notes.append(f"  {label}.{field}={value[field]}")
            if value.get("token"):
                notes.append(f"  {label}.token 存在=True")
        elif value:
            notes.append(f"{label}={type(value).__name__}")
    meta = video.get("meta")
    if isinstance(meta, dict):
        notes.append(f"video.meta keys={sorted(meta)}")
        if isinstance(meta.get("token_auth"), dict):
            notes.append(f"  meta.token_auth 字段={sorted(meta['token_auth'])}")
    for key in ("play_addr_hdr", "duration", "is_source_HDR", "ratio"):
        if key in video:
            notes.append(f"video.{key}={video[key] if key != 'play_addr_hdr' else '存在'}")
    return notes


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    cookies = {}
    if credentials.is_file():
        cookies = json.loads(credentials.read_text(encoding="utf-8")).get("cookies", {})
    lines = [f"aweme_id={aweme_id} 登录字段={len(cookies)}"]

    for host in DETAIL_HOSTS:
        url = f"{host}/aweme/v1/aweme/detail/?" + urlencode(app_params(aweme_id))
        try:
            response = requests.get(url, headers={"User-Agent": UA_APP, "Accept": "*/*"},
                                    cookies=cookies, timeout=20)
            body = response.text[:2]
            lines.append(f"\n[{host}] status={response.status_code} 长度={len(response.text)} 起始={body}")
            try:
                blob = response.json()
            except ValueError:
                lines.append("  非 JSON")
                continue
            lines.extend("  " + note for note in summarize(blob))
        except requests.RequestException as error:
            lines.append(f"[{host}] !! {type(error).__name__}")

    # 只消费详情明确下发的完整请求，不用候选主机替换授权上下文。
    from original_parser.client import OriginalParser, ParseError, check_url
    with OriginalParser(cookies=cookies, auto_guest=False) as parser:
        detail = parser.detail(aweme_id)
    token = (detail.get("video") or {}).get("play_auth_token")
    if not isinstance(token, str) or not token:
        lines.append("\nweb 详情无 play_auth_token")
    else:
        lines.append("\nweb play_auth_token 存在=True")
        try:
            url = check_url(token, ("bytedanceapi.com", "douyin.com", "volcengineapi.com", "snssdk.com"))
        except ParseError:
            lines.append("缺少可直接请求的完整官方 URL；未组合主机、路径或授权")
        else:
            query = parse_qs(urlsplit(url).query, keep_blank_values=True)
            lines.append(f"play_auth_token 参数名={sorted(query)}")
            try:
                response = requests.get(url, headers={"User-Agent": UA_APP, "Accept": "*/*"},
                                        timeout=20, allow_redirects=False)
                lines.append(f"host={urlsplit(url).hostname} status={response.status_code} "
                             f"响应字节数={len(response.content)}")
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                lines.append(f"响应字段={sorted(payload) if isinstance(payload, dict) else []}")
            except requests.RequestException as error:
                lines.append(f"请求失败 {type(error).__name__}")

    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"app-tokenauth-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
