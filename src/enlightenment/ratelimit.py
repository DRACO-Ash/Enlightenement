"""Two-tier rate limiting.

A coarse limiter protects the process on every route; a strict limiter protects the
expensive, state-changing routes. Both are fixed-window counters keyed by caller, with
a bounded key table so a flood of distinct callers cannot grow memory without limit.
Time is injected so the tests are deterministic rather than wall-clock dependent.
"""

from __future__ import annotations

import time
from collections.abc import Callable

#: Upper bound on tracked keys. Beyond this the oldest windows are evicted first.
MAX_TRACKED_KEYS = 4096


class RateLimiter:
    """Allow at most ``limit`` calls per ``window_seconds`` for each key."""

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        *,
        now: Callable[[], float] | None = None,
        max_keys: int = MAX_TRACKED_KEYS,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window = window_seconds
        self._now = now if now is not None else time.monotonic
        self._max_keys = max_keys
        # key -> (window start, calls counted in that window)
        self._windows: dict[str, tuple[float, int]] = {}

    @property
    def limit(self) -> int:
        """The number of calls allowed per window."""
        return self._limit

    def allow(self, key: str) -> bool:
        """Record a call for ``key`` and return whether it is within the limit."""
        now = self._now()
        start, count = self._windows.get(key, (now, 0))
        if now - start >= self._window:
            start, count = now, 0
        count += 1
        self._windows[key] = (start, count)
        # Pruning runs AFTER the call is recorded, so the table size is bounded at every
        # observable moment rather than only before an insert.
        self._prune(now)
        return count <= self._limit

    def _prune(self, now: float) -> None:
        """Drop finished windows, then hard-cap the table oldest-window-first."""
        expired = [k for k, (start, _) in self._windows.items() if now - start >= self._window]
        for key in expired:
            del self._windows[key]
        overflow = len(self._windows) - self._max_keys
        if overflow > 0:
            oldest = sorted(self._windows, key=lambda k: self._windows[k][0])[:overflow]
            for key in oldest:
                del self._windows[key]
