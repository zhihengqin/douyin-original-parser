import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from playwright.sync_api import Error, TimeoutError as BrowserTimeout

from original_parser import guest
from original_parser.client import ParseError


COMPLETE_COOKIES = [
    {"name": "ttwid", "value": "test-guest"},
    {"name": "UIFID_TEMP", "value": "test-uifid"},
]


@contextmanager
def anonymous_browser(*, cookies=None, navigation_error=None, launch_error=None):
    manager = MagicMock()
    launcher = manager.__enter__.return_value.chromium.launch
    browser = launcher.return_value
    context = browser.new_context.return_value
    page = context.new_page.return_value
    context.cookies.return_value = COMPLETE_COOKIES if cookies is None else cookies
    if launch_error is not None:
        launcher.side_effect = launch_error
    if navigation_error is not None:
        page.goto.side_effect = navigation_error
    clock = [0.0]

    def advance(milliseconds):
        clock[0] += milliseconds / 1000

    page.wait_for_timeout.side_effect = advance
    with patch("playwright.sync_api.sync_playwright", return_value=manager), \
            patch.object(guest.time, "monotonic", side_effect=lambda: clock[0]):
        yield launcher, browser, context, page


class GuestNavigationTests(unittest.TestCase):
    def test_navigation_does_not_wait_for_full_page_initialization(self):
        with anonymous_browser() as (launcher, browser, _, page):
            cookies = guest._earn_guest()
        self.assertEqual(cookies, {row["name"]: row["value"] for row in COMPLETE_COOKIES})
        page.goto.assert_called_once_with(
            "https://www.douyin.com/", wait_until="commit", timeout=20000)
        launcher.assert_called_once()
        browser.close.assert_called_once()

    def test_navigation_timeout_preserves_already_issued_guest(self):
        with anonymous_browser(navigation_error=BrowserTimeout("navigation timed out")) as (_, browser, _, page):
            cookies = guest._earn_guest()
        self.assertTrue(cookies.get("ttwid") and cookies.get("UIFID_TEMP"))
        page.wait_for_timeout.assert_not_called()
        browser.close.assert_called_once()

    def test_guest_can_arrive_after_navigation_timeout_without_a_second_navigation(self):
        with anonymous_browser(navigation_error=BrowserTimeout("navigation timed out")) as (launcher, browser, context, page):
            context.cookies.side_effect = [[], COMPLETE_COOKIES]
            cookies = guest._earn_guest()
        self.assertEqual(cookies["UIFID_TEMP"], "test-uifid")
        self.assertEqual(context.cookies.call_count, 2)
        page.wait_for_timeout.assert_called_once_with(500)
        page.goto.assert_called_once()
        launcher.assert_called_once()
        browser.close.assert_called_once()

    def test_incomplete_cookies_after_timeout_still_fail_within_deadline(self):
        for partial in ([COMPLETE_COOKIES[0]], [COMPLETE_COOKIES[1]]):
            with self.subTest(cookie=partial[0]["name"]):
                with anonymous_browser(cookies=partial, navigation_error=BrowserTimeout("timeout")) as (_, browser, context, _):
                    with self.assertRaises(ParseError) as caught:
                        guest._earn_guest()
                self.assertEqual(caught.exception.code, "guest_initialization_failed")
                self.assertIn("导航超时", str(caught.exception))
                self.assertEqual(context.cookies.call_count, 50)
                browser.close.assert_called_once()

    def test_network_error_remains_failure_and_does_not_expose_arbitrary_text(self):
        secret = "private-cookie-or-signed-url"
        error = Error("Page.goto: net::ERR_CONNECTION_RESET https://example.invalid/?token=" + secret)
        with anonymous_browser(navigation_error=error) as (_, browser, context, _):
            with self.assertRaises(ParseError) as caught:
                guest._earn_guest()
        self.assertEqual(caught.exception.code, "guest_initialization_failed")
        self.assertIn("homepage_navigation", str(caught.exception))
        self.assertIn("net::ERR_CONNECTION_RESET", str(caught.exception))
        self.assertNotIn(secret, str(caught.exception))
        context.cookies.assert_not_called()
        browser.close.assert_called_once()

    def test_missing_browser_retains_setup_error(self):
        with anonymous_browser(launch_error=Error("Executable doesn't exist")):
            with self.assertRaises(ParseError) as caught:
                guest._earn_guest()
        self.assertEqual(caught.exception.code, "guest_setup_required")


if __name__ == "__main__":
    unittest.main()
