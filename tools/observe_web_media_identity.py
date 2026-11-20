"""Compare natural Web player media requests with the same session's detail rows."""

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))
DEST = ROOT / "output" / "web-media-identity-20261118"
WORKS = ("7708052871413075238", "7702453019425672467")


def identity(url):
    match = re.search(r"/video/tos/([^/]+)/([^/]+)/([^/?]+)", urlsplit(url).path)
    if not match:
        return None
    value = "/".join(match.groups())
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def detail_rows(data, work_id):
    items = data.get("aweme_details") or ([data["aweme_detail"]] if data.get("aweme_detail") else [])
    output = []
    for item in items:
        if str(item.get("aweme_id")) != work_id:
            continue
        for index, row in enumerate((item.get("video") or {}).get("bit_rate") or []):
            addr = row.get("play_addr") or {}
            output.append({
                "index": index,
                "gear_name": row.get("gear_name"),
                "quality_type": row.get("quality_type"),
                "bit_rate": row.get("bit_rate"),
                "data_size": addr.get("data_size"),
                "identities": sorted({value for u in addr.get("url_list") or [] if (value := identity(u))}),
            })
    return output


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for work_id in WORKS:
            context = browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai", viewport={"width": 1440, "height": 900})
            page = context.new_page()
            report = {"work_id": work_id, "details": [], "media": [], "states": [], "errors": []}
            stage = ["navigation"]

            def response_handler(response):
                path = urlsplit(response.url).path
                if "/video/tos/" in path:
                    report["media"].append({"stage": stage[0], "identity": identity(response.url),
                                            "status": response.status,
                                            "content_range": response.headers.get("content-range")})
                elif "aweme/detail/" in path:
                    try:
                        data = response.json()
                        report["details"].append({"stage": stage[0], "status": response.status,
                                                  "business_status": data.get("status_code"),
                                                  "rows": detail_rows(data, work_id)})
                    except Exception as error:
                        report["errors"].append("detail:" + type(error).__name__)

            def state(label):
                report["states"].append(page.evaluate("""label => ({stage: label,
                    videos: [...document.querySelectorAll('video')].map(v => ({width: v.videoWidth,
                    height: v.videoHeight, paused: v.paused, time: Math.round(v.currentTime)}))})""", label))

            page.on("response", response_handler)
            try:
                page.goto("https://www.douyin.com/video/" + work_id, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(20000)
                if page.get_by_text("登录后免费畅享高清视频", exact=True).count():
                    page.mouse.click(1042, 249)
                    page.wait_for_timeout(1000)
                stage[0] = "play"
                page.mouse.move(900, 625)
                page.wait_for_timeout(5000)
                state("before_quality")
                stage[0] = "quality"
                controls = page.locator("xg-icon").filter(has_text="智能")
                for i in range(controls.count()):
                    if controls.nth(i).is_visible():
                        controls.nth(i).hover(timeout=3000)
                        break
                page.wait_for_timeout(1000)
                option = page.get_by_text("高清 720P", exact=True)
                if option.count() and option.first.is_visible():
                    option.first.click(timeout=3000)
                    report["clicked"] = "高清 720P"
                    page.wait_for_timeout(8000)
                else:
                    report["errors"].append("720p_option_not_visible")
                state("after_quality")
            except Exception as error:
                report["errors"].append("page:" + type(error).__name__)
            finally:
                (DEST / (work_id + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                context.close()
        browser.close()


if __name__ == "__main__":
    main()
