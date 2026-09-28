"""Process-wide queue, request coalescing, result cache and upstream cooldown.

One guard belongs to one service process.  Its loader must perform the complete
parse, including media verification, so all expensive work shares the same
concurrency limit.  No URLs, credentials or cache keys are logged or exposed.
"""

from __future__ import annotations

import copy
import logging
import math
import random
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any

from .client import ParseError

_LOG = logging.getLogger(__name__)
_RESTRICTION_CODES = frozenset({
    "upstream_empty_response", "upstream_non_json", "upstream_forbidden",
    "upstream_rate_limited", "credentials_required", "credentials_rejected",
})


@dataclass(frozen=True)
class GuardConfig:
    # 相邻上游任务之间的等待区间（秒）：在下限与上限之间随机取值；两个值相同表示固定间隔。
    interval_range: tuple[float, float] = (3, 6)
    cache_ttl: float = 300
    cache_max_entries: int = 128
    max_pending: int = 6
    wait_timeout: float = 150
    failure_threshold: int = 3
    cooldown: float = 900
    expiry_margin: float = 60

    def __post_init__(self) -> None:
        for name, minimum, maximum, inclusive in (
            ("cache_ttl", 0, 86400, True),
            ("wait_timeout", 0, 3600, False),
            ("cooldown", 0, 86400, False),
            ("expiry_margin", 0, 86400, True),
        ):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or value > maximum
                    or (value < minimum if inclusive else value <= minimum)
                    or not math.isfinite(value)):
                raise ValueError(f"{name} must be a finite number in the allowed range")
        values = tuple(self.interval_range) if not isinstance(self.interval_range, (int, float)) else ()
        if len(values) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float))
                                   or not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("interval_range must be two non-negative numbers")
        if values[0] > values[1]:
            raise ValueError("interval_range lower bound must not exceed the upper bound")
        for name, minimum, maximum in (
            ("cache_max_entries", 0, 10000),
            ("max_pending", 0, 1000),
            ("failure_threshold", 1, 1000),
        ):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not minimum <= value <= maximum):
                raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")

    @property
    def interval_upper(self) -> float:
        """区间上限，用作重试提示；单一配置值时即该值本身。"""
        return float(self.interval_range[1])


class GuardError(ParseError):
    def __init__(self, code: str, message: str, retry_after: float):
        super().__init__(code, message)
        self.retry_after = max(1, math.ceil(retry_after))


@dataclass
class _Task:
    key: Hashable
    loader: Callable[[], dict]
    waiters: int = 0
    started: bool = False
    done: bool = False
    result: dict | None = None
    error: BaseException | None = None


@dataclass
class _Cached:
    result: dict
    deadline: float
    wall_deadline: float


def _detached_error(error: BaseException) -> BaseException:
    """Each waiting caller gets its own traceback, without retaining a loader."""
    if isinstance(error, GuardError):
        return GuardError(error.code, str(error), error.retry_after)
    if isinstance(error, ParseError):
        return ParseError(error.code, str(error))
    try:
        return copy.copy(error).with_traceback(None)
    except Exception:
        return RuntimeError(str(error))


def _expiry(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = float(value)
    except (ValueError, OverflowError):
        return None
    # The upstream contract is Unix seconds.  A 13-digit millisecond value
    # must not accidentally extend a near-expiry URL's cache lifetime.
    return parsed if math.isfinite(parsed) and 0 < parsed < 1e12 else None


class RequestGuard:
    def __init__(self, config: GuardConfig | None = None, *,
                 clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time):
        self.config = config if config is not None else GuardConfig()
        self._clock = clock
        self._wall_clock = wall_clock
        self._condition = threading.Condition()
        self._pending: deque[_Task] = deque()
        self._tasks: dict[Hashable, _Task] = {}
        self._cache: OrderedDict[Hashable, _Cached] = OrderedDict()
        self._active: _Task | None = None
        self._shutdown = False
        self._state = "closed"
        self._consecutive_failures = 0
        self._cooldown_until = 0.0
        self._next_start = 0.0
        self._counts = dict(requests=0, cache_hits=0, coalesced=0, started=0,
                            completed=0, rejected=0, timeouts=0)
        self._thread = threading.Thread(target=self._work,
                                        name="parser-request-guard", daemon=True)
        self._thread.start()

    def run(self, key: Hashable, loader: Callable[[], dict]) -> dict:
        """Run one complete parse, or join an identical request already queued.

        A caller timing out does not cancel a running parse.  That parse can
        still satisfy another caller and populate the success cache.
        """
        hash(key)
        if not callable(loader):
            raise TypeError("loader must be callable")
        with self._condition:
            self._counts["requests"] += 1
            if self._shutdown:
                self._counts["rejected"] += 1
                raise self._closed_error()
            cached = self._cached(key)
            if cached is not None:
                self._counts["cache_hits"] += 1
                return copy.deepcopy(cached)

            task = self._tasks.get(key)
            if task is not None:
                self._counts["coalesced"] += 1
            else:
                now = self._clock()
                if (self._state == "half_open" or
                        (self._state == "open" and now < self._cooldown_until)):
                    self._counts["rejected"] += 1
                    raise self._cooldown_error()
                # With no waiting slots configured, admit the first job when
                # idle so that the worker can take its sole execution slot.
                if (len(self._pending) >= self.config.max_pending
                        and (self._active is not None or self._pending)):
                    self._counts["rejected"] += 1
                    raise GuardError("busy", "解析等待队列已满，请稍后重试",
                                     self.config.interval_upper)
                if self._state == "open":
                    self._state = "half_open"
                task = _Task(key=key, loader=loader)
                self._tasks[key] = task
                self._pending.append(task)
            task.waiters += 1
            self._condition.notify_all()
            deadline = self._clock() + self.config.wait_timeout
            try:
                while not task.done:
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        self._counts["timeouts"] += 1
                        raise GuardError("queue_timeout", "等待解析结果超时，请稍后重试",
                                         self.config.interval_upper)
                    self._condition.wait(remaining)
                if task.error is not None:
                    raise _detached_error(task.error)
                assert task.result is not None
                return copy.deepcopy(task.result)
            finally:
                task.waiters -= 1
                if not task.done and not task.started and task.waiters == 0:
                    self._pending.remove(task)
                    self._tasks.pop(task.key, None)
                    # A half-open request that never ran is not a failed probe.
                    if self._state == "half_open":
                        self._state = "open"
                    self._condition.notify_all()

    def snapshot(self) -> dict:
        """Return operational state only; never include keys or request data."""
        with self._condition:
            self._purge_cache()
            self._condition.notify_all()
            return {
                "state": self._state,
                "shutdown": self._shutdown,
                "active": int(self._active is not None),
                "pending": len(self._pending),
                "inflight": len(self._tasks),
                "cached": len(self._cache),
                "consecutive_failures": self._consecutive_failures,
                "retry_after": self._retry_after(),
                **self._counts,
            }

    def close(self) -> None:
        """Wake all callers immediately; an active loader may finish in place."""
        with self._condition:
            if self._shutdown:
                return
            self._shutdown = True
            self._cancel_pending(self._closed_error())
            if self._active is not None:
                self._active.error = self._closed_error()
                self._active.done = True
                self._tasks.pop(self._active.key, None)
            self._cache.clear()
            self._condition.notify_all()

    @staticmethod
    def _closed_error() -> GuardError:
        return GuardError("busy", "解析服务正在停止，请稍后重试", 1)

    def _retry_after(self) -> int:
        if self._state == "open":
            return max(0, math.ceil(self._cooldown_until - self._clock()))
        if self._state == "half_open":
            return max(1, math.ceil(self.config.interval_upper))
        return 0

    def _cooldown_error(self) -> GuardError:
        return GuardError("upstream_cooldown", "上游连续返回受限响应，解析服务正在冷却，请稍后重试",
                          self._retry_after())

    def _purge_cache(self) -> None:
        now, wall_now = self._clock(), self._wall_clock()
        for key in list(self._cache):
            entry = self._cache[key]
            if now >= entry.deadline or wall_now >= entry.wall_deadline:
                del self._cache[key]

    def _cached(self, key: Hashable) -> dict | None:
        self._purge_cache()
        entry = self._cache.get(key)
        if entry is None:
            return None
        self._cache.move_to_end(key)
        return entry.result

    def _save_cache(self, key: Hashable, result: dict) -> None:
        if not self.config.cache_ttl or not self.config.cache_max_entries:
            return
        data = result.get("data")
        if (result.get("code") != 0 or isinstance(result.get("code"), bool)
                or not isinstance(data, dict) or data.get("source_selected") is not True
                or not isinstance(data.get("probe"), dict)
                or data["probe"].get("ok") is not True):
            return
        rows = data.get("video_list")
        if not isinstance(rows, list) or not rows:
            return
        expires = [_expiry(data.get("expires_at"))]
        for row in rows:
            if not isinstance(row, dict):
                return
            expires.append(_expiry(row.get("expires_at")))
        if any(value is None for value in expires):
            return
        # Check every returned candidate: even an unselected URL must not
        # outlive its upstream validity simply because the selected one does.
        wall_deadline = min(expires) - self.config.expiry_margin
        ttl = min(self.config.cache_ttl, wall_deadline - self._wall_clock())
        if ttl <= 0:
            return
        self._purge_cache()
        self._cache[key] = _Cached(result, self._clock() + ttl, wall_deadline)
        self._cache.move_to_end(key)
        while len(self._cache) > self.config.cache_max_entries:
            self._cache.popitem(last=False)

    def _cancel_pending(self, error: GuardError) -> None:
        while self._pending:
            task = self._pending.popleft()
            task.error = _detached_error(error)
            task.done = True
            self._tasks.pop(task.key, None)

    def _sample_interval(self) -> float:
        """在配置的区间内随机取一个间隔，避免出现固定周期；上下限相同时返回固定值。"""
        lower, upper = self.config.interval_range
        if lower <= 0 and upper <= 0:
            return 0.0
        if lower >= upper:
            return upper
        return random.uniform(lower, upper)

    def _open_circuit(self) -> None:
        self._state = "open"
        self._cooldown_until = self._clock() + self.config.cooldown
        self._cancel_pending(self._cooldown_error())
        _LOG.warning("parser_cooldown_open failures=%s retry_after=%s",
                     self._consecutive_failures, self._retry_after())

    def _work(self) -> None:
        while True:
            with self._condition:
                while True:
                    if self._shutdown:
                        return
                    if not self._pending:
                        self._condition.wait()
                        continue
                    delay = self._next_start - self._clock()
                    if delay > 0:
                        self._condition.wait(delay)
                        continue
                    task = self._pending.popleft()
                    task.started = True
                    self._active = task
                    self._counts["started"] += 1
                    break
            result, error = None, None
            try:
                result = task.loader()
                if not isinstance(result, dict):
                    raise TypeError("parse loader must return a dictionary")
                result = copy.deepcopy(result)
            except BaseException as exc:
                # Keep the daemon alive and release waiters even if a loader
                # terminates abnormally; do not retain its traceback/locals.
                error = _detached_error(exc)
            with self._condition:
                self._counts["completed"] += 1
                self._next_start = self._clock() + self._sample_interval()
                self._active = None
                self._tasks.pop(task.key, None)
                if not self._shutdown:
                    task.result, task.error = result, error
                    succeeded = (error is None and result.get("code") == 0
                                 and not isinstance(result.get("code"), bool))
                    code = (getattr(error, "code", None) if error is not None
                            else result.get("code"))
                    if succeeded:
                        self._consecutive_failures = 0
                        self._state = "closed"
                        self._cooldown_until = 0.0
                        try:
                            self._save_cache(task.key, result)
                        except Exception:
                            # Caching is optional: malformed cache metadata
                            # must never terminate the worker or strand callers.
                            self._cache.pop(task.key, None)
                            _LOG.warning("parser_cache_skipped reason=cache_error")
                    else:
                        if isinstance(code, str) and code in _RESTRICTION_CODES:
                            self._consecutive_failures += 1
                        if (self._state == "half_open" or
                                self._consecutive_failures >= self.config.failure_threshold):
                            self._open_circuit()
                    task.done = True
                self._condition.notify_all()
