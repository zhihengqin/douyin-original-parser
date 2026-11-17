"""检查同一作者其它作品在官方 fplay 里是否下发原片档，判断是不是逐条策略。

用法：python tools/probe_series_originals.py <aweme_id> [credentials.json]
"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from original_parser.client import OriginalParser, signed_headers, signed_query  # noqa: E402

POST_URL = "https://www.douyin.com/aweme/v1/web/aweme/post/"


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    blob = json.loads(credentials.read_text(encoding="utf-8"))
    cookies, ua = blob.get("cookies"), blob.get("user_agent")
    lines = [f"aweme_id={aweme_id}"]
    with OriginalParser(cookies=cookies, user_agent=ua, auto_guest=False) as parser:
        detail = parser.detail(aweme_id)
        author = detail.get("author") or {}
        sec_uid = author.get("sec_uid")
        lines.append(f"author={author.get('nickname')} sec_uid={sec_uid}")
        params = {
            "device_platform": "webapp", "aid": "6383", "channel": "channel_pc_web",
            "sec_user_id": sec_uid, "max_cursor": "0", "count": "20",
            "publish_video_strategy_type": "2", "version_code": "170400",
            "version_name": "17.4.0", "cookie_enabled": "true", "platform": "PC",
            "browser_language": "zh-CN", "browser_platform": "Win32",
            "browser_name": "Chrome", "browser_version": "139.0.0.0",
            "screen_width": "1920", "screen_height": "1080", "downlink": "10",
        }
        query = signed_query(params, cookies)
        if not query:
            lines.append("无法签名（缺 uifid）")
        else:
            response = requests.get(f"{POST_URL}?{query}",
                                    headers={"User-Agent": ua, **signed_headers(query),
                                             "Referer": "https://www.douyin.com/"},
                                    cookies=cookies, timeout=25)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            items = payload.get("aweme_list") or []
            if not items:
                lines.append(f"x-secsdk 签名 status={response.status_code} 作品数=0，改用 a_bogus")
                ab_query = parser._a_bogus_query(params)
                response = requests.get(f"{POST_URL}?{ab_query}",
                                        headers={"User-Agent": ua,
                                                 "Referer": "https://www.douyin.com/"},
                                        cookies=cookies, timeout=25)
                try:
                    payload = response.json()
                except ValueError:
                    lines.append(f"a_bogus 签名后仍非 JSON，长度={len(response.text)}")
                    payload = {}
                items = payload.get("aweme_list") or []
                lines.append(f"a_bogus status={response.status_code} 作品数={len(items)} "
                             f"status_code={payload.get('status_code')}")
            lines.append(f"最终作品数={len(items)}")
            for item in items:
                if not isinstance(item, dict):
                    continue
                video = item.get("video") or {}
                vid = (video.get("play_addr") or {}).get("uri")
                model = video.get("video_model")
                model = json.loads(model) if isinstance(model, str) else model
                fallback = (model or {}).get("fallback_api")
                url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
                gears = []
                origin = "无 video_model"
                if isinstance(url, str):
                    parts = urlsplit(url)
                    base = {k: v for k, v in parse_qs(parts.query, keep_blank_values=True).items()
                            if k != "logo_type"}
                    base["force_fids"] = [base64.b64encode(b"original").decode("ascii")]
                    request_url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                              urlencode(base, doseq=True), ""))
                    try:
                        payload2 = parser._json(request_url, stage="档位")
                        rows = ((payload2.get("video_info") or {}).get("data") or {}).get("video_list") or []
                        if isinstance(rows, dict):
                            rows = list(rows.values())
                        gears = [row for row in rows if isinstance(row, dict)]
                        has_original = any(str(row.get("quality")).lower() in ("original", "source")
                                           for row in gears)
                        origin = "有原片档" if has_original else "无原片档"
                    except Exception as error:  # noqa: BLE001
                        origin = f"档位失败 {type(error).__name__}"
                    time.sleep(0.4)
                top = max((int(row.get("size") or 0) for row in gears), default=0)
                lines.append(f"  {item.get('aweme_id')} vid={vid} HDR={video.get('is_source_HDR')} "
                             f"档位={len(gears)} 最大={top} {origin}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"series-originals-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
