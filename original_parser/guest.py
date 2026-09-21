"""在独立的匿名浏览器会话中取得访客 Cookie，进程内短期复用。"""

import os
import threading
import time
from pathlib import Path

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")
UIFID_NAMES = ("uifid", "uifid_temp", "uifidtemp", "UIFID", "UIFID_TEMP", "UIFIDTEMP")
CACHE_SECONDS = 20 * 60
_lock = threading.Lock()
_cached_cookies: dict[str, str] = {}
_expires_at = 0.0
_failure: tuple[str, str] | None = None
_retry_after = 0.0


def cached_guest() -> tuple[dict[str, str], str] | None:
    with _lock:
        if _cached_cookies and time.monotonic() < _expires_at:
            return dict(_cached_cookies), USER_AGENT
    return None


def get_guest(rejected: dict | None = None) -> tuple[dict[str, str], str]:
    """同一进程只初始化一次；仅失效的那份缓存触发更新，防止并发重复开浏览器。"""
    from .client import ParseError

    global _cached_cookies, _expires_at, _failure, _retry_after
    with _lock:
        if (_cached_cookies and time.monotonic() < _expires_at
                and _cached_cookies != rejected):
            return dict(_cached_cookies), USER_AGENT
        if _failure and time.monotonic() < _retry_after:
            raise ParseError(*_failure)
        # 初始化失败也不继续复用刚被平台拒绝的访客信息。
        _cached_cookies = {}
        _expires_at = 0.0
        try:
            _cached_cookies = _earn_guest()
        except ParseError as exc:
            _failure = (exc.code, str(exc))
            _retry_after = time.monotonic() + 15
            raise
        _failure = None
        _retry_after = 0.0
        _expires_at = time.monotonic() + CACHE_SECONDS
        return dict(_cached_cookies), USER_AGENT


def _earn_guest() -> dict[str, str]:
    from .client import ParseError

    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise ParseError("guest_setup_required", "自动访客初始化需要 Playwright，请用当前解释器安装 requirements.txt，"
                         "再执行 python -m playwright install chromium") from exc
    shared_browsers = Path(__file__).resolve().parent.parent / ".browsers"
    if shared_browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(shared_browsers))
    try:
        with sync_playwright() as playwright:
            # 全新非持久上下文，不读取个人浏览器资料或已有登录状态。
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                context = browser.new_context(user_agent=USER_AGENT, locale="zh-CN",
                                              timezone_id="Asia/Shanghai")
                page = context.new_page()
                page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=20000)
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    jar = {c["name"]: c["value"] for c in context.cookies("https://www.douyin.com/")}
                    if jar.get("ttwid") and any(jar.get(name) for name in UIFID_NAMES):
                        return jar
                    page.wait_for_timeout(500)
            finally:
                browser.close()
    except Error as exc:
        if "Executable doesn't exist" in str(exc):
            raise ParseError("guest_setup_required", "未安装 Chromium，请用当前解释器执行 "
                             "python -m playwright install chromium；Linux 部署请重新运行安装脚本") from exc
        raise ParseError("guest_initialization_failed", "无法完成抖音访客初始化，请检查浏览器运行依赖和网络；"
                         "可在本地浏览器确认抖音是否要求额外验证") from exc
    raise ParseError("guest_initialization_failed", "抖音没有下发 UIFID 访客标识，可能需要额外验证；"
                     "请检查当前网络，或通过 --cookie-file 提供有效访客凭据")
