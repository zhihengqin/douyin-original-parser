"""Exercise the public HTTP and CLI contracts without contacting Douyin."""

import concurrent.futures
import contextlib
import http.client
import io
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from original_parser import cli, server
from original_parser.client import ParseError
from original_parser.guard import GuardConfig


AWEME = "7689381368630906122"
OTHER = "7685326449011608873"


def response_payload(aweme_id=AWEME, *, with_probe=True, marker="original"):
    expiry = int(time.time()) + 3600
    return {"code": 0, "msg": "原画解析成功", "data": {
        "aweme_id": aweme_id, "url": "https://video.douyinvod.com/example.mp4",
        "source_selected": True, "probe": {"ok": True} if with_probe else None,
        "expires_at": expiry, "video_list": [{"expires_at": expiry}], "marker": marker,
    }}


class LocalService:
    """Run the actual request handler and guard on an ephemeral loopback port."""

    def __init__(self, parse=None, *, config=None, **settings):
        self.parse = parse or (lambda text, probe, options: response_payload(text, with_probe=probe))
        self.config = config or GuardConfig(interval_range=(0, 0), wait_timeout=2)
        self.settings = settings
        self.constructed = []
        self.parsed = []
        self.ready = threading.Event()
        self.thread_errors = []
        self.http_server = None
        self.stack = contextlib.ExitStack()

    def __enter__(self):
        owner = self

        class FakeParser:
            def __init__(self, **options):
                self.options = options
                owner.constructed.append(options)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def parse(self, text, *, with_probe):
                owner.parsed.append((text, with_probe))
                return owner.parse(text, with_probe, self.options)

        class FastLocalServer(ThreadingHTTPServer):
            def serve_forever(self, poll_interval=0.5):
                super().serve_forever(poll_interval=0.01)

        def create_server(address, handler):
            handler.log_message = lambda *args: None
            self.http_server = FastLocalServer(address, handler)
            self.ready.set()
            return self.http_server

        self.stack.enter_context(patch.object(server, "OriginalParser", FakeParser))
        self.stack.enter_context(patch.object(server, "ThreadingHTTPServer", create_server))
        self.stack.enter_context(patch("builtins.print"))

        def run():
            try:
                server.serve("127.0.0.1", 0, guard_config=self.config, **self.settings)
            except BaseException as exc:
                self.thread_errors.append(exc)
                self.ready.set()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        if not self.ready.wait(2) or self.thread_errors:
            self.stack.close()
            raise AssertionError(f"Local server did not start: {self.thread_errors}")
        return self

    def __exit__(self, *_):
        try:
            self.http_server.shutdown()
            self.thread.join(2)
            if self.thread.is_alive():
                raise AssertionError("Local server failed to stop")
            if self.thread_errors:
                raise AssertionError(f"Local server failed: {self.thread_errors}")
        finally:
            self.stack.close()

    def request(self, payload=None, *, path="/parse"):
        conn = http.client.HTTPConnection("127.0.0.1", self.http_server.server_port, timeout=3)
        try:
            if payload is None:
                conn.request("GET", path)
            else:
                conn.request("POST", path, json.dumps(payload), {"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            conn.close()

    def health(self):
        return self.request(path="/health")[2]


class ServerGuardTests(unittest.TestCase):
    def eventually(self, predicate, timeout=1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.003)
        self.assertTrue(predicate(), "HTTP service did not reach the expected state")

    def test_link_id_and_share_text_merge_into_one_parse_with_compatible_json(self):
        entered, release = threading.Event(), threading.Event()
        expected = response_payload()

        def parse(text, with_probe, options):
            entered.set()
            self.assertTrue(release.wait(2))
            return expected

        with LocalService(parse, detail_mode="browser", browser_profile="native") as service:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                try:
                    first = pool.submit(service.request, {"url": f"https://www.douyin.com/video/{AWEME}"})
                    self.assertTrue(entered.wait(1))
                    second = pool.submit(service.request, {"url": AWEME})
                    third = pool.submit(service.request, {
                        "share_text": f"分享作品 https://www.douyin.com/video/{AWEME}?from=web 复制打开抖音",
                    }, path="/api/v1/resolve")
                    self.eventually(lambda: service.health()["protection"]["coalesced"] == 2)
                finally:
                    release.set()
                for future in (first, second, third):
                    status, headers, body = future.result(2)
                    self.assertEqual(status, 200)
                    self.assertEqual(body, expected)
                    self.assertIn("application/json", headers["Content-Type"])
            self.assertEqual(service.parsed, [(AWEME, True)])
            self.assertEqual(len(service.constructed), 1)
            options = service.constructed[0]
            self.assertFalse(options["refresh_guest_on_rejection"])
            self.assertEqual(options["detail_mode"], "browser")
            self.assertEqual(options["browser_profile"], "native")
            self.assertTrue(options["auto_guest"])

    def test_probe_choices_are_separate_and_unverified_results_are_not_cached(self):
        with LocalService() as service:
            skipped = service.request({"url": AWEME, "with_probe": False})
            verified = service.request({"url": AWEME, "with_probe": True})
            verified_again = service.request({"url": AWEME})
            skipped_again = service.request({"url": AWEME, "with_probe": False})
            self.assertIsNone(skipped[2]["data"]["probe"])
            self.assertTrue(verified[2]["data"]["probe"]["ok"])
            self.assertEqual(verified_again[2], verified[2])
            self.assertIsNone(skipped_again[2]["data"]["probe"])
            self.assertEqual(service.parsed, [(AWEME, False), (AWEME, True), (AWEME, False)])

    def test_force_refresh_bypasses_cache_and_updates_both_public_endpoints(self):
        calls = []

        def parse(text, with_probe, options):
            calls.append(text)
            return response_payload(text, with_probe=with_probe, marker=f"attempt-{len(calls)}")

        with LocalService(parse) as service:
            initial = service.request({"url": AWEME})
            cached = service.request({"url": AWEME, "force_refresh": False})
            self.assertEqual(cached[2], initial[2])
            refreshed = service.request({"url": AWEME, "force_refresh": True},
                                        path="/api/v1/resolve")
            self.assertEqual(refreshed[0], 200)
            self.assertEqual(refreshed[2]["data"]["marker"], "attempt-2")
            current = service.request({"url": AWEME})
            self.assertEqual(current[2], refreshed[2])
            self.assertEqual(calls, [AWEME, AWEME])

    def test_three_restrictions_pause_upstream_and_return_503_retry_contract(self):
        def restricted(*_):
            raise ParseError("upstream_empty_response", "视频页面详情接口返回 HTTP 200 空内容")

        config = GuardConfig(interval_range=(0, 0), wait_timeout=2, failure_threshold=3, cooldown=900)
        with LocalService(restricted, config=config) as service:
            for _ in range(3):
                status, _, body = service.request({"url": AWEME})
                self.assertEqual(status, 502)
                self.assertEqual(body["code"], "upstream_empty_response")
            status, headers, body = service.request({"url": OTHER})
            self.assertEqual(status, 503)
            self.assertEqual(body["code"], "upstream_cooldown")
            self.assertIsNone(body["data"])
            self.assertGreater(body["retry_after_seconds"], 0)
            self.assertEqual(int(headers["Retry-After"]), body["retry_after_seconds"])
            self.assertEqual(len(service.parsed), 3)
            self.assertEqual(service.health()["protection"]["state"], "open")
            self.assertEqual(len(service.parsed), 3)

    def test_full_queue_and_wait_timeout_return_429_with_retry_information(self):
        entered, release = threading.Event(), threading.Event()

        def blocked(text, with_probe, options):
            entered.set()
            self.assertTrue(release.wait(2))
            return response_payload()

        config = GuardConfig(interval_range=(0, 0), max_pending=0, wait_timeout=0.15)
        with LocalService(blocked, config=config) as service:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                try:
                    active = pool.submit(service.request, {"url": AWEME})
                    self.assertTrue(entered.wait(1))
                    status, headers, body = service.request({"url": OTHER})
                    self.assertEqual((status, body["code"]), (429, "busy"))
                    self.assertEqual(int(headers["Retry-After"]), body["retry_after_seconds"])
                    status, headers, body = active.result(1)
                    self.assertEqual((status, body["code"]), (429, "queue_timeout"))
                    self.assertEqual(int(headers["Retry-After"]), body["retry_after_seconds"])
                finally:
                    release.set()
            self.eventually(lambda: service.health()["protection"]["active"] == 0)
            self.assertEqual(len(service.parsed), 1)

    def test_health_and_invalid_input_never_construct_an_upstream_parser(self):
        with LocalService() as service:
            initial = service.health()
            self.assertTrue(initial["ok"])
            self.assertEqual(initial["provider"], "douyin-official-source")
            self.assertEqual(initial["protection"]["started"], 0)
            for payload in (
                {"url": "https://example.com/video/" + AWEME},
                {"url": "https://www.douyin.com.attacker.example/video/" + AWEME},
                {"url": "not a video"}, {"url": AWEME, "with_probe": "true"},
                {"url": AWEME, "force_refresh": "true"},
                {"url": AWEME, "force_refresh": 1},
                {"url": AWEME, "force_refresh": None},
                {"url": ""}, [],
            ):
                with self.subTest(payload=payload):
                    self.assertEqual(service.request(payload)[0], 400)
            after = service.health()
            self.assertEqual(after["protection"]["requests"], 0)
            self.assertEqual(service.constructed, [])
            self.assertEqual(service.parsed, [])

    def test_cookie_file_content_change_uses_new_credentials_and_cache_scope(self):
        def parse(text, with_probe, options):
            self.assertFalse(options["auto_guest"])
            self.assertFalse(options["refresh_guest_on_rejection"])
            return response_payload(text, with_probe=with_probe, marker=options["cookies"]["sessionid"])

        with tempfile.TemporaryDirectory() as directory:
            cookie_file = Path(directory) / "credentials.json"

            def write(value):
                cookie_file.write_text(json.dumps({"cookies": {"sessionid": value},
                                                   "user_agent": "test-user-agent"}), encoding="utf-8")

            write("test-one")
            with LocalService(parse, cookie_file=cookie_file) as service:
                first = service.request({"url": AWEME})
                cached = service.request({"url": AWEME})
                self.assertEqual(first[2], cached[2])
                self.assertEqual(len(service.parsed), 1)
                write("test-two")
                changed = service.request({"url": AWEME})
                self.assertEqual(changed[0], 200)
                self.assertEqual(first[2]["data"]["marker"], "test-one")
                self.assertEqual(changed[2]["data"]["marker"], "test-two")
                self.assertEqual(len(service.parsed), 2)
                self.assertEqual(service.constructed[-1]["user_agent"], "test-user-agent")


class GuardCliTests(unittest.TestCase):
    def test_service_options_reach_server_and_guard_configuration(self):
        with patch.object(server, "serve") as serve_mock, \
                patch("sys.stdout", new_callable=io.StringIO), \
                patch("sys.stderr", new_callable=io.StringIO):
            status = cli.main([
                "--serve", "--host", "0.0.0.0", "--port", "9876", "--max-concurrent", "8",
                "--detail-mode", "browser", "--browser-profile", "windows",
                "--request-interval", "12", "--cache-ttl", "180", "--cache-max-entries", "20",
                "--queue-size", "4", "--queue-wait-timeout", "90",
                "--failure-threshold", "2", "--cooldown-seconds", "600",
            ])
        self.assertEqual(status, 0)
        self.assertEqual(serve_mock.call_args.args, ("0.0.0.0", 9876))
        settings = serve_mock.call_args.kwargs
        self.assertEqual(settings["max_concurrent"], 8)
        self.assertEqual(settings["detail_mode"], "browser")
        self.assertEqual(settings["browser_profile"], "windows")
        self.assertEqual(settings["guard_config"], GuardConfig(
            interval_range=(12, 12), cache_ttl=180, cache_max_entries=20, max_pending=4,
            wait_timeout=90, failure_threshold=2, cooldown=600,
        ))

    def test_invalid_numeric_configuration_does_not_start_service(self):
        for flag, value in (("--request-interval", "nan"), ("--cache-ttl", "inf"),
                            ("--queue-wait-timeout", "0"), ("--queue-size", "-1")):
            with self.subTest(flag=flag, value=value), \
                    patch.object(server, "serve") as serve_mock, \
                    patch("sys.stdout", new_callable=io.StringIO), \
                    patch("sys.stderr", new_callable=io.StringIO) as errors:
                self.assertEqual(cli.main(["--serve", flag, value]), 2)
                serve_mock.assert_not_called()
                self.assertEqual(json.loads(errors.getvalue())["code"], "local_error")


if __name__ == "__main__":
    unittest.main()
