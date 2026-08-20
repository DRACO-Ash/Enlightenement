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

import json

import pytest

from enlightenment.scenario import (
    FINGERPRINT_LENGTH,
    MAX_PAYLOAD_BYTES,
    MAX_PAYLOAD_DEPTH,
    TICK_MILLISECONDS,
    Event,
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
    """The check that stops a fingerprint depending on a value unequal to itself.

    A NaN compares unequal to itself, so it would make a run's digest depend on nothing.
    `json.dumps(..., allow_nan=False)` is what refuses it.

    **This test used to record the NaN and then expect `fingerprint()` to raise.** That was the
    defect the security gate found, not the test: in an append-only log with no remove, one bad
    write permanently deprived the run of a fingerprint. The refusal moved to `record()`, so the
    assertion moved with it, and `Event.canonical()` is exercised directly here to keep the
    serialisation-level check as well as the write-level one.
    """
    with pytest.raises(ValueError, match="Out of range float"):
        Event(tick=1, kind="measured", payload={"value": float("nan")}).canonical()


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
    # Every event round-trips through JSON. The line here was
    # `all(math.isfinite(1.0) for _ in run(...))`, whose predicate ignores the loop variable and
    # is therefore a tautology, labelled as though it checked serialisability. It did not.
    assert all(json.loads(event) for event in run(20260820))


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


#: The fingerprint of `_simulate(20260820)`, measured and pinned.
GOLDEN_FINGERPRINT = "0ad9d5d62012ddb1"


def test_the_fingerprint_is_stable_across_processes_not_only_within_one() -> None:
    """A golden value, because every other determinism test compares two runs in ONE interpreter.

    The module claims a replay months later runs in a different process, and that string hashing
    is randomised per process so set iteration order cannot be relied on. That claim was true when
    measured, under `PYTHONHASHSEED` of 0, 1, 12345, 99999 and `random`, but nothing pinned it: a
    future change that made the fingerprint process-dependent would have stayed green, because
    both halves of every comparison would have moved together.

    A literal is the only assertion that catches that. If this fails after a deliberate change to
    the log format, update it; if it fails without one, something has become process-dependent.
    """
    assert _simulate(20260820).fingerprint() == GOLDEN_FINGERPRINT


# --- the log's boundary, hardened after the security gate ---------------------------------


def test_the_log_is_genuinely_append_only_not_only_documented_as_such() -> None:
    """`events` used to be a public list, so the docstring's promise was a convention.

    Measured before the fix: `log.events[1] = Event(...)` rewrote history, `log.events.clear()`
    emptied the log, and a forged log compared equal under `replay_is_identical`. The list is
    private now and this returns a tuple, so there is no remove, no update and no handle on the
    storage.

    What this still is not is tamper-evident: the fingerprint is unkeyed, so whoever reaches the
    object can recompute it. It detects divergence, which is what a replay needs.
    """
    log = RunLog(seed=1)
    log.record(ScenarioClock(tick=1), "first")
    log.record(ScenarioClock(tick=2), "second")

    assert isinstance(log.events, tuple)
    with pytest.raises((AttributeError, TypeError)):
        log.events[0] = Event(tick=0, kind="forged")  # type: ignore[index]
    with pytest.raises(AttributeError):
        log.events.clear()  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        log.events = ()  # type: ignore[misc]
    assert [event.kind for event in log.events] == ["first", "second"]


def test_a_non_finite_payload_is_refused_at_the_write_not_at_the_fingerprint() -> None:
    """The placement is the fix, not the check.

    A NaN used to be accepted and then made `fingerprint()` raise. In an append-only log with no
    remove, that permanently deprived the run of a fingerprint: the bad event could not be taken
    out. Failing at the write is the only boundary where the caller can still do something.
    """
    log = RunLog(seed=1)
    with pytest.raises(ValueError, match="cannot be serialised"):
        log.record(ScenarioClock(tick=1), "measured", value=float("nan"))
    assert log.events == (), "the refused event must not have been appended"
    # And the log is still usable afterwards, which is the whole point.
    log.record(ScenarioClock(tick=1), "measured", value=1.0)
    assert len(log.fingerprint()) == FINGERPRINT_LENGTH


def test_an_unserialisable_payload_is_refused_as_one_exception_type() -> None:
    """Bytes, a set, a cyclic structure: all refused, all as `ValueError`."""
    log = RunLog(seed=1)
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    for description, payload in (
        ("bytes", {"raw": b"\x00"}),
        ("a set", {"options": {1, 2}}),
        ("a cyclic structure", {"loop": cyclic}),
        ("an arbitrary object", {"thing": object()}),
    ):
        with pytest.raises(ValueError, match=r"cannot be serialised|nests deeper"):
            log.record(ScenarioClock(tick=1), "event", **payload)  # type: ignore[arg-type]
        assert log.events == (), f"{description} was appended before it was refused"


def test_an_over_large_payload_is_refused() -> None:
    """A 50 MB event was accepted. It is neither replayable in any useful sense nor needed."""
    log = RunLog(seed=1)
    with pytest.raises(ValueError, match="over the"):
        log.record(ScenarioClock(tick=1), "bulk", blob="x" * (MAX_PAYLOAD_BYTES + 1))
    assert log.events == ()
    # Just under the limit is accepted, so the bound is a bound and not a ban.
    log.record(ScenarioClock(tick=1), "bulk", blob="x" * (MAX_PAYLOAD_BYTES - 200))
    assert len(log.events) == 1


def test_a_deeply_nested_payload_is_refused_before_json_recurses() -> None:
    """200,000 levels raised a `RecursionError` from inside `json.dumps`.

    That is not a `ValueError`, and it leaves the interpreter near its stack limit for whatever
    runs next, so the depth is checked before serialisation rather than after it fails.
    """
    log = RunLog(seed=1)
    nested: dict[str, object] = {"leaf": 1}
    for _ in range(MAX_PAYLOAD_DEPTH + 2):
        nested = {"deeper": nested}
    with pytest.raises(ValueError, match="nests deeper"):
        log.record(ScenarioClock(tick=1), "nested", **nested)
    assert log.events == ()


def test_a_newline_in_a_payload_cannot_forge_a_log_line() -> None:
    """`json.dumps` escapes it, so log-line injection is structurally closed rather than filtered.

    Asserted rather than assumed, because the audit module elsewhere strips control characters
    explicitly and a reader could reasonably expect this one to do the same.
    """
    log = RunLog(seed=1)
    log.record(ScenarioClock(tick=1), "note", text="a\nb\rFAKE_EVENT")
    canonical = log.events[0].canonical()
    assert "\n" not in canonical
    assert "\\n" in canonical


def test_the_depth_check_walks_lists_as_well_as_dicts() -> None:
    """Nesting can be built out of lists too, and the recursive walk must follow both.

    Coverage found the list branch unexercised: every earlier nesting fixture was dicts all the
    way down, so a depth guard that only descended into dicts would have passed them all.
    """
    log = RunLog(seed=1)
    nested: object = "leaf"
    for _ in range(MAX_PAYLOAD_DEPTH + 2):
        nested = [nested]
    with pytest.raises(ValueError, match="nests deeper"):
        log.record(ScenarioClock(tick=1), "nested", items=nested)
    assert log.events == ()
    # A tuple is the same case, and `json` serialises it as an array.
    shallow: object = ("leaf",)
    log.record(ScenarioClock(tick=1), "shallow", items=shallow)
    assert len(log.events) == 1
