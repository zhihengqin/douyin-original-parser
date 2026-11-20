import json
import os
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import async_playwright
from tools.capture_web_quality_transition import ROOT, capture_one, dismiss_visible_promo, select_visible_quality


class WebQualityTransitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_overlapping_requests_keep_their_own_phase_and_body(self):
        # Drive the Playwright event handlers locally; no browser or network.
        page = MagicMock()
        context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context))
        handlers = {}
        page.on.side_effect = handlers.__setitem__
        page.title = AsyncMock(return_value="Example")
        page.evaluate = AsyncMock(return_value={"visible_text": [], "videos": []})
        page.get_by_text.return_value.count = AsyncMock(return_value=0)
        page.url = "https://www.douyin.com/video/1"

        def request(value):
            return MagicMock(resource_type="xhr", method="GET", post_data=None, redirected_from=None,
                             url="https://www.douyin.com/aweme/detail?fixture=" + value)

        first, second = request("private-a"), request("private-b")
        def response(req, code):
            return SimpleNamespace(request=req, status=code, headers={"content-type": "application/json"},
                                   body=AsyncMock(return_value=b'{"aweme_detail":{"aweme_id":"1"}}'))

        ok, interrupted = response(first, 200), response(second, 503)

        async def goto(*args, **kwargs):
            handlers["request"](first)
            return SimpleNamespace(status=200)

        async def wait(delay):
            if delay == 9000:
                handlers["request"](second)
                handlers["response"](ok)
                handlers["response"](interrupted)
                second.failure = "network error"
                handlers["requestfailed"](second)
                handlers["requestfinished"](first)

        page.goto = goto
        page.wait_for_timeout = wait
        report = await capture_one(browser, "1", "control", 100)
        one, two = report["network"]
        self.assertEqual(one["url"], two["url"])
        self.assertEqual((one["phase_started"], two["phase_started"]),
                         ("navigation", "natural_playback_control"))
        self.assertEqual(one["phase_response"], "natural_playback_control")
        self.assertEqual((one["status"], two["status"]), (200, 503))
        self.assertTrue(one["json_body"]["detail_work_matches"])
        self.assertNotIn("failure", one)
        self.assertEqual(two["failure"], "network error")
        self.assertNotIn("json_body", two)
        interrupted.body.assert_not_awaited()
        self.assertEqual([p["phase"] for p in report["phase_changes"]],
                         ["navigation", "natural_playback_control", "response_body_summary"])
        self.assertNotIn("private-", json.dumps(report))
        context.close.assert_awaited_once()

    async def test_visible_player_controls_on_local_page(self):
        with patch.dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=os.environ.get(
                "PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))):
            async with async_playwright() as playwright:
                executable = Path(playwright.chromium.executable_path)
                if not executable.is_file():
                    self.skipTest("Local Chromium not installed")
                browser = await playwright.chromium.launch(executable_path=str(executable))
                try:
                    page = await browser.new_page()
                    await page.set_content("""
                        <style>
                          video, xg-icon, .btn {display:block; width: 200px}
                          video {height: 120px} .virtual {display:none}
                          xg-icon:hover .virtual {display:block}
                          #login-full-panel-test {height:0}
                        </style>
                        <button aria-label="关闭" onclick="document.body.remove()">其他弹窗</button>
                        <div id="login-full-panel-test">
                          <div class="YoNA2Hyj" style="position:fixed;top:10px;right:10px"
                             onclick="this.parentElement.remove()"><svg width="18" height="18"></svg></div>
                        </div>
                        <video></video>
                        <xg-icon class="xgplayer-playclarity-setting">
                          <span class="gear"><span class="btn">智能</span></span>
                          <div class="virtual"><button class="item"
                            onclick="document.querySelector('.btn').textContent=this.textContent">高清 720P</button></div>
                        </xg-icon>
                        <button onclick="document.body.remove()">标清 540P</button>
                    """)
                    self.assertTrue(await dismiss_visible_promo(page))
                    self.assertFalse(await dismiss_visible_promo(page))
                    with patch.object(page, "wait_for_timeout", AsyncMock()):
                        success = {"ui_actions": [], "states": []}
                        await select_visible_quality(page, "高清 720P", success, lambda _: None, lambda: 0)
                        self.assertEqual(success["quality_menu"], ["高清 720P"])
                        self.assertTrue(success["quality_readback"]["selection_matches"])
                        self.assertEqual(success["quality_readback"]["visible_video_sizes"],
                                         [{"width": 0, "height": 0}])
                        missing = {"ui_actions": [], "states": []}
                        await select_visible_quality(page, "标清 540P", missing, lambda _: None, lambda: 0)
                        self.assertNotIn("quality_readback", missing)
                        self.assertEqual(missing["ui_actions"][-1]["action"], "click_quality")
                        self.assertFalse(missing["ui_actions"][-1]["performed"])
                        self.assertEqual(await page.locator("video").count(), 1)
                finally:
                    await browser.close()
