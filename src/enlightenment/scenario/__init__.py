"""The deterministic scenario engine: seeded, fixed-timestep, replayable.

Phase 0 step 3 of the flight plan, and it is a gate rather than a feature: *"Prove by test that
the same seed yields an identical event log twice. This is the gate the debrief depends on."*

Everything the trainer claims rests on this. A debrief replays a scored run from its seed and its
event log and overlays what an expert would have seen. If the replay diverges from the original by
even one event, the debrief is showing the operator a run they did not have, and every score
explanation built on it is fiction.

The three rules that make replay possible, each enforced by a test rather than a convention:

● **One seeded source of randomness, passed explicitly.** No module-level `random`, no clock, no
  `os.urandom`, no set or dict iteration order relied upon. A function that cannot reach a global
  cannot be made non-deterministic by one.
● **A fixed timestep, in integer ticks.** Floating-point time accumulates differently depending on
  the order operations happen to be performed in; integer ticks multiplied by a fixed step do not.
● **An append-only event log that IS the run.** State is derived from the log, never alongside it,
  so there is no second copy to disagree.

The one hazard this cannot close by construction is the pinned `sgp4` extension, which was
measured returning different results for identical calls on a well-shaped but meaningless element
set. The checksum gate in `load_elements` keeps such an element set out of a scenario, which is
why that control is on by default.
"""

from __future__ import annotations

from enlightenment.scenario.determinism import (
    FINGERPRINT_LENGTH,
    MAX_PAYLOAD_BYTES,
    MAX_PAYLOAD_DEPTH,
    MAX_PAYLOAD_NODES,
    TICK_MILLISECONDS,
    Event,
    RunLog,
    ScenarioClock,
    SeededRandom,
    replay_is_identical,
)

__all__ = [
    "FINGERPRINT_LENGTH",
    "MAX_PAYLOAD_BYTES",
    "MAX_PAYLOAD_DEPTH",
    "MAX_PAYLOAD_NODES",
    "TICK_MILLISECONDS",
    "Event",
    "RunLog",
    "ScenarioClock",
    "SeededRandom",
    "replay_is_identical",
]
