"""Physics core: pure functions, small, no input or output.

Everything in the trainer scores against this module, so it is built and proved before
anything that depends on it, per the flight plan's Phase 0 ordering. The rule that keeps it
honest: no function here reads a file, touches a clock, or holds state. A scenario, a drill
item and a debrief must all be able to call the same function and get the same answer.
"""

from __future__ import annotations

from enlightenment.physics.angles import (
    normalise_degrees,
    normalise_longitude,
    shortest_separation_degrees,
    wrap_to_pi,
)
from enlightenment.physics.propagation import (
    PropagationError,
    StateVector,
    element_line_checksum_ok,
    load_elements,
    propagate_minutes_since_epoch,
)
from enlightenment.physics.relative import (
    EARTH_MU_KM3_S2,
    HILL_FRAME,
    RelativeMotionError,
    RelativeState,
    mean_motion_from_elements,
    mean_motion_rad_s,
    no_drift_alongtrack_rate_km_s,
    propagate_relative,
)
from enlightenment.physics.times import (
    J2000_JULIAN_DATE,
    greenwich_mean_sidereal_degrees,
    julian_date_from_utc,
    sub_satellite_longitude_degrees,
)

__all__ = [
    "EARTH_MU_KM3_S2",
    "HILL_FRAME",
    "J2000_JULIAN_DATE",
    "PropagationError",
    "RelativeMotionError",
    "RelativeState",
    "StateVector",
    "element_line_checksum_ok",
    "greenwich_mean_sidereal_degrees",
    "julian_date_from_utc",
    "load_elements",
    "mean_motion_from_elements",
    "mean_motion_rad_s",
    "no_drift_alongtrack_rate_km_s",
    "normalise_degrees",
    "normalise_longitude",
    "propagate_minutes_since_epoch",
    "propagate_relative",
    "shortest_separation_degrees",
    "sub_satellite_longitude_degrees",
    "wrap_to_pi",
]
