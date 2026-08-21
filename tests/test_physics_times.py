"""Time and Earth-rotation conversions, validated against the pinned library, not against memory.

The lesson this module was written around. The first version of `greenwich_mean_sidereal_degrees`
was checked against a reference value I recalled from a textbook example, and disagreed with it by
131 degrees. The implementation was right and the remembered number was wrong. So the golden
source here is `sgp4.propagation.gstime` in the pinned wheel, which is a validated implementation
the machine can produce on demand, plus one independent almanac sanity check that a human can
verify without trusting either.

That is the same pattern as the Vallado vectors: the authority is something shipped and checkable,
never a figure written from recollection.
"""

from __future__ import annotations

import math

import pytest
from sgp4.propagation import gstime

from enlightenment.physics.angles import shortest_separation_degrees
from enlightenment.physics.times import (
    J2000_JULIAN_DATE,
    greenwich_mean_sidereal_degrees,
    julian_date_from_utc,
    sub_satellite_longitude_degrees,
)

#: Epochs spanning 46 years, including the J2000 epoch itself and a leap year, so the polynomial
#: is exercised either side of its own reference point rather than only near it.
EPOCHS = [
    (1980, 1, 1, 0, 0, 0.0),
    (1992, 8, 1, 22, 14, 0.0),
    (2000, 1, 1, 12, 0, 0.0),
    (2016, 2, 29, 6, 30, 30.0),
    (2026, 8, 20, 0, 0, 0.0),
]

#: Measured worst disagreement with the library across the epochs above: 1.6e-10 degrees. This
#: bound is three orders above that, which is loose enough to survive a libm difference and far
#: tighter than anything that could matter to a plot.
GMST_TOLERANCE_DEGREES = 1e-7


@pytest.mark.parametrize("epoch", EPOCHS, ids=lambda e: f"{e[0]}-{e[1]:02d}-{e[2]:02d}")
def test_sidereal_time_agrees_with_the_pinned_library(epoch: tuple[int, ...]) -> None:
    """The golden check. The library is the authority; this module is what the trainer calls."""
    julian_date = julian_date_from_utc(*epoch)  # type: ignore[arg-type]
    mine = greenwich_mean_sidereal_degrees(julian_date)
    theirs = math.degrees(gstime(julian_date)) % 360.0
    difference = abs(((mine - theirs + 180.0) % 360.0) - 180.0)
    assert difference < GMST_TOLERANCE_DEGREES, (
        f"{epoch}: {mine:.9f} against the library's {theirs:.9f}, off by {difference:.3e} deg"
    )


def test_sidereal_time_matches_an_almanac_by_hand() -> None:
    """One check a human can verify without trusting the library either.

    Sidereal time at 0h Universal Time on 1 August 1992 is about 20h 40m in an almanac. This
    computes 20h 39m, which agrees. It is here because the failure mode that started this module
    was trusting a remembered number, and two independent sources beat one.
    """
    hours = greenwich_mean_sidereal_degrees(julian_date_from_utc(1992, 8, 1)) / 15.0
    assert 20.6 < hours < 20.7, f"got {hours:.3f} h, almanac says about 20h 40m"


def test_the_j2000_epoch_is_the_julian_date_it_claims_to_be() -> None:
    """2000 January 1 at 12:00 is Julian Date 2451545.0, by definition of the epoch."""
    assert julian_date_from_utc(2000, 1, 1, 12, 0, 0.0) == J2000_JULIAN_DATE


@pytest.mark.parametrize(
    ("earlier", "later"),
    [
        ((2026, 1, 1), (2026, 1, 2)),
        ((2026, 2, 28), (2026, 3, 1)),
        ((2024, 2, 28), (2024, 2, 29)),
        ((1999, 12, 31), (2000, 1, 1)),
    ],
    ids=["consecutive days", "non-leap February", "leap day", "century boundary"],
)
def test_the_julian_date_increases_by_a_day_across_a_calendar_boundary(
    earlier: tuple[int, int, int], later: tuple[int, int, int]
) -> None:
    """The January-and-February shift in the algorithm is where a date bug would hide.

    2026 is not a leap year, so 28 February to 1 March is one day; 2024 is, so 28 to 29 February
    is one day as well. Both are asserted, because an algorithm that got the leap rule backwards
    would pass one and fail the other.
    """
    span = julian_date_from_utc(*later) - julian_date_from_utc(*earlier)
    assert span == pytest.approx(1.0)


def test_sidereal_time_advances_by_a_sidereal_day_not_a_solar_one() -> None:
    """The distinction that names the quantity. A solar day is 360 degrees of the Sun; a sidereal
    day is 360 degrees of the stars, so Earth rotation advances about 360.9856 degrees per solar
    day. A test that only checked "it increases" would pass on a solar-day implementation.
    """
    start = julian_date_from_utc(2026, 8, 20)
    advance = greenwich_mean_sidereal_degrees(start + 1.0) - greenwich_mean_sidereal_degrees(start)
    assert advance % 360.0 == pytest.approx(360.9856 % 360.0, abs=1e-3)


def test_sidereal_time_stays_inside_the_half_open_interval() -> None:
    """It is folded through `normalise_degrees`, so the same rounding seam is closed here too."""
    for day in range(0, 4000, 37):
        angle = greenwich_mean_sidereal_degrees(J2000_JULIAN_DATE + day)
        assert 0.0 <= angle < 360.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_time_is_refused_rather_than_producing_an_angle(bad: float) -> None:
    """A NaN here becomes a plotted longitude with no mark, which nobody reads as an error."""
    with pytest.raises(ValueError, match="must be finite"):
        greenwich_mean_sidereal_degrees(bad)
    with pytest.raises(ValueError, match="second must be finite"):
        julian_date_from_utc(2026, 8, 20, 0, 0, bad)


def test_a_sub_satellite_longitude_lands_in_the_geo_belt_convention() -> None:
    """The one frame conversion v1 needs, and it must produce the interval a belt plot uses."""
    julian_date = julian_date_from_utc(2026, 8, 20, 12, 0, 0.0)
    for x, y in ((42164.0, 0.0), (0.0, 42164.0), (-42164.0, 0.0), (0.0, -42164.0)):
        longitude = sub_satellite_longitude_degrees((x, y, 0.0), julian_date)
        assert -180.0 <= longitude < 180.0


#: One sidereal day in days. Earth turns once relative to the stars in this time, not in a solar
#: day, which is the distinction the whole module rests on.
SIDEREAL_DAY_DAYS = 0.99726957


@pytest.mark.parametrize(
    ("label", "day_fraction", "inertial_advance_degrees"),
    [
        ("a quarter sidereal day", 0.25, 90.0),
        ("half a sidereal day", 0.5, 180.0),
        ("a full sidereal day", 1.0, 360.0),
    ],
)
def test_a_geostationary_object_holds_its_longitude(
    label: str, day_fraction: float, inertial_advance_degrees: float
) -> None:
    """The sign of the Earth-rotation term, and the first version of this test did not test it.

    A geostationary object's inertial right ascension advances at exactly Earth's rotation rate,
    so its longitude below is constant. Get the sign wrong and it appears to travel round the
    planet twice a day, which is the 131-degree class of error this whole module exists to avoid
    manufacturing.

    **Why the fraction is parametrised.** The original test used a FULL sidereal day and an
    inertial advance of 2*pi, so both operands returned to their starting values and the
    subtraction was symmetric: measured, the correct sign gives -0.0000 degrees of drift and the
    inverted sign also gives 0.0000. Inverting the operator left the entire suite green. The
    quarter-day case is the discriminating one: correct gives -0.0000, inverted gives -180.0000.
    The full day is kept because it is the physically meaningful statement, and it is now labelled
    as the case that does not discriminate rather than trusted as the one that does.
    """
    start = julian_date_from_utc(2026, 8, 20)
    radius = 42164.0
    angle = math.radians(inertial_advance_degrees)
    later_position = (radius * math.cos(angle), radius * math.sin(angle), 0.0)

    first = sub_satellite_longitude_degrees((radius, 0.0, 0.0), start)
    second = sub_satellite_longitude_degrees(
        later_position, start + SIDEREAL_DAY_DAYS * day_fraction
    )
    drift = shortest_separation_degrees(first, second)
    assert abs(drift) < 0.05, f"{label}: a geostationary object drifted {drift:.4f} degrees"


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_non_finite_position_is_refused_by_the_longitude_conversion(bad: float) -> None:
    """Fail closed at the boundary, as everywhere else in this package."""
    with pytest.raises(ValueError, match="position must be finite"):
        sub_satellite_longitude_degrees((bad, 0.0, 0.0), J2000_JULIAN_DATE)


@pytest.mark.parametrize("julian_date", [1e308, -1e308, 1e11, -1e11])
def test_a_julian_date_that_is_finite_but_absurd_is_refused(julian_date: float) -> None:
    """Finite was not sufficient: the cubic term overflows well inside the float range.

    `1e308` raised an undocumented `OverflowError` straight past the documented contract. The
    bound is roughly plus or minus 27 million years, absurdly generous for a trainer and small
    enough that the polynomial cannot overflow.
    """
    with pytest.raises(ValueError, match="outside the range"):
        greenwich_mean_sidereal_degrees(julian_date)


@pytest.mark.parametrize("component", ["hour", "minute", "second"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_every_time_of_day_component_is_checked_for_finiteness(component: str, bad: float) -> None:
    """The first version checked `second` alone, so a non-finite hour or minute returned a NaN
    Julian Date silently: exactly the failure the guard exists to prevent, one argument along.
    """
    arguments = {"hour": 0, "minute": 0, "second": 0.0}
    arguments[component] = bad
    with pytest.raises(ValueError, match=f"{component} must be finite"):
        julian_date_from_utc(2026, 8, 20, **arguments)  # type: ignore[arg-type]


# --- the guard that was widened twice -----------------------------------------------------


@pytest.mark.parametrize(
    "component",
    ["year", "month", "day", "hour", "minute", "second"],
)
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_every_date_and_time_component_is_checked_for_finiteness(
    component: str, bad: float
) -> None:
    """ALL SIX arguments, parametrised, because widening this guard took two attempts.

    The first version checked `second` alone. The second widened it to the three time-of-day
    arguments and stopped one short of the date: `day` is declared `int` exactly as `hour` is, and
    `julian_date_from_utc(2000, 1, nan)` returned `nan` while `day=inf` returned `inf`. Widening a
    guard to the arguments that were REPORTED rather than to the whole signature is how a boundary
    gets fixed twice, so the whole signature is enumerated here and a new argument that is not
    covered will read as an obvious gap in this list.
    """
    arguments: dict[str, float] = {
        "year": 2000,
        "month": 1,
        "day": 1,
        "hour": 12,
        "minute": 0,
        "second": 0.0,
    }
    arguments[component] = bad
    with pytest.raises(ValueError, match=component):
        julian_date_from_utc(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("component", "value"),
    [
        ("year", 1e308),
        ("year", 10**400),
        ("month", 10**400),
        ("day", 1e308),
        ("day", 10**500),
        ("year", -1e308),
        # The time-of-day half. Narrowing the bound back to the three date components left this
        # whole file green without these, which is the fault this guard has now had four times:
        # the arguments that were REPORTED get covered and the rest of the signature does not.
        # Measured under the narrow bound: `hour=1e308` returned 4.1666666666666665e+306,
        # `second=1e308` returned 1.1574074074074075e+303, `hour=1e17` returned
        # 4166666669118211.0, and `hour=10**400` raised the undocumented `OverflowError` the
        # guard exists to replace.
        ("hour", 1e308),
        ("hour", 1e17),
        ("hour", 10**400),
        ("minute", 1e308),
        ("minute", 10**400),
        ("second", 1e308),
        ("second", 10**400),
    ],
    ids=[
        "year 1e308",
        "year huge int",
        "month huge int",
        "day 1e308",
        "day huge int",
        "year -1e308",
        "hour 1e308",
        "hour 1e17",
        "hour huge int",
        "minute 1e308",
        "minute huge int",
        "second 1e308",
        "second huge int",
    ],
)
def test_a_calendar_component_too_large_to_be_a_date_is_refused(
    component: str, value: float
) -> None:
    """MAGNITUDE, not only finiteness, and this guard has now been widened three times.

    `1e308` is finite and satisfies `value == int(value)`, so both earlier loops passed it and
    `math.floor(365.25 * (year + 4716))` raised a bare `OverflowError`. An integer `10**400` is
    worse: `math.isfinite` ITSELF raises `OverflowError: int too large to convert to float` on it,
    so the guard written to prevent an undocumented exception was throwing one, before the
    magnitude check could see the value. Integers skip the finiteness test now, being finite by
    construction.

    And the silent direction, which is worse than either: `year=1e300, month=3` returned
    3.652425e+302 and `day=1e308` returned 1e+308. Finite numbers that are not dates, handed back
    without complaint, into a function whose whole purpose is that a bad time never reaches a
    plotted longitude. The bound is derived from `MAX_JULIAN_DATE`, which
    `greenwich_mean_sidereal_degrees` twenty lines below had applied for this exact reason since
    the day it was written - so the lesson was in the file and was not carried across.
    """
    arguments: dict[str, float] = {
        "year": 2000,
        "month": 1,
        "day": 1,
        "hour": 12,
        "minute": 0,
        "second": 0.0,
    }
    arguments[component] = value
    with pytest.raises(ValueError, match="Julian Date"):
        julian_date_from_utc(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("hour", "minute", "second"),
    [(12.5, 0, 0.0), (0, 30.5, 0.0), (0, 0, 30.25), (12, 30, 30.5)],
)
def test_a_fractional_time_of_day_is_accepted(hour: float, minute: float, second: float) -> None:
    """The half of the integrality rule I INTRODUCED, and left untested.

    Merging the six components into one loop meant the whole-number check had to be scoped back to
    year, month and day, because a fractional hour or second is ordinary and correct. Widening it to
    all six left the entire suite green: none of the fifteen `julian_date_from_utc` call sites in
    this suite passed a fractional time, so nothing asserted the behaviour the scoping exists to
    preserve.

    That is the same asymmetry the guard's own comment says has now happened four times - the
    reported half gets thirteen cases and the half I added gets none.
    """
    assert math.isfinite(julian_date_from_utc(2000, 1, 1, hour, minute, second))


@pytest.mark.parametrize("component", ["year", "month", "day"])
def test_a_fractional_calendar_index_is_still_refused(component: str) -> None:
    """The control for the test above: the scoping must exempt the times, not the dates."""
    arguments: dict[str, float] = {"year": 2000, "month": 1, "day": 1}
    arguments[component] = arguments[component] + 0.5
    with pytest.raises(ValueError, match="whole number"):
        julian_date_from_utc(**arguments)  # type: ignore[arg-type]


def test_a_real_calendar_date_is_still_accepted() -> None:
    """The control: the bound must refuse a non-date, not refuse a date.

    Both ends of anything this trainer will see, plus the Julian Date epoch itself, because a
    magnitude guard that clipped the useful range would satisfy every test above while being
    broken.
    """
    assert julian_date_from_utc(2000, 1, 1, 12, 0, 0.0) == 2451545.0
    for year in (-4712, 1957, 2026, 9999):
        assert math.isfinite(julian_date_from_utc(year, 1, 1))


@pytest.mark.parametrize(("year", "month"), [(2000.5, 1), (2000, 1.5)])
def test_the_calendar_indices_refuse_a_fractional_value(year: float, month: float) -> None:
    """`year` and `month` index the calendar rather than scaling it.

    They previously raised `ValueError` and `OverflowError` from the integer floor division
    further down, which was not silent but was not documented either, and an undocumented
    exception type is a control a caller cannot handle. A fractional year is not a rounding
    question, it is a caller who passed the wrong thing.
    """
    with pytest.raises(ValueError, match="whole number"):
        julian_date_from_utc(year, month, 1)  # type: ignore[arg-type]


def test_a_position_on_the_spin_axis_is_refused_rather_than_given_a_longitude() -> None:
    """`atan2(0.0, 0.0)` is 0.0 by convention, not an error, so this returned a plausible angle.

    Measured before the fix: `(0.0, 0.0, 0.0)` at J2000 returned 79.539 degrees, a number that
    looks entirely reasonable for a point that has no longitude at all. A plausible wrong answer
    is the worst kind in a trainer whose whole purpose is teaching people to distrust a plotted
    position, and every sibling in this package documents or refuses its degenerate case.
    """
    with pytest.raises(ValueError, match="spin axis"):
        sub_satellite_longitude_degrees((0.0, 0.0, 0.0), 2451545.0)
    with pytest.raises(ValueError, match="spin axis"):
        sub_satellite_longitude_degrees((0.0, 0.0, 7000.0), 2451545.0)


def test_a_position_just_off_the_axis_still_gets_a_longitude() -> None:
    """The control for the refusal above: it must refuse the degenerate case, not the small one."""
    longitude = sub_satellite_longitude_degrees((1e-9, 0.0, 7000.0), 2451545.0)
    assert math.isfinite(longitude)
