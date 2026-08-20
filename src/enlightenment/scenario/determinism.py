"""Seeded randomness, an integer clock, and an append-only event log.

Small on purpose. This module holds no scenario content and no physics: it is the substrate that
makes a run reproducible, and keeping it free of both is what lets it be proved.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any, Final

#: Milliseconds per tick. The scenario clock counts INTEGER ticks and multiplies, so elapsed time
#: is exact and independent of the order in which steps were taken. Accumulating a float step
#: instead gives a different answer depending on how the additions were grouped, which is a
#: divergence a replay would inherit.
TICK_MILLISECONDS: Final = 100

#: The digest length used for a run's fingerprint. Sixteen hex characters is ample to detect a
#: divergence and short enough to appear in a log line an operator can read back.
FINGERPRINT_LENGTH: Final = 16


class SeededRandom:
    """The only source of randomness a scenario may use.

    Wraps `random.Random` rather than the module-level functions, because the module-level
    functions share one global state: two scenarios running in the same process would draw from
    each other's stream, and a replay would depend on what else the process had done. An instance
    per run cannot.

    Deliberately NOT `secrets` or `os.urandom`. This randomness must be reproducible, which is the
    opposite of what a cryptographic source provides. Nothing here protects anything; the team
    token and the session signing key are elsewhere and are not this.
    """

    __slots__ = ("_draws", "_random", "_seed")

    def __init__(self, seed: int) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError(f"seed must be an int, got {type(seed).__name__}")
        self._seed = seed
        self._random = random.Random(seed)  # noqa: S311 - reproducibility is the requirement
        self._draws = 0

    @property
    def seed(self) -> int:
        """The seed this stream was built from. Recorded in the run log."""
        return self._seed

    @property
    def draws(self) -> int:
        """How many values have been taken.

        Exposed because it is the cheapest divergence detector there is: two runs that drew a
        different NUMBER of values cannot produce the same log, whatever the values were.
        """
        return self._draws

    def uniform(self, low: float, high: float) -> float:
        """A float in ``[low, high]``."""
        self._draws += 1
        return self._random.uniform(low, high)

    def integer(self, low: float, high: float) -> int:
        """An integer in ``[low, high]``, inclusive of both ends."""
        self._draws += 1
        return self._random.randint(int(low), int(high))

    def choice(self, options: list[Any]) -> Any:
        """One of ``options``.

        Takes a LIST, not a set or a dict view, and that signature is the control: set iteration
        order depends on hash values, which vary between processes when hash randomisation is on,
        so choosing from a set is non-deterministic across runs even with the same seed.
        """
        if not options:
            raise ValueError("cannot choose from an empty sequence")
        self._draws += 1
        return self._random.choice(options)


@dataclass(frozen=True, slots=True)
class ScenarioClock:
    """An integer-tick clock. Immutable, so advancing returns a new clock.

    Frozen for the same reason the state vectors are: a clock that can be mutated in place can be
    advanced twice by two callers who each think they advanced it once.
    """

    tick: int = 0

    @property
    def elapsed_milliseconds(self) -> int:
        """Exact elapsed time. Integer multiplication, never accumulated addition."""
        return self.tick * TICK_MILLISECONDS

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed time in seconds, for the physics layer, derived from the exact integer."""
        return self.elapsed_milliseconds / 1000.0

    def advance(self, ticks: int = 1) -> ScenarioClock:
        """Return the clock ``ticks`` later. Refuses to go backwards or nowhere."""
        if ticks < 1:
            raise ValueError(f"a scenario clock advances by at least one tick, got {ticks!r}")
        return ScenarioClock(tick=self.tick + ticks)


@dataclass(frozen=True, slots=True)
class Event:
    """One thing that happened, at one tick. The unit the run log is made of.

    ``payload`` is serialised with sorted keys when the log is fingerprinted, so two logically
    identical events cannot produce different digests because a dictionary was built in a
    different order.
    """

    tick: int
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    def canonical(self) -> str:
        """A stable string form. Sorted keys, no whitespace, no non-finite floats.

        `allow_nan=False` is the important argument. A NaN in a payload would serialise as the
        non-standard `NaN` token, compare unequal to itself, and make a run's fingerprint depend on
        nothing at all. It fails loudly here instead.
        """
        return json.dumps(
            {"tick": self.tick, "kind": self.kind, "payload": self.payload},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


@dataclass(slots=True)
class RunLog:
    """The append-only record that IS the run.

    Append-only is the design: there is no `remove` and no `update`, because a log that can be
    edited after the fact cannot certify a replay. State is derived from the log by folding over
    it, never stored beside it, so there is no second copy to fall out of step.
    """

    seed: int
    events: list[Event] = field(default_factory=list)

    def record(self, clock: ScenarioClock, kind: str, **payload: Any) -> None:
        """Append one event at the clock's current tick.

        Refuses an out-of-order tick. A log whose ticks do not increase monotonically cannot be
        replayed forwards, and the cheapest place to catch that is where it would be written.
        """
        if self.events and clock.tick < self.events[-1].tick:
            raise ValueError(
                f"event at tick {clock.tick} follows tick {self.events[-1].tick};"
                " a run log is append-only and monotonic"
            )
        self.events.append(Event(tick=clock.tick, kind=kind, payload=dict(payload)))

    def fingerprint(self) -> str:
        """A digest over the seed and every event, in order.

        The comparison a determinism test actually makes. Two runs are identical when their
        fingerprints match, and the seed is included so two runs that produced no events are not
        trivially equal.
        """
        digest = hashlib.sha256()
        digest.update(f"seed:{self.seed}".encode())
        for event in self.events:
            digest.update(event.canonical().encode())
        return digest.hexdigest()[:FINGERPRINT_LENGTH]


def replay_is_identical(first: RunLog, second: RunLog) -> bool:
    """Whether two runs are the same run.

    A function rather than an operator override, so the comparison a test makes is the same
    comparison the debrief makes. Compares the fingerprint, then the event count, then each
    event: the fingerprint alone would be enough, and the rest is there so a failure says WHERE
    they diverged rather than only that they did.
    """
    # Length FIRST, then the digest. Two reasons, and the second is the real one.
    #
    # Cheapest check first is the obvious half. The other half: with the digest first, this branch
    # was unreachable, because two logs of different lengths always digest differently, so the
    # length check could only ever fire on a 64-bit collision. Coverage found it as a dead line.
    # It is not removable, though: `zip(..., strict=True)` below RAISES on a length mismatch, so
    # without this the function would crash rather than answer. Reordering makes it both reachable
    # and correct, which is better than either keeping dead code or removing a needed guard.
    if len(first.events) != len(second.events):
        return False
    if first.fingerprint() != second.fingerprint():
        return False
    return all(
        left.canonical() == right.canonical()
        for left, right in zip(first.events, second.events, strict=True)
    )
