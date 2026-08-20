"""Angle handling, isolated because the plus-or-minus-180 seam is a named bug trap.

The flight plan lists "angle wrapping across the plus or minus 180 seam" as a regression
trap to name explicitly, and the reason is operational: GEO belt plots are longitude
against inclination, so a geostationary object drifting past the antimeridian is exactly
where a naive implementation reports a drift rate of hundreds of degrees per day. That
artefact class is what competency axis five ("uncertainty and calibration") exists to train,
so the trainer must not manufacture its own version of it.

Degrees are used at the boundary because procedures, plots and operators all speak degrees.
Radians stay inside the propagator.
"""

from __future__ import annotations

import math

#: A full turn in degrees. Named so the wrap arithmetic reads as intent, not magic.
FULL_TURN_DEGREES = 360.0

#: Half a turn. The seam itself.
HALF_TURN_DEGREES = 180.0


def _fold_into_turn(value: float, turn: float) -> float:
    """Return ``value`` reduced modulo a POSITIVE ``turn``, guaranteed strictly below it.

    Python's ``%`` does not guarantee that on its own, and the gap is exactly the seam this
    module exists to close. For a tiny negative input the exact answer is a hair under a
    full turn, an amount too small to represent at that magnitude, so the result rounds UP
    to the turn itself and lands on the excluded end of a half-open interval. Property
    testing found it at ``-1.13e-78``, where ``angle % 360.0`` returns ``360.0``.

    That is not a curiosity. It is the drift-rate artefact in miniature: a value a hair
    below one end of the interval reported at the other end, which is a swing of a whole
    turn for a body that did not move.

    ``turn`` must be positive. Both call sites pass a module constant, and for a negative
    turn the guard below would be true for every input and return zero for all of them, so
    the contract is stated rather than defended.
    """
    folded = value % turn
    return 0.0 if folded >= turn else folded


def normalise_degrees(angle: float) -> float:
    """Return ``angle`` in ``[0, 360)``.

    Used for right ascension, argument of perigee and mean anomaly, where the natural
    range starts at zero.
    """
    if not math.isfinite(angle):
        raise ValueError(f"angle must be finite, got {angle!r}")
    return _fold_into_turn(angle, FULL_TURN_DEGREES)


def normalise_longitude(longitude: float) -> float:
    """Return ``longitude`` in ``[-180, 180)``, the convention GEO belt plots use.

    The half-open interval matters: 180 and -180 are the same meridian, and allowing both
    lets the same physical location compare unequal, which is how a "drift" of 360 degrees
    per timestep gets reported.

    **Fold first, then shift, and the order is the whole correctness argument.** The obvious
    implementation adds half a turn, folds, and subtracts it back. That version passed the
    low end of the interval and failed the high end, because the ADDITION loses the
    precision before the fold ever sees it: ``179.99999999999997 + 180.0`` rounds to
    ``360.0``, the fold correctly maps that to ``0.0``, and subtracting half a turn returns
    ``-180.0`` for an input that was already in range. Two frames one representable step
    apart then reported a drift of ``-359.99999999999994`` for 2.8e-14 degrees of real
    motion, which is the artefact this module exists to prevent, reintroduced by the fix
    for it. A shared helper cannot see that: the damage is done in its argument.

    Folding into ``[0, 360)`` first and subtracting a whole turn from the upper half touches
    the input with no lossy arithmetic at all. Verified over 600,000 random samples and
    4,000 exhaustive representable steps either side of both ends.
    """
    if not math.isfinite(longitude):
        raise ValueError(f"longitude must be finite, got {longitude!r}")
    folded = _fold_into_turn(longitude, FULL_TURN_DEGREES)
    return folded - FULL_TURN_DEGREES if folded >= HALF_TURN_DEGREES else folded


def wrap_to_pi(radians: float) -> float:
    """Return ``radians`` in ``[-pi, pi)``. The radian twin of :func:`normalise_longitude`."""
    if not math.isfinite(radians):
        raise ValueError(f"angle must be finite, got {radians!r}")
    folded = _fold_into_turn(radians, math.tau)
    return folded - math.tau if folded >= math.pi else folded


def shortest_separation_degrees(first: float, second: float) -> float:
    """Signed separation from ``first`` to ``second``, in ``[-180, 180)``.

    THE function the drift-rate bug hides in. Subtracting two longitudes either side of the
    antimeridian gives about 360 degrees; the shortest way round gives the truth. A GEO
    object crossing the seam between two observations is a routine occurrence, not an edge
    case, so this is the only permitted way to difference two angles in this codebase.
    """
    return normalise_longitude(second - first)
