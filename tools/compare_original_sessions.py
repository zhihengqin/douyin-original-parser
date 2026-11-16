"""Compare official original discovery before and after a manual browser login.

Run from the repository root. Browser credentials remain in memory; only
allowlisted metadata is written. This diagnostic never reads/writes the
original catalog and does not change the production parser's behavior.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from original_parser import browser_detail
from original_parser.client import MAX_JSON_BYTES, OriginalParser, ParseError
from original_parser.guest import UIFID_NAMES

CONTROL = "7695305664234589459"
TARGETS = ("7707196543073275177", "7704677676878925119")
SESSION_COOKIES = {"sessionid", "sessionid_ss", "sid_tt"}
QUALITY_NAMES = {"original", "source", "normal", "low", "lower", "lowest", "adapt",
                 "adapt_low", "adapt_lower", "adapt_lowest", "high", "highest"}


def run_detail_fetch(page, work):
    """Use the production page request, adding only fixed diagnostic fields."""
    from playwright.sync_api import TimeoutError as BrowserTimeout

    marker = "result.detail = data?.aweme_detail;"
    if browser_detail.PAGE_FETCH.count(marker) != 1:
        raise RuntimeError("page_fetch_diagnostic_marker_changed")
    script = browser_detail.PAGE_FETCH.replace(marker, marker + """
                result.server_status = Number.isInteger(data?.status_code) ? data.status_code : null;
                result.filter_reason = data?.filter_detail?.filter_reason === 'series_control_filter'
                    ? 'series_control_filter' : data?.filter_detail?.filter_reason ? 'other_filter' : null;
    """)
    key = "__sessionComparison_" + uuid.uuid4().hex
    page.evaluate(script, {"awemeId": work, "maxBytes": MAX_JSON_BYTES,
                           "timeoutMs": 20000, "jobKey": key})
    try:
        handle = page.wait_for_function(
            "key => {const job = window[key]; return job?.done ? job.result : false;}",
            arg=key, timeout=25000, polling=100)
    except BrowserTimeout:
        return {"error": "page_request_wait_timeout"}
    try:
        return handle.json_value()
    finally:
        handle.dispose()


def safe_id(value):
    text = str(value or "")
    return text if re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", text) else None


def safe_number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) < 10**15 else None


def media_identity(row):
    """Never copy URLs, arbitrary strings, keys or tokens into the report."""
    quality = row.get("quality", row.get("official_quality"))
    digest = str(row.get("file_hash") or "")
    return {"quality": quality if quality in QUALITY_NAMES else "unknown",
            "file_id": safe_id(row.get("file_id")),
            "file_hash": digest.lower() if re.fullmatch(r"[a-fA-F0-9]{32}", digest) else None,
            "size": safe_number(row.get("size")),
            "width": safe_number(row.get("vwidth", row.get("width"))),
            "height": safe_number(row.get("vheight", row.get("height")))}


class DiagnosticParser(OriginalParser):
    def __init__(self, **kwargs):
        super().__init__(auto_guest=False, **kwargs)
        self.directories = []

    def _catalog_original_candidate(self, detail, video_id):
        return None

    def _source_candidates(self, payload, video_id):
        info = payload.get("video_info") or {}
        data = info.get("data") or {}
        rows = data.get("video_list") or []
        rows = list(rows.values()) if isinstance(rows, dict) else rows
        self.directories.append({
            "selector": "original" if not self.directories else "source",
            "code": safe_number(payload.get("code")),
            "info_code": safe_number(info.get("code")),
            "status": safe_number(data.get("status")),
            "video_id": safe_id(data.get("video_id")),
            "rows": [media_identity(row) for row in rows[:100] if isinstance(row, dict)]
                    if isinstance(rows, list) else [],
        })
        return super()._source_candidates(payload, video_id)


def analyze_detail(work, detail, cookies, user_agent, *, on_verified=None):
    result = {"work": work, "detail_matches": False, "original_verified": False,
              "availability": "inconclusive"}
    if not isinstance(detail, dict) or str(detail.get("aweme_id")) != work:
        result["error_code"] = "detail_unavailable"
        return result
    video = detail.get("video") or {}
    result.update(detail_matches=True,
                  video_id=safe_id((video.get("play_addr") or {}).get("uri")),
                  video_model_present=bool(video.get("video_model")))
    with DiagnosticParser(cookies=cookies, user_agent=user_agent) as parser:
        try:
            _, candidates = parser.source_streams(detail)
            result["original_candidates"] = len(candidates)
            failures = []
            for candidate in candidates:
                try:
                    probe = parser.probe(candidate)
                except ParseError as error:
                    failures.append(safe_id(error.code))
                    continue
                result.update(original_verified=True, selected=media_identity(candidate),
                              availability="verified_original",
                              probe={key: probe.get(key) for key in (
                                  "ok", "actual_size", "duration_seconds", "has_video", "has_audio")})
                if on_verified is not None:
                    on_verified(work, candidate["url"])
                break
            if not result["original_verified"]:
                result.update(error_code="probe_failed", probe_errors=failures)
        except ParseError as error:
            result["error_code"] = safe_id(error.code)
        finally:
            result["directories"] = parser.directories
    if result.get("error_code") == "source_unavailable":
        if not result["video_model_present"]:
            result["availability"] = "model_not_supplied"
        elif len(result["directories"]) == 2 and all(
                directory["code"] == directory["info_code"] == 0
                and directory["status"] == 10 and directory["video_id"] == result["video_id"]
                and directory["rows"] and all(row["quality"] not in ("original", "source")
                                              for row in directory["rows"])
                for directory in result["directories"]):
            result["availability"] = "valid_directory_without_original"
    return result


def cookie_snapshot(context):
    return {cookie["name"]: cookie["value"]
            for cookie in context.cookies("https://www.douyin.com/")}


def collect(page, work, *, on_verified=None):
    from playwright.sync_api import Error, TimeoutError as BrowserTimeout

    try:
        response = page.goto("https://www.douyin.com/video/" + work,
                             wait_until="domcontentloaded", timeout=25000)
        location = urlsplit(page.url)
        if (location.scheme, location.netloc, location.path.rstrip("/")) != (
                "https", "www.douyin.com", "/video/" + work):
            return {"work": work, "original_verified": False, "error_code": "page_redirected"}
        if response is None or response.status != 200:
            return {"work": work, "original_verified": False, "error_code": "page_http_error",
                    "page_http": response.status if response else None}
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            cookies = cookie_snapshot(page.context)
            if cookies.get("ttwid") and any(cookies.get(key) for key in UIFID_NAMES):
                break
            page.wait_for_timeout(250)
        fetched = run_detail_fetch(page, work)
        cookies = cookie_snapshot(page.context)
        if fetched.get("error") or fetched.get("status") != 200 or not fetched.get("json_valid"):
            return {"work": work, "original_verified": False,
                    "error_code": safe_id(fetched.get("error")) or "page_detail_failed",
                    "detail_http": safe_number(fetched.get("status"))}
        result = analyze_detail(work, fetched.get("detail"), cookies, page.evaluate("navigator.userAgent"),
                                on_verified=on_verified)
        result.update(detail_http=fetched.get("status"), detail_bytes=fetched.get("bytes"),
                      server_status=fetched.get("server_status"), filter_reason=fetched.get("filter_reason"),
                      session_cookie_present=any(cookies.get(key) for key in SESSION_COOKIES))
        return result
    except BrowserTimeout:
        return {"work": work, "original_verified": False, "error_code": "browser_timeout"}
    except Error:
        return {"work": work, "original_verified": False, "error_code": "browser_error"}
    except Exception as error:
        # Exception text may contain signed URLs. Save only the class name.
        return {"work": work, "original_verified": False, "error_code": "diagnostic_error",
                "error_type": type(error).__name__}


def comparison(phases, targets):
    maps = {name: {row["work"]: row for row in rows} for name, rows in phases.items()}
    complete = all(name in maps for name in ("anonymous_before", "session_after_login", "anonymous_after"))
    controls_ok = complete and all(maps[name].get(CONTROL, {}).get("original_verified", False) for name in maps)
    out = []
    for work in targets:
        verified = {name: rows.get(work, {}).get("original_verified", False) for name, rows in maps.items()}
        session_present = maps.get("session_after_login", {}).get(work, {}).get("session_cookie_present", False)
        interpretable = {"verified_original", "model_not_supplied", "valid_directory_without_original"}
        adequate = controls_ok and session_present and all(
            rows.get(work, {}).get("detail_matches", False)
            and rows.get(work, {}).get("availability") in interpretable for rows in maps.values())
        interpretation = "inconclusive"
        if adequate:
            if verified["session_after_login"] and not verified["anonymous_before"] and not verified["anonymous_after"]:
                interpretation = "original_only_in_session_after_login"
            elif not any(verified.values()):
                interpretation = "no_original_in_tested_sessions"
            else:
                interpretation = "availability_varies_check_phase_results"
        out.append({"work": work, "verified_by_phase": verified, "interpretation": interpretation})
    return {"all_control_probes_passed": bool(controls_ok), "targets": out}


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_phase(context, targets, *, on_verified=None):
    page = context.new_page()
    browser_detail.configure_platform(page, "windows")
    rows = []
    for work in (CONTROL, *targets):
        result = collect(page, work, on_verified=on_verified)
        rows.append(result)
        print(f"{work}: " + ("原片及媒体校验通过" if result["original_verified"] else result.get("error_code", "未取得原片")), flush=True)
    return page, rows


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="同作品登录前后原片诊断；Cookie不落盘，禁用历史原片catalog")
    ap.add_argument("works", nargs="*", default=list(TARGETS), help="待对照作品ID；自动加入原片成功样本")
    ap.add_argument("--anonymous-only", action="store_true", help="只跑匿名基线，不等待登录")
    ap.add_argument("--show-verified-url", action="store_true", help="原片媒体校验通过时在终端显示临时下载地址；报告仍不保存地址")
    ap.add_argument("--report", type=Path, default=PROJECT / "output" / ("session-compare-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json"))
    args = ap.parse_args(argv)
    if not args.works or any(not re.fullmatch(r"\d{15,22}", work) for work in args.works):
        ap.error("请输入15至22位作品ID")
    targets = list(dict.fromkeys(work for work in args.works if work != CONTROL))
    if not targets:
        ap.error("请至少指定一个待对照作品，成功样本会自动加入")
    if args.report.exists():
        ap.error("报告文件已存在，请换一个 --report 路径")
    browsers = PROJECT / ".browsers"
    if browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    report = {"created_at": datetime.now().astimezone().isoformat(), "control": CONTROL,
              "catalog_disabled": True, "credentials_saved": False, "phases": {}}
    on_verified = (lambda work, url: print(f"{work} 已验证原片地址：{url}", flush=True)) if args.show_verified_url else None
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=args.anonymous_only, channel="chromium", timeout=20000)
            try:
                settings = {"locale": "zh-CN", "timezone_id": "Asia/Shanghai"}
                context = browser.new_context(**settings)
                print("正在运行匿名基线。登录只是待验证条件，工具不保证恢复原片。", flush=True)
                page, report["phases"]["anonymous_before"] = run_phase(context, targets, on_verified=on_verified)
                write_report(args.report, report)
                if args.anonymous_only:
                    report["stop_reason"] = "anonymous_only"
                else:
                    page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=25000)
                    print("请在新开的浏览器中手动登录抖音，然后回到此窗口按回车。输入 q 取消。", flush=True)
                    if input().strip().lower() == "q":
                        report["stop_reason"] = "user_cancelled"
                    elif not any(cookie_snapshot(context).get(key) for key in SESSION_COOKIES):
                        report["stop_reason"] = "no_session_cookie_detected"
                        print("未检测到会话Cookie，已保留匿名报告。", flush=True)
                    else:
                        report["session_cookie_present"] = True
                        print("已检测到会话Cookie；这本身不证明账号或媒体权限。开始相同作品对照。", flush=True)
                        _, report["phases"]["session_after_login"] = run_phase(context, targets, on_verified=on_verified)
                        write_report(args.report, report)
                        # An independent anonymous replay checks for changes over time.
                        clean = browser.new_context(**settings)
                        try:
                            _, report["phases"]["anonymous_after"] = run_phase(clean, targets, on_verified=on_verified)
                        finally:
                            clean.close()
                        report["stop_reason"] = "completed"
            finally:
                browser.close()
    except (KeyboardInterrupt, EOFError):
        report["stop_reason"] = "interrupted"
    except Exception as error:
        report.update(stop_reason="browser_or_runtime_error", error_type=type(error).__name__)
    report["comparison"] = comparison(report["phases"], targets)
    write_report(args.report, report)
    print(f"脱敏报告：{args.report.resolve()}", flush=True)
    print("只有 original_verified=true 表示本次已完成原片媒体校验。", flush=True)
    return 0 if report.get("stop_reason") in ("completed", "anonymous_only") else 2


if __name__ == "__main__":
    raise SystemExit(main())
