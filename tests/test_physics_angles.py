"""The plus-or-minus-180 seam, which the flight plan names as a regression trap.

Why this gets its own module and property-based tests rather than a handful of examples: the
bug is a SEAM, and a seam is exactly what example-based tests miss. The operational stake is
concrete. The LEARNED register records an ASTRA 1M case where a millisecond epoch gap produced
a drift rate of about minus 22,900,000 degrees per day. A GEO object crossing the antimeridian
between two observations is routine, and a naive subtraction reports roughly 360 degrees of
drift for a body that barely moved.

The trainer must not manufacture its own version of that artefact, because competency axis five
exists to train operators to recognise it in REAL data. A trainer whose own maths produces it
teaches the wrong lesson.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from enlightenment.physics import (
    normalise_degrees,
    normalise_longitude,
    shortest_separation_degrees,
    wrap_to_pi,
)

#: Finite, sane angles. Excludes NaN and infinity, which are rejected explicitly elsewhere.
ANGLES = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)

#: Longitudes inside the canonical interval.
LONGITUDES = st.floats(min_value=-180.0, max_value=179.999, allow_nan=False, allow_infinity=False)

#: The value Hypothesis found on the first run of this module. ``x % 360.0`` returns ``360.0``
#: for it: the exact answer is a hair under a full turn, unrepresentable at this magnitude, so
#: it rounds to the excluded end. Kept as a named constant, not an inline literal, so the
#: regression reads as a recorded finding rather than a magic number.
TINY_NEGATIVE_DEGREES = -1.1324634486784985e-78

#: The same defect in the longitude wrapper: one representable step below the minus-180 meridian.
JUST_BELOW_MINUS_180 = math.nextafter(-180.0, -181.0)

#: And in the radian wrapper.
JUST_BELOW_MINUS_PI = math.nextafter(-math.pi, -4.0)


# --- the seam, by example first so the intent is readable -----------------------------


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (179.0, -179.0, 2.0),  # eastward across the antimeridian
        (-179.0, 179.0, -2.0),  # westward across it
        (0.0, 10.0, 10.0),
        (10.0, 0.0, -10.0),
        (0.0, 180.0, -180.0),  # the seam itself, resolved to the half-open end
    ],
)
def test_the_shortest_way_round_is_taken_across_the_antimeridian(
    first: float, second: float, expected: float
) -> None:
    """Two degrees apart, not 358. This is the drift-rate bug in one assertion."""
    assert shortest_separation_degrees(first, second) == pytest.approx(expected)


def test_a_geo_object_crossing_the_seam_reports_a_plausible_drift_rate() -> None:
    """The operational form of the same bug, stated in the units an operator reads.

    A geostationary object drifting slowly east crosses the antimeridian between two daily
    observations. Naive subtraction gives about minus 359.9 degrees per day, which is
    physically impossible for a GEO body and is precisely the artefact class the trainer
    teaches operators to spot in real feeds.
    """
    yesterday, today = 179.95, -179.95
    naive = today - yesterday
    correct = shortest_separation_degrees(yesterday, today)
    assert abs(naive) > 300.0, "the naive calculation should be obviously wrong"
    assert correct == pytest.approx(0.1, abs=1e-9)


# --- invariants, property-based, because a seam needs a search not a sample ------------


@given(ANGLES)
def test_a_normalised_longitude_always_lands_in_the_half_open_interval(angle: float) -> None:
    """Half-open on purpose: 180 and -180 are the same meridian, and admitting both lets one
    physical location compare unequal to itself.
    """
    normalised = normalise_longitude(angle)
    assert -180.0 <= normalised < 180.0


@given(ANGLES)
def test_normalising_a_longitude_moves_it_by_a_whole_number_of_turns(angle: float) -> None:
    """The value must be the SAME direction, not merely inside the range."""
    turns = (angle - normalise_longitude(angle)) / 360.0
    assert turns == pytest.approx(round(turns), abs=1e-6)


@given(ANGLES)
@example(TINY_NEGATIVE_DEGREES)
def test_normalising_a_bearing_always_lands_in_zero_to_a_full_turn(angle: float) -> None:
    assert 0.0 <= normalise_degrees(angle) < 360.0


@given(ANGLES)
@example(JUST_BELOW_MINUS_PI)
def test_wrapping_radians_always_lands_in_minus_pi_to_pi(angle: float) -> None:
    wrapped = wrap_to_pi(angle)
    assert -math.pi <= wrapped < math.pi


# --- the rounding seam, found by property testing and pinned by example ----------------
#
# These three values are not hypothetical. Hypothesis found the first one on the first run of
# this module, and the other two are its twins in the other two wrappers. Each is a hair below
# one end of a half-open interval, at a magnitude where the exact answer is not representable,
# so the naive ``%`` rounds UP and returns the EXCLUDED end. Reported to an operator that is a
# swing of a whole turn for a body that did not move, which is the artefact class competency
# axis five teaches people to recognise in real feeds.
#
# Pinned as examples as well as properties because a property test only rediscovers this if the
# search happens to reach the same corner. A regression must fail on the first run, every run.


@pytest.mark.parametrize(
    ("function", "argument", "low", "high"),
    [
        (normalise_degrees, TINY_NEGATIVE_DEGREES, 0.0, 360.0),
        (normalise_longitude, JUST_BELOW_MINUS_180, -180.0, 180.0),
        (wrap_to_pi, JUST_BELOW_MINUS_PI, -math.pi, math.pi),
    ],
)
def test_a_value_a_hair_below_the_interval_does_not_land_on_the_excluded_end(
    function: object, argument: float, low: float, high: float
) -> None:
    """The naive ``(x + half) % turn - half`` returns ``high`` for each of these. It must not."""
    result = function(argument)  # type: ignore[operator]
    assert low <= result < high, f"{argument!r} landed on the excluded end: {result!r}"


def test_the_seam_rounding_bug_reads_as_a_whole_turn_of_false_drift() -> None:
    """The operational statement of the same defect, in the units an operator reads.

    A near-antipodal pair in the GEO belt, sampled twice. The target moves by 1.4e-14 degrees
    between the two samples, which is nothing. The naive arithmetic reports the separation as
    plus 180 on the first sample and minus 180 on the second, so the DRIFT between consecutive
    frames comes out as a full 360 degrees. That is the ASTRA 1M artefact class exactly: a
    whole turn of fabricated motion for a body that did not move.

    The numbers below are measured against the naive expression, not asserted from reasoning.
    """
    observer = 90.0
    first_sample = -90.00000000000003
    second_sample = math.nextafter(first_sample, 0.0)

    physical_move = abs(second_sample - first_sample)
    assert physical_move < 1e-13, "the target must barely move between samples"

    reported = [
        shortest_separation_degrees(observer, first_sample),
        shortest_separation_degrees(observer, second_sample),
    ]
    assert reported[1] - reported[0] == pytest.approx(0.0, abs=1e-9), (
        f"a body that moved {physical_move!r} degrees was reported as drifting "
        f"{reported[1] - reported[0]!r} degrees"
    )
    # Both samples resolve to the WESTWARD end of the half-open interval, not one of each.
    assert reported == [-180.0, -180.0]


@given(LONGITUDES)
def test_normalising_an_already_normalised_longitude_changes_nothing(angle: float) -> None:
    """Idempotence. A value that shifts on a second pass would drift over a long scenario."""
    once = normalise_longitude(angle)
    assert normalise_longitude(once) == pytest.approx(once)


@given(LONGITUDES, LONGITUDES)
def test_separation_never_exceeds_half_a_turn(first: float, second: float) -> None:
    """The defining property: the shortest way round is never more than 180 degrees."""
    assert -180.0 <= shortest_separation_degrees(first, second) < 180.0


@given(LONGITUDES, LONGITUDES)
def test_reversing_a_separation_negates_it(first: float, second: float) -> None:
    """Antisymmetry, except at the seam where both directions are exactly 180."""
    forward = shortest_separation_degrees(first, second)
    backward = shortest_separation_degrees(second, first)
    if forward == pytest.approx(-180.0):
        assert backward == pytest.approx(-180.0)
    else:
        assert forward == pytest.approx(-backward)


# --- rejection, not coercion, at the boundary -----------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("function", [normalise_degrees, normalise_longitude, wrap_to_pi])
def test_a_non_finite_angle_is_rejected_rather_than_propagated(
    bad: float, function: object
) -> None:
    """A NaN that propagates silently becomes a plot with no marks and a score with no reason.
    Rejecting at the boundary is the same fail-closed rule the HTTP layer applies to a body.
    """
    with pytest.raises(ValueError, match="finite"):
        function(bad)  # type: ignore[operator]
