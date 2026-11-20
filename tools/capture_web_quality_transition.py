"""Capture desktop-Web requests around natural playback and quality selection.

The report stores route metadata and small JSON field summaries only. It never
stores cookies, full URLs, query values, request bodies, or response bodies.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, urlsplit

from playwright.async_api import Error, async_playwright


ROOT = Path(__file__).resolve().parents[1]
WORKS = ("7708052871413075238", "7707954213745085746")
QUALITY_CHOICES = ("control", "高清 720P", "标清 540P")
JSON_LIMIT = 4 * 1024 * 1024


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def sha256(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()


def route_path(path: str) -> str:
    path = re.sub(r"/video/tos/[^/?]+", "/video/tos/:object", path)
    path = re.sub(r"(?<![A-Za-z0-9])[0-9a-fA-F]{24,}(?![A-Za-z0-9])", ":hex", path)
    path = re.sub(r"(?<![A-Za-z0-9])[0-9]{10,}(?![A-Za-z0-9])", ":id", path)
    return path[:512]


def url_summary(url: str) -> dict:
    parts = urlsplit(url)
    query_keys = sorted({key[:80] for key, _ in parse_qsl(parts.query, keep_blank_values=True)})
    path_digest = None
    if "/video/tos/" in parts.path:
        path_digest = sha256(parts.path)[:24]
    return {"host": (parts.hostname or "").lower(), "path": route_path(parts.path),
            "query_keys": query_keys[:120], "media_path_sha256": path_digest}


def visible_texts(values: list[str]) -> list[str]:
    return sorted({re.sub(r"\s+", " ", value).strip()[:120]
                   for value in values if value and value.strip()})[:80]


def quality_rows(detail: dict) -> list[dict]:
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    rows = []
    for row in video.get("bit_rate") or []:
        if not isinstance(row, dict):
            continue
        address = row.get("play_addr") if isinstance(row.get("play_addr"), dict) else {}
        rows.append({"gear_name": str(row.get("gear_name") or "")[:60],
                     "quality_type": row.get("quality_type"),
                     "bit_rate": safe_int(row.get("bit_rate")),
                     "size": safe_int(address.get("data_size")),
                     "width": safe_int(address.get("width")),
                     "height": safe_int(address.get("height")),
                     "file_hash": (address.get("file_hash")
                                   if isinstance(address.get("file_hash"), str)
                                   and re.fullmatch(r"[0-9a-fA-F]{32}", address.get("file_hash"))
                                   else None)})
    return rows[:100]


def safe_int(value):
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if abs(result) < 10**16 else None


def json_summary(payload: object, work: str) -> dict:
    result = {"root_type": type(payload).__name__}
    if not isinstance(payload, dict):
        return result
    result["root_keys"] = sorted(str(key)[:80] for key in payload)[:120]
    result["mentions_work"] = work in json.dumps(payload, ensure_ascii=True)
    detail = payload.get("aweme_detail")
    if isinstance(detail, dict):
        result["detail_work_matches"] = str(detail.get("aweme_id") or "") == work
        result["detail_status_code"] = safe_int(payload.get("status_code"))
        result["detail_quality_rows"] = quality_rows(detail)
        video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
        model = video.get("video_model")
        if isinstance(model, str):
            try:
                model = json.loads(model)
            except (ValueError, RecursionError):
                model = None
        result["detail_model_present"] = isinstance(model, dict) and bool(model)
        result["detail_fallback_present"] = bool(
            model.get("fallback_api") if isinstance(model, dict) else False)
    info = payload.get("video_info")
    data = info.get("data") if isinstance(info, dict) else None
    if isinstance(data, dict):
        rows = data.get("video_list")
        rows = list(rows.values()) if isinstance(rows, dict) else rows
        result["catalog"] = {"code": safe_int(payload.get("code")),
                             "status": safe_int(data.get("status")),
                             "row_count": len(rows) if isinstance(rows, list) else 0,
                             "rows": quality_rows({"video": {"bit_rate": rows}})
                             if isinstance(rows, list) else []}
    return result


async def page_state(page, label: str) -> dict:
    values = await page.evaluate("""label => ({
        label,
        videos: [...document.querySelectorAll('video')].map(video => ({
            width: video.videoWidth, height: video.videoHeight,
            paused: video.paused, current_time: Math.round(video.currentTime),
            ready_state: video.readyState
        })),
        visible_text: [...document.querySelectorAll('xg-icon,[role=menu],button,[role=button]')]
          .filter(element => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden'
              && style.display !== 'none';
          }).map(element => (element.innerText || element.getAttribute('aria-label')
            || element.getAttribute('title') || '').trim()).filter(Boolean)
    })""", label)
    values["visible_text"] = visible_texts(values.get("visible_text") or [])
    return values


async def dismiss_visible_promo(page) -> bool:
    # Some panel roots have no bounds, but their visible close button does.
    panel = page.locator('[id^="login-full-panel"], #douyin_login_comp_flat_panel_header')
    for close in (panel.get_by_role("button", name=re.compile(r"^(关闭|关闭登录弹窗|close)$", re.I)),
                  panel.locator('button[title="关闭"], [role="button"][title="关闭"]'),
                  panel.locator(".YoNA2Hyj:has(svg)")):
        visible = close.filter(visible=True)
        if await visible.count():
            await visible.first.click(timeout=2000)
            return True
    return False


async def select_visible_quality(page, choice, report, mark_phase, elapsed_ms):
    actions = report["ui_actions"]
    video = page.locator("video:visible").first
    control = page.locator("xg-icon.xgplayer-playclarity-setting:visible").first

    async def perform(name, locator, operation, **fields):
        action = {"action": name, **fields, "started_ms": elapsed_ms(), "performed": False}
        actions.append(action)
        try:
            if not await locator.count():
                action["reason"] = "visible_element_missing"
                return False
            await operation(timeout=3000)
            action["performed"] = True
        except Error as error:
            action["error_type"] = type(error).__name__
        finally:
            action["time_ms"] = elapsed_ms()
        return action["performed"]

    mark_phase("hover_visible_video")
    if not await perform("hover_visible_video", video, video.hover):
        return
    mark_phase("hover_quality_control")
    if not await perform("hover_quality_control", control, control.hover):
        return
    await page.wait_for_timeout(1000)
    # Exclude the current-value button: it repeats the selected menu item.
    labels = control.get_by_text(re.compile(r"^(高清 720P|标清 540P|智能)$")).and_(
        control.locator(":not(.gear .btn, .gear .btn *)")).filter(visible=True)
    report["quality_menu"] = visible_texts(await labels.all_inner_texts())
    if report["quality_menu"]:
        mark_phase("quality_menu_open")
        report["states"].append(await page_state(page, "quality_menu_open"))
    target = control.get_by_text(choice, exact=True).and_(labels).first
    mark_phase("quality_click_" + ("720p" if choice == "高清 720P" else "540p"))
    if not await perform("click_quality", target, target.click, label=choice):
        return
    mark_phase("after_quality_click")
    await page.wait_for_timeout(10000)
    # Leave the menu and reveal the toolbar so its current value can be read.
    await perform("reveal_selected_quality", video, video.hover)
    buttons = control.locator(".gear .btn:visible")
    texts = visible_texts(await buttons.all_inner_texts())
    displayed = texts[0] if len(texts) == 1 else None
    sizes = await page.locator("video:visible").evaluate_all(
        "(videos) => videos.map(v => ({width: v.videoWidth, height: v.videoHeight}))")
    report["quality_readback"] = {"time_ms": elapsed_ms(), "requested": choice,
                                  "displayed": displayed,
                                  "selection_matches": displayed == choice if displayed else None,
                                  "visible_video_sizes": sizes}


async def capture_one(browser, work: str, choice: str, settle_ms: int) -> dict:
    context = await browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai",
                                        viewport={"width": 1440, "height": 960})
    page = await context.new_page()
    phase = {"name": "navigation"}
    phase_changes = [{"phase": "navigation", "time_ms": 0}]
    records = []
    entries_by_request = {}
    response_objects = []
    started = time.perf_counter()

    def elapsed_ms() -> float:
        return round((time.perf_counter() - started) * 1000, 2)

    def mark_phase(name: str) -> None:
        phase["name"] = name
        phase_changes.append({"phase": name, "time_ms": elapsed_ms()})

    def on_request(request):
        kind = request.resource_type
        if kind not in {"document", "xhr", "fetch", "media", "websocket"}:
            return
        entry = {"index": len(records), "phase_started": phase["name"],
                 "request_ms": elapsed_ms(), "method": request.method,
                 "resource_type": kind, "url": url_summary(request.url),
                 "has_post_data": request.post_data is not None,
                 "redirected_from": bool(request.redirected_from)}
        records.append(entry)
        # Parallel requests can have identical redacted URLs.
        entries_by_request[request] = entry

    def on_response(response):
        request = response.request
        entry = entries_by_request.get(request)
        if entry is None:
            return
        headers = response.headers
        entry.update({"phase_response": phase["name"], "response_ms": elapsed_ms(),
                      "status": response.status,
                      "mime_type": headers.get("content-type", "").split(";", 1)[0][:100],
                      "content_length": safe_int(headers.get("content-length")),
                      "content_range": re.sub(r"/\d+", "/:total", headers.get("content-range", ""))[:100],
                      "cache_control": headers.get("cache-control", "")[:120]})
        response_objects.append((entry, response))

    def on_finished(request):
        entry = entries_by_request.get(request)
        if entry is not None:
            entry["finished_ms"] = elapsed_ms()

    def on_failed(request):
        entry = entries_by_request.get(request)
        if entry is not None:
            entry["failure"] = (request.failure or "failed")[:120]
            entry["phase_failed"] = phase["name"]
            entry["failed_ms"] = elapsed_ms()

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("requestfinished", on_finished)
    page.on("requestfailed", on_failed)
    report = {"work": work, "action": choice, "started_at": stamp(),
              "logged_in_state": False, "network": [], "states": [], "quality_menu": [],
              "ui_actions": []}
    try:
        response = await page.goto("https://www.douyin.com/video/" + work,
                                   wait_until="commit", timeout=30000)
        report["document_status"] = response.status if response else None
        await page.wait_for_timeout(settle_ms)
        report["page_title_is_verification"] = "验证" in await page.title()
        report["on_requested_work_path"] = urlsplit(page.url).path.rstrip("/") == "/video/" + work
        promo_present = await page.get_by_text("登录后免费畅享高清视频", exact=True).count() > 0
        report["login_promo_present"] = promo_present
        if choice != "control":
            mark_phase("dismiss_visible_promo")
            try:
                report["ui_actions"].append({"action": "dismiss_visible_promo",
                                             "performed": await dismiss_visible_promo(page)})
            except Error as error:
                report["ui_actions"].append({"action": "dismiss_visible_promo",
                                             "performed": False,
                                             "error_type": type(error).__name__})
        report["states"].append(await page_state(page, "natural_playback"))
        if choice == "control":
            mark_phase("natural_playback_control")
            await page.wait_for_timeout(9000)
        else:
            await select_visible_quality(page, choice, report, mark_phase, elapsed_ms)
            report["states"].append(await page_state(page, "after_quality_action"))
        await page.wait_for_timeout(1000)
    except Error as error:
        report["browser_error_type"] = type(error).__name__
    finally:
        mark_phase("response_body_summary")
        body_candidates = []
        for entry, response in response_objects:
            mime = entry.get("mime_type", "").lower()
            host = (entry.get("url") or {}).get("host", "")
            body_phase = entry.get("phase_started") or ""
            route = (entry.get("url") or {}).get("path", "")
            api_host = host == "douyin.com" or host.endswith(".douyin.com") \
                or host == "snssdk.com" or host.endswith(".snssdk.com")
            selected_phase = ("quality_menu" in body_phase or "quality_click" in body_phase
                              or body_phase == "after_quality_click")
            if ("finished_ms" not in entry or not api_host
                    or not ("xhr" == entry.get("resource_type")
                                     or "fetch" == entry.get("resource_type"))
                    or "json" not in mime
                    or (entry.get("content_length") or 0) > JSON_LIMIT
                    or not (selected_phase or "/aweme/detail" in route
                            or "/video/fplay/" in route)):
                continue
            body_candidates.append((entry, response))
        body_candidates.sort(key=lambda pair: (
            not ("quality_click" in (pair[0].get("phase_started") or "")
                 or pair[0].get("phase_started") == "after_quality_click"),
            pair[0].get("request_ms", 0)))
        for entry, response in body_candidates[:24]:
            try:
                body = await asyncio.wait_for(response.body(), timeout=2.5)
                if len(body) > JSON_LIMIT:
                    entry["json_body"] = {"readable": False, "reason": "over_size_limit"}
                    continue
                entry["response_bytes"] = len(body)
                entry["response_sha256"] = sha256(body)
                payload = json.loads(body.decode("utf-8", "replace"))
                entry["json_body"] = json_summary(payload, work)
            except (Error, ValueError, RecursionError, asyncio.TimeoutError):
                entry["json_body"] = {"readable": False}
        report["network"] = records
        report["phase_changes"] = phase_changes
        report["ended_at"] = stamp()
        await context.close()
    return report


async def run(output: Path, settle_ms: int):
    if output.exists():
        raise SystemExit("输出文件已存在，请指定新路径")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(timeout=20000)
        rows = []
        try:
            for work in WORKS:
                # Fresh contexts keep each control and click run independent.
                choices = ("control", "高清 720P", "标清 540P")
                for choice in choices:
                    row = await capture_one(browser, work, choice, settle_ms)
                    rows.append(row)
                    counts = Counter(item.get("phase_started") for item in row["network"])
                    route_delta = sorted({item["url"]["path"] for item in row["network"]
                                          if item.get("phase_started") in {
                                              "hover_quality_control", "quality_menu_open",
                                              "quality_click_720p", "quality_click_540p",
                                              "after_quality_click"}})
                    last_state = row["states"][-1] if row["states"] else {}
                    print(work, choice, row.get("document_status"), last_state.get("videos"),
                          dict(counts), route_delta[:16], flush=True)
        finally:
            await browser.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {"created_at": stamp(),
              "scope": "anonymous desktop Web page; natural playback, hover, and visible quality selection",
              "works": list(WORKS), "cookies_or_raw_urls_saved": False,
              "capture_fields": "request/response route summaries, query names, status, MIME, phase, small JSON key and media-row summaries",
              "observations": rows}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    print("Saved sanitized capture:", output.resolve(), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settle-ms", type=int, default=18000,
                        help="natural playback time after navigation (8000-45000 ms)")
    args = parser.parse_args()
    if not 8000 <= args.settle_ms <= 45000:
        parser.error("--settle-ms must be between 8000 and 45000")
    asyncio.run(run(args.output, args.settle_ms))


if __name__ == "__main__":
    main()
