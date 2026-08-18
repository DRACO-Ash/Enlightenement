"""Two-tier rate limiting.

A coarse limiter protects the process on every route; a strict limiter protects the
expensive, state-changing routes. Both are fixed-window counters keyed by caller, with
a bounded key table so a flood of distinct callers cannot grow memory without limit.
Time is injected so the tests are deterministic rather than wall-clock dependent.

The table bound fails CLOSED. When the table is full, a caller that is not already
tracked is refused rather than admitted by evicting a tracked caller: evicting resets
the evicted caller's count, which is a limiter that opens under exactly the pressure it
exists to handle.
"""

from __future__ import annotations

import time
from collections.abc import Callable

#: Upper bound on tracked keys. Beyond this an untracked key is refused, not admitted.
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
        # key -> (window start, calls counted in that window). Insertion-ordered, which
        # keeps the expiry sweep linear and needs no sort.
        self._windows: dict[str, tuple[float, int]] = {}

    @property
    def limit(self) -> int:
        """The number of calls allowed per window."""
        return self._limit

    def allow(self, key: str) -> bool:
        """Record a call for ``key`` and return whether it is within the limit."""
        now = self._now()
        self._drop_expired(now)
        tracked = self._windows.get(key)
        if tracked is None and len(self._windows) >= self._max_keys:
            # Fail closed: the table is full of live windows, so refuse the new caller
            # rather than evicting a tracked one and resetting its count.
            return False
        start, count = tracked if tracked is not None else (now, 0)
        if now - start >= self._window:
            start, count = now, 0
        self._windows[key] = (start, count + 1)
        return count + 1 <= self._limit

    def _drop_expired(self, now: float) -> None:
        """Remove every window that has finished. Linear, no sort."""
        expired = [k for k, (start, _) in self._windows.items() if now - start >= self._window]
        for key in expired:
            del self._windows[key]

    def tracked_keys(self) -> int:
        """How many callers currently hold a live window. Exposed so a test can assert
        the memory bound without reaching into a private attribute.
        """
        return len(self._windows)
