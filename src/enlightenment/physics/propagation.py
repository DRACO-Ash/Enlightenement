"""SGP4 propagation, wrapped so the rest of the trainer never touches the library directly.

Why a wrapper at all, rather than calling `sgp4` from the scenario engine: the library
returns an error CODE and a tuple of raw floats in TEME kilometres and kilometres per
second. Two of the flight plan's named bug traps live in exactly that gap.

● **TEME is not J2000.** The library's output frame is True Equator Mean Equinox of date.
  Treating it as J2000 is a silently-wrong answer of the worst kind: plausible, stable, and
  off by an amount that grows with epoch separation. The frame is therefore carried in the
  type, so it cannot be forgotten, and any conversion must be explicit.
● **An error code that is not checked is a fabricated state vector.** SGP4 signals decay,
  a bad element set and a hyperbolic orbit through a return code. Ignoring it yields
  numbers that look like a position. Every code is turned into an exception here, because
  a trainer that scores an operator against a fabricated state is worse than one that
  refuses to run.

The units are stated in every name. "Kilometres" and "minutes since epoch" are spelled out
rather than implied, because degrees-versus-radians and metres-versus-kilometres are the
other two traps the plan names.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from sgp4.api import Satrec

#: The frame SGP4 produces. Carried in the type so it cannot be assumed to be J2000.
TEME_OF_DATE: Final = "TEME_OF_DATE"

#: SGP4 error codes, from the library's own documentation, mapped to readable causes.
#: Code 0 is success. Anything else means the state vector must not be used.
SGP4_ERRORS: Final[dict[int, str]] = {
    1: "mean eccentricity out of range (not 0 <= e < 1)",
    2: "mean motion below zero",
    3: "instantaneous eccentricity out of range (not 0 <= e < 1)",
    4: "semi-latus rectum below zero",
    5: "epoch element set was a sub-orbital trajectory",
    6: "satellite has decayed",
}


class PropagationError(RuntimeError):
    """Raised when SGP4 cannot produce a usable state vector.

    Deliberately an exception rather than a sentinel: a scenario built on a decayed or
    hyperbolic element set must fail the solvability check loudly at authoring time, not
    serve an operator a plot of numbers that mean nothing.
    """

    def __init__(self, code: int) -> None:
        cause = SGP4_ERRORS.get(code, f"unknown SGP4 error code {code}")
        super().__init__(f"SGP4 refused to propagate: {cause}")
        self.code = code


@dataclass(frozen=True, slots=True)
class StateVector:
    """A propagated state, with its frame and units in the type.

    Immutable on purpose. A state vector that can be mutated after a solvability check is a
    state vector that can differ between the check and the score.
    """

    position_km: tuple[float, float, float]
    velocity_km_s: tuple[float, float, float]
    frame: str = TEME_OF_DATE

    @property
    def radius_km(self) -> float:
        """Geocentric distance. The cheapest sanity check there is."""
        return math.hypot(*self.position_km)

    @property
    def speed_km_s(self) -> float:
        """Speed magnitude."""
        return math.hypot(*self.velocity_km_s)


def load_elements(line1: str, line2: str) -> Satrec:
    """Build a propagator from the two element-set lines.

    Kept as its own function so a scenario template can be validated at authoring time
    without propagating, and so the library type appears in exactly one place.
    """
    return Satrec.twoline2rv(line1, line2)


def propagate_minutes_since_epoch(elements: Satrec, minutes: float) -> StateVector:
    """Propagate ``minutes`` past the element-set epoch.

    Minutes since epoch, not a wall-clock time, and that is deliberate: it is the
    quantity SGP4 actually takes, and every conversion from a calendar time is a chance to
    reintroduce the leap-second and TLE-epoch traps. The scenario engine owns time; this
    function owns propagation.

    Raises :class:`PropagationError` on any non-zero SGP4 code.
    """
    code, position, velocity = elements.sgp4_tsince(minutes)
    if code != 0:
        raise PropagationError(code)
    return StateVector(
        position_km=(float(position[0]), float(position[1]), float(position[2])),
        velocity_km_s=(float(velocity[0]), float(velocity[1]), float(velocity[2])),
    )
