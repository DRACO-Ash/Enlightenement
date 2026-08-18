"""The limiter holds its boundary exactly, bounds its memory, and fails CLOSED.

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
    limiter = RateLimiter(3, 60.0, now=FakeClock())
    assert [limiter.allow("a") for _ in range(3)] == [True, True, True]
    assert limiter.allow("a") is False


def test_one_call_below_the_limit_still_passes() -> None:
    limiter = RateLimiter(3, 60.0, now=FakeClock())
    assert [limiter.allow("a") for _ in range(2)] == [True, True]


def test_keys_are_independent() -> None:
    limiter = RateLimiter(1, 60.0, now=FakeClock())
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


def test_a_finished_window_is_dropped_from_the_table() -> None:
    """The expiry sweep, asserted directly rather than only through the hard cap."""
    clock = FakeClock()
    limiter = RateLimiter(5, 60.0, now=clock)
    limiter.allow("a")
    limiter.allow("b")
    assert limiter.tracked_keys() == 2
    clock.advance(60.0)
    limiter.allow("a")
    assert limiter.tracked_keys() == 1


def test_a_full_table_refuses_a_new_caller_rather_than_evicting_a_tracked_one() -> None:
    """Fail closed. Evicting resets the evicted caller's count, which opens the limiter
    under exactly the key-table pressure it exists to survive.
    """
    limiter = RateLimiter(5, 3600.0, now=FakeClock(), max_keys=8)
    admitted = [limiter.allow(f"caller-{index}") for index in range(8)]
    assert all(admitted)
    assert limiter.allow("caller-8") is False
    assert limiter.tracked_keys() == 8


def test_a_tracked_caller_is_still_counted_when_the_table_is_full() -> None:
    limiter = RateLimiter(2, 3600.0, now=FakeClock(), max_keys=2)
    assert limiter.allow("a") is True
    assert limiter.allow("b") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False


def test_the_key_table_never_exceeds_its_bound_under_a_flood() -> None:
    limiter = RateLimiter(5, 3600.0, now=FakeClock(), max_keys=8)
    for index in range(200):
        limiter.allow(f"caller-{index}")
    assert limiter.tracked_keys() <= 8


def test_the_limit_is_reported() -> None:
    assert RateLimiter(7, 60.0).limit == 7


@pytest.mark.parametrize("limit", [0, -1])
def test_a_nonsensical_limit_is_refused(limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        RateLimiter(limit, 60.0)


@pytest.mark.parametrize("window", [0.0, -5.0])
def test_a_nonsensical_window_is_refused(window: float) -> None:
    with pytest.raises(ValueError, match="window_seconds must be positive"):
        RateLimiter(1, window)
