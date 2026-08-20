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

#: Longest serialised event accepted. A 50 MB payload was accepted by the first version, which is
#: neither replayable in any useful sense nor something a scenario legitimately needs.
MAX_PAYLOAD_BYTES: Final = 64 * 1024

#: Deepest nesting accepted in a payload. 200,000 levels raised an undocumented `RecursionError`
#: from inside `json.dumps`; a scenario event is a flat record of a few fields.
MAX_PAYLOAD_DEPTH: Final = 8


def _check_payload_depth(value: Any, depth: int = 0) -> None:
    """Refuse a payload nested deeper than `MAX_PAYLOAD_DEPTH`, before `json` recurses on it.

    Checked separately rather than left to `json.dumps` raising, because a `RecursionError` is not
    a `ValueError` and can leave the interpreter close to its stack limit for whatever runs next.
    """
    if depth > MAX_PAYLOAD_DEPTH:
        raise ValueError(f"payload nests deeper than {MAX_PAYLOAD_DEPTH} levels")
    if isinstance(value, dict):
        for item in value.values():
            _check_payload_depth(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _check_payload_depth(item, depth + 1)


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


class RunLog:
    """The append-only record that IS the run.

    **Append-only is now enforced, not merely intended.** The first version exposed `events` as a
    public list, so `log.events[1] = ...`, `log.events.clear()` and wholesale replacement all
    worked, and a forged log compared equal under `replay_is_identical`. The docstring said "a log
    that can be edited after the fact cannot certify a replay" while permitting exactly that. The
    list is private now and `events` returns a tuple, so there is no remove, no update, and no
    handle on the underlying storage.

    **What this still is not: tamper-evident.** The fingerprint is an unkeyed digest, so whoever
    can reach the object can recompute it. It detects DIVERGENCE, which is what a replay needs. If
    a run artefact ever has to withstand a motivated editor, that needs a keyed Message
    Authentication Code and a signing key, and that is a different control with a different
    threat model. Stated here so nobody reads this one as the other.

    State is derived from the log by folding over it, never stored beside it, so there is no
    second copy to fall out of step.
    """

    __slots__ = ("_events", "seed")

    def __init__(self, seed: int, events: tuple[Event, ...] | list[Event] | None = None) -> None:
        self.seed = seed
        self._events: list[Event] = list(events or ())

    @property
    def events(self) -> tuple[Event, ...]:
        """The events so far, as an immutable tuple. There is deliberately no setter."""
        return tuple(self._events)

    def record(self, clock: ScenarioClock, kind: str, **payload: Any) -> None:
        """Append one event at the clock's current tick.

        Every check happens HERE rather than at fingerprint time, and that placement is the fix
        for a real defect: a non-finite payload value used to be accepted and then made
        `fingerprint()` raise, so an append-only log with no remove could be permanently deprived
        of a fingerprint by one bad write. Failing at the write is the only boundary at which the
        caller can still do something about it.

        Refuses:

        ● an out-of-order tick, because a log whose ticks do not increase cannot be replayed
          forwards;
        ● a payload that will not serialise, including a non-finite float at any depth;
        ● a payload over `MAX_PAYLOAD_BYTES`, or nested past `MAX_PAYLOAD_DEPTH`, because a
          50 MB event and a 200,000-deep dict were both accepted, the second raising an
          undocumented `RecursionError`.

        **Not whitelisted by field name**, unlike `audit.py`, and that is a deliberate difference:
        an audit line has a fixed vocabulary, whereas an event log's whole purpose is carrying
        whatever a scenario needs to replay. The controls that matter here are therefore size,
        depth and serialisability. The consequence is that a caller CAN put a credential or a
        personal detail in a payload, so the scenario engine must not, and the DPIA records that
        as a design obligation rather than a technical guarantee.
        """
        if self._events and clock.tick < self._events[-1].tick:
            raise ValueError(
                f"event at tick {clock.tick} follows tick {self._events[-1].tick};"
                " a run log is append-only and monotonic"
            )
        event = Event(tick=clock.tick, kind=kind, payload=dict(payload))
        _check_payload_depth(event.payload)
        try:
            canonical = event.canonical()
        except (ValueError, TypeError, RecursionError) as unserialisable:
            raise ValueError(
                f"event {kind!r} at tick {clock.tick} cannot be serialised, so it could never be"
                f" replayed: {unserialisable}"
            ) from unserialisable
        if len(canonical) > MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"event {kind!r} at tick {clock.tick} serialises to {len(canonical)} bytes,"
                f" over the {MAX_PAYLOAD_BYTES} limit"
            )
        self._events.append(event)

    def fingerprint(self) -> str:
        """A digest over the seed and every event, in order.

        The comparison a determinism test actually makes. Two runs are identical when their
        fingerprints match, and the seed is included so two runs that produced no events are not
        trivially equal.

        Cannot fail on a log built through `record`, because everything that could make it fail is
        refused at the write.
        """
        digest = hashlib.sha256()
        digest.update(f"seed:{self.seed}".encode())
        for event in self._events:
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
