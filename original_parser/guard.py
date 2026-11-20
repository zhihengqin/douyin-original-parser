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
    # 每个工作线程完成任务后的等待区间（秒）；相同作品仍只执行一次。
    interval_range: tuple[float, float] = (0.5, 1.0)
    worker_count: int = 3
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
            ("worker_count", 1, 32),
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
    generation: int = 0
    probe: bool = False


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
        self._active: dict[Hashable, _Task] = {}
        self._shutdown = False
        self._state = "closed"
        self._consecutive_failures = 0
        self._cooldown_until = 0.0
        self._generation = 0
        self._counts = dict(requests=0, cache_hits=0, coalesced=0, started=0,
                            completed=0, rejected=0, timeouts=0)
        self._threads = [threading.Thread(target=self._work,
                                         name=f"parser-request-guard-{index + 1}", daemon=True)
                         for index in range(self.config.worker_count)]
        for thread in self._threads:
            thread.start()

    def run(self, key: Hashable, loader: Callable[[], dict], *, force_refresh: bool = False) -> dict:
        """Run one complete parse, or join an identical request already queued.

        A caller timing out does not cancel a running parse.  That parse can
        still satisfy another caller and populate the success cache.
        """
        hash(key)
        if not callable(loader):
            raise TypeError("loader must be callable")
        if not isinstance(force_refresh, bool):
            raise TypeError("force_refresh must be bool")
        with self._condition:
            self._counts["requests"] += 1
            if self._shutdown:
                self._counts["rejected"] += 1
                raise self._closed_error()
            # 下载方发现直链失效时，必须清除旧结果；刷新失败也不能回落到旧地址。
            # 后续仍复用同作品的在途任务，并受原有队列、间隔与冷却控制。
            if force_refresh:
                self._cache.pop(key, None)
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
                # 空闲工作线程各自可接一条，额外等待任务受队列容量约束。
                capacity = self.config.max_pending + self.config.worker_count - len(self._active)
                if len(self._pending) >= capacity:
                    self._counts["rejected"] += 1
                    raise GuardError("busy", "解析等待队列已满，请稍后重试",
                                     self.config.interval_upper)
                probe = self._state == "open"
                if probe:
                    self._state = "half_open"
                task = _Task(key=key, loader=loader, generation=self._generation, probe=probe)
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
                    # 尚未执行的探测无人等待时，恢复到冷却状态，允许后续请求重新探测。
                    if task.probe and task.generation == self._generation and self._state == "half_open":
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
                "workers": self.config.worker_count,
                "active": len(self._active),
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
            for task in self._active.values():
                task.error = self._closed_error()
                task.done = True
                self._tasks.pop(task.key, None)
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
                or not isinstance(data, dict)
                or not isinstance(data.get("probe"), dict)
                or data["probe"].get("ok") is not True):
            return
        if (data.get("source_selected") is not True
                or data.get("fallback_used") is not False
                or data.get("source_evidence") not in ("official_quality", "official_play_hash")):
            return
        rows = data.get("video_list")
        if not isinstance(rows, list) or not rows:
            return
        if any(not isinstance(row, dict)
               or row.get("quality") != "source"
               or row.get("source_evidence") not in ("official_quality", "official_play_hash")
               for row in rows):
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
        self._generation += 1
        self._cooldown_until = self._clock() + self.config.cooldown
        self._cancel_pending(self._cooldown_error())
        _LOG.warning("解析服务进入冷却，限制失败次数=%s，建议等待秒数=%s",
                     self._consecutive_failures, self._retry_after())

    def _work(self) -> None:
        next_start = 0.0
        while True:
            with self._condition:
                while True:
                    if self._shutdown:
                        return
                    if not self._pending:
                        self._condition.wait()
                        continue
                    delay = next_start - self._clock()
                    if delay > 0:
                        self._condition.wait(delay)
                        continue
                    task = self._pending.popleft()
                    task.started = True
                    self._active[task.key] = task
                    self._counts["started"] += 1
                    break
            result, error = None, None
            try:
                result = task.loader()
                if not isinstance(result, dict):
                    raise TypeError("parse loader must return a dictionary")
                result = copy.deepcopy(result)
            except BaseException as exc:
                # 单个任务异常不能终止工作线程，也不长期保留调用栈。
                error = _detached_error(exc)
            with self._condition:
                self._counts["completed"] += 1
                next_start = self._clock() + self._sample_interval()
                self._active.pop(task.key, None)
                self._tasks.pop(task.key, None)
                if not self._shutdown:
                    task.result, task.error = result, error
                    succeeded = (error is None and result.get("code") == 0
                                 and not isinstance(result.get("code"), bool))
                    code = (getattr(error, "code", None) if error is not None
                            else result.get("code"))
                    # 冷却前已发出的旧任务可以返回结果，但不能提前关闭新一轮冷却。
                    current_generation = task.generation == self._generation
                    if succeeded:
                        if current_generation:
                            self._consecutive_failures = 0
                            self._state = "closed"
                            self._cooldown_until = 0.0
                        try:
                            self._save_cache(task.key, result)
                        except Exception:
                            # 缓存异常不能终止工作线程或使等待者失去结果。
                            self._cache.pop(task.key, None)
                            _LOG.warning("解析结果缓存写入失败，已跳过缓存")
                    elif current_generation:
                        if isinstance(code, str) and code in _RESTRICTION_CODES:
                            self._consecutive_failures += 1
                        if (self._state == "half_open" or
                                self._consecutive_failures >= self.config.failure_threshold):
                            self._open_circuit()
                    task.done = True
                self._condition.notify_all()
