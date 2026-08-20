"""Seeded randomness, an integer clock, and an append-only event log.

Small on purpose. This module holds no scenario content and no physics: it is the substrate that
makes a run reproducible, and keeping it free of both is what lets it be proved.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
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


def _freeze(value: Any, depth: int = 0) -> Any:
    """Return ``value`` with every mapping and sequence in it made immutable, recursively.

    **Depth-bounded, and the bound is not decoration.** The first version of this function
    recursed without one and ran BEFORE `_check_payload_depth`, because freezing happens in
    `Event.__post_init__` and the depth walk happens in `RunLog._append`. A self-referential
    payload therefore raised `RecursionError` here instead of `ValueError` there: the freeze had
    moved a guarded failure back in front of its own guard. Caught by the existing
    unserialisable-payload test, which is what that test is for.

    Adding the bound here made the separate `_check_payload_depth` walk in `RunLog._append`
    unreachable - every payload is frozen at `Event` construction, so nothing nested past the
    limit can survive to reach it - and it was deleted rather than left in place. A guard with no
    reachable input reads as a live control to the next reader and to a coverage report, which is
    how a repository accumulates defences nobody can trust. The bound belongs in ONE place, and
    this is the earliest one.

    Why bound depth at all, kept from the walk that used to carry it: a 200,000-level payload
    raised an undocumented `RecursionError` from inside `json.dumps`, and a `RecursionError` is
    not a `ValueError` and can leave the interpreter close to its stack limit for whatever runs
    next. A scenario event is a flat record of a few fields.

    The fix for a real forge. `Event` was a frozen dataclass, which froze the REFERENCE to the
    payload and not the payload, so `log.events[1].payload["outcome"] = "pass"` rewrote history
    through the public API with no private access at all: a divergent run was forged back to the
    genuine run's fingerprint and `replay_is_identical` returned True. Freezing the reference and
    calling the object immutable is the same class of error as a shallow copy in a security
    boundary.
    """
    if depth > MAX_PAYLOAD_DEPTH:
        raise ValueError(f"payload nests deeper than {MAX_PAYLOAD_DEPTH} levels")
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item, depth + 1) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item, depth + 1) for item in value)
    return value


def _plain(value: Any) -> Any:
    """Return ``value`` with the frozen views converted back to what `json` can serialise.

    `json.dumps` handles `dict` and `list`, not `MappingProxyType` and not `tuple` keys, so the
    freeze needs a matching thaw for the digest path only. The thawed copy is local to
    `canonical()` and never escapes, so it cannot become a second handle on the stored payload.
    """
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


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
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze the payload, recursively, so the frozen dataclass is actually frozen.

        Done here rather than in `RunLog.record` so that an `Event` constructed anywhere is
        immutable, including one a test builds directly. `object.__setattr__` is the documented
        way to assign inside a frozen dataclass and is what `dataclasses` itself uses.
        """
        object.__setattr__(self, "payload", _freeze(self.payload))

    def canonical(self) -> str:
        """A stable string form. Sorted keys, no whitespace, no non-finite floats.

        `allow_nan=False` is the important argument. A NaN in a payload would serialise as the
        non-standard `NaN` token, compare unequal to itself, and make a run's fingerprint depend on
        nothing at all. It fails loudly here instead.
        """
        return json.dumps(
            {"tick": self.tick, "kind": self.kind, "payload": _plain(self.payload)},
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
    handle on the underlying storage - and `Event` freezes its payload recursively, which is the
    half that was missing. The tuple alone left `log.events[1].payload["outcome"] = "pass"`
    working, so a divergent run could be forged back to the genuine fingerprint through the public
    API with no private access. The digest is also taken at the write now, so a payload mutated
    afterwards can neither change it nor break it.

    **What this still is not: tamper-evident.** The fingerprint is an unkeyed digest, so whoever
    can reach the object can recompute it. It detects DIVERGENCE, which is what a replay needs. If
    a run artefact ever has to withstand a motivated editor, that needs a keyed Message
    Authentication Code and a signing key, and that is a different control with a different
    threat model. Stated here so nobody reads this one as the other.

    State is derived from the log by folding over it, never stored beside it, so there is no
    second copy to fall out of step.
    """

    __slots__ = ("_canonicals", "_events", "_seed")

    def __init__(self, seed: int, events: tuple[Event, ...] | list[Event] | None = None) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError(f"a run log's seed must be an int, got {type(seed).__name__}")
        self._seed = seed
        self._events: list[Event] = []
        self._canonicals: list[str] = []
        for event in events or ():
            self._append(event)

    @property
    def seed(self) -> int:
        """The seed this run was drawn from. Read-only, and that is a fix.

        `seed` was a plain writable slot, so `log.seed = 999` moved the fingerprint of a finished
        run after the fact. An append-only log whose seed can be rewritten is not append-only:
        the seed is part of what the fingerprint attests.
        """
        return self._seed

    @property
    def events(self) -> tuple[Event, ...]:
        """The events so far, as an immutable tuple of immutable events.

        Both halves are load-bearing and the second was missing. The tuple stopped
        `log.events[1] = ...`; it did not stop `log.events[1].payload["outcome"] = "pass"`,
        because the payload was a live dict. `Event.__post_init__` freezes it now.
        """
        return tuple(self._events)

    def _append(self, event: Event) -> None:
        """Validate ``event`` and store it with the digest of its canonical form.

        One path, used by `record` and by the `events=` constructor argument alike. The
        constructor used to bypass every check `record` performs, which meant an out-of-order tick
        and a NaN payload were both accepted through a public parameter and the second permanently
        bricked `fingerprint()`. A control with a second door is not a control.
        """
        if self._events and event.tick < self._events[-1].tick:
            raise ValueError(
                f"event at tick {event.tick} follows tick {self._events[-1].tick};"
                " a run log is append-only and monotonic"
            )
        try:
            canonical = event.canonical()
        except (ValueError, TypeError, RecursionError) as unserialisable:
            raise ValueError(
                f"event {event.kind!r} at tick {event.tick} cannot be serialised, so it could"
                f" never be replayed: {unserialisable}"
            ) from unserialisable
        if len(canonical) > MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"event {event.kind!r} at tick {event.tick} serialises to {len(canonical)} bytes,"
                f" over the {MAX_PAYLOAD_BYTES} limit"
            )
        self._events.append(event)
        self._canonicals.append(canonical)

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
        personal detail in a payload, so the scenario engine must not. That obligation is recorded
        in the DPIA at risk R4, and it is a design obligation rather than a technical guarantee.
        An earlier version of this paragraph cited the DPIA before the DPIA said it, which is the
        crediting-a-control-that-does-not-exist fault pointing the other way.
        """
        self._append(Event(tick=clock.tick, kind=kind, payload=dict(payload)))

    def fingerprint(self) -> str:
        """A digest over the seed and every event, in order.

        The comparison a determinism test actually makes. Two runs are identical when their
        fingerprints match, and the seed is included so two runs that produced no events are not
        trivially equal.

        **Digested from the canonical form captured AT THE WRITE, never recomputed from the stored
        event.** That is the second half of the payload-freeze fix and it is defence in depth: even
        if some future change reintroduces a mutable path into a payload, it cannot alter a digest
        that was taken before it, and it cannot make this method raise. The previous version
        recomputed `event.canonical()` here, so a payload mutated afterwards both changed the
        fingerprint and, with a NaN, made this method raise for ever on a log with no remove.

        **Every field is length-prefixed**, so the digest has domain separation. Without it, the
        seed and the events were concatenated with no boundary, and `RunLog(1)` digested
        identically to `RunLog("1")` while a seed could be chosen to imitate an event.

        Cannot fail on any log this class will construct, because everything that could make it
        fail is refused at the write, through the one path both entrances use.
        """
        digest = hashlib.sha256()
        for field_bytes in (f"seed:{self._seed}".encode(), *(c.encode() for c in self._canonicals)):
            digest.update(f"{len(field_bytes)}:".encode())
            digest.update(field_bytes)
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
