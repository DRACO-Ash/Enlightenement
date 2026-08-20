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
    """Return ``value`` reduced modulo ``turn``, guaranteed STRICTLY below ``turn``.

    Python's ``%`` does not guarantee that on its own, and the gap is exactly the seam this
    module exists to close. For a tiny negative input the exact answer is a hair under a
    full turn, an amount too small to represent at that magnitude, so the result rounds UP
    to the turn itself and lands on the excluded end of a half-open interval. Property
    testing found it at ``-1.13e-78``, where ``angle % 360.0`` returns ``360.0``.

    That is not a curiosity. It is the drift-rate artefact in miniature: a value a hair
    below one end of the interval reported at the other end, which is a swing of a whole
    turn for a body that did not move. Folding here means every wrapper in this module
    inherits the guarantee from one place, rather than three near-copies of the same
    arithmetic each having to remember it.
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
    """
    if not math.isfinite(longitude):
        raise ValueError(f"longitude must be finite, got {longitude!r}")
    shifted = _fold_into_turn(longitude + HALF_TURN_DEGREES, FULL_TURN_DEGREES)
    return shifted - HALF_TURN_DEGREES


def wrap_to_pi(radians: float) -> float:
    """Return ``radians`` in ``[-pi, pi)``. The radian twin of :func:`normalise_longitude`."""
    if not math.isfinite(radians):
        raise ValueError(f"angle must be finite, got {radians!r}")
    shifted = _fold_into_turn(radians + math.pi, math.tau)
    return shifted - math.pi


def shortest_separation_degrees(first: float, second: float) -> float:
    """Signed separation from ``first`` to ``second``, in ``[-180, 180)``.

    THE function the drift-rate bug hides in. Subtracting two longitudes either side of the
    antimeridian gives about 360 degrees; the shortest way round gives the truth. A GEO
    object crossing the seam between two observations is a routine occurrence, not an edge
    case, so this is the only permitted way to difference two angles in this codebase.
    """
    return normalise_longitude(second - first)
