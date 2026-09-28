"""Regression checks for upstream restriction reporting and request reduction."""

import io
import types
import unittest
from unittest.mock import MagicMock, patch

from original_parser import browser_detail, client
from original_parser.client import OriginalParser, ParseError, resolve_id_local


AWEME = "7689381368630906122"
VIDEO_URL = f"https://www.douyin.com/video/{AWEME}"


class RawBody(io.BytesIO):
    def read(self, size=-1, **_):
        return super().read(size)


class HttpResponse:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body
        self.raw = RawBody(body)
        self.headers = {"Content-Type": "application/json"}
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.raw.close()
        self.closed = True

    def iter_content(self, size):
        for start in range(0, len(self.body), size):
            yield self.body[start:start + size]


class RequestFailureTests(unittest.TestCase):
    def test_upstream_http_failures_keep_distinct_circuit_breaker_codes(self):
        cases = (
            (200, b"", "upstream_empty_response"),
            (200, b" \r\n", "upstream_empty_response"),
            (200, b"<html>unavailable</html>", "upstream_non_json"),
            (403, b"Forbidden", "upstream_forbidden"),
            (403, b"Blocked by ArgusSecurityPlugin Uifid Not Found", "credentials_required"),
            (403, b"Blocked by ArgusSecurityPlugin Signature Not Found", "credentials_rejected"),
            (429, b"", "upstream_rate_limited"),
            (444, b"", "upstream_forbidden"),
        )
        for status, body, code in cases:
            with self.subTest(status=status, code=code), OriginalParser(auto_guest=False) as parser:
                response = HttpResponse(status, body)
                with patch.object(parser, "_get", return_value=response) as request:
                    with self.assertRaises(ParseError) as caught:
                        parser._json(client.DETAIL_URL, stage="作品详情接口")
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(request.call_count, 1)
                self.assertTrue(response.closed)

    def test_server_mode_uses_one_detail_request_without_refreshing_cached_or_new_guest(self):
        credentials = ({"UIFID_TEMP": "test-visitor", "ttwid": "test-ttwid"}, "test-user-agent")
        for has_cached_guest in (False, True):
            with self.subTest(has_cached_guest=has_cached_guest), \
                    patch.object(client, "cached_guest", return_value=credentials if has_cached_guest else None), \
                    patch.object(client, "get_guest", return_value=credentials) as get_guest:
                with OriginalParser(refresh_guest_on_rejection=False) as parser, \
                        patch.object(parser, "_get", return_value=HttpResponse(200, b"")) as request:
                    with self.assertRaises(ParseError) as caught:
                        parser.detail(AWEME)
                    self.assertEqual(caught.exception.code, "upstream_empty_response")
                    self.assertEqual(request.call_count, 1)
                    self.assertEqual(parser.session.headers["User-Agent"], "test-user-agent")
                    self.assertEqual(parser.session.cookies.get("UIFID_TEMP"), "test-visitor")
                if has_cached_guest:
                    get_guest.assert_not_called()
                else:
                    # Initializing a missing visitor is permitted; refreshing
                    # the same rejected visitor would make an extra request.
                    get_guest.assert_called_once_with()

    def test_browser_page_and_detail_restrictions_report_codes_and_close_browser(self):
        class BrowserError(Exception):
            pass

        class BrowserTimeout(BrowserError):
            pass

        for blocked_stage in ("video_page", "detail"):
            for status, code in ((403, "upstream_forbidden"), (444, "upstream_forbidden"),
                                 (429, "upstream_rate_limited")):
                with self.subTest(blocked_stage=blocked_stage, status=status):
                    playwright = MagicMock()
                    browser = playwright.chromium.launch.return_value
                    context = browser.new_context.return_value
                    page = context.new_page.return_value
                    page.url = VIDEO_URL
                    context.cookies.return_value = [
                        {"name": "ttwid", "value": "test-ttwid"},
                        {"name": "UIFID_TEMP", "value": "test-visitor"},
                    ]
                    callbacks = []
                    page.on.side_effect = lambda event, callback: callbacks.append(callback)

                    def goto(*args, **kwargs):
                        for callback in callbacks:
                            callback(types.SimpleNamespace(
                                url=client.DETAIL_URL + "?aweme_id=" + AWEME, status=200))
                        return types.SimpleNamespace(status=status if blocked_stage == "video_page" else 200)

                    page.goto.side_effect = goto
                    manager = MagicMock()
                    manager.__enter__.return_value = playwright
                    fake_api = types.ModuleType("playwright.sync_api")
                    fake_api.Error = BrowserError
                    fake_api.TimeoutError = BrowserTimeout
                    fake_api.sync_playwright = MagicMock(return_value=manager)
                    detail_response = {"status": status, "bytes": 0, "json_valid": False}
                    with patch.dict("sys.modules", {"playwright.sync_api": fake_api}), \
                            patch.object(browser_detail, "configure_platform", return_value="test-user-agent"), \
                            patch.object(browser_detail, "run_page_fetch", return_value=detail_response) as fetch, \
                            patch.object(browser_detail, "emit"):
                        with self.assertRaises(ParseError) as caught:
                            browser_detail.get_browser_detail(AWEME, profile="windows")
                    self.assertEqual(caught.exception.code, code)
                    browser.close.assert_called_once()
                    self.assertEqual(fetch.call_count, int(blocked_stage == "detail"))

    def test_known_id_inputs_normalize_locally_and_short_links_remain_deferred(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected network access")):
            for text in (AWEME, VIDEO_URL, f"分享作品 {VIDEO_URL}。复制此链接",
                         f"https://www.douyin.com/?modal_id={AWEME}"):
                with self.subTest(text=text):
                    found, url = resolve_id_local(text)
                    self.assertEqual(found, AWEME)
                    self.assertTrue(url.startswith("https://www.douyin.com/"))
            self.assertEqual(resolve_id_local("打开 https://v.douyin.com/example/"),
                             (None, "https://v.douyin.com/example/"))

    def test_local_normalization_rejects_lookalike_hosts_and_embedded_credentials(self):
        bad_urls = (
            f"https://www.douyin.com.evil.example/video/{AWEME}",
            f"https://evil.example/douyin.com/video/{AWEME}",
            f"https://user:password@www.douyin.com/video/{AWEME}",
            f"https://www.douyin.com:9999/video/{AWEME}",
        )
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected network access")):
            for url in bad_urls:
                with self.subTest(url=url), self.assertRaises(ParseError) as caught:
                    resolve_id_local("复制打开 " + url)
                self.assertEqual(caught.exception.code, "invalid_url")


if __name__ == "__main__":
    unittest.main()
