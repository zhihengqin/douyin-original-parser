"""实验性检查详情 play 链接的参数名称和实际大小；不据大小认定原画。

用法：python tools/probe_official_play_urls.py <aweme_id> [credentials.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from original_parser.client import OriginalParser  # noqa: E402


def head(url: str, ua: str, cookies: dict) -> str:
    try:
        response = requests.get(url, headers={"User-Agent": ua, "Range": "bytes=0-15",
                                             "Referer": "https://www.douyin.com/"},
                                cookies=cookies, timeout=25, allow_redirects=True)
        ranged = response.headers.get("Content-Range", "")
        final = urlsplit(response.url)
        marker = "/video/tos/cn/"
        object_path = final.path.split(marker, 1)[1] if marker in final.path else "未识别稳定对象"
        return (f"status={response.status_code} type={response.headers.get('Content-Type')} "
                f"total={ranged.split('/')[-1] if '/' in ranged else 0} "
                f"final_host={final.hostname} object={object_path}")
    except requests.RequestException as error:
        return f"!! {type(error).__name__}"


def main(argv: list[str]) -> int:
    aweme_id = argv[1]
    credentials = Path(argv[2]) if len(argv) > 2 else ROOT / "credentials.json"
    blob = json.loads(credentials.read_text(encoding="utf-8"))
    cookies = blob.get("cookies") or {}
    ua = blob.get("user_agent") or ""
    lines = [f"aweme_id={aweme_id}"]
    with OriginalParser(cookies=cookies, user_agent=ua, auto_guest=False) as parser:
        detail = parser.detail(aweme_id)
    video = detail.get("video") or {}
    for label in ("play_addr", "play_addr_265", "download_addr"):
        addr = video.get(label)
        if not isinstance(addr, dict):
            continue
        lines.append(f"\n=== {label} size={addr.get('data_size')} "
                     f"file_hash={addr.get('file_hash')} wh={addr.get('width')}x{addr.get('height')} ===")
        for url in (addr.get("url_list") or []):
            split = urlsplit(url)
            if split.netloc.startswith("api"):
                query = parse_qs(split.query)
                lines.append(f"  play 链接参数名: {sorted(query)}")
            else:
                query = parse_qs(split.query)
                marker = "/video/tos/cn/"
                object_path = split.path.split(marker, 1)[1] if marker in split.path else "未识别稳定对象"
                lines.append(f"  CDN host={split.hostname} object={object_path} "
                             f"参数名={sorted(query)}")
            lines.append(f"  实测: {head(url, ua, cookies)}")
    # 用官方 sign/file_id 改 ratio 再试
    lines.append("\n=== 用官方 sign+file_id 改 ratio ===")
    sign_url = None
    for url in ((video.get("download_addr") or {}).get("url_list") or []):
        if "aweme/v1/play" in url:
            sign_url = url
            break
    if sign_url:
        split = urlsplit(sign_url)
        base = parse_qs(split.query)
        for ratio in ("default", "origin", "2160p", "1440p", "1080p", "720p", "source", "hd"):
            params = {k: list(v) for k, v in base.items()}
            params["ratio"] = [ratio]
            target = urlunsplit((split.scheme, split.netloc, split.path,
                                 urlencode(params, doseq=True), ""))
            lines.append(f"  ratio={ratio}: {head(target, ua, cookies)}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / f"official-play-urls-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
