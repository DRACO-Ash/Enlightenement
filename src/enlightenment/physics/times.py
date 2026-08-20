"""Time and Earth-rotation conversions, with the scale named in every signature.

Named `times` rather than `time` deliberately: a module called `time` inside a package shadows
nothing today, but it invites `import time` to resolve somewhere unexpected in a future
refactor, and the cost of finding that out is far above the cost of one extra letter.

Two of the flight plan's named traps live here, and both are silent.

● **UT1 is not UTC.** Earth rotation runs on UT1; civil time runs on UTC, and they differ by up
  to 0.9 seconds (DUT1) because leap seconds keep UTC near UT1 in whole steps. 0.9 seconds of
  Earth rotation is about 0.0037 degrees of longitude, roughly 400 metres at the equator, which
  is small until it is compared against a plot from another source and read as a real offset.
  This module takes UT1 and says so. The scenario engine owns the conversion, and for synthetic
  training data DUT1 is legitimately zero because there is no real observation to reconcile.
● **A TLE epoch is not a calendar time.** The element-set epoch is a two-digit year and a
  fractional day of year, and SGP4 takes MINUTES SINCE THAT EPOCH. Nothing here converts one to
  the other implicitly. `propagate_minutes_since_epoch` takes minutes for that reason, and this
  module exists so a scenario can state a wall-clock time separately and explicitly.

No leap-second table is shipped. That is a deliberate limitation, not an oversight: a table goes
stale, a stale table is worse than none, and v1 serves synthetic data with no real epoch to
reconcile. If real observations ever arrive, the table becomes versioned content with an owner
and a review date, like the noise model.
"""

from __future__ import annotations

import math
from typing import Final

from enlightenment.physics.angles import normalise_degrees, normalise_longitude

#: The Julian Date of the J2000.0 epoch, 2000 January 1 at 12:00 Terrestrial Time.
J2000_JULIAN_DATE: Final = 2451545.0

#: Days in a Julian century, the unit the Earth-rotation polynomial is expressed in.
DAYS_PER_JULIAN_CENTURY: Final = 36525.0

#: The widest Julian Date this polynomial is evaluated over. Roughly plus or minus 27 million
#: years, which is absurdly generous for a trainer and far below the magnitude at which the cubic
#: term overflows a double. A bound is needed because "finite" was not sufficient: 1e308 raised an
#: undocumented `OverflowError` straight past the documented contract.
MAX_JULIAN_DATE: Final = 1e10

#: Largest magnitude accepted for a calendar year, month or day. Derived from `MAX_JULIAN_DATE`
#: rather than chosen: a year contributes roughly 365.25 days, so anything past this cannot land
#: inside the Julian Date range the sidereal-time polynomial will accept, and the two bounds
#: therefore cannot disagree. Comfortably past every real epoch - 27 million years either side of
#: the present - and short of the magnitudes that made `math.floor` raise an undocumented
#: `OverflowError` or, worse, return a finite number that was not a date.
MAX_CALENDAR_COMPONENT: Final = MAX_JULIAN_DATE / 365.25

#: How much of an out-of-range component an error message may repeat. An integer has no width
#: limit, so the message needs one.
MAX_SHOWN_COMPONENT: Final = 24

#: The components that index the calendar rather than scaling a fraction of a day. Only these
#: three must be whole numbers; a fractional hour or second is ordinary.
CALENDAR_INDICES: Final = frozenset({"year", "month", "day"})

#: Seconds in a day, and the seconds-of-time to degrees-of-arc factor (86400 / 360).
SECONDS_PER_DAY: Final = 86400.0
SECONDS_PER_DEGREE: Final = 240.0

#: March, as a month number. Before this, a year is treated as ending in the previous one by the
#: Julian Date algorithm, which is why the guard below exists at all.
MARCH: Final = 3


def julian_date_from_utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: float = 0.0
) -> float:
    """Return the Julian Date for a proleptic Gregorian calendar date and time.

    The standard algorithm, with January and February treated as months 13 and 14 of the previous
    year so the leap-day arithmetic falls at the end of the year rather than the middle.

    Rejects a non-finite second outright, for the same reason every other boundary in this package
    does: a NaN here propagates into an Earth-rotation angle and then into a plotted longitude,
    where it is a mark that never appears rather than an error anybody sees.
    """
    # ALL SIX components, and getting here took two goes. The first version checked `second`
    # alone, so a non-finite hour or minute returned a NaN or an infinite Julian Date silently.
    # The second widened it to the three time-of-day arguments and stopped one short of the date:
    # `day` is declared `int` exactly as `hour` is, and `julian_date_from_utc(2000, 1, nan)`
    # returned `nan`, `day=inf` returned `inf`. Widening a guard to "the ones that were reported"
    # rather than to the whole signature is how a boundary gets fixed twice.
    #
    # `year` and `month` were not silent - they raised `ValueError` and `OverflowError` from the
    # integer floor division below - but neither was documented, and an undocumented exception
    # type is a control a caller cannot handle.
    for name, value in (
        ("year", year),
        ("month", month),
        ("day", day),
        ("hour", hour),
        ("minute", minute),
        ("second", second),
    ):
        # `math.isfinite` is asked only about floats, because it RAISES on an integer too large
        # to convert - `math.isfinite(10**400)` gives `OverflowError: int too large to convert to
        # float`, so the guard meant to stop an undocumented exception was raising one itself, and
        # before the magnitude bound below could see the value. An `int` is finite by
        # construction, so skipping it is not a relaxation.
        if not isinstance(value, int) and not math.isfinite(value):
            raise ValueError(f"{name} must be finite, got {value!r}")
        # MAGNITUDE, not only finiteness, and this bound was missing while the lesson sat twenty
        # lines below in `greenwich_mean_sidereal_degrees`: "finite is not sufficient". Measured
        # before it: `year=1e308` raised a bare `OverflowError` from `math.floor`, an int `10**400`
        # raised `OverflowError: int too large to convert to float`, and - the silent direction,
        # which is worse - `year=1e300, month=3` returned 3.652425e+302 and `day=1e308` returned
        # 1e+308. Those are finite values that are not dates, handed back with no complaint, and
        # the whole point of this guard is that a bad time never reaches a plotted longitude.
        #
        # **ALL SIX, and this is the THIRD time this one guard has been widened.** Round one
        # checked `second`. Round two widened finiteness to all six and magnitude to year, month
        # and day. Round three is this: `hour=1e308` returned 4.1666666666666665e+306,
        # `second=1e308` returned 1.1574074074074075e+303, and `hour=10**400` raised the exact
        # undocumented `OverflowError` the guard exists to replace - from the `day_fraction`
        # arithmetic instead of from `math.floor`. The test immediately above this one enumerates
        # all six for finiteness and says in its own docstring that widening a guard to the
        # arguments that were REPORTED is how a boundary gets fixed twice. It then got fixed a
        # third time, one guard along, in the same file, by me, in the next commit.
        #
        # One loop over one tuple now, so a seventh argument cannot be half-covered.
        #
        # Bounded by what can produce a Julian Date this package will accept, so the two guards
        # agree instead of one of them being decorative. The same bound serves all six: a
        # time-of-day component past 27 million is no more a time than it is a date.
        if abs(value) > MAX_CALENDAR_COMPONENT:
            # Bounded by TRUNCATION, not by formatting. `value!r` put four hundred digits in the
            # message for `10**400`, and the obvious fix, `float(value):.6g`, raises the very
            # `OverflowError: int too large to convert to float` this guard exists to replace.
            # Converting an out-of-range value in order to complain about it is the trap.
            shown = repr(value)
            if len(shown) > MAX_SHOWN_COMPONENT:
                shown = f"{shown[:MAX_SHOWN_COMPONENT]}... ({len(shown)} digits)"
            raise ValueError(
                f"{name} of {shown} cannot produce a Julian Date within plus or minus"
                f" {MAX_JULIAN_DATE:g}"
            )
        # Integrality applies to the DATE components only: they index the calendar rather than
        # scaling it, so a fractional value there is not a rounding question, it is a caller who
        # passed the wrong thing. A fractional hour or second is ordinary and correct.
        if name in CALENDAR_INDICES and value != int(value):
            raise ValueError(f"{name} must be a whole number, got {value!r}")
    if month < MARCH:
        year -= 1
        month += 12
    century = year // 100
    gregorian_correction = 2 - century + century // 4
    day_fraction = (hour + minute / 60.0 + second / 3600.0) / 24.0
    return (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day
        + gregorian_correction
        - 1524.5
        + day_fraction
    )


def greenwich_mean_sidereal_degrees(julian_date_ut1: float) -> float:
    """Return Greenwich Mean Sidereal Time in degrees, in ``[0, 360)``.

    The IAU 1982 polynomial, which is the form SGP4's own deep-space model uses. Verified against
    `sgp4.propagation.gstime` in the pinned wheel across five epochs spanning 46 years, agreeing
    to 1.6e-10 degrees, and separately sanity-checked against an almanac: sidereal time at 0h UT
    on 1 August 1992 comes out at 20h 39m, and the almanac says about 20h 40m.

    That second check earned its place. The first version of this was written against a reference
    value recalled from memory rather than read, and disagreed with it by 131 degrees. The
    implementation was right and the remembered number was wrong, which is the argument for
    validating against something the machine can produce rather than something I can recall.

    ``julian_date_ut1`` is UT1, not UTC. See the module docstring.
    """
    if not math.isfinite(julian_date_ut1):
        raise ValueError(f"julian date must be finite, got {julian_date_ut1!r}")
    if abs(julian_date_ut1) > MAX_JULIAN_DATE:
        # Finite is not sufficient: the cubic term overflows well inside the float range, and
        # 1e308 raised an undocumented `OverflowError`. The bound is enormous compared with any
        # date a trainer will see and small enough that the polynomial cannot overflow.
        raise ValueError(
            f"julian date {julian_date_ut1!r} is outside the range this polynomial is defined"
            f" over (plus or minus {MAX_JULIAN_DATE:g})"
        )
    centuries = (julian_date_ut1 - J2000_JULIAN_DATE) / DAYS_PER_JULIAN_CENTURY
    seconds_of_time = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * centuries
        + 0.093104 * centuries**2
        - 6.2e-6 * centuries**3
    )
    degrees = (seconds_of_time % SECONDS_PER_DAY) / SECONDS_PER_DEGREE
    # Folded through the angles module rather than left to `%`, because the same rounding seam
    # that put a longitude at the excluded end of its interval applies here.
    return normalise_degrees(degrees)


def sub_satellite_longitude_degrees(
    position_km: tuple[float, float, float], julian_date_ut1: float
) -> float:
    """Return the east longitude below a TEME position, in ``[-180, 180)``.

    This is the one frame conversion v1 needs, and it needs only Earth rotation: the geographic
    longitude under a point is its right ascension minus Greenwich Mean Sidereal Time. Precession
    and nutation are NOT applied, so this is the True Equator Mean Equinox of date longitude, and
    for a GEO belt plot of longitude against inclination that is the correct and sufficient
    answer.

    **What this deliberately is not.** It is not a conversion to J2000, and it is not a geodetic
    latitude and longitude on a reference ellipsoid. Both need precession, nutation and polar
    motion, which need a validated library rather than an implementation written from memory here.
    `skyfield` is the pinned-in-waiting choice for that, deferred with a written reason until
    something genuinely requires it.
    """
    x, y, _ = position_km
    if not all(math.isfinite(component) for component in position_km):
        raise ValueError(f"position must be finite, got {position_km!r}")
    # A point on the spin axis has no longitude, and `atan2(0.0, 0.0)` is 0.0 by convention
    # rather than an error, so this returned a plausible-looking angle - 79.539 degrees at J2000 -
    # for an input that has none. A plausible wrong answer is the worst kind in a trainer whose
    # purpose is teaching people to distrust a plotted position. Every sibling in this package
    # documents or refuses its degenerate case; this one silently had one.
    if x == 0.0 and y == 0.0:
        raise ValueError(
            "a position on the spin axis has no longitude; the equatorial projection of"
            f" {position_km!r} is zero"
        )
    right_ascension = math.degrees(math.atan2(y, x))
    return normalise_longitude(right_ascension - greenwich_mean_sidereal_degrees(julian_date_ut1))
