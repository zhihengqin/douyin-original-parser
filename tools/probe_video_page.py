"""探针：用无头浏览器打开作品页，录制网页端自己发起的官方请求与返回的媒体地址。

只读：不登录、不改本地浏览器资料；只看这条作品页面自己请求了什么、返回里有没有原片桶。
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

A = sys.argv[1] if len(sys.argv) > 1 else "7707993970332290314"
URL = f"https://www.douyin.com/video/{A}"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from original_parser.guest import USER_AGENT  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

seen = []
interesting = []


def on_response(response):
    url = response.url
    if "tos-cn" in url:
        bucket = next((x for x in urlsplit(url).path.split("/") if x.startswith("tos-cn-")), "-")
        if url not in [s for s, _ in seen]:
            seen.append((url, bucket, response.status))
    if "/aweme/" in url or "/video/" in url:
        if "/aweme/" in url:
            interesting.append((url, response.status))


with sync_playwright() as playwright:
    shared = Path(__file__).resolve().parent.parent / ".browsers"
    browser = playwright.chromium.launch(headless=True, channel="chromium", timeout=25000)
    try:
        context = browser.new_context(user_agent=USER_AGENT, locale="zh-CN",
                                      timezone_id="Asia/Shanghai")
        page = context.new_page()
        page.on("response", on_response)
        try:
            page.goto(URL, wait_until="commit", timeout=30000)
        except Exception as exc:  # noqa: BLE001
            print("goto:", type(exc).__name__, str(exc)[:80])
        page.wait_for_timeout(15000)
        # 让播放器真正发起取流
        try:
            page.evaluate("() => { const v = document.querySelector('video');"
                          " if (v) { v.muted = true; v.play().catch(() => {}); } }")
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(12000)
        print("title:", (page.title() or "")[:60])
        print("video tags:", page.evaluate("() => document.querySelectorAll('video').length"))
        print("video srcs:", page.evaluate(
            "() => Array.from(document.querySelectorAll('video')).map(v => (v.currentSrc || v.src || '').slice(0, 200))"))
        html = page.content()
        print("html length:", len(html))
        print("page 内 tos-cn-v- 命中:", len(re.findall(r"tos-cn-v-", html)))
        print("page 内 tos-cn 桶名:", sorted(set(re.findall(r"tos-cn-[a-z0-9-]+", html)))[:6])
        print("\n=== 页面请求到的 tos-cn 地址 ===")
        for url, bucket, status in seen[:20]:
            print(f"{status} {bucket:22} {url[:110]}")
        print("\n=== /aweme/ 接口 ===")
        for url, status in interesting[:20]:
            print(f"{status} {url[:150]}")
    finally:
        browser.close()
