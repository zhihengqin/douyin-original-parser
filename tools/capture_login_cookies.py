r"""打开一个可见的 Chromium，让用户自己扫码登录抖音，登录成功后把 Cookie 存成凭据文件。

默认产物：output/login-capture-时间戳.json，格式与 load_credentials 一致。
默认目录已被 Git 忽略；指定其它路径时由调用者保管，不覆盖现有文件。

用法：
    .venv\Scripts\python.exe tools\capture_login_cookies.py [输出路径] [超时秒数]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from original_parser.guest import USER_AGENT  # noqa: E402

LOGIN_COOKIES = ("sessionid", "sessionid_ss", "passport_csrf_token")


def log(message: str) -> None:
    print(message, flush=True)


def main(argv: list[str]) -> int:
    output = (Path(argv[1]) if len(argv) > 1 else
              ROOT / "output" / f"login-capture-{time.time_ns()}.json")
    timeout = float(argv[2]) if len(argv) > 2 else 900.0
    if output.exists():
        log("输出文件已存在，请指定新的凭据文件路径")
        return 2
    from playwright.sync_api import Error, sync_playwright

    browsers = ROOT / ".browsers"
    if browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, channel="chromium", timeout=30000)
        context = browser.new_context(user_agent=USER_AGENT, locale="zh-CN",
                                      timezone_id="Asia/Shanghai")
        page = context.new_page()
        try:
            page.goto("https://www.douyin.com/", wait_until="commit", timeout=25000)
        except Error as error:
            log(f"首页导航未完成（{type(error).__name__}），继续等待登录")
        try:
            page.evaluate("""
                () => {
                    const box = document.createElement('div');
                    box.textContent = '请在这个窗口里扫码登录抖音；登录成功后窗口会自动关闭。';
                    box.style.cssText = 'position:fixed;z-index:2147483647;top:0;left:0;right:0;'
                        + 'padding:14px;background:#111;color:#fff;font:16px/1.5 sans-serif;text-align:center';
                    document.body.appendChild(box);
                }
            """)
        except Error:
            pass
        log("浏览器已打开，等待扫码登录……")
        deadline = time.monotonic() + timeout
        found: dict[str, str] = {}
        while time.monotonic() < deadline:
            jar = {cookie["name"]: cookie["value"] for cookie in
                   context.cookies("https://www.douyin.com/")}
            names = [name for name in LOGIN_COOKIES if jar.get(name)]
            if "sessionid" in names:
                found = jar
                break
            time.sleep(2)
        context.close()
        browser.close()

    if not found:
        log("超时未检测到登录 Cookie，未写入任何文件")
        return 3
    # 保留当前抖音网页会话实际下发的字段，避免白名单遗漏新增认证字段。
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"cookies": found, "user_agent": USER_AGENT}, stream,
                  ensure_ascii=False, indent=2)
    log(f"已写入 {output}（{len(found)} 个字段：{', '.join(sorted(found))}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
