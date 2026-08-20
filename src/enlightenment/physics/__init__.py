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
    load_elements,
    propagate_minutes_since_epoch,
)

__all__ = [
    "PropagationError",
    "StateVector",
    "load_elements",
    "normalise_degrees",
    "normalise_longitude",
    "propagate_minutes_since_epoch",
    "shortest_separation_degrees",
    "wrap_to_pi",
]
