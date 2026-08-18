"""The limiter holds its boundary exactly and bounds its own memory.

The boundary is mutated in both directions: a limiter that allowed one call more or one
call fewer than it claims would fail here.
"""

from __future__ import annotations

import pytest

from enlightenment.ratelimit import RateLimiter


class FakeClock:
    """A monotonic clock the test advances explicitly."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_allows_exactly_the_limit_then_refuses() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3, 60.0, now=clock)
    assert [limiter.allow("a") for _ in range(3)] == [True, True, True]
    assert limiter.allow("a") is False


def test_one_call_below_the_limit_still_passes() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3, 60.0, now=clock)
    assert [limiter.allow("a") for _ in range(2)] == [True, True]


def test_keys_are_independent() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 60.0, now=clock)
    assert limiter.allow("a") is True
    assert limiter.allow("b") is True
    assert limiter.allow("a") is False


def test_window_resets_only_after_it_elapses() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 60.0, now=clock)
    assert limiter.allow("a") is True
    clock.advance(59.9)
    assert limiter.allow("a") is False
    clock.advance(0.1)
    assert limiter.allow("a") is True


def test_key_table_is_capped_so_a_flood_cannot_grow_memory() -> None:
    clock = FakeClock()
    limiter = RateLimiter(5, 3600.0, now=clock, max_keys=8)
    for index in range(200):
        limiter.allow(f"caller-{index}")
    assert len(limiter._windows) <= 8


def test_the_limit_is_reported() -> None:
    assert RateLimiter(7, 60.0).limit == 7


@pytest.mark.parametrize(("limit", "window"), [(0, 60.0), (-1, 60.0)])
def test_a_nonsensical_limit_is_refused(limit: int, window: float) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        RateLimiter(limit, window)


@pytest.mark.parametrize("window", [0.0, -5.0])
def test_a_nonsensical_window_is_refused(window: float) -> None:
    with pytest.raises(ValueError, match="window_seconds must be positive"):
        RateLimiter(1, window)
