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

Tolerance is MEASURED, not chosen. Across 640 comparable rows the worst position deviation is
1.17e-7 km (about 0.12 mm) and the worst velocity deviation 8.53e-10 km/s. The bounds below sit
roughly two orders of magnitude above that: loose enough to survive a libm difference between
platforms, tight enough that any real regression in the propagation path fails the suite.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import sgp4

from enlightenment.physics import (
    PropagationError,
    StateVector,
    load_elements,
    propagate_minutes_since_epoch,
)
from enlightenment.physics.propagation import SGP4_ERRORS, TEME_OF_DATE

#: A TLE line is 69 characters. `SGP4-VER.TLE` appends start, stop and step values after the
#: checksum on line 2, so the line is truncated rather than passed through whole.
TLE_LINE_LENGTH = 69

#: Measured worst-case deviation was 1.17e-7 km. See the module docstring for the measurement.
POSITION_TOLERANCE_KM = 1e-5

#: Measured worst-case deviation was 8.53e-10 km/s.
VELOCITY_TOLERANCE_KM_S = 1e-8

#: The counts the pinned wheel actually ships. Asserted so a dependency bump that silently
#: shrinks the reference set fails loudly instead of leaving a suite that proves less.
EXPECTED_ELEMENT_SETS = 32
EXPECTED_REFERENCE_ROWS = 641

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


def _load_element_sets() -> dict[int, tuple[str, str]]:
    """Parse `SGP4-VER.TLE` into element-set pairs keyed by satellite number."""
    sets: dict[int, tuple[str, str]] = {}
    first: str | None = None
    for raw in (_reference_directory() / "SGP4-VER.TLE").read_text().splitlines():
        line = raw.rstrip()
        if line.startswith("#"):
            continue
        if line.startswith("1 "):
            first = line[:TLE_LINE_LENGTH]
        elif line.startswith("2 ") and first is not None:
            sets[int(line[2:7])] = (first, line[:TLE_LINE_LENGTH])
            first = None
    return sets


def _load_reference_rows() -> dict[int, list[tuple[float, ...]]]:
    """Parse `tcppver.out` into rows of (tsince, x, y, z, vx, vy, vz) keyed by satellite.

    The file marks each satellite with a `"<number> xx"` header, then one row per timestep.
    Rows carry trailing orbital-element diagnostics which are read past, not parsed: this
    module verifies the state vector, and asserting on columns nothing consumes would be
    coverage of the reference file rather than of the propagator.
    """
    rows: dict[int, list[tuple[float, ...]]] = {}
    satellite: int | None = None
    for raw in (_reference_directory() / "tcppver.out").read_text().splitlines():
        fields = raw.split()
        if len(fields) == 2 and fields[1] == "xx":
            satellite = int(fields[0])
            rows[satellite] = []
        elif satellite is not None and len(fields) >= REFERENCE_COLUMNS:
            rows[satellite].append(tuple(float(f) for f in fields[:REFERENCE_COLUMNS]))
    return rows


ELEMENT_SETS = _load_element_sets()
REFERENCE_ROWS = _load_reference_rows()


# --- the reference data itself, guarded so a dependency bump cannot quietly weaken this ---


def test_the_reference_data_ships_the_full_verification_set() -> None:
    """A shrinking reference set is a suite that proves less while still reporting green."""
    assert len(ELEMENT_SETS) == EXPECTED_ELEMENT_SETS
    assert sum(len(r) for r in REFERENCE_ROWS.values()) == EXPECTED_REFERENCE_ROWS


def test_every_satellite_in_the_reference_output_has_an_element_set() -> None:
    """Otherwise a row could be skipped silently and the suite would still pass."""
    assert not set(REFERENCE_ROWS) - set(ELEMENT_SETS)


# --- the golden vectors, one case per satellite so a failure names the orbit ---------------


@pytest.mark.parametrize("satellite", sorted(REFERENCE_ROWS))
def test_propagation_matches_the_vallado_reference_output(satellite: int) -> None:
    """Every published row, to the measured tolerance.

    Parametrised per satellite rather than as one loop because the verification set is chosen
    to span regimes: deep-space resonance, near-earth drag, high eccentricity, the Lyddane
    fix. A failure that names the satellite names the regime, which is the difference between
    a diagnosis and a rerun.
    """
    elements = load_elements(*ELEMENT_SETS[satellite])
    compared = 0
    for tsince, x, y, z, vx, vy, vz in REFERENCE_ROWS[satellite]:
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
        assert compared > 0, f"satellite {satellite} contributed no comparison at all"


def test_the_whole_reference_set_is_actually_compared_not_mostly_skipped() -> None:
    """The guard against a green suite that compared nothing.

    An earlier version of this file could have passed with every row skipped by an exception,
    which is the failure mode a per-satellite loop invites. The total is asserted against the
    reference count minus the one row SGP4 legitimately refuses.
    """
    compared = 0
    for satellite, rows in REFERENCE_ROWS.items():
        elements = load_elements(*ELEMENT_SETS[satellite])
        for row in rows:
            try:
                propagate_minutes_since_epoch(elements, row[0])
            except PropagationError:
                continue
            compared += 1
    assert compared == EXPECTED_REFERENCE_ROWS - 1


# --- the unchecked-error-code trap, with a witness from the published data ------------------


def test_the_error_case_in_the_official_set_raises_instead_of_returning_numbers() -> None:
    """Satellite 33334 is the trap, and Vallado shipped it.

    Without the code check this call returns a tuple of floats that reads as a position. A
    trainer that scores an operator against a fabricated state is worse than one that refuses
    to run, so the wrapper raises.
    """
    elements = load_elements(*ELEMENT_SETS[REFUSED_SATELLITE])
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


def test_an_unknown_error_code_is_reported_rather_than_swallowed() -> None:
    """A future library version could add a code. Silence there would be the same defect."""
    assert "unknown SGP4 error code 99" in str(PropagationError(99))


# --- the TEME-as-J2000 trap ----------------------------------------------------------------


def test_a_propagated_state_carries_its_frame_and_the_frame_is_not_j2000() -> None:
    """The frame is in the type because forgetting it is silent and grows with epoch gap.

    The number this produces is plausible, stable, and wrong by an amount nobody notices until
    it is compared against an ephemeris from another source.
    """
    elements = load_elements(*ELEMENT_SETS[5])
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
    state = propagate_minutes_since_epoch(load_elements(*ELEMENT_SETS[5]), 0.0)
    assert state.radius_km == pytest.approx(math.dist((0.0, 0.0, 0.0), (x, y, z)), abs=1e-6)
    assert state.speed_km_s == pytest.approx(math.dist((0.0, 0.0, 0.0), (vx, vy, vz)), abs=1e-9)


def test_a_geostationary_reference_orbit_sits_at_a_plausible_radius() -> None:
    """A units check with teeth: kilometres against metres is one of the named traps, and it
    shows up as a radius three orders of magnitude wrong. Satellite 4632 is the highly
    eccentric case from the set, so the bound is stated as an envelope, not a point.
    """
    state = propagate_minutes_since_epoch(load_elements(*ELEMENT_SETS[4632]), 0.0)
    assert 6_400.0 < state.radius_km < 100_000.0
    assert 0.5 < state.speed_km_s < 15.0
