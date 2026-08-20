"""SGP4 against Vallado's own published reference output, not against numbers I chose.

This is the flight plan's Phase 0 gate: "Vallado test vectors green, property tests green,
named traps for the TEME-as-J2000 and angle-wrap bugs. Nothing else is built until this is
right, because everything scores against it."

The reference data ships INSIDE the pinned `sgp4` wheel: `SGP4-VER.TLE` holds the verification
element sets and `tcppver.out` holds the expected state vectors, both from the AIAA 2006-6753
distribution. Reading them, rather than transcribing a handful of numbers into this file, is
the whole point. A transcribed vector is a number I asserted; a parsed one is a number the
reference asserts, and the hard rule against inventing a figure applies to test data first.

Two named traps get a live witness here rather than a hypothetical one.

● **The unchecked error code.** Satellite 33334 in the official verification set returns SGP4
  error code 3 (instantaneous eccentricity out of range). A wrapper that ignores the code
  hands the caller a tuple of floats that look exactly like a position. The published data
  proves the refusal fires, which is stronger than a synthetic element set I built to fail.
● **TEME is not J2000.** Every state vector carries its frame, and a test asserts the frame is
  what SGP4 actually produces. The failure mode is silent and grows with epoch separation, so
  the only defence is that the frame is never implicit.

Tolerance is MEASURED, not chosen. Across 666 comparable rows the worst position deviation is
1.17e-7 km (about 0.12 mm) and the worst velocity deviation 8.53e-10 km/s. The two margins are
NOT the same and are stated separately rather than rounded into one claim: the position bound
of 1e-5 km sits about 85 times above its measurement, the velocity bound of 1e-8 km/s about 12
times above its own. Both are loose enough to survive a libm difference between platforms and
tight enough that a real regression in the propagation path fails the suite; the velocity
bound has the less margin and is the one to watch on a new runner.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest
import sgp4
from sgp4.api import SGP4_ERRORS as LIBRARY_SGP4_ERRORS
from sgp4.api import Satrec

from enlightenment.physics import (
    PropagationError,
    StateVector,
    element_line_checksum_ok,
    load_elements,
    propagate_minutes_since_epoch,
)
from enlightenment.physics.propagation import (
    BOUNDARY_REFUSAL,
    SGP4_ERRORS,
    TEME_OF_DATE,
    TLE_LINE_LENGTH,
)

#: `TLE_LINE_LENGTH` is imported from the module under test rather than restated here.
#: `SGP4-VER.TLE` appends start, stop and step values after the checksum on line 2, so the
#: line is truncated to that width rather than passed through whole.

#: Measured worst-case deviation 1.17e-7 km, at satellite 20413, t=1844335.0. This bound is
#: about 85 times that.
POSITION_TOLERANCE_KM = 1e-5

#: Measured worst-case deviation 8.53e-10 km/s, at satellite 9880, t=840.0. This bound is about
#: 12 times that, the tighter of the two margins.
VELOCITY_TOLERANCE_KM_S = 1e-8

#: The counts the pinned wheel actually ships, in OCCURRENCE order.
#:
#: These were 32 and 641, and the difference is a defect this suite reported as thoroughness.
#: Satellite 20413 appears TWICE in `SGP4-VER.TLE` - identical elements, two different time
#: spans of 26 and 70 rows. Both parsers keyed by satellite number, so the second occurrence
#: overwrote the first and 26 published rows of an e=0.786 deep-space case were never
#: compared. The guard written to catch a shrinking reference set was asserting the shrunk
#: total, under a docstring that called it the full set.
#:
#: Occurrence-ordered lists, not dicts, is the fix. A dict keyed by a value the source does not
#: guarantee unique is a silent drop by construction.
EXPECTED_ELEMENT_BLOCKS = 33
EXPECTED_REFERENCE_ROWS = 667

#: The one row in the whole set that SGP4 legitimately refuses, so 666 are comparable.
EXPECTED_COMPARISONS = 666

#: The one satellite in the verification set that SGP4 refuses, and the code it refuses with.
REFUSED_SATELLITE = 33334
REFUSED_CODE = 3

#: Columns per reference row before the optional trailing orbital-element diagnostics.
REFERENCE_COLUMNS = 7


def _reference_directory() -> Path:
    """Locate the data files inside the installed `sgp4` package.

    Deliberately not a vendored copy: a vendored copy can drift from the propagator it is
    meant to verify, and then the suite proves agreement with a stale snapshot.
    """
    directory = Path(sgp4.__file__).parent
    for name in ("SGP4-VER.TLE", "tcppver.out"):
        if not (directory / name).is_file():
            raise AssertionError(f"the pinned sgp4 wheel no longer ships {name}")
    return directory


def _load_element_blocks() -> list[tuple[int, tuple[str, str]]]:
    """Parse `SGP4-VER.TLE` into `(satellite, (line1, line2))` in FILE order.

    A list, not a dict: satellite number is not unique in this file and keying by it drops
    data without a word.
    """
    blocks: list[tuple[int, tuple[str, str]]] = []
    first: str | None = None
    for raw in (_reference_directory() / "SGP4-VER.TLE").read_text().splitlines():
        line = raw.rstrip()
        if line.startswith("#"):
            continue
        if line.startswith("1 "):
            first = line[:TLE_LINE_LENGTH]
        elif line.startswith("2 ") and first is not None:
            blocks.append((int(line[2:7]), (first, line[:TLE_LINE_LENGTH])))
            first = None
    return blocks


def _load_reference_blocks() -> list[tuple[int, list[tuple[float, ...]]]]:
    """Parse `tcppver.out` into `(satellite, rows)` in FILE order.

    The file marks each block with a `"<number> xx"` header, then one row per timestep of
    (tsince, x, y, z, vx, vy, vz). Rows carry trailing orbital-element diagnostics which are
    read past, not parsed: this module verifies the state vector, and asserting on columns
    nothing consumes would be coverage of the reference file rather than of the propagator.
    """
    blocks: list[tuple[int, list[tuple[float, ...]]]] = []
    current: list[tuple[float, ...]] | None = None
    for raw in (_reference_directory() / "tcppver.out").read_text().splitlines():
        fields = raw.split()
        if len(fields) == 2 and fields[1] == "xx":
            current = []
            blocks.append((int(fields[0]), current))
        elif current is not None and len(fields) >= REFERENCE_COLUMNS:
            current.append(tuple(float(f) for f in fields[:REFERENCE_COLUMNS]))
    return blocks


ELEMENT_BLOCKS = _load_element_blocks()
REFERENCE_BLOCKS = _load_reference_blocks()

#: A by-number lookup for the handful of spot tests that name one orbit. First occurrence
#: wins, which is harmless HERE because no spot test names the duplicated satellite - but it
#: is deliberately not what the golden comparison uses.
ELEMENT_SETS = dict(reversed(ELEMENT_BLOCKS))
REFERENCE_ROWS = dict(reversed(REFERENCE_BLOCKS))


def _reference_propagator(lines: tuple[str, str]) -> Satrec:
    """Load a REFERENCE element set, with the checksum check deliberately off.

    `load_elements` verifies the TLE checksum by default, and five of the sixty-six lines in
    `SGP4-VER.TLE` fail it - both lines of satellite 33333 and line 1 of 33334 and 33335. They
    are synthetic verification vectors, not real element sets, so the default that protects
    authored content would here refuse the authority the module is measured against.

    Named rather than a bare `verify_checksum=False` at each call site, so the opt-out is one
    decision with one reason attached, and so a new test cannot inherit it by copy and paste.
    """
    return load_elements(*lines, verify_checksum=False)


# --- the reference data itself, guarded so a dependency bump cannot quietly weaken this ---


def test_the_reference_data_ships_the_full_verification_set() -> None:
    """A shrinking reference set is a suite that proves less while still reporting green.

    Counted over occurrence-ordered lists, so a repeated satellite number cannot hide inside
    the total the way it did when these were dicts.
    """
    assert len(ELEMENT_BLOCKS) == EXPECTED_ELEMENT_BLOCKS
    assert len(REFERENCE_BLOCKS) == EXPECTED_ELEMENT_BLOCKS
    assert sum(len(rows) for _, rows in REFERENCE_BLOCKS) == EXPECTED_REFERENCE_ROWS


def test_the_parsed_row_count_equals_the_data_lines_in_the_file() -> None:
    """Counted independently of the parser, so a parser that silently drops a row is caught.

    The assertion above compares the parser's output to a number I wrote down. This one
    compares it to the FILE, by counting every line whose first field parses as a float. A
    constant can be updated to match a bug; the file cannot.
    """
    data_lines = 0
    for raw in (_reference_directory() / "tcppver.out").read_text().splitlines():
        fields = raw.split()
        if len(fields) < REFERENCE_COLUMNS:
            continue
        try:
            float(fields[0])
        except ValueError:
            continue
        data_lines += 1
    assert sum(len(rows) for _, rows in REFERENCE_BLOCKS) == data_lines


def test_the_duplicated_satellite_number_is_still_present_twice() -> None:
    """The specific loss, pinned so it cannot recur silently.

    Satellite 20413 carries two time spans under one number. If a future refactor keys by
    satellite again, this fails and names the reason.
    """
    numbers = [satellite for satellite, _ in ELEMENT_BLOCKS]
    repeated = {n for n in numbers if numbers.count(n) > 1}
    assert repeated, "the reference set no longer repeats a satellite number; simplify above"
    for number in repeated:
        assert numbers.count(number) == [s for s, _ in REFERENCE_BLOCKS].count(number)


def test_the_two_files_list_the_same_satellites_in_the_same_order() -> None:
    """The golden comparison pairs the two files by POSITION, so the order is load-bearing."""
    assert [s for s, _ in ELEMENT_BLOCKS] == [s for s, _ in REFERENCE_BLOCKS]


# --- the golden vectors, one case per BLOCK so a failure names the orbit and the span -----


@pytest.mark.parametrize(
    "index",
    range(len(REFERENCE_BLOCKS)),
    ids=[
        f"{satellite}#{[s for s, _ in REFERENCE_BLOCKS][:i].count(satellite)}"
        for i, (satellite, _) in enumerate(REFERENCE_BLOCKS)
    ],
)
def test_propagation_matches_the_vallado_reference_output(index: int) -> None:
    """Every published row, to the measured tolerance.

    Parametrised per BLOCK rather than per satellite number, and that distinction is the point:
    satellite 20413 contributes two blocks, and keying on the number dropped one of them.

    Split per block rather than as one loop because the verification set is chosen to span
    regimes: deep-space resonance, near-earth drag, high eccentricity, the Lyddane fix. A
    failure that names the block names the regime, which is the difference between a diagnosis
    and a rerun.
    """
    satellite, rows = REFERENCE_BLOCKS[index]
    element_satellite, lines = ELEMENT_BLOCKS[index]
    assert element_satellite == satellite, "the two files fell out of step"

    elements = _reference_propagator(lines)
    compared = 0
    for tsince, x, y, z, vx, vy, vz in rows:
        try:
            state = propagate_minutes_since_epoch(elements, tsince)
        except PropagationError:
            # A refusal is the correct answer for the deliberate error case in the set; it is
            # asserted directly in its own test rather than swallowed as "no comparison".
            continue
        position_error = math.dist(state.position_km, (x, y, z))
        velocity_error = math.dist(state.velocity_km_s, (vx, vy, vz))
        assert position_error < POSITION_TOLERANCE_KM, (
            f"satellite {satellite} at t={tsince}: position off by {position_error:.3e} km"
        )
        assert velocity_error < VELOCITY_TOLERANCE_KM_S, (
            f"satellite {satellite} at t={tsince}: velocity off by {velocity_error:.3e} km/s"
        )
        compared += 1
    if satellite != REFUSED_SATELLITE:
        assert compared > 0, f"block {index} (satellite {satellite}) compared nothing at all"


def test_the_whole_reference_set_is_actually_compared_not_mostly_skipped() -> None:
    """The guard against a green suite that compared nothing.

    A per-block loop that swallows exceptions can pass with every row skipped, which is the
    failure mode this shape invites. The total is asserted against the file's own row count
    minus the one row SGP4 legitimately refuses.
    """
    compared = 0
    for (satellite, rows), (element_satellite, lines) in zip(
        REFERENCE_BLOCKS, ELEMENT_BLOCKS, strict=True
    ):
        assert element_satellite == satellite
        elements = _reference_propagator(lines)
        for row in rows:
            try:
                propagate_minutes_since_epoch(elements, row[0])
            except PropagationError:
                continue
            compared += 1
    assert compared == EXPECTED_COMPARISONS


# --- the unchecked-error-code trap, with a witness from the published data ------------------


def test_the_error_case_in_the_official_set_raises_instead_of_returning_numbers() -> None:
    """Satellite 33334 is the trap, and Vallado shipped it.

    Without the code check this call returns a tuple of floats that reads as a position. A
    trainer that scores an operator against a fabricated state is worse than one that refuses
    to run, so the wrapper raises.
    """
    elements = _reference_propagator(ELEMENT_SETS[REFUSED_SATELLITE])
    tsince = REFERENCE_ROWS[REFUSED_SATELLITE][0][0]
    with pytest.raises(PropagationError) as raised:
        propagate_minutes_since_epoch(elements, tsince)
    assert raised.value.code == REFUSED_CODE
    assert SGP4_ERRORS[REFUSED_CODE] in str(raised.value)


def test_every_sgp4_error_code_names_a_readable_cause() -> None:
    """A bare code in a log is a support ticket. The message must stand on its own."""
    assert set(SGP4_ERRORS) == {1, 2, 3, 4, 5, 6}
    for code, cause in SGP4_ERRORS.items():
        assert cause.strip(), f"code {code} has no cause"
        assert str(PropagationError(code)).endswith(cause)


def test_the_local_error_table_covers_exactly_the_codes_the_library_defines() -> None:
    """Parity with the pinned library, because the previous version of this test did not check.

    It asserted only that each cause was non-empty and echoed in the message, so it happily
    certified entry 5 as "epoch element set was a sub-orbital trajectory" - a cause I invented,
    where the library says the code is no longer in use. A test that checks a string against
    itself proves the string exists, not that it is true.

    Keys, not values: the phrasing here is deliberately more readable than the library's
    (`nm`, `mrt`), so asserting equal text would force a choice between accuracy and clarity.
    Asserting equal key sets catches the thing that actually goes stale - a code added or
    retired by a dependency bump.
    """
    assert set(SGP4_ERRORS) == set(LIBRARY_SGP4_ERRORS)


def test_no_local_cause_contradicts_the_library_on_the_retired_code() -> None:
    """Code 5 specifically, because it is the one that was wrong and the one that reads oddest.

    A future reader seeing "no longer in use" may be tempted to tidy it into something that
    sounds like an orbital fault. It is not one, and this test says so.
    """
    assert "no longer in use" in SGP4_ERRORS[5]
    assert "no longer in use" in LIBRARY_SGP4_ERRORS[5]


def test_an_unknown_error_code_is_reported_rather_than_swallowed() -> None:
    """A future library version could add a code. Silence there would be the same defect."""
    assert "unknown SGP4 error code 99" in str(PropagationError(99))


# --- the TEME-as-J2000 trap ----------------------------------------------------------------


def test_a_propagated_state_carries_its_frame_and_the_frame_is_not_j2000() -> None:
    """The frame is in the type because forgetting it is silent and grows with epoch gap.

    The number this produces is plausible, stable, and wrong by an amount nobody notices until
    it is compared against an ephemeris from another source.
    """
    elements = _reference_propagator(ELEMENT_SETS[5])
    state = propagate_minutes_since_epoch(elements, 0.0)
    assert state.frame == TEME_OF_DATE
    assert "J2000" not in state.frame
    assert "TEME" in state.frame


def test_the_frame_default_cannot_be_overridden_after_construction() -> None:
    """Frozen on purpose: a state that can be relabelled between check and score is not a fact."""
    state = StateVector(position_km=(1.0, 2.0, 3.0), velocity_km_s=(4.0, 5.0, 6.0))
    with pytest.raises((AttributeError, TypeError)):
        state.frame = "J2000"  # type: ignore[misc]


# --- derived quantities, cross-checked against the reference row ---------------------------


def test_radius_and_speed_agree_with_the_reference_row() -> None:
    """The cheapest sanity check there is, verified against published numbers.

    Satellite 5 at epoch: the reference gives the position and velocity components, so the
    magnitudes follow from them rather than from a figure I would otherwise have to assert.
    """
    _, x, y, z, vx, vy, vz = REFERENCE_ROWS[5][0]
    state = propagate_minutes_since_epoch(_reference_propagator(ELEMENT_SETS[5]), 0.0)
    assert state.radius_km == pytest.approx(math.dist((0.0, 0.0, 0.0), (x, y, z)), abs=1e-6)
    assert state.speed_km_s == pytest.approx(math.dist((0.0, 0.0, 0.0), (vx, vy, vz)), abs=1e-9)


def test_a_propagated_radius_is_in_kilometres_not_metres() -> None:
    """A units check, named for what it actually asserts.

    This was called `test_a_geostationary_reference_orbit_sits_at_a_plausible_radius`, and it
    made no GEO assertion: satellite 4632 is the highly eccentric case from the set, so the
    bound is an envelope spanning low orbit to well past the belt. A test name that promises
    more than the body delivers is how a reader concludes something is covered when it is not.

    The envelope still has teeth for the trap it is aimed at. Kilometres against metres is one
    of the named unit traps, and it shows as a radius three orders of magnitude out, far
    outside this range in either direction.
    """
    state = propagate_minutes_since_epoch(_reference_propagator(ELEMENT_SETS[4632]), 0.0)
    assert 6_400.0 < state.radius_km < 100_000.0
    assert 0.5 < state.speed_km_s < 15.0


# --- the boundary, hardened after the security gate ---------------------------------------
#
# Five findings came out of the security review of this module. Two are here, and both are the
# same class: a refusal that did not happen, or happened as the wrong exception type.
#
# The first is the sharper one. `sgp4_tsince(float("inf"))` returns error code **0** with an
# all-NaN state, so the exact thing this wrapper exists to prevent - a fabricated state vector
# passing an unchecked success code - arrives THROUGH the code check rather than around it.
# Checking the code was necessary and not sufficient, and the module's own docstring claimed
# otherwise. Nothing reaches this from an HTTP route yet; the guard goes in before anything
# does, because a NaN in a scored run is a plot with no marks and a score with no reason.


def _reference_elements() -> Satrec:
    """A known-good propagator, so a boundary test fails for the reason it names."""
    return _reference_propagator(ELEMENT_SETS[5])


@pytest.mark.parametrize("minutes", [float("inf"), float("-inf"), float("nan")])
def test_a_non_finite_time_is_refused_rather_than_propagated(minutes: float) -> None:
    """The input half of the guard."""
    # Matched on the INPUT guard's own words. `match="finite"` was satisfied by the output
    # guard's "non-finite state" too, so deleting the input guard left this green: two controls,
    # one assertion, and the weaker one propping up the test for the stronger.
    with pytest.raises(PropagationError, match="minutes since epoch must be finite"):
        propagate_minutes_since_epoch(_reference_elements(), minutes)


def test_the_library_really_does_report_success_for_a_non_finite_time() -> None:
    """The fact the input guard exists for, asserted against the LIBRARY not the wrapper.

    `sgp4_tsince(inf)` returns code 0 with an all-NaN state. Stating that here means the guard
    reads as a response to measured behaviour rather than as caution, and if a future version
    starts refusing it properly this test fails and says so.
    """
    code, position, velocity = _reference_elements().sgp4_tsince(float("inf"))
    assert code == 0, "the library now refuses this itself; the input guard may be redundant"
    assert all(math.isnan(component) for component in (*position, *velocity))


#: Extreme but FINITE times, spanning both signs up to the edge of the double range.
EXTREME_FINITE_MINUTES = [
    1e6,
    1e9,
    1e12,
    1e15,
    1e18,
    1e20,
    1e25,
    1e30,
    1e50,
    1e100,
    1e200,
    1e300,
    1.7e308,
    -1e12,
    -1e100,
    -1e300,
    -1.7e308,
]


@pytest.mark.parametrize("minutes", EXTREME_FINITE_MINUTES)
def test_an_extreme_finite_time_yields_either_a_refusal_or_a_finite_state(minutes: float) -> None:
    """No fabricated state at any magnitude of time, on a GOOD element set.

    This test alone is why the output guard was briefly removed as dead code: varying `minutes`
    on a good element set finds nothing, because every non-finite result here already carries a
    non-zero code. It kept only one axis fixed, which is the mistake. The element-set axis is
    covered by the test below, and that one does reach the guard.
    """
    try:
        state = propagate_minutes_since_epoch(_reference_elements(), minutes)
    except PropagationError:
        return  # a refusal is the correct outcome and needs nothing further
    components = (*state.position_km, *state.velocity_km_s)
    assert all(math.isfinite(component) for component in components)


#: Element-set lines that PASS the column and charset check and still mean nothing. This is
#: what a content author produces by accident, and it is the axis the first measurement missed.
WELL_SHAPED_BUT_MEANINGLESS = [
    ("every column an X", "1" + "X" * 68),
    ("every column a nine", "1 " + "9" * 67),
    (
        "an alphabetic epoch",
        "1 00005U 58002B   ABCDE.ABCDEFGH  .00000023  00000-0  28098-4 0  4753",
    ),
]

#: How many times to repeat a call that is known not to be dependably deterministic.
MEANINGLESS_REPEATS = 16


@pytest.mark.parametrize(
    ("description", "line"),
    WELL_SHAPED_BUT_MEANINGLESS,
    ids=[d for d, _ in WELL_SHAPED_BUT_MEANINGLESS],
)
def test_a_meaningless_element_set_is_never_served_as_a_non_finite_state(
    description: str, line: str
) -> None:
    """Whatever the library does, the wrapper never hands back a non-finite state.

    Written to repeat, because the library is NOT dependably deterministic here: three
    identical consecutive calls in one process returned all-NaN, then a finite plausible
    state, then all-NaN. A single-shot assertion on either outcome would be flaky, and a
    flaky test on a determinism hazard is worse than none.

    So the assertion is the invariant that holds under both outcomes: either the wrapper
    refuses, or what it returns is finite. Never a NaN dressed as a position.
    """
    assert len(line) == TLE_LINE_LENGTH, "the fixture must pass the column check to be a test"
    good_second_line = ELEMENT_BLOCKS[0][1][1]
    for _ in range(MEANINGLESS_REPEATS):
        # Checksum off deliberately: this test exercises the layer BELOW it, which is
        # what has to hold if a line ever reaches the propagator without being checked.
        elements = load_elements(line, good_second_line, verify_checksum=False)
        try:
            state = propagate_minutes_since_epoch(elements, 0.0)
        except PropagationError:
            continue
        components = (*state.position_km, *state.velocity_km_s)
        assert all(math.isfinite(component) for component in components), (
            "a non-finite state escaped the output guard"
        )


@pytest.mark.parametrize(
    ("description", "line"),
    WELL_SHAPED_BUT_MEANINGLESS,
    ids=[d for d, _ in WELL_SHAPED_BUT_MEANINGLESS],
)
def test_the_checksum_catches_what_the_shape_check_and_the_guards_cannot(
    description: str, line: str
) -> None:
    """The layer that actually rejects these, and why it is not at propagation time.

    A finite wrong number is indistinguishable from a finite right one inside
    `propagate_minutes_since_epoch`, so the output guard cannot be the whole answer. The
    published TLE checksum can tell, and every meaningless line here fails it.

    It is not a gate in `load_elements` because five of the sixty-six lines in Vallado's own
    verification file fail it too - they are synthetic vectors, not real element sets - and a
    control that refuses the reference data is not a control. It belongs in the scenario
    engine's solvability check, at authoring time.
    """
    assert not element_line_checksum_ok(line)


def test_the_checksum_accepts_most_of_the_reference_set_but_not_all_of_it() -> None:
    """The measurement behind that decision, asserted rather than asserted-about.

    If a future wheel ships a corrected verification file, this fails and says the checksum
    could be promoted to a hard gate in `load_elements`.
    """
    lines = [line for _, pair in ELEMENT_BLOCKS for line in pair]
    failing = [line for line in lines if not element_line_checksum_ok(line)]
    assert len(lines) == 66
    assert len(failing) == 5, (
        "the reference set's checksum failures have changed; revisit whether"
        " element_line_checksum_ok can become a hard gate in load_elements"
    )
    assert any(line.startswith(f"1 {REFUSED_SATELLITE}") for line in failing)


def test_a_boundary_refusal_is_distinguishable_from_a_library_code() -> None:
    """`code` is what a caller switches on, so a boundary refusal must not look like code 3."""
    with pytest.raises(PropagationError) as raised:
        propagate_minutes_since_epoch(_reference_elements(), float("nan"))
    assert raised.value.code == BOUNDARY_REFUSAL
    assert raised.value.code not in SGP4_ERRORS


#: Element-set lines the library would otherwise fail on with its OWN exception type. The
#: first three were found by the security review attacking `twoline2rv` directly: a NUL raised
#: `ValueError: embedded null character`, a lone surrogate raised `UnicodeEncodeError`, and a
#: non-string raised `TypeError`. A caller told to expect `PropagationError` got none of them.
HOSTILE_ELEMENT_LINES: list[tuple[str, object]] = [
    ("an embedded NUL", "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  47\x005"),
    (
        "a lone surrogate",
        "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  47\ud80053",
    ),
    ("not text at all", 12345),
    ("empty", ""),
    ("truncated", "1 00005U 58002B   00179.78495062"),
    ("far too long", "1" * 100_000),
    (
        "a newline in the middle",
        "1 00005U 58002B   00179.78495062\n.00000023  00000-0  28098-4 0  4",
    ),
    (
        "a tab substituted for a space",
        "1\t00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0 475",
    ),
    (
        "a four-byte emoji",
        "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4\U0001f680",
    ),
]


@pytest.mark.parametrize(
    ("description", "line"), HOSTILE_ELEMENT_LINES, ids=[d for d, _ in HOSTILE_ELEMENT_LINES]
)
def test_a_malformed_element_line_is_refused_as_one_exception_type(
    description: str, line: object
) -> None:
    """One type out, whatever went in. A caller cannot fail closed on an exception it was
    never told about, and three of these previously escaped the module's stated contract.
    """
    good = ELEMENT_SETS[5][1]
    with pytest.raises(PropagationError):
        load_elements(line, good)  # type: ignore[arg-type]
    with pytest.raises(PropagationError):
        load_elements(ELEMENT_SETS[5][0], line)  # type: ignore[arg-type]


def test_the_hostile_lines_would_not_all_be_refused_by_the_library_alone() -> None:
    """The control: prove at least one hostile line escapes `PropagationError` WITHOUT the
    boundary check, so this block is testing the guard rather than the library.

    Without this, a library that happened to reject everything already would leave the
    parametrised test above green and meaningless.
    """
    escaped: list[str] = []
    for description, line in HOSTILE_ELEMENT_LINES:
        try:
            Satrec.twoline2rv(line, ELEMENT_SETS[5][1])  # type: ignore[arg-type]
        except PropagationError:  # pragma: no cover - the raw library never raises ours
            continue
        except Exception:  # measuring the library's raw failure surface, whatever it is
            escaped.append(description)
        else:
            escaped.append(f"{description} (accepted silently)")
    assert escaped, "the library refuses everything itself; the boundary check proves nothing"


def test_a_good_element_line_with_trailing_whitespace_is_still_accepted() -> None:
    """The boundary must reject malformed input without rejecting real-world formatting.

    Element-set files routinely carry trailing whitespace or a line ending. Refusing those
    would be a fail-closed control that fails on valid data, which is its own defect.
    """
    first, second = ELEMENT_SETS[5]
    padded = propagate_minutes_since_epoch(
        load_elements(first + "  \r\n", second + " ", verify_checksum=False), 0.0
    )
    plain = propagate_minutes_since_epoch(_reference_propagator((first, second)), 0.0)
    assert padded.position_km == plain.position_km


# --- the checksum gate, now that it has a caller ------------------------------------------


@pytest.mark.parametrize(
    ("description", "line"),
    WELL_SHAPED_BUT_MEANINGLESS,
    ids=[d for d, _ in WELL_SHAPED_BUT_MEANINGLESS],
)
def test_load_elements_refuses_a_meaningless_line_by_default(description: str, line: str) -> None:
    """The wiring, asserted. For one commit this control existed with no call site.

    `verify_checksum` defaults to True, so a line of the right width and charset but
    meaningless fields never reaches the library - which would otherwise accept it, report
    success, and return a state built from uninitialised memory.
    """
    with pytest.raises(PropagationError, match="checksum"):
        load_elements(line, ELEMENT_BLOCKS[0][1][1])


def test_the_checksum_gate_can_be_opted_out_of_and_only_the_reference_suite_does() -> None:
    """The opt-out exists for the reference data alone, and that is asserted not asserted-about.

    A default-strict control with a widely-copied opt-out beside it is a control in name only,
    so the number of CALL SITES that switch it off is pinned. There are three: the reference
    propagator, and two tests that deliberately exercise the layer beneath the gate.

    Counted by parsing the file, not by searching its text. The first version counted the string
    and found six, because docstrings that discuss the opt-out and the test's own literal all
    matched. A guard that counts mentions instead of calls measures prose.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    opt_outs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "verify_checksum"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is False
    ]
    assert len(opt_outs) == 3, (
        f"{len(opt_outs)} call sites opt out of the checksum gate at lines"
        f" {[node.lineno for node in opt_outs]}; each one needs a written reason"
    )


@pytest.mark.parametrize(
    "not_a_line",
    ["", " ", "1 25544U", "1" * 68, "1" * 70, None, 12345, b"1" * 69],
    ids=["empty", "one space", "truncated", "68 columns", "70 columns", "none", "int", "bytes"],
)
def test_the_checksum_predicate_returns_false_rather_than_raising(not_a_line: object) -> None:
    """A predicate that raises is not a predicate.

    The first version indexed column 69 directly, so an empty string raised `IndexError` and a
    non-string raised `TypeError`. Both binding gates found it independently: the same defect
    class fixed in `load_elements` in that very commit, reintroduced in the validator beside
    it. This is the input class the function exists to reject, so rejecting it must be the one
    thing it cannot do by crashing.
    """
    assert element_line_checksum_ok(not_a_line) is False


def test_the_checksum_predicate_accepts_a_real_element_set_line() -> None:
    """The control for the test above: a validator that returned False always would pass it."""
    good = next(
        line for _, pair in ELEMENT_BLOCKS for line in pair if element_line_checksum_ok(line)
    )
    assert element_line_checksum_ok(good) is True
    assert element_line_checksum_ok(good + "\r\n") is True, "a line ending must not matter"


def test_the_checksum_gate_checks_line_two_as_well_as_line_one() -> None:
    """Both lines, and the second one was an uncovered branch.

    The gate loops over the pair, so a good line 1 with a bad line 2 is the case that only
    reaches the second iteration. Coverage showed the partial branch; a wrong checksum on
    line 2 is exactly as likely an authoring mistake as one on line 1.
    """
    good_first, good_second = ELEMENT_SETS[5]
    assert element_line_checksum_ok(good_first), "the fixture's line 1 must be valid"

    # Flip the checksum digit on line 2 only.
    digit = int(good_second[TLE_LINE_LENGTH - 1])
    bad_second = good_second[: TLE_LINE_LENGTH - 1] + str((digit + 1) % 10)
    assert not element_line_checksum_ok(bad_second)

    with pytest.raises(PropagationError, match="line 2 fails the TLE checksum"):
        load_elements(good_first, bad_second)


def test_the_checksum_gate_lets_a_valid_element_set_through() -> None:
    """The positive control for the gate, and the branch nothing else reached.

    Every other default-checksum call in this suite is expected to RAISE, and the reference
    propagator opts out, so the path where both lines pass and the loop simply completes was
    uncovered. A gate proved only by its refusals is a gate that might refuse everything.
    """
    first, second = ELEMENT_SETS[5]
    assert element_line_checksum_ok(first)
    assert element_line_checksum_ok(second)
    state = propagate_minutes_since_epoch(load_elements(first, second), 0.0)
    assert state.frame == TEME_OF_DATE
    assert 6_000.0 < state.radius_km < 60_000.0
