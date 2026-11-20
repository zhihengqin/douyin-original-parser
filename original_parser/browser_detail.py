"""通过正常视频页面的请求流程取得原画详情，供正式 HTTP 服务使用。"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

logger = logging.getLogger(__name__)
_browser_slot = threading.BoundedSemaphore(3)


def configure_browser_concurrency(worker_count):
    """服务启动时将浏览器并发与实际解析线程数对齐。"""
    global _browser_slot
    _browser_slot = threading.BoundedSemaphore(worker_count)


def emit(stage, **fields):
    # 字段由本模块选择，不写入 Cookie、详情正文或签名 URL。
    logger.info("browser_detail %s", json.dumps({"stage": stage, **fields}, ensure_ascii=False))


PAGE_FETCH = r"""({awemeId, maxBytes, timeoutMs, jobKey}) => {
    const state = {done: false, result: null};
    window[jobKey] = state;
    // 启动调用立即返回，Python 另用独立时限等待结果。
    setTimeout(() => {
        const controller = new AbortController();
        let reader;
        let timer;
        let phase = 'await_fetch';
        let metadata = {};
        const cancel = () => {
            try {controller.abort();} catch (_) {}
            // 取消也可能永不完成，只尝试清理，不等待它。
            try {if (reader) Promise.resolve(reader.cancel()).catch(() => {});} catch (_) {}
        };
        const work = async () => {
            // 使用页面当前的 fetch，不注入项目签名或替换成原生 fetch。
            const response = await window.fetch(
                '/aweme/v1/web/aweme/detail/?aweme_id=' + awemeId + '&aid=392139&device_platform=webapp',
                {credentials: 'include', redirect: 'error', signal: controller.signal});
            const result = {status: response.status, bytes: 0, json_valid: false};
            const type = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
            result.content_type = /^[a-z0-9!#$&^_.+-]+\/[a-z0-9!#$&^_.+-]+$/.test(type) ? type : 'unknown';
            metadata = result;
            phase = 'read_body';
            const chunks = [];
            if (response.body) {
                reader = response.body.getReader();
                while (true) {
                    const {value, done} = await reader.read();
                    if (done) break;
                    result.bytes += value.byteLength;
                    if (result.bytes > maxBytes) {
                        return {...result, error: 'response_too_large'};
                    }
                    chunks.push(value);
                }
            }
            const raw = new Uint8Array(result.bytes);
            let offset = 0;
            for (const chunk of chunks) {raw.set(chunk, offset); offset += chunk.byteLength;}
            phase = 'parse_json';
            try {
                const data = JSON.parse(new TextDecoder().decode(raw));
                result.json_valid = true;
                // 详情只传回 Python 内存用于原画校验，不打印或写入文件。
                result.detail = data?.aweme_detail;
            } catch (_) {}
            return result;
        };
        const deadline = new Promise(resolve => {
            timer = setTimeout(() => resolve({...metadata, phase, error: 'page_request_timeout'}), timeoutMs);
        });
        // 截止时间覆盖请求及正文读取，不依赖网页 SDK 响应 AbortSignal。
        Promise.race([Promise.resolve().then(work), deadline]).then(
            result => {
                state.result = result;
                state.done = true;
                clearTimeout(timer);
                if (result.error) cancel();
            },
            error => {
                state.result = {...metadata, phase,
                    error: error?.name === 'AbortError' ? 'page_request_timeout' : 'page_request_failed'};
                state.done = true;
                clearTimeout(timer);
                cancel();
            });
    }, 0);
    return true;
}"""


def run_page_fetch(page, aweme_id, max_bytes, *, timeout_ms=20000, wait_ms=25000):
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    job_key = "__parserPageDiagnostic_" + uuid.uuid4().hex
    page.evaluate(PAGE_FETCH, {"awemeId": aweme_id, "maxBytes": max_bytes,
                              "timeoutMs": timeout_ms, "jobKey": job_key})
    try:
        handle = page.wait_for_function(
            "key => {const job = window[key]; return job?.done ? job.result : false;}",
            arg=job_key, timeout=wait_ms, polling=100)
    except PlaywrightTimeoutError:
        # 不再对失去响应的页面执行 evaluate；让调用方关闭浏览器。
        return {"error": "page_request_wait_timeout", "phase": "browser_wait"}
    try:
        return handle.json_value()
    finally:
        handle.dispose()


IDENTITY_SCRIPT = """async () => {
    const data = navigator.userAgentData;
    if (!data) return null;
    const high = await data.getHighEntropyValues([
        'architecture', 'bitness', 'model', 'platformVersion', 'fullVersionList', 'wow64']);
    return {userAgent: navigator.userAgent, platform: navigator.platform,
        metadata: {brands: data.brands, mobile: data.mobile, platform: data.platform,
            architecture: high.architecture, bitness: high.bitness, model: high.model,
            platformVersion: high.platformVersion, fullVersionList: high.fullVersionList,
            wow64: high.wow64}};
}"""


def configure_platform(page, profile):
    """在离线 HTTPS 页面读取真实浏览器身份，并对当前页面设置 CDP 覆盖。"""
    from original_parser.client import ParseError

    route_pattern = "https://parser-platform.invalid/**"
    observed_headers = {}

    def offline_page(route):
        observed_headers.clear()
        observed_headers.update(route.request.headers)
        route.fulfill(status=200, content_type="text/html", body="<!doctype html><title>Identity check</title>")

    page.route(route_pattern, offline_page)
    try:
        page.goto("https://parser-platform.invalid/before", wait_until="load", timeout=5000)
        identity = page.evaluate(IDENTITY_SCRIPT)
        required = {"brands", "mobile", "platform", "architecture", "bitness", "model",
                    "platformVersion", "fullVersionList", "wow64"}
        if (not identity or not required.issubset(identity["metadata"])
                or any(identity["metadata"][name] is None for name in required)):
            raise ParseError("browser_profile_unavailable", "无法读取完整浏览器身份")
        # 两组都保留实际版本和品牌，并使用相同的 Chrome 标记。
        user_agent = identity["userAgent"].replace("HeadlessChrome/", "Chrome/")
        platform_name = identity["platform"]
        metadata = dict(identity["metadata"])
        if profile == "windows":
            user_agent = re.sub(r"\([^)]*\)", "(Windows NT 10.0; Win64; x64)", user_agent, count=1)
            platform_name = "Win32"
            metadata.update(platform="Windows", platformVersion="10.0.0", architecture="x86",
                            bitness="64", model="", mobile=False, wow64=False)
        session = page.context.new_cdp_session(page)
        session.send("Emulation.setUserAgentOverride", {
            "userAgent": user_agent, "platform": platform_name, "userAgentMetadata": metadata,
        })
        page.goto("https://parser-platform.invalid/after", wait_until="load", timeout=5000)
        actual = page.evaluate(IDENTITY_SCRIPT)
        matches = bool(actual and actual["userAgent"] == user_agent
                       and actual["platform"] == platform_name and actual["metadata"] == metadata
                       and observed_headers.get("user-agent") == user_agent
                       and observed_headers.get("sec-ch-ua-platform") == '"' + metadata["platform"] + '"')
        emit("browser_profile", profile=profile, verified=matches,
             navigator_platform=actual["platform"] if actual else None,
             client_hints_platform=actual["metadata"]["platform"] if actual else None,
             user_agent=user_agent)
        if not matches:
            raise ParseError("browser_profile_mismatch", "浏览器身份覆盖未通过读回验证")
        return user_agent
    finally:
        page.unroute(route_pattern, offline_page)


def get_browser_detail(aweme_id, *, timeout=20, profile="windows"):
    """每条任务使用独立匿名会话，浏览器并发上限跟随解析线程数。"""
    from .client import ParseError

    if not re.fullmatch(r"\d{15,22}", aweme_id):
        raise ParseError("invalid_input", "作品 ID 格式无效")
    if profile not in ("current", "native", "windows"):
        raise ValueError("不支持的浏览器平台配置")
    slots = _browser_slot
    if not slots.acquire(timeout=min(max(float(timeout), 0), 10)):
        raise ParseError("browser_busy", "浏览器解析繁忙，请稍后重试")
    try:
        return _fetch_browser_detail(aweme_id, timeout=timeout, profile=profile)
    finally:
        slots.release()


def _fetch_browser_detail(aweme_id, *, timeout, profile):
    from .client import MAX_JSON_BYTES, ParseError
    from .guest import UIFID_NAMES, USER_AGENT

    try:
        from playwright.sync_api import Error, TimeoutError as PlaywrightTimeoutError, sync_playwright
    except ImportError as exc:
        raise ParseError("guest_setup_required", "页面解析需要安装项目的 Playwright 依赖") from exc
    browsers = Path(__file__).resolve().parent.parent / ".browsers"
    if browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    stage = "browser_launch"
    request_ms = max(1000, min(int(timeout * 1000), 60000))
    emit("start", aweme_id=aweme_id, profile=profile)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium", timeout=20000)
            try:
                settings = {"locale": "zh-CN", "timezone_id": "Asia/Shanghai"}
                if profile == "current":
                    settings["user_agent"] = USER_AGENT
                context = browser.new_context(**settings)
                page = context.new_page()
                stage = "browser_profile"
                user_agent = USER_AGENT if profile == "current" else configure_platform(page, profile)
                natural_responses = []

                def observe(response):
                    parts = urlsplit(response.url)
                    if (parts.scheme == "https" and parts.hostname == "www.douyin.com"
                            and parts.path == "/aweme/v1/web/aweme/detail/"
                            and parse_qs(parts.query).get("aweme_id") == [aweme_id]):
                        natural_responses.append(response.status)

                page.on("response", observe)
                stage = "video_page"
                response = page.goto("https://www.douyin.com/video/" + aweme_id,
                                     wait_until="domcontentloaded", timeout=25000)
                parts = urlsplit(page.url)
                if (parts.scheme != "https" or parts.netloc != "www.douyin.com"
                        or parts.path.rstrip("/") != "/video/" + aweme_id):
                    raise ParseError("detail_unavailable", "视频页面未停留在目标作品，可能需要验证或作品不可见")
                if response is not None and response.status == 429:
                    raise ParseError("upstream_rate_limited", "视频页面返回 HTTP 429，请稍后重试")
                if response is not None and response.status in (403, 444):
                    raise ParseError("upstream_forbidden", "视频页面拒绝了请求（HTTP " + str(response.status) + "）")
                if response is None or response.status != 200:
                    raise ParseError("upstream_error", "视频页面未返回 HTTP 200")
                stage = "page_initialization"
                deadline = time.monotonic() + 20
                ready = False
                while time.monotonic() < deadline:
                    cookies = {c["name"]: c["value"] for c in context.cookies("https://www.douyin.com/")}
                    ready = bool(cookies.get("ttwid") and any(cookies.get(name) for name in UIFID_NAMES))
                    if ready and natural_responses:
                        break
                    page.wait_for_timeout(250)
                page.remove_listener("response", observe)
                emit(stage, guest_ready=ready, natural_detail_seen=bool(natural_responses))
                if not ready:
                    raise ParseError("guest_initialization_failed", "视频页面未取得完整访客标识")
                stage = "page_fetch"
                result = run_page_fetch(page, aweme_id, MAX_JSON_BYTES,
                                        timeout_ms=request_ms, wait_ms=request_ms + 5000)
                detail = result.pop("detail", None)
                emit(stage, **result)
                error = result.get("error")
                if error in ("page_request_timeout", "page_request_wait_timeout"):
                    raise ParseError("browser_detail_timeout", "视频页面的详情请求未在限定时间内完成")
                if error:
                    raise ParseError("browser_detail_failed", "视频页面详情请求失败（" + error + "）")
                if result.get("status") == 429:
                    raise ParseError("upstream_rate_limited", "视频页面详情接口返回 HTTP 429，请稍后重试")
                if result.get("status") in (403, 444):
                    raise ParseError("upstream_forbidden", "视频页面详情接口拒绝了请求（HTTP " + str(result.get("status")) + "）")
                if result.get("status") != 200:
                    raise ParseError("upstream_error", "视频页面详情接口返回 HTTP " + str(result.get("status")))
                if not result.get("bytes"):
                    raise ParseError("upstream_empty_response", "视频页面详情接口返回 HTTP 200 空内容")
                if not result.get("json_valid"):
                    raise ParseError("upstream_non_json", "视频页面详情接口返回非 JSON 内容")
                if not isinstance(detail, dict) or str(detail.get("aweme_id")) != aweme_id:
                    raise ParseError("detail_unavailable", "视频页面未返回目标作品详情")
                # 关闭浏览器前取最新快照；后续继续用现有 source/probe 校验完整原画。
                cookies = {c["name"]: c["value"] for c in context.cookies("https://www.douyin.com/")}
                emit("detail_ready", aweme_id=aweme_id, cookie_count=len(cookies))
                return detail, cookies, user_agent
            finally:
                try:
                    browser.close()
                except Exception:
                    stage = "browser_close"
                    raise
    except ParseError:
        raise
    except PlaywrightTimeoutError as exc:
        raise ParseError("browser_detail_timeout", "浏览器解析等待超时，阶段=" + stage) from exc
    except Error as exc:
        logger.warning("browser_detail_failed stage=%s category=%s", stage, type(exc).__name__)
        raise ParseError("browser_detail_failed", "浏览器解析失败，阶段=" + stage) from exc
