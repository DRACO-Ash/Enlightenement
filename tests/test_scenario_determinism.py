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

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from enlightenment.scenario import (
    FINGERPRINT_LENGTH,
    MAX_PAYLOAD_BYTES,
    MAX_PAYLOAD_DEPTH,
    MAX_PAYLOAD_NODES,
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


#: Public names a package's submodules define and the package deliberately does NOT re-export,
#: each one a tuning constant or an internal bound rather than API surface. A curated list with a
#: written reason, in the same idiom as the checksum opt-out census: a NEW public name must either
#: be exported or be added here on purpose, so the reverse check cannot be satisfied by drift.
#:
#: These are legitimately internal, and two of the reasons first written here were wrong before
#: being checked - which matters, because a curation list is worth what its reasons are worth.
#:
#: `MARCH`, `SECONDS_PER_DAY`, `SECONDS_PER_DEGREE`, `SECONDS_PER_MINUTE` and
#: `DAYS_PER_JULIAN_CENTURY` are arithmetic constants inside one function's derivation.
#: `PRINTABLE_ASCII_LOW/HIGH`, `TLE_LINE_LENGTH` and `CALENDAR_INDICES` each bound one
#: validator. `MAX_*` are bounds a caller reads from an error message, not from the package.
#:
#: `SGP4_ERRORS`, `TEME_OF_DATE` and `BOUNDARY_REFUSAL` were described as "looked up through the
#: functions that use them". The suite disproves it: `TEME_OF_DATE` is compared directly by
#: callers in `test_physics_propagation.py`, and `propagation.py` documents `BOUNDARY_REFUSAL` as
#: the value "a caller switching on `.code`" reads, which a test does. The real reason is that
#: they are imported from the SUBMODULE, alongside `PropagationError`, which is a defensible
#: convention and not the one that was claimed.
DELIBERATELY_NOT_RE_EXPORTED: dict[str, frozenset[str]] = {
    "scenario": frozenset(),
    "physics": frozenset(
        {
            "BOUNDARY_REFUSAL",
            "CALENDAR_INDICES",
            "DAYS_PER_JULIAN_CENTURY",
            "MARCH",
            "MAX_CALENDAR_COMPONENT",
            "MAX_JULIAN_DATE",
            "MAX_SHOWN_COMPONENT",
            "PRINTABLE_ASCII_HIGH",
            "PRINTABLE_ASCII_LOW",
            "SECONDS_PER_DAY",
            "SECONDS_PER_DEGREE",
            "SECONDS_PER_MINUTE",
            "SGP4_ERRORS",
            "TEME_OF_DATE",
            "TLE_LINE_LENGTH",
        }
    ),
}


@pytest.mark.parametrize("package_name", ["scenario", "physics"])
def test_the_package_exports_what_it_documents(package_name: str) -> None:
    """The `__all__` is a promise, and it is asserted in BOTH directions now.

    The first version checked one direction only: a name in `__all__` that does not resolve. That
    catches a typo and misses the fault that actually happened three times in one release, which
    is a public name the module defines and `__all__` does not list. `MAX_PAYLOAD_BYTES`,
    `MAX_PAYLOAD_DEPTH` and `relative_acceleration_km_s2` were each added to `__all__` by hand
    after the fact; the loop never noticed, because nothing asked the reverse question.

    Both packages, because `physics` had no equivalent test at all and it is the larger of the two.
    A name is public if it does not start with an underscore and is defined in one of the
    package's own modules - an import of `math` or `Final` is not the package's to export.
    """
    package = importlib.import_module(f"enlightenment.{package_name}")

    absent = [name for name in package.__all__ if not hasattr(package, name)]
    assert not absent, f"exported but absent from enlightenment.{package_name}: {absent}"

    # Public names are derived from each SUBMODULE's namespace, not from `__module__` on the
    # value, and that is a fix rather than a style choice. `__module__` exists on a class or a
    # function and not on an `int`, `float` or `str`, so the first version of this check was blind
    # to every exported CONSTANT - while its own docstring named `MAX_PAYLOAD_BYTES` and
    # `MAX_PAYLOAD_DEPTH`, both constants, as two of the three faults it was written to catch.
    # Proved: dropping `MAX_PAYLOAD_BYTES` from `__all__` left it green.
    unexported: set[str] = set()
    for module_name, submodule in vars(package).items():
        if not isinstance(submodule, ModuleType) or module_name.startswith("_"):
            continue
        if not getattr(submodule, "__name__", "").startswith(f"enlightenment.{package_name}."):
            continue
        annotations = getattr(submodule, "__annotations__", {})
        unexported |= {
            name
            for name in vars(submodule)
            if not name.startswith("_")
            and name not in package.__all__
            # Defined HERE, not imported into it: a `Final` annotation marks this module's own
            # constant, and a `__module__` pointing back at this package marks its own class or
            # function. An imported `math` or `Any` has neither.
            and (
                name in annotations
                or getattr(vars(submodule)[name], "__module__", "") == submodule.__name__
            )
            and not isinstance(vars(submodule)[name], ModuleType)
        }
    unexported -= DELIBERATELY_NOT_RE_EXPORTED[package_name]
    assert not unexported, (
        f"enlightenment.{package_name} defines these public names and does not list them in"
        f" __all__, so a caller cannot rely on them and this suite would not notice their"
        f" removal: {sorted(unexported)}"
    )
    assert "Event" in importlib.import_module("enlightenment.scenario").__all__


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
#:
#: Moved from `0ad9d5d62012ddb1` when the digest gained a length prefix per field, which was a
#: deliberate format change for domain separation: without it the seed and the events were
#: concatenated with no boundary. Re-measured under `PYTHONHASHSEED` of 0, 1, 12345, 99999 and
#: `random`, all five agreeing, rather than taken from one run.
GOLDEN_FINGERPRINT = "8f952d44b09fb117"


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


# --- the forge the tuple did not close ----------------------------------------------------


def test_a_payload_cannot_be_rewritten_through_the_events_property() -> None:
    """THE defeat of the previous append-only claim, asserted so it cannot come back.

    `Event` was a frozen dataclass holding a plain dict, which froze the reference and not the
    payload. Measured on the shipped code: two runs that genuinely diverged were made to agree by
    one item assignment through the public `events` property, with no private access, and
    `replay_is_identical` then returned True. Freezing a container's reference and calling the
    container immutable is the same class of error as a shallow copy at a security boundary.
    """
    genuine = RunLog(seed=1)
    genuine.record(ScenarioClock(tick=0), "start", outcome="none")
    genuine.record(ScenarioClock(tick=1), "score", outcome="pass")

    divergent = RunLog(seed=1)
    divergent.record(ScenarioClock(tick=0), "start", outcome="none")
    divergent.record(ScenarioClock(tick=1), "score", outcome="fail")
    assert not replay_is_identical(genuine, divergent)

    with pytest.raises(TypeError):
        divergent.events[1].payload["outcome"] = "pass"  # type: ignore[index]
    assert not replay_is_identical(genuine, divergent), "a divergent run was forged into agreement"


def test_a_nested_payload_is_frozen_all_the_way_down() -> None:
    """One level of freezing would leave the same forge one level in.

    `MappingProxyType` over a dict of dicts protects only the outer view, so the freeze has to
    recurse or it is a speed bump. Lists too: a list inside a payload is an ordered part of what
    the fingerprint attests.
    """
    log = RunLog(seed=1)
    log.record(ScenarioClock(tick=0), "state", detail={"axis": {"score": 1}, "history": [1, 2]})
    payload = log.events[0].payload
    with pytest.raises(TypeError):
        payload["detail"]["axis"]["score"] = 99  # type: ignore[index]
    assert isinstance(payload["detail"]["history"], tuple), (
        "a list inside a payload stayed mutable, so the sequence the fingerprint covers can be"
        " reordered after the write"
    )


def test_the_fingerprint_is_taken_at_the_write_not_recomputed() -> None:
    """Defence in depth behind the freeze, and the fix for a permanent brick.

    The digest used to be recomputed from the stored event every time it was asked for, so a
    payload mutated afterwards changed it, and a NaN placed there made `fingerprint()` raise for
    ever on a log with no remove. Digesting the canonical form captured at the write means neither
    is possible even if some later change reintroduces a mutable path.
    """
    log = RunLog(seed=1)
    log.record(ScenarioClock(tick=0), "measured", value=1.0)
    before = log.fingerprint()
    stored = log.events[0].payload
    with pytest.raises(TypeError):
        stored["value"] = float("nan")  # type: ignore[index]
    assert log.fingerprint() == before
    assert log.fingerprint() == before, "the digest is not stable across repeated calls"


def test_the_seed_cannot_be_rewritten_after_the_fact() -> None:
    """The seed is part of what the fingerprint attests, so a writable seed is a rewritable run."""
    log = RunLog(seed=1)
    log.record(ScenarioClock(tick=0), "start")
    before = log.fingerprint()
    with pytest.raises(AttributeError):
        log.seed = 999  # type: ignore[misc]
    assert log.fingerprint() == before


@pytest.mark.parametrize("bad_seed", ["1", 1.0, True, None, b"1"])
def test_a_run_log_refuses_a_seed_that_is_not_an_integer(bad_seed: object) -> None:
    """Same rule as `SeededRandom`, and it was missing here.

    `bool` is listed because it IS an `int` in Python, so an `isinstance` check alone accepts
    `RunLog(seed=True)` and digests it as `seed:True`. A seed is drawn from a scenario definition,
    and `True` there is a mistake, not a seed.
    """
    with pytest.raises(TypeError):
        RunLog(seed=bad_seed)  # type: ignore[arg-type]


def test_the_digest_separates_the_seed_from_the_events() -> None:
    """Concatenation with no boundary let one field imitate another.

    Without a length prefix per field, `seed:1` followed by an event digested identically to a
    seed chosen to contain the event's own canonical text. The seed type check closes the
    `RunLog(1)` versus `RunLog("1")` case at the door; the prefix closes the general one.
    """
    plain = RunLog(seed=1)
    plain.record(ScenarioClock(tick=0), "a")
    imitation = RunLog(seed=1)
    imitation.record(ScenarioClock(tick=0), "a", extra="b")
    assert plain.fingerprint() != imitation.fingerprint()

    empty_one = RunLog(seed=11)
    empty_two = RunLog(seed=1)
    empty_two_events = RunLog(seed=1)
    empty_two_events.record(ScenarioClock(tick=0), "1")
    assert (
        len({empty_one.fingerprint(), empty_two.fingerprint(), empty_two_events.fingerprint()}) == 3
    )


@pytest.mark.parametrize(
    ("label", "events"),
    [
        ("an out-of-order tick", [Event(tick=9, kind="late"), Event(tick=1, kind="early")]),
        ("a non-finite payload", [Event(tick=0, kind="m", payload={"v": float("nan")})]),
        ("an unserialisable payload", [Event(tick=0, kind="m", payload={"v": object()})]),
    ],
)
def test_the_constructor_seam_enforces_what_record_enforces(
    label: str, events: list[Event]
) -> None:
    """A control with a second door is not a control.

    The `events=` argument is a public parameter and it bypassed every check `record` performs.
    Measured: ticks `[9, 1]` accepted out of order, and a NaN payload accepted and then making
    `fingerprint()` raise for ever - which is the exact defect the write-time validation was
    introduced to close, still reachable through the other entrance. Both paths go through
    `_append` now.
    """
    with pytest.raises(ValueError, match=r"append-only|serialised"):
        RunLog(seed=1, events=events)


#: How long the node-budget refusal may take, enforced as a subprocess timeout. Measured at 0.064
#: seconds, so thirty seconds is roughly 470 times the observed cost: this asserts boundedness,
#: not this machine's speed, and will not flake on a loaded runner.
NODE_BUDGET_DEADLINE_SECONDS = 30.0

#: The repository root, for launching the deadline subprocess with `src` importable.
ROOT = Path(__file__).resolve().parent.parent


def test_a_flat_payload_over_the_node_budget_is_refused_in_process() -> None:
    """The budget's refusal branch, exercised where COVERAGE can see it.

    Moving the two shared-reference tests into subprocesses was necessary - an unbudgeted build of
    that payload never returns, so an in-process call cannot be bounded - but it took the refusal
    branch out of the coverage measurement with it, and `determinism.py` dropped off 100%. A
    control measured only in a child process is a control the coverage report cannot vouch for.

    A FLAT payload over the budget needs no expansion: 100,001 elements is one list, built in
    milliseconds, and it charges the budget past its limit on the ordinary path. Cheap, in-process,
    and it exercises the same raise.

    **The constant is pinned to a LITERAL, and the previous version was not.** Sizing the payload
    as `MAX_PAYLOAD_NODES + 1` self-adjusts to whatever the constant says, so only the lowering
    direction was caught: measured, raising it to 200,000 left this whole file green, and a
    weakened cost bound on the shared-reference class would have shipped unnoticed. A bound
    asserted relative to itself is not asserted.
    """
    assert MAX_PAYLOAD_NODES == 100_000, (
        "the node budget changed; if that is deliberate, update the literals below, because a cap"
        " asserted only relative to itself cannot catch being raised"
    )
    log = RunLog(seed=1)
    with pytest.raises(ValueError, match="nodes"):
        log.record(ScenarioClock(tick=0), "flat", v=[0] * 100_001)
    assert log.events == (), "a refused write must append nothing"


def test_a_flat_payload_just_under_the_node_budget_is_refused_for_its_size() -> None:
    """The two caps in the right order, and a control I first wrote wrong.

    My first attempt asserted that a flat payload just under the node budget is ACCEPTED, as a
    control against the constant being raised. It fails, correctly: 99,998 integers serialise to
    roughly 200 KB, three times `MAX_PAYLOAD_BYTES`, so the byte cap refuses it. There is no flat
    payload that reaches the node budget and stays under the byte cap, which is worth knowing -
    for FLAT input the byte cap is the binding constraint, and the node budget exists for input
    whose serialised size is never computed because the expansion never finishes.

    So the honest control is the ordering: just under the budget must refuse for SIZE, just over
    must refuse for NODES.

    **What this does NOT do, corrected because the docstring claimed it did.** It said this "pins
    both constants against each other" so that raising `MAX_PAYLOAD_NODES` would make the byte cap
    fire first and turn the sibling test red. Measured, that is false: the budget is charged during
    the freeze while bytes are only measured after the freeze returns, so an over-budget payload
    always raises "nodes" whatever the constant says. Raising it to 200,000 left the whole file
    green. The absolute assertion in the sibling test is what catches that now; this test covers
    the ORDER, and nothing more.
    """
    log = RunLog(seed=1)
    with pytest.raises(ValueError, match="bytes"):
        log.record(ScenarioClock(tick=0), "under", v=[0] * 99_998)
    assert log.events == ()


def _refusal_in_a_subprocess(call: str, expected_reason: str) -> str:
    """Build the shared-reference payload in a child process and report how ``call`` ended.

    One caller now. It was shared between two node-budget tests until they turned out to be the
    same assertion twice and one was deleted; the helper stays because the reason for it is
    structural, not a matter of how many callers it has.

    The payload is a few hundred bytes of live objects at depth 7 that expands to 40**6 = 4.1
    billion nodes, so a build without the budget does not fail, it does not RETURN - which is why
    the assertion has to live behind a real timeout rather than a stopwatch taken after the call.
    """
    programme = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "from enlightenment.scenario.determinism import RunLog, ScenarioClock\n"
        "v = 'z' * 10\n"
        "for _ in range(6):\n"
        "    v = [v] * 40\n"
        "log = RunLog(seed=1)\n"
        "try:\n"
        f"    {call}\n"
        "    print('ACCEPTED')\n"
        "except ValueError as refusal:\n"
        f"    print('REFUSED' if {expected_reason!r} in str(refusal) else 'WRONG-REASON')\n"
        "print('EVENTS', len(log.events))\n"
    )
    try:
        completed = subprocess.run(  # noqa: S603 - this interpreter and a literal programme
            [sys.executable, "-c", programme],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=NODE_BUDGET_DEADLINE_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"the write did not return within {NODE_BUDGET_DEADLINE_SECONDS}s, so the cost of"
            " accepting a payload is not bounded before the work is done"
        )
    lines = completed.stdout.split()
    assert lines[-2:] == ["EVENTS", "0"], (
        f"a refused write must append nothing; got {completed.stdout.strip()!r} with"
        f" {completed.stderr.strip()[:200]!r}"
    )
    return lines[0]


def test_the_node_budget_refuses_within_a_hard_deadline_in_a_separate_process() -> None:
    """The refusal's SPEED, bounded by a real timeout rather than by a stopwatch.

    My first attempt at this measured `time.monotonic()` either side of the call. That cannot work,
    and the reason is the whole point of the control: a stopwatch after the call bounds nothing
    when the call never returns. Deleting `budget.spend()` makes the process allocate until the
    machine or the runner kills it, and the elapsed-time assertion is never reached - so the test
    hung instead of failing, which in CI reads as broken infrastructure rather than as this control
    being gone.

    A subprocess with `timeout=` is the only version that actually holds. `_Budget` in
    `determinism.py` claims the refusal arrives in milliseconds instead of never; here that claim
    is enforced. (The docstring this used to point at went with the duplicate test it belonged to,
    which is how a cross-reference becomes a dangling one.)
    """
    assert (
        _refusal_in_a_subprocess("log.record(ScenarioClock(tick=0), 'boom', v=v)", "nodes")
        == "REFUSED"
    )


def test_an_ordinary_nested_payload_is_still_well_within_the_node_budget() -> None:
    """The control: the budget must refuse an expansion, not refuse structure.

    A guard that rejected everything would satisfy the test above while being broken, so a payload
    of the shape a real scenario event carries is asserted to pass.
    """
    log = RunLog(seed=1)
    log.record(
        ScenarioClock(tick=0),
        "scored",
        axes={"detection": 0.8, "custody": 0.6},
        history=[1, 2, 3, 4, 5],
        detail={"procedure": "geo-belt", "version": {"content": "v1"}},
    )
    assert len(log.events) == 1
    assert len(log.fingerprint()) == FINGERPRINT_LENGTH
