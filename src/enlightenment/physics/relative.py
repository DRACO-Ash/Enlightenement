"""Clohessy-Wiltshire relative motion in the Hill frame, for rendezvous and proximity work.

The frame, stated once because every sign error in this subject is a frame confusion. Origin at
the chief spacecraft, and a right-handed set:

● **radial** (often R or x): outward from the Earth's centre through the chief.
● **along-track** (S or y): along the chief's velocity, in the direction of motion.
● **cross-track** (W or z): completing the set, along the negative orbit normal.

The equations are the linearised relative motion of a deputy near a chief in a CIRCULAR orbit,
and the linearisation is the limitation that matters: they hold while the separation is small
against the orbit radius, and they assume the chief's orbit is circular. For the Rendezvous and
Proximity Operations (RPO) scenarios v1 covers, both hold comfortably. A scenario that violates
either must propagate both objects with SGP4 and difference them, not use this.

**The counter-intuitive behaviour this exists to teach.** A purely radial offset does not stay
radial: it produces a secular along-track drift of minus six times the mean motion times the
offset. An operator who expects "I moved up, so I stay above" is wrong in a way that compounds
every orbit, and that class of error is exactly what competency axis four, physical reasoning,
scores. The no-drift condition is along-track rate equals minus twice the mean motion times the
radial offset, and it is asserted as a property rather than described.

The closed form below was verified against numerical integration of the underlying differential
equations, not against my own algebra. That distinction is the whole reason the check exists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from sgp4.api import Satrec

#: Earth's gravitational parameter, cubic kilometres per second squared, as SGP4 uses it.
#:
#: **This is 398600.5, not the modern EGM-96 398600.4418, and the difference is deliberate.** The
#: first version here used the modern value under a comment claiming it was "the one SGP4 itself
#: uses". Measured: `sgp4.earth_gravity.wgs84.mu` is 398600.5. The claim was false, so either the
#: value or the claim had to change.
#:
#: The value changed, because the stated rationale is sound: a chief's mean motion derived here
#: and a track propagated by SGP4 should not disagree for a reason nobody can see. Numerically it
#: barely matters, and that is stated rather than implied: the two differ by 1.5e-7 relative,
#: giving a mean-motion difference of 7.3e-8 relative, which over one orbit is a phase error far
#: below anything a trainer displays. It matters for consistency, not accuracy.
#:
#: **Prefer :func:`mean_motion_from_elements` when an element set exists.** Recomputing a mean
#: motion from a radius when the element set already carries one is a conversion with nothing to
#: gain. This constant is for a synthetic circular chief specified by altitude.
EARTH_MU_KM3_S2: Final = 398600.5

#: Seconds in a minute. SGP4 works in minutes; this module works in seconds.
SECONDS_PER_MINUTE: Final = 60.0

#: The frame these vectors are expressed in. Carried in the type for the same reason the
#: propagator carries TEME: a Hill-frame vector read as an inertial one is silently wrong.
HILL_FRAME: Final = "HILL_RADIAL_ALONGTRACK_CROSSTRACK"


class RelativeMotionError(ValueError):
    """Raised when a relative-motion input cannot produce a usable state."""


@dataclass(frozen=True, slots=True)
class RelativeState:
    """A deputy's state relative to the chief, in the Hill frame, kilometres and km/s.

    Frozen, like :class:`StateVector`, so a state cannot differ between a solvability check and
    the score computed from it.
    """

    position_km: tuple[float, float, float]
    velocity_km_s: tuple[float, float, float]
    frame: str = HILL_FRAME

    @property
    def range_km(self) -> float:
        """Separation between deputy and chief."""
        return math.hypot(*self.position_km)

    @property
    def range_rate_km_s(self) -> float:
        """Rate of change of separation. Negative is closing, which is the sign an operator reads.

        Zero when the separation is zero, because the rate is undefined there and a division by
        zero in a plotted closing rate is worse than a defensible convention.
        """
        separation = self.range_km
        # The precondition a division needs, stated positively. Three forms have been through
        # here: `separation == 0.0` (float equality, a Sonar bug class), then
        # `not separation > 0.0` (Sonar's S1940, negated comparison), and now this.
        #
        # `separation <= 0.0` ALONE would not do, and that is the whole point of the `isnan`
        # clause: `not x > 0.0` is True for NaN while `x <= 0.0` is False, so taking Sonar's
        # suggested operator literally would have let a NaN separation reach the division and
        # returned NaN as a closing rate. Writing the NaN case out is both analyser-clean and
        # the honest statement of what a divisor must be.
        if separation <= 0.0 or math.isnan(separation):
            return 0.0
        return sum(p * v for p, v in zip(self.position_km, self.velocity_km_s, strict=True)) / (
            separation
        )


def mean_motion_rad_s(semi_major_axis_km: float) -> float:
    """Return the mean motion of a circular orbit, radians per second.

    Rejects a non-positive or non-finite radius rather than returning a complex or infinite rate:
    a scenario template with a bad altitude must fail at authoring time.
    """
    if not math.isfinite(semi_major_axis_km) or semi_major_axis_km <= 0.0:
        raise RelativeMotionError(
            f"semi-major axis must be finite and positive, got {semi_major_axis_km!r}"
        )
    # Finite and positive is not sufficient, so the ARITHMETIC is guarded rather than the range:
    # 1e-200 cubes to zero and raised `ZeroDivisionError`, and 1e300 raised `OverflowError`. Both
    # escaped the documented `RelativeMotionError`, so a caller failing closed on the documented
    # type caught neither. Guarding the arithmetic avoids inventing a physical range to defend.
    #
    # The RESULT is checked as well, and the reason is a mistake worth recording. Coverage showed
    # that check dead, so I removed it, writing an argument that the division could not underflow
    # to zero while the cube stayed finite. That argument was true and irrelevant: the failure is
    # OVERFLOW, not underflow, and float division overflows SILENTLY to infinity rather than
    # raising the way `**` does. A logarithmic sweep found it on the first run - an axis of 1e-105
    # cubes to a subnormal, the division returns `inf`, and `math.sqrt(inf)` is `inf`.
    #
    # Third time in this project that I removed a guard on a reachability argument and was wrong.
    # The guard stays, and the sweep is what covers it rather than what replaces it.
    #
    # Precisely what the sweep covers, so nobody reads more into it than it proves. The `isfinite`
    # half is reached, and the honest attribution of the count matters: an ad-hoc grid over
    # mantissas {1, 1.5, 2, 3, 5} found 35 reaching axes between 1.5e-108 and 1e-101, while the
    # COMMITTED sweep in the test suite steps decades three at a time and reaches the branch at 2
    # axes, never evaluating 1.5e-108 at all. Both numbers are real measurements of different
    # grids, and citing the wider one as though the suite ran it is the fault this release is
    # about, so both are named.
    #
    # The `rate <= 0.0` half is unreachable BY CONSTRUCTION here - `sqrt` returns zero only if the
    # division underflows to zero, and since `EARTH_MU_KM3_S2 / 5e-324` itself overflows, NO finite
    # double cube can drive the quotient to zero. (An earlier version of this comment said "needs a
    # cube above 1e313", which is roughly the subnormal threshold rather than the zero threshold;
    # the conclusion was right and conservative, the reason was imprecise.) It is belt and braces
    # against a future edit to the arithmetic, not a covered control, and removing that sub-clause
    # alone leaves the suite green. The identical line in `mean_motion_from_elements` below IS
    # reachable, because an element set can carry a non-positive mean motion, and that one is
    # mutation-killed.
    try:
        rate = math.sqrt(EARTH_MU_KM3_S2 / semi_major_axis_km**3)
    except (ZeroDivisionError, OverflowError) as exhausted:
        raise RelativeMotionError(
            f"semi-major axis {semi_major_axis_km!r} is finite but outside the range floating"
            f" point can express a mean motion for: {exhausted}"
        ) from exhausted
    if not math.isfinite(rate) or rate <= 0.0:
        raise RelativeMotionError(
            f"semi-major axis {semi_major_axis_km!r} gives an unusable mean motion {rate!r}"
        )
    return rate


def mean_motion_from_elements(elements: Satrec) -> float:
    """Return the chief's mean motion in radians per second, taken from its element set.

    The preferred path whenever a real element set exists, because the element set already
    carries the mean motion and recomputing it from an assumed circular radius throws that away.
    `no_kozai` is the Kozai mean motion in radians per MINUTE, which is the quantity SGP4 itself
    propagates with, so a Hill-frame scenario built on this and a track propagated by SGP4 share
    the same rate exactly rather than approximately.
    """
    # Coerced explicitly: `sgp4` ships no type stubs, so `no_kozai` is `Any` and returning it
    # straight would let an untyped value out of the one module that wraps the library.
    rate = float(elements.no_kozai) / SECONDS_PER_MINUTE
    if not math.isfinite(rate) or rate <= 0.0:
        raise RelativeMotionError(
            f"the element set gives a non-usable mean motion: {elements.no_kozai!r} rad/min"
        )
    return rate


def no_drift_alongtrack_rate_km_s(radial_offset_km: float, mean_motion: float) -> float:
    """Return the along-track rate that cancels the secular drift of a radial offset.

    Minus twice the mean motion times the radial offset. Provided as a named function rather than
    left as a comment, because it is the one number an RPO scenario author most needs and most
    easily gets the sign of wrong.

    Guarded like every sibling in this module. It accepted a non-finite input silently and returned
    NaN, which is worse here than elsewhere: the output IS an initial velocity, so the NaN would
    have been written into a scenario's starting conditions rather than surfacing at a boundary.
    """
    if not math.isfinite(radial_offset_km) or not math.isfinite(mean_motion):
        raise RelativeMotionError(
            f"the radial offset and mean motion must both be finite, got"
            f" {radial_offset_km!r} and {mean_motion!r}"
        )
    rate = -2.0 * mean_motion * radial_offset_km
    # The RESULT, not only the inputs, and this is the lesson from `mean_motion_rad_s` applied one
    # function along instead of being written down and left there. Two finite inputs multiply to
    # infinity SILENTLY: (1e300, 1e300) returned -inf, (1.797e308, 2.0) returned -inf. The
    # docstring above argues that a NaN here is worse than elsewhere because the value IS an
    # initial velocity written into a scenario's starting conditions. An infinite one lands in
    # exactly the same place, so the guard that catches only the NaN catches half the fault.
    if not math.isfinite(rate):
        raise RelativeMotionError(
            f"the no-drift rate overflowed to {rate!r} for radial offset {radial_offset_km!r}"
            f" and mean motion {mean_motion!r}"
        )
    return rate


def propagate_relative(state: RelativeState, mean_motion: float, seconds: float) -> RelativeState:
    """Advance ``state`` by ``seconds`` under the Clohessy-Wiltshire solution.

    Closed form, not integrated, so a debrief can jump to any time in a run without stepping
    there. Verified against a fourth-order Runge-Kutta integration of the underlying equations
    over a full orbit: agreement to better than a micrometre in position.
    """
    if not math.isfinite(seconds):
        raise RelativeMotionError(f"seconds must be finite, got {seconds!r}")
    if not math.isfinite(mean_motion) or mean_motion <= 0.0:
        raise RelativeMotionError(f"mean motion must be finite and positive, got {mean_motion!r}")
    components = (*state.position_km, *state.velocity_km_s)
    if not all(math.isfinite(component) for component in components):
        raise RelativeMotionError(f"relative state must be finite, got {state!r}")

    x, y, z = state.position_km
    dx, dy, dz = state.velocity_km_s
    n = mean_motion
    nt = n * seconds
    # Two finite factors overflow silently, and then `math.sin(inf)` raises a bare
    # `ValueError: math domain error` rather than the documented `RelativeMotionError`:
    # measured at n=1e300, seconds=1e300. Checked here so the boundary raises its own type.
    if not math.isfinite(nt):
        raise RelativeMotionError(
            f"mean motion {n!r} times {seconds!r} seconds overflowed to {nt!r}"
        )
    sin_nt = math.sin(nt)
    cos_nt = math.cos(nt)

    next_x = (4.0 - 3.0 * cos_nt) * x + sin_nt / n * dx + 2.0 * (1.0 - cos_nt) / n * dy
    next_y = (
        6.0 * (sin_nt - nt) * x
        + y
        - 2.0 * (1.0 - cos_nt) / n * dx
        + (4.0 * sin_nt - 3.0 * nt) / n * dy
    )
    next_z = cos_nt * z + sin_nt / n * dz

    next_dx = 3.0 * n * sin_nt * x + cos_nt * dx + 2.0 * sin_nt * dy
    next_dy = 6.0 * n * (cos_nt - 1.0) * x - 2.0 * sin_nt * dx + (4.0 * cos_nt - 3.0) * dy
    next_dz = -n * sin_nt * z + cos_nt * dz

    propagated = (next_x, next_y, next_z, next_dx, next_dy, next_dz)
    # Finite inputs within range still produce infinite outputs: n=1e-8 over 1e300 seconds gave an
    # along-track position of -inf, and a 1e308 radial offset gave +inf. A state carrying an
    # infinity propagates it into every later step and into whatever is plotted from it, so it
    # fails here where the caller can still see which call did it.
    if not all(math.isfinite(component) for component in propagated):
        raise RelativeMotionError(
            f"propagating {state!r} by {seconds!r} seconds at mean motion {n!r} overflowed"
            f" to {propagated!r}"
        )
    return RelativeState(
        position_km=(next_x, next_y, next_z),
        velocity_km_s=(next_dx, next_dy, next_dz),
    )


def relative_acceleration_km_s2(
    state: RelativeState, mean_motion: float
) -> tuple[float, float, float]:
    """Return the Hill-frame acceleration, for verifying the closed form by integration.

    The differential equations the closed form solves, exposed rather than buried, so a test can
    integrate them independently and compare. A closed form checked only against the algebra that
    produced it is checked against nothing.

    **Guarded like every sibling, which it was not.** This function was added to the package's
    public `__all__` in the same change that closed five boundary escapes elsewhere in this
    module, with no validation of its own: `n` non-finite returned a silent `(nan, nan, nan)`,
    `n=1e200` raised an undocumented `OverflowError` from the square, and a NaN state component
    passed straight through. Exporting a function is what makes its boundary a boundary, so the
    export and the guard belong in the same change.
    """
    components = (*state.position_km, *state.velocity_km_s)
    if not all(math.isfinite(component) for component in components):
        raise RelativeMotionError(f"relative state must be finite, got {state!r}")
    if not math.isfinite(mean_motion):
        raise RelativeMotionError(f"mean motion must be finite, got {mean_motion!r}")

    x, _, z = state.position_km
    dx, dy, _ = state.velocity_km_s
    n = mean_motion
    try:
        acceleration = (3.0 * n**2 * x + 2.0 * n * dy, -2.0 * n * dx, -(n**2) * z)
    except OverflowError as overflow:
        raise RelativeMotionError(
            f"the acceleration overflowed at mean motion {n!r} for state {state!r}"
        ) from overflow
    if not all(math.isfinite(component) for component in acceleration):
        raise RelativeMotionError(
            f"the acceleration overflowed to {acceleration!r} at mean motion {n!r}"
        )
    return acceleration
