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
from hypothesis import example, given, settings
from hypothesis import strategies as st

from enlightenment.physics import (
    normalise_degrees,
    normalise_longitude,
    shortest_separation_degrees,
    wrap_to_pi,
)
from enlightenment.physics.angles import HALF_TURN_DEGREES

#: Finite, sane angles. Excludes NaN and infinity, which are rejected explicitly elsewhere.
ANGLES = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)

#: The largest representable longitude inside ``[-180, 180)``, and the input that exposed the
#: half-fix: the first `_fold_into_turn` version reported it at ``-180.0``.
JUST_BELOW_180 = math.nextafter(180.0, 0.0)

#: Its radian twin.
JUST_BELOW_PI = math.nextafter(math.pi, 0.0)

#: The smallest representable longitude strictly inside the interval above -180. This is the
#: value that falsified `test_reversing_a_separation_negates_it`: the separations are exactly
#: antisymmetric here, and the test's tolerance-gated seam branch demanded they both be -180.
#: Pinned as an example so the regression is deterministic rather than one-run-in-five.
JUST_BELOW_MINUS_180_IN_RANGE = math.nextafter(-180.0, 0.0)

#: Example budget for the seam properties, above Hypothesis's default of 100.
#:
#: The default found the antisymmetry defect in about one run in five, and I had already
#: reported the loop green from a run that did not. A property test's verdict is only as strong
#: as its search, and "green once" is weak evidence for a boundary this narrow.
#:
#: Measured cost, as a DELTA rather than an absolute, because the absolute goes stale every time
#: a test is added and has now been wrong twice: this file takes about 3.5s at 2,000 examples
#: against 1.2s at the default 100, so the budget costs roughly 2.3s. Worth paying. The
#: changelog carries the whole-suite figure for the release it describes; a per-run total does
#: not belong in a module constant that nobody re-measures.
SEAM_EXAMPLES = 2_000

#: Longitudes inside the canonical interval, to the LAST representable value.
#:
#: This bound was `179.999`, and that cap is why the suite certified a defect as closed. The
#: whole failing band - every value between `179.999` and `180.0` - sat outside the strategy,
#: so the idempotence, separation and antisymmetry properties never saw it. A property test is
#: only as good as its domain, and a domain that stops short of the boundary is a property test
#: that agrees with you about the interior.
LONGITUDES = st.floats(
    min_value=-180.0, max_value=JUST_BELOW_180, allow_nan=False, allow_infinity=False
)

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
@example(JUST_BELOW_180)
@example(JUST_BELOW_MINUS_180)
def test_a_normalised_longitude_always_lands_in_the_half_open_interval(angle: float) -> None:
    """Half-open on purpose: 180 and -180 are the same meridian, and admitting both lets one
    physical location compare unequal to itself.
    """
    normalised = normalise_longitude(angle)
    assert -180.0 <= normalised < 180.0


@pytest.mark.parametrize(
    ("function", "argument"),
    [(normalise_longitude, JUST_BELOW_180), (wrap_to_pi, JUST_BELOW_PI)],
    ids=["longitude", "radians"],
)
def test_a_value_already_inside_the_interval_is_returned_unchanged(
    function: object, argument: float
) -> None:
    """The half-fix, pinned. Not merely "in range" - UNCHANGED.

    The first `_fold_into_turn` version returned `-180.0` for `179.99999999999997`, an input
    already in range, because it added half a turn before folding and the addition rounded to
    a full turn. In-range was true; correct was not. Asserting equality is what distinguishes
    the two, and asserting only the range is how the defect passed the suite the first time.
    """
    assert function(argument) == argument  # type: ignore[operator]


def test_two_frames_one_step_apart_near_the_high_end_report_no_drift() -> None:
    """The operational form of the half-fix, in the units an operator reads.

    Measured against the pre-fix implementation: these two frames, 2.8e-14 degrees apart,
    reported a drift of -359.99999999999994 degrees per frame. A whole turn of fabricated
    motion at the OTHER end of the interval from the one the first fix closed.
    """
    earlier = math.nextafter(JUST_BELOW_180, 0.0)
    later = JUST_BELOW_180
    assert abs(later - earlier) < 1e-13, "the frames must be adjacent for this to be a test"
    assert shortest_separation_degrees(earlier, later) == pytest.approx(0.0, abs=1e-9)
    assert normalise_longitude(later) - normalise_longitude(earlier) == pytest.approx(0.0, abs=1e-9)


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
@example(JUST_BELOW_PI)
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


def test_a_drift_is_the_separation_of_two_samples_never_the_difference_of_two_separations() -> None:
    """The usage rule the seam actually implies, and it is not a defect to be fixed.

    ANY half-open interval has a discontinuity at its seam: two longitudes a representable
    step either side of the antimeridian map to opposite ends by definition, so subtracting
    their normalised values gives about a whole turn. No implementation removes that, and
    chasing it is how the first fix here reintroduced the artefact at the other end.

    What removes it is computing the drift the right way round. `shortest_separation_degrees`
    takes the two RAW samples and returns the short way between them. Differencing two
    separations already measured against a third point straddles the seam whenever that third
    point is near their antipode, and then the answer is a whole turn no matter how correct
    the normalisation is.

    Both numbers below are measured, and the wrong one is measured too, because a rule stated
    without its counter-example is a rule nobody follows.
    """
    observer = 90.0
    earlier = -90.00000000000003
    later = math.nextafter(earlier, 0.0)
    physical_move = abs(later - earlier)
    assert physical_move < 1e-13, "the target must barely move between samples"

    # RIGHT: the separation of the two samples.
    assert shortest_separation_degrees(earlier, later) == pytest.approx(0.0, abs=1e-9)

    # WRONG, and asserted as wrong: two separations from an observer near their antipode.
    against_observer = (
        shortest_separation_degrees(observer, earlier),
        shortest_separation_degrees(observer, later),
    )
    fabricated = against_observer[1] - against_observer[0]
    assert abs(fabricated) > 300.0, (
        "the seam discontinuity has moved; the rule this test states may need restating"
    )


@given(LONGITUDES)
def test_normalising_an_already_normalised_longitude_changes_nothing(angle: float) -> None:
    """Idempotence. A value that shifts on a second pass would drift over a long scenario."""
    once = normalise_longitude(angle)
    assert normalise_longitude(once) == pytest.approx(once)


@given(LONGITUDES, LONGITUDES)
@settings(max_examples=SEAM_EXAMPLES)
@example(0.0, JUST_BELOW_180)
@example(0.0, JUST_BELOW_MINUS_180_IN_RANGE)
def test_separation_never_exceeds_half_a_turn(first: float, second: float) -> None:
    """The defining property: the shortest way round is never more than 180 degrees."""
    assert -180.0 <= shortest_separation_degrees(first, second) < 180.0


@given(LONGITUDES, LONGITUDES)
@settings(max_examples=SEAM_EXAMPLES)
@example(0.0, JUST_BELOW_MINUS_180_IN_RANGE)
@example(0.0, -HALF_TURN_DEGREES)
@example(-HALF_TURN_DEGREES, 0.0)
def test_reversing_a_separation_negates_it(first: float, second: float) -> None:
    """Antisymmetry, with the seam case gated on EXACT equality rather than a tolerance.

    This test was the defect, not the implementation, and it took the widened `LONGITUDES`
    domain to expose it: the near-seam band is now sampled, and the failure appeared in about
    one run in five.

    The seam special case is real. At exactly -180 both directions give -180, because the
    half-open interval admits only one of the two ends. But the branch was written as
    `forward == pytest.approx(-180.0)`, and `pytest.approx` defaults to a RELATIVE tolerance of
    1e-6, so it claimed the special case for a band about 1.8e-4 degrees wide. For
    `second = -179.99999999999997` the separations are exactly antisymmetric at
    -179.99999999999997 and +179.99999999999997, and the test demanded the second be -180.

    A tolerance on a BRANCH CONDITION is not the same thing as a tolerance on a comparison.
    Here it widened an exact special case into a band where the general rule still applies.
    """
    forward = shortest_separation_degrees(first, second)
    backward = shortest_separation_degrees(second, first)
    if forward == -HALF_TURN_DEGREES:
        assert backward == -HALF_TURN_DEGREES
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
