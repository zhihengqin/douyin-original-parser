"""实验性读取详情明确下发的完整 VOD URL，输出脱敏错误结构。

play_auth_token 若只有查询串而没有官方主机，不猜测主机或拼造授权请求。
本工具不保存原始错误正文，也不据授权字段认定原画。

用法：python tools/probe_vod_error.py <aweme_id> [credentials.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

UA_APP = ("com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN; SM-G988N; "
          "Build/TP1A.220624.014; Cronet/TTNetVersion:4c4dc92c/1.0.9.102)")


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    cookies = json.loads(credentials.read_text(encoding="utf-8")).get("cookies", {})
    from original_parser.client import OriginalParser, ParseError, check_url

    with OriginalParser(cookies=cookies, auto_guest=False) as parser:
        detail = parser.detail(aweme_id)
    video = detail.get("video") or {}
    token = video.get("play_auth_token")
    if not isinstance(token, str) or not token:
        print("web 详情无 play_auth_token")
        return 3
    split = urlsplit(token)
    lines = [f"aweme_id={aweme_id}", "play_auth_token 存在=True"]
    try:
        url = check_url(token, ("bytedanceapi.com", "douyin.com", "volcengineapi.com", "snssdk.com"))
    except ParseError:
        lines.append("缺少可直接请求的完整官方 URL；未组合主机、路径或授权")
        exit_code = 3
    else:
        query = parse_qs(split.query, keep_blank_values=True)
        lines.append(f"token 参数名={sorted(query)}")
        try:
            response = requests.get(url, headers={"User-Agent": UA_APP, "Accept": "*/*"},
                                    timeout=20, allow_redirects=False)
            lines.append(f"host={split.hostname} status={response.status_code} 响应字节数={len(response.content)}")
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                lines.append(f"响应字段={sorted(payload)}")
                meta = payload.get("ResponseMetadata")
                error = meta.get("Error") if isinstance(meta, dict) else None
                lines.append(f"错误字段={sorted(error) if isinstance(error, dict) else []}")
            else:
                lines.append("没有 JSON 对象响应")
            exit_code = 0
        except requests.RequestException as error:
            lines.append(f"请求失败 {type(error).__name__}")
            exit_code = 2
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"vod-error-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
