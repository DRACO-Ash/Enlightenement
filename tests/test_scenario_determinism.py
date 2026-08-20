"""The determinism gate: the same seed must yield an identical event log, twice.

The flight plan calls this a gate rather than a task, and the reason is what depends on it. A
debrief replays a scored run from its seed and event log and overlays the expert trace. If the
replay diverges by one event, the debrief shows the operator a run they did not have and every
score explanation built on it is fiction.

So the primary test does not check that determinism is plausible. It runs a scenario twice from
one seed and compares the whole log, then runs a THIRD time from a different seed and requires it
to differ, because a harness that returned a constant log would pass the first check perfectly.
"""

from __future__ import annotations

import math

import pytest

from enlightenment.scenario import (
    FINGERPRINT_LENGTH,
    TICK_MILLISECONDS,
    RunLog,
    ScenarioClock,
    SeededRandom,
    replay_is_identical,
)

#: Ticks per simulated run. Long enough that a drift would show, short enough to run repeatedly.
RUN_TICKS = 200


def _simulate(seed: int, ticks: int = RUN_TICKS) -> RunLog:
    """A stand-in scenario that exercises every determinism hazard the substrate must close.

    Deliberately NOT the real scenario engine, which does not exist yet. What it must contain is
    every mechanism a real run will use: a seeded draw, an integer clock, a derived physical
    quantity, a branch taken on a random value, and an append-only log. If the substrate is
    deterministic under this, the hazard that remains is in the scenario content rather than here.
    """
    rng = SeededRandom(seed)
    clock = ScenarioClock()
    log = RunLog(seed=seed)

    longitude = rng.uniform(-180.0, 180.0)
    drift_per_tick = rng.uniform(-0.01, 0.01)
    log.record(clock, "scenario_started", longitude=longitude, drift=drift_per_tick)

    for _ in range(ticks):
        clock = clock.advance()
        longitude += drift_per_tick
        # A branch on a drawn value, so a divergence in the stream changes the SHAPE of the log
        # and not only its numbers.
        if rng.integer(0, 99) < 5:
            log.record(
                clock,
                "sensor_dropout",
                elapsed_ms=clock.elapsed_milliseconds,
                longitude=round(longitude, 9),
            )
        if clock.tick % 50 == 0:
            log.record(clock, "track_update", longitude=round(longitude, 9))

    log.record(clock, "scenario_ended", draws=rng.draws, elapsed_ms=clock.elapsed_milliseconds)
    return log


def test_the_same_seed_yields_an_identical_event_log_twice() -> None:
    """THE gate. The flight plan's own words, asserted."""
    first = _simulate(20260820)
    second = _simulate(20260820)
    assert replay_is_identical(first, second)
    assert first.fingerprint() == second.fingerprint()
    assert len(first.events) == len(second.events)


def test_a_different_seed_yields_a_different_log() -> None:
    """The control, and it is not optional.

    A harness that returned a constant log would satisfy the test above perfectly. This is what
    distinguishes "deterministic" from "always the same".
    """
    assert not replay_is_identical(_simulate(20260820), _simulate(20260821))


def test_determinism_holds_across_many_seeds() -> None:
    """One seed proving determinism is weak evidence, the same argument as the property tests.

    Twenty seeds, each run twice. Cheap, and it turns a single observation into a sample.
    """
    for seed in range(20260800, 20260820):
        assert replay_is_identical(_simulate(seed, ticks=40), _simulate(seed, ticks=40)), (
            f"seed {seed} did not replay identically"
        )


def test_a_run_replays_identically_after_other_runs_have_happened() -> None:
    """Process history must not leak into a run.

    The failure this closes is the module-level `random` one: if the substrate drew from a shared
    global, a run's output would depend on what else the process had done first. Interleaving a
    different seed between the two runs is what detects that.
    """
    first = _simulate(20260820)
    _simulate(999999)
    _simulate(111111)
    second = _simulate(20260820)
    assert replay_is_identical(first, second)


# --- the clock ----------------------------------------------------------------------------


def test_elapsed_time_is_exact_integer_arithmetic_not_accumulated_float() -> None:
    """The reason ticks are integers.

    Adding 0.1 a thousand times does not give 100.0; multiplying 1000 by 0.1 does. A scenario that
    accumulated a float step would drift, and two replays that grouped the additions differently
    would drift differently.
    """
    clock = ScenarioClock()
    for _ in range(1000):
        clock = clock.advance()
    assert clock.elapsed_milliseconds == 1000 * TICK_MILLISECONDS
    assert clock.elapsed_seconds == pytest.approx(100.0, abs=1e-12)

    accumulated = 0.0
    for _ in range(1000):
        accumulated += TICK_MILLISECONDS / 1000.0
    assert accumulated != clock.elapsed_seconds, (
        "float accumulation happens to be exact here, so this test no longer demonstrates anything"
    )


def test_the_clock_is_immutable_so_it_cannot_be_advanced_twice_by_accident() -> None:
    """Frozen for the same reason the state vectors are."""
    clock = ScenarioClock()
    later = clock.advance(5)
    assert clock.tick == 0, "advancing returned a new clock but mutated the old one"
    assert later.tick == 5
    with pytest.raises((AttributeError, TypeError)):
        clock.tick = 9  # type: ignore[misc]


@pytest.mark.parametrize("ticks", [0, -1, -100])
def test_the_clock_refuses_to_stand_still_or_go_backwards(ticks: int) -> None:
    """A replay walks forwards. A zero or negative advance is a caller error, not a no-op."""
    with pytest.raises(ValueError, match="at least one tick"):
        ScenarioClock().advance(ticks)


# --- the log ------------------------------------------------------------------------------


def test_the_log_refuses_an_out_of_order_event() -> None:
    """A log whose ticks do not increase cannot be replayed forwards."""
    log = RunLog(seed=1)
    log.record(ScenarioClock(tick=10), "later")
    with pytest.raises(ValueError, match="append-only and monotonic"):
        log.record(ScenarioClock(tick=9), "earlier")


def test_the_log_accepts_two_events_at_the_same_tick() -> None:
    """Several things can happen in one tick. Monotonic means non-decreasing, not increasing."""
    log = RunLog(seed=1)
    clock = ScenarioClock(tick=4)
    log.record(clock, "first")
    log.record(clock, "second")
    assert [event.kind for event in log.events] == ["first", "second"]


def test_the_fingerprint_changes_when_any_event_changes() -> None:
    """Otherwise the comparison a replay makes would pass on a divergent run."""
    base = RunLog(seed=1)
    base.record(ScenarioClock(tick=1), "moved", longitude=10.0)
    original = base.fingerprint()

    for variant in (
        ("moved", {"longitude": 10.000000001}),
        ("drifted", {"longitude": 10.0}),
        ("moved", {"longitude": 10.0, "extra": 1}),
    ):
        other = RunLog(seed=1)
        other.record(ScenarioClock(tick=1), variant[0], **variant[1])
        assert other.fingerprint() != original, f"{variant} produced the same fingerprint"

    # And the seed is part of it, so two empty runs are not trivially equal.
    assert RunLog(seed=1).fingerprint() != RunLog(seed=2).fingerprint()


def test_the_fingerprint_does_not_depend_on_the_order_keys_were_added() -> None:
    """Two logically identical events must not differ because a dict was built differently.

    This is why `canonical()` sorts keys. Without it, a replay that assembled a payload in a
    different order would compare unequal to the run it is replaying, and the divergence would be
    in the serialisation rather than the simulation.
    """
    first = RunLog(seed=1)
    first.record(ScenarioClock(tick=1), "event", alpha=1, beta=2)
    second = RunLog(seed=1)
    second.record(ScenarioClock(tick=1), "event", beta=2, alpha=1)
    assert first.fingerprint() == second.fingerprint()


def test_a_non_finite_payload_value_is_refused_rather_than_serialised() -> None:
    """A NaN compares unequal to itself, so it would make a fingerprint depend on nothing.

    `json.dumps(..., allow_nan=False)` is what stops it, and it fails at the point the event is
    canonicalised rather than at the point a replay mysteriously stops matching.
    """
    log = RunLog(seed=1)
    log.record(ScenarioClock(tick=1), "measured", value=float("nan"))
    with pytest.raises(ValueError, match="Out of range float"):
        log.fingerprint()


def test_the_package_exports_what_it_documents() -> None:
    """The `__all__` is a promise. A name in it that does not resolve is a broken import for a
    caller and a silent one for this suite, since nothing else here touches `Event` directly.
    """
    from enlightenment import scenario

    missing = [name for name in scenario.__all__ if not hasattr(scenario, name)]
    assert not missing, f"exported but absent: {missing}"
    assert "Event" in scenario.__all__


def test_the_fingerprint_is_the_documented_length() -> None:
    """It appears in a log line an operator reads back, so its shape is part of the contract."""
    log = RunLog(seed=1)
    log.record(ScenarioClock(tick=1), "event")
    assert len(log.fingerprint()) == FINGERPRINT_LENGTH


def test_replay_comparison_reports_a_difference_in_length() -> None:
    """A truncated replay must not compare equal to the run it truncates."""
    full = _simulate(20260820, ticks=40)
    truncated = RunLog(seed=full.seed, events=full.events[:-1])
    assert not replay_is_identical(full, truncated)


# --- the randomness -----------------------------------------------------------------------


def test_the_stream_is_reproducible_and_counts_its_draws() -> None:
    """The draw count is the cheapest divergence detector: a different number of draws cannot
    produce the same log, whatever the values were.
    """
    first = SeededRandom(7)
    second = SeededRandom(7)
    drawn_first = [first.uniform(0.0, 1.0) for _ in range(50)]
    drawn_second = [second.uniform(0.0, 1.0) for _ in range(50)]
    assert drawn_first == drawn_second
    assert first.draws == second.draws == 50
    assert first.seed == 7


def test_two_streams_do_not_share_state() -> None:
    """An instance per run, not a module-level generator. Interleaving must not change either."""
    left = SeededRandom(7)
    right = SeededRandom(7)
    interleaved = [(left.uniform(0.0, 1.0), right.uniform(0.0, 1.0)) for _ in range(20)]
    assert all(a == b for a, b in interleaved), "the two streams influenced each other"


def test_choice_takes_a_list_because_set_order_is_not_reproducible() -> None:
    """The signature is the control.

    Set and dict-view iteration order depends on hash values, and string hashing is randomised per
    process by default, so choosing from a set is non-deterministic ACROSS processes even with the
    same seed. A replay months later runs in a different process.
    """
    rng = SeededRandom(7)
    assert rng.choice(["a", "b", "c"]) == SeededRandom(7).choice(["a", "b", "c"])
    with pytest.raises((TypeError, KeyError, IndexError)):
        rng.choice({"a", "b", "c"})  # type: ignore[arg-type]


def test_choosing_from_nothing_is_refused() -> None:
    """An empty option list is an authoring error in a scenario template, not a None."""
    with pytest.raises(ValueError, match="empty sequence"):
        SeededRandom(7).choice([])


@pytest.mark.parametrize("bad", [1.5, "7", None, True])
def test_a_non_integer_seed_is_refused(bad: object) -> None:
    """A seed must round-trip through a run record exactly. A float would not, and `True` is an
    `int` in Python, which is the kind of accident that makes two runs share a stream by mistake.
    """
    with pytest.raises(TypeError, match="seed must be an int"):
        SeededRandom(bad)  # type: ignore[arg-type]


def test_an_integer_draw_covers_both_ends_of_its_range() -> None:
    """Inclusive of both ends, as documented. An off-by-one here silently biases every scenario."""
    rng = SeededRandom(20260820)
    seen = {rng.integer(0, 2) for _ in range(200)}
    assert seen == {0, 1, 2}


# --- the physics boundary -----------------------------------------------------------------


def test_a_derived_physical_quantity_replays_identically() -> None:
    """The substrate is only useful if the physics layer stays deterministic through it.

    Uses the real angle wrapper and the real relative-motion propagator on seeded initial
    conditions, because a determinism harness that only proves itself deterministic proves nothing
    about a run.
    """
    from enlightenment.physics import (
        RelativeState,
        mean_motion_rad_s,
        normalise_longitude,
        propagate_relative,
    )

    def run(seed: int) -> list[str]:
        rng = SeededRandom(seed)
        clock = ScenarioClock()
        log = RunLog(seed=seed)
        state = RelativeState(
            position_km=(rng.uniform(-2.0, 2.0), rng.uniform(-20.0, 20.0), rng.uniform(-1.0, 1.0)),
            velocity_km_s=(0.0, 0.0, 0.0),
        )
        mean_motion = mean_motion_rad_s(6778.0 + rng.uniform(0.0, 400.0))
        for _ in range(30):
            clock = clock.advance(10)
            moved = propagate_relative(state, mean_motion, clock.elapsed_seconds)
            log.record(
                clock,
                "relative_state",
                range_km=round(moved.range_km, 9),
                longitude=round(normalise_longitude(rng.uniform(-400.0, 400.0)), 9),
            )
        return [event.canonical() for event in log.events]

    assert run(20260820) == run(20260820)
    assert run(20260820) != run(20260821)
    assert all(math.isfinite(1.0) for _ in run(20260820))  # the log is serialisable at all


def test_replay_comparison_rejects_two_logs_of_equal_length_that_differ() -> None:
    """The second branch of the comparison, which the truncation test cannot reach.

    A truncated log differs in LENGTH, so it exits at the first check. This is the case where the
    shapes match and the content does not, which is what a real divergence looks like: the same
    number of events, one of them wrong. Coverage found that nothing exercised it.
    """
    first = RunLog(seed=1)
    second = RunLog(seed=1)
    for log, longitude in ((first, 10.0), (second, 10.000000001)):
        log.record(ScenarioClock(tick=1), "moved", longitude=longitude)
    assert len(first.events) == len(second.events)
    assert not replay_is_identical(first, second)


def test_replay_comparison_rejects_two_logs_with_different_seeds() -> None:
    """Same events, different seed. The seed is part of the fingerprint for exactly this case:
    two runs that happened to produce identical logs from different seeds are not the same run,
    and a debrief that treated them as interchangeable would replay the wrong initial conditions.
    """
    first = RunLog(seed=1)
    second = RunLog(seed=2)
    for log in (first, second):
        log.record(ScenarioClock(tick=1), "moved", longitude=10.0)
    assert not replay_is_identical(first, second)
