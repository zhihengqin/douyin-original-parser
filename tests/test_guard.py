"""Offline concurrency and cache safety checks for the upstream request guard."""

import concurrent.futures
import copy
import math
import threading
import time
import unittest
from unittest.mock import patch

from original_parser.client import ParseError
from original_parser.guard import GuardConfig, GuardError, RequestGuard


class Clock:
    def __init__(self):
        self.monotonic = 1000.0
        self.wall = 2_000_000_000.0

    def advance(self, seconds):
        self.monotonic += seconds
        self.wall += seconds


def verified_result(*, expiry=None, marker="original"):
    if expiry is None:
        expiry = time.time() + 3600
    return {
        "code": 0,
        "data": {
            "aweme_id": "7689381368630906122",
            "source_selected": True,
            "probe": {"ok": True},
            "expires_at": expiry,
            "url": "https://video.douyinvod.com/example.mp4",
            "video_list": [{"expires_at": expiry, "quality": "original"}],
            "marker": marker,
        },
    }


class GuardTests(unittest.TestCase):
    def guard(self, clock=None, **overrides):
        options = {"interval_range": (0, 0), "wait_timeout": 2}
        options.update(overrides)
        kwargs = {} if clock is None else {
            "clock": lambda: clock.monotonic,
            "wall_clock": lambda: clock.wall,
        }
        guard = RequestGuard(GuardConfig(**options), **kwargs)
        self.addCleanup(guard.close)
        return guard

    def eventually(self, predicate, timeout=1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.002)
        self.assertTrue(predicate(), "Concurrent operation did not reach the expected state")

    def assert_guard_error(self, code, fn):
        with self.assertRaises(GuardError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        self.assertGreaterEqual(caught.exception.retry_after, 1)
        return caught.exception

    def test_same_key_shares_work_but_returns_independent_results(self):
        guard = self.guard()
        entered, release = threading.Event(), threading.Event()
        calls = []
        original = verified_result()

        def load():
            calls.append(1)
            entered.set()
            self.assertTrue(release.wait(2))
            return original

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            try:
                futures = [pool.submit(guard.run, ("video", True), load)]
                self.assertTrue(entered.wait(1))
                futures.extend(pool.submit(guard.run, ("video", True), load)
                               for _ in range(3))
                self.eventually(lambda: guard.snapshot()["coalesced"] == 3)
            finally:
                release.set()
            results = [future.result(2) for future in futures]

        self.assertEqual(calls, [1])
        results[0]["data"]["video_list"][0]["quality"] = "changed"
        results[1]["data"]["probe"]["ok"] = False
        self.assertEqual(results[2], original)
        cached = guard.run(("video", True), lambda: self.fail("Cache should avoid upstream"))
        self.assertEqual(cached, original)
        cached["data"]["marker"] = "changed again"
        self.assertEqual(guard.run(("video", True), load), original)

    def test_different_keys_are_fifo_serial_and_spaced_after_completion(self):
        interval = 0.06
        # 本用例验证串行与间隔本身，用固定间隔（下限等于上限）得到确定的行为。
        guard = self.guard(interval_range=(interval, interval))
        entered, release = threading.Event(), threading.Event()
        trace = []
        active = 0
        maximum_active = 0
        lock = threading.Lock()

        def load(key):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
                trace.append(("start", key, time.monotonic()))
            if key == "first":
                entered.set()
                self.assertTrue(release.wait(2))
            with lock:
                trace.append(("end", key, time.monotonic()))
                active -= 1
            return verified_result(marker=key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            try:
                first = pool.submit(guard.run, "first", lambda: load("first"))
                self.assertTrue(entered.wait(1))
                second = pool.submit(guard.run, "second", lambda: load("second"))
                self.eventually(lambda: guard.snapshot()["pending"] == 1)
                third = pool.submit(guard.run, "third", lambda: load("third"))
                self.eventually(lambda: guard.snapshot()["pending"] == 2)
            finally:
                release.set()
            self.assertEqual([future.result(2)["data"]["marker"]
                              for future in (first, second, third)], ["first", "second", "third"])

        self.assertEqual(maximum_active, 1)
        self.assertEqual([(event, key) for event, key, _ in trace], [
            ("start", "first"), ("end", "first"),
            ("start", "second"), ("end", "second"),
            ("start", "third"), ("end", "third"),
        ])
        self.assertGreaterEqual(trace[2][2] - trace[1][2], interval - 0.008)
        self.assertGreaterEqual(trace[4][2] - trace[3][2], interval - 0.008)

    def test_interval_is_sampled_inside_configured_range(self):
        # 使用与生产默认一致的区间，避免测试和默认值脱节。
        guard = self.guard(interval_range=(3, 6))
        samples = [guard._sample_interval() for _ in range(60)]
        for sample in samples:
            self.assertGreaterEqual(sample, 3)
            self.assertLessEqual(sample, 6)
        # 区间内必须随机取值，不能每次都是同一个数。
        self.assertGreater(len(set(samples)), 1)

    def test_fixed_interval_when_bounds_are_equal(self):
        guard = self.guard(interval_range=(10, 10))
        self.assertEqual([guard._sample_interval() for _ in range(5)], [10] * 5)

    def test_invalid_interval_range_is_rejected(self):
        for value in ((10, 5), (5,), (-1, 5)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                GuardConfig(interval_range=value)

    def test_cache_expires_at_configured_ttl(self):
        clock = Clock()
        guard = self.guard(clock, cache_ttl=30)
        calls = []

        def load():
            calls.append(1)
            return verified_result(expiry=clock.wall + 3600)

        guard.run("video", load)
        clock.advance(29)
        guard.run("video", load)
        self.assertEqual(len(calls), 1)
        clock.advance(2)
        guard.run("video", load)
        self.assertEqual(len(calls), 2)

    def test_cache_honors_earliest_mirror_expiry_and_safety_margin(self):
        clock = Clock()
        guard = self.guard(clock, cache_ttl=300, expiry_margin=60)
        result = verified_result(expiry=clock.wall + 1000)
        result["data"]["video_list"].append({"expires_at": str(int(clock.wall + 80))})
        calls = []

        def load():
            calls.append(1)
            return copy.deepcopy(result)

        guard.run("video", load)
        clock.advance(19)
        guard.run("video", load)
        self.assertEqual(len(calls), 1)
        clock.advance(2)
        guard.run("video", load)
        self.assertEqual(len(calls), 2)

    def test_wall_clock_jump_cannot_serve_an_expired_download_url(self):
        clock = Clock()
        guard = self.guard(clock, cache_ttl=300, expiry_margin=60)
        calls = []

        def load():
            calls.append(1)
            return verified_result(expiry=clock.wall + 120)

        guard.run("video", load)
        # NTP or a manual correction can move wall time without moving the
        # monotonic deadline used to regulate queue waits and request pacing.
        clock.wall += 61
        guard.run("video", load)
        self.assertEqual(len(calls), 2)

    def test_unknown_expiry_unverified_and_nearly_expired_results_are_not_cached(self):
        clock = Clock()
        baseline = verified_result(expiry=clock.wall + 3600)
        variants = []
        for expiry in (None, "invalid", float("nan"), float("inf"), clock.wall - 1, clock.wall + 59,
                       int(clock.wall * 1000), str(int(clock.wall * 1000))):
            value = copy.deepcopy(baseline)
            value["data"]["expires_at"] = expiry
            variants.append((f"expiry={expiry}", value))
        for name, mutate in [
            ("missing selected expiry", lambda d: d.pop("expires_at")),
            ("unknown mirror expiry", lambda d: d["video_list"].append({"expires_at": None})),
            ("missing mirror expiry", lambda d: d["video_list"].append({})),
            ("numeric milliseconds mirror expiry", lambda d: d["video_list"].append({
                "expires_at": int(clock.wall * 1000)})),
            ("string milliseconds mirror expiry", lambda d: d["video_list"].append({
                "expires_at": str(int(clock.wall * 1000))})),
            ("without probe", lambda d: d.update(probe=None)),
            ("failed probe", lambda d: d.update(probe={"ok": False})),
            ("not original", lambda d: d.update(source_selected=False)),
        ]:
            value = copy.deepcopy(baseline)
            mutate(value["data"])
            variants.append((name, value))

        for name, value in variants:
            with self.subTest(name=name):
                guard = self.guard(clock)
                calls = []

                def load():
                    calls.append(1)
                    return value

                guard.run("video", load)
                guard.run("video", load)
                self.assertEqual(len(calls), 2)

    def test_cache_capacity_uses_recently_used_entries(self):
        guard = self.guard(cache_max_entries=2)
        calls = []

        def run(key):
            def load():
                calls.append(key)
                return verified_result(marker=key)
            return guard.run(key, load)

        for key in ("a", "b", "a", "c", "a", "b"):
            run(key)
        self.assertEqual(calls, ["a", "b", "c", "b"])
        self.assertLessEqual(guard.snapshot()["cached"], 2)

    def test_disabled_cache_still_allows_requests(self):
        for settings in ({"cache_ttl": 0}, {"cache_max_entries": 0}):
            with self.subTest(settings=settings):
                guard = self.guard(**settings)
                calls = []

                def load():
                    calls.append(1)
                    return verified_result()

                guard.run("video", load)
                guard.run("video", load)
                self.assertEqual(len(calls), 2)

    def test_repeated_restrictions_open_breaker_but_cached_success_remains_available(self):
        clock = Clock()
        guard = self.guard(clock, failure_threshold=3, cooldown=900)
        cached = guard.run("cached", lambda: verified_result(expiry=clock.wall + 3600))
        calls = []

        def restricted():
            calls.append(1)
            raise ParseError("upstream_empty_response", "No body")

        for key in range(3):
            with self.assertRaises(ParseError) as caught:
                guard.run(key, restricted)
            self.assertEqual(caught.exception.code, "upstream_empty_response")
        self.assertEqual(guard.snapshot()["state"], "open")
        self.assert_guard_error("upstream_cooldown", lambda: guard.run("later", restricted))
        self.assertEqual(guard.run("cached", restricted), cached)
        self.assertEqual(len(calls), 3)

    def test_opening_breaker_releases_queue_without_calling_loaders(self):
        guard = self.guard(failure_threshold=1)
        entered, release = threading.Event(), threading.Event()
        called = []

        def restricted():
            entered.set()
            self.assertTrue(release.wait(2))
            raise ParseError("upstream_empty_response", "No body")

        def queued():
            called.append(1)
            return verified_result()

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            try:
                first = pool.submit(guard.run, "first", restricted)
                self.assertTrue(entered.wait(1))
                waiting = [pool.submit(guard.run, key, queued) for key in ("second", "third")]
                self.eventually(lambda: guard.snapshot()["pending"] == 2)
            finally:
                release.set()
            with self.assertRaises(ParseError):
                first.result(2)
            for future in waiting:
                self.assert_guard_error("upstream_cooldown", lambda: future.result(2))
        self.assertEqual(called, [])
        self.assertEqual(guard.snapshot()["pending"], 0)

    def test_cooldown_allows_one_trial_and_failed_trial_restarts_cooldown(self):
        clock = Clock()
        guard = self.guard(clock, failure_threshold=1, cooldown=30)

        def restricted():
            raise ParseError("upstream_empty_response", "No body")

        with self.assertRaises(ParseError):
            guard.run("first", restricted)
        clock.advance(29)
        self.assert_guard_error("upstream_cooldown", lambda: guard.run("early", restricted))
        clock.advance(2)
        entered, release = threading.Event(), threading.Event()

        def trial():
            entered.set()
            self.assertTrue(release.wait(2))
            return restricted()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            try:
                future = pool.submit(guard.run, "trial", trial)
                self.assertTrue(entered.wait(1))
                self.assertEqual(guard.snapshot()["state"], "half_open")
                self.assert_guard_error("upstream_cooldown", lambda: guard.run("extra", restricted))
            finally:
                release.set()
            with self.assertRaises(ParseError):
                future.result(2)
        self.assertEqual(guard.snapshot()["state"], "open")
        self.assertGreaterEqual(guard.snapshot()["retry_after"], 29)
        clock.advance(31)
        good = guard.run("recovered", lambda: verified_result(expiry=clock.wall + 3600))
        self.assertTrue(good["data"]["probe"]["ok"])
        self.assertEqual(guard.snapshot()["state"], "closed")
        self.assertEqual(guard.snapshot()["consecutive_failures"], 0)
        guard.run("next", lambda: verified_result(expiry=clock.wall + 3600))

    def test_validation_or_missing_source_errors_do_not_open_breaker(self):
        guard = self.guard(failure_threshold=1)
        for code in ("invalid_input", "invalid_url", "source_unavailable", "probe_failed"):
            with self.subTest(code=code):
                def fail():
                    raise ParseError(code, "Expected failure")

                with self.assertRaises(ParseError) as caught:
                    guard.run(code, fail)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(guard.snapshot()["state"], "closed")
        self.assertTrue(guard.run("good", verified_result)["data"]["probe"]["ok"])

    def test_success_breaks_consecutive_restriction_count(self):
        guard = self.guard(failure_threshold=2)

        def restricted():
            raise ParseError("upstream_empty_response", "No body")

        with self.assertRaises(ParseError):
            guard.run("bad1", restricted)
        guard.run("good", verified_result)
        with self.assertRaises(ParseError):
            guard.run("bad2", restricted)
        self.assertEqual(guard.snapshot()["state"], "closed")
        self.assertEqual(guard.snapshot()["consecutive_failures"], 1)

    def test_full_queue_rejects_new_key_but_existing_work_can_be_shared(self):
        guard = self.guard(max_pending=1)
        entered, release = threading.Event(), threading.Event()
        calls = []

        def load(key):
            calls.append(key)
            if key == "active":
                entered.set()
                self.assertTrue(release.wait(2))
            return verified_result(marker=key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            try:
                active = pool.submit(guard.run, "active", lambda: load("active"))
                self.assertTrue(entered.wait(1))
                pending = pool.submit(guard.run, "pending", lambda: load("pending"))
                self.eventually(lambda: guard.snapshot()["pending"] == 1)
                shared = pool.submit(guard.run, "pending", lambda: self.fail("Should coalesce"))
                self.eventually(lambda: guard.snapshot()["coalesced"] == 1)
                self.assert_guard_error("busy", lambda: guard.run("excess", verified_result))
            finally:
                release.set()
            active.result(2)
            self.assertEqual(pending.result(2), shared.result(2))
        self.assertEqual(calls, ["active", "pending"])

    def test_timed_out_queued_work_is_removed_without_running(self):
        guard = self.guard(wait_timeout=0.06)
        entered, release = threading.Event(), threading.Event()
        calls = []

        def active_loader():
            entered.set()
            self.assertTrue(release.wait(2))
            return verified_result()

        def stale_loader():
            calls.append("stale")
            return verified_result()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            try:
                active = pool.submit(guard.run, "active", active_loader)
                self.assertTrue(entered.wait(1))
                queued = pool.submit(guard.run, "stale", stale_loader)
                self.assert_guard_error("queue_timeout", lambda: queued.result(1))
                self.assert_guard_error("queue_timeout", lambda: active.result(1))
                self.eventually(lambda: guard.snapshot()["pending"] == 0)
            finally:
                release.set()
        self.eventually(lambda: guard.snapshot()["active"] == 0)
        guard.run("next", verified_result)
        self.assertEqual(calls, [])

    def test_timed_out_active_work_still_deduplicates_until_completion(self):
        guard = self.guard(wait_timeout=0.06)
        entered, release = threading.Event(), threading.Event()
        calls = []

        def loader():
            calls.append(1)
            entered.set()
            self.assertTrue(release.wait(2))
            return verified_result()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            try:
                first = pool.submit(guard.run, "same", loader)
                self.assertTrue(entered.wait(1))
                self.assert_guard_error("queue_timeout", lambda: first.result(1))
                second = pool.submit(guard.run, "same", loader)
                self.eventually(lambda: guard.snapshot()["coalesced"] == 1)
            finally:
                release.set()
            self.assertTrue(second.result(1)["data"]["probe"]["ok"])
        self.assertEqual(calls, [1])

    def test_one_timed_out_waiter_does_not_cancel_another_waiters_queued_work(self):
        guard = self.guard(wait_timeout=0.2)
        entered, release = threading.Event(), threading.Event()
        calls = []

        def active_loader():
            entered.set()
            self.assertTrue(release.wait(2))
            return verified_result()

        def queued_loader():
            calls.append(1)
            return verified_result()

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            try:
                active = pool.submit(guard.run, "active", active_loader)
                self.assertTrue(entered.wait(1))
                first_waiter = pool.submit(guard.run, "queued", queued_loader)
                self.eventually(lambda: guard.snapshot()["pending"] == 1)
                time.sleep(0.1)
                second_waiter = pool.submit(guard.run, "queued", queued_loader)
                self.eventually(lambda: guard.snapshot()["coalesced"] == 1)
                self.assert_guard_error("queue_timeout", lambda: first_waiter.result(1))
                self.assert_guard_error("queue_timeout", lambda: active.result(1))
                self.assertEqual(guard.snapshot()["pending"], 1)
            finally:
                release.set()
            self.assertTrue(second_waiter.result(1)["data"]["probe"]["ok"])
        self.assertEqual(calls, [1])

    def test_unexpected_loader_exception_does_not_kill_worker(self):
        guard = self.guard()

        def fail():
            raise ValueError("Unexpected test failure")

        with self.assertRaises(ValueError):
            guard.run("bad", fail)
        result = guard.run("good", verified_result)
        self.assertTrue(result["data"]["probe"]["ok"])
        self.assertEqual(guard.snapshot()["active"], 0)

    def test_cache_write_failure_still_returns_parse_result_and_keeps_worker_alive(self):
        guard = self.guard()
        parsed = verified_result(marker="first")
        with patch.object(guard, "_save_cache", side_effect=RuntimeError("Cache storage unavailable")):
            self.assertEqual(guard.run("video", lambda: parsed), parsed)
        second = guard.run("video", lambda: verified_result(marker="second"))
        self.assertEqual(second["data"]["marker"], "second")
        self.assertEqual(guard.snapshot()["active"], 0)

    def test_close_releases_queue_and_rejects_new_work_without_waiting_for_loader(self):
        guard = self.guard()
        entered, release = threading.Event(), threading.Event()
        calls = []

        def active_loader():
            entered.set()
            self.assertTrue(release.wait(2))
            return verified_result()

        def queued_loader():
            calls.append(1)
            return verified_result()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            try:
                active = pool.submit(guard.run, "active", active_loader)
                self.assertTrue(entered.wait(1))
                queued = pool.submit(guard.run, "queued", queued_loader)
                self.eventually(lambda: guard.snapshot()["pending"] == 1)
                before = time.monotonic()
                guard.close()
                self.assertLess(time.monotonic() - before, 0.5)
                self.assert_guard_error("busy", lambda: queued.result(1))
                self.assert_guard_error("busy", lambda: guard.run("new", verified_result))
                self.assertTrue(guard.snapshot()["shutdown"])
            finally:
                release.set()
            try:
                active.result(1)
            except GuardError as exc:
                self.assertEqual(exc.code, "busy")
        self.assertEqual(calls, [])
        guard.close()


if __name__ == "__main__":
    unittest.main()
