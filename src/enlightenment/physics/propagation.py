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

#: SGP4 error codes mapped to readable causes. Code 0 is success; anything else means the
#: state vector must not be used.
#:
#: **Every entry is a faithful rendering of `sgp4.api.SGP4_ERRORS`, and one of them was not.**
#: Entry 5 previously read "epoch element set was a sub-orbital trajectory". The library says
#: "(error 5 no longer in use; it meant the satellite was underground)". I wrote a plausible
#: cause instead of reading the one that shipped, which is the hard rule against inventing a
#: fact, broken inside a diagnostic, in a trainer whose whole purpose is teaching diagnosis.
#: Entry 3 said "instantaneous" where the library says "perturbed"; the library's word wins.
#:
#: The phrasing is expanded for readability - "mean motion" for the library's `nm`,
#: "semi-latus rectum" for `semilatus rectum` - but never for MEANING. A parity test asserts
#: the key sets match, so a dependency bump that adds or retires a code fails the suite
#: instead of leaving this table quietly wrong again.
SGP4_ERRORS: Final[dict[int, str]] = {
    1: "mean eccentricity is outside the range 0 to 1",
    2: "mean motion (nm) is less than zero",
    3: "perturbed eccentricity is outside the range 0 to 1",
    4: "semi-latus rectum is less than zero",
    5: "error 5 is no longer in use; it meant the satellite was underground",
    6: "mean radius is below 1.0, which indicates the satellite has decayed",
}

#: An element-set line is exactly this many columns. Anything else is not a TLE.
TLE_LINE_LENGTH: Final = 69

#: The printable ASCII range an element-set line is drawn from, as code points.
PRINTABLE_ASCII_LOW: Final = 0x20
PRINTABLE_ASCII_HIGH: Final = 0x7E

#: The code carried by a refusal this module made itself, rather than one SGP4 reported.
#: Zero is SGP4's SUCCESS code, so it can never collide with a real library code, and a
#: caller switching on `.code` therefore reads a boundary rejection as "not from SGP4".
BOUNDARY_REFUSAL: Final = 0


class PropagationError(RuntimeError):
    """Raised when SGP4 cannot produce a usable state vector.

    Deliberately an exception rather than a sentinel: a scenario built on a decayed or
    hyperbolic element set must fail the solvability check loudly at authoring time, not
    serve an operator a plot of numbers that mean nothing.

    One exception type covers both a code SGP4 reported and a refusal this module made at
    its own boundary, because a caller has the same job either way: do not use the state.
    """

    def __init__(self, code: int, reason: str | None = None) -> None:
        if reason is None:
            cause = SGP4_ERRORS.get(code, f"unknown SGP4 error code {code}")
            detail = f"SGP4 refused to propagate: {cause}"
        else:
            detail = f"refused at the boundary: {reason}"
        super().__init__(detail)
        self.code = code

    @classmethod
    def from_input(cls, reason: str) -> PropagationError:
        """Build a boundary refusal: bad element line, non-finite time, non-finite result."""
        return cls(BOUNDARY_REFUSAL, reason)


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


def _check_element_line(line: object, position: int) -> str:
    """Validate one element-set line before it reaches the C extension.

    The library is a compiled extension reached with caller-supplied strings, so the
    boundary is validated here rather than trusted. Attacking it directly showed no crash
    and no memory amplification: a ten-million-character line costs about 11ms and 20MB,
    because the extension reads fixed columns and ignores the rest. What it DID do is leak
    three exception types past this module's stated contract - `ValueError: embedded null
    character` for a NUL, `UnicodeEncodeError` for a lone surrogate, `TypeError` for a
    non-string - so a caller told to expect :class:`PropagationError` got something else.

    A real element-set line is exactly 69 printable ASCII columns. Checking that here means
    the extension only ever sees input of the shape it documents, and every rejection
    arrives as one exception type. Fail closed at the boundary, as everywhere else.
    """
    if not isinstance(line, str):
        raise PropagationError.from_input(f"element-set line {position} is not text")
    stripped = line.rstrip()
    if len(stripped) != TLE_LINE_LENGTH:
        raise PropagationError.from_input(
            f"element-set line {position} is {len(stripped)} columns, expected {TLE_LINE_LENGTH}"
        )
    if not all(PRINTABLE_ASCII_LOW <= ord(char) <= PRINTABLE_ASCII_HIGH for char in stripped):
        raise PropagationError.from_input(
            f"element-set line {position} holds a character outside printable ASCII"
        )
    return stripped


def element_line_checksum_ok(line: str) -> bool:
    """Return whether ``line`` satisfies the published TLE checksum in column 69.

    The rule is part of the element-set format, not something invented here: sum the digits in
    columns 1 to 68, counting a minus sign as 1 and every other character as 0, and the last
    digit is that total modulo ten.

    **This is deliberately NOT a gate inside :func:`load_elements`, and the reason matters.**
    Five of the sixty-six element-set lines in Vallado's own verification file fail it,
    including the deliberate error case at satellite 33334. They are synthetic test vectors
    rather than real element sets, and refusing them would refuse the reference data this
    module is verified against. A control that rejects the authority is not a control.

    So it lives here as a function the SCENARIO ENGINE calls in its solvability check, which
    the flight plan requires before any generated scenario is served. That is the right place:
    authoring-time content validation, where a wrong checksum means an author made a mistake,
    rather than propagation time, where it would mean the reference set is wrong.

    It earns its keep because it catches the input class nothing else can. A line of the right
    width and charset but meaningless fields passes the shape check, and the library then
    accepts it, reports success, and returns a state built from uninitialised memory - measured
    below in :func:`propagate_minutes_since_epoch`. Every such line tried failed this checksum.
    """
    total = 0
    for character in line[: TLE_LINE_LENGTH - 1]:
        if character.isdigit():
            total += int(character)
        elif character == "-":
            total += 1
    checksum = line[TLE_LINE_LENGTH - 1]
    return checksum.isdigit() and total % 10 == int(checksum)


def load_elements(line1: str, line2: str) -> Satrec:
    """Build a propagator from the two element-set lines.

    Kept as its own function so a scenario template can be validated at authoring time
    without propagating, and so the library type appears in exactly one place.

    Raises :class:`PropagationError` for anything the library will not accept, including the
    third-party exception types it would otherwise raise itself.
    """
    first = _check_element_line(line1, 1)
    second = _check_element_line(line2, 2)
    try:
        return Satrec.twoline2rv(first, second)
    except Exception as exc:  # pragma: no cover - see below
        # No test covers this line, and that is stated rather than papered over. Six
        # well-shaped but meaningless lines were fed to the library directly and it raised for
        # none of them: it reads fixed columns and accepts whatever it finds. So with
        # `_check_element_line` in front, this branch has no known reachable input.
        #
        # It stays anyway, unlike the other dead branch this release removed. The difference is
        # what can be proved. There, the measurement was exhaustive over the input axis. Here,
        # six samples of a compiled third-party surface are not an enumeration of it, and
        # claiming otherwise is the error. A caller told to expect PropagationError should get
        # PropagationError even from a case nobody found.
        raise PropagationError.from_input(f"the library refused the element set: {exc}") from exc


def propagate_minutes_since_epoch(elements: Satrec, minutes: float) -> StateVector:
    """Propagate ``minutes`` past the element-set epoch.

    Minutes since epoch, not a wall-clock time, and that is deliberate: it is the
    quantity SGP4 actually takes, and every conversion from a calendar time is a chance to
    reintroduce the leap-second and TLE-epoch traps. The scenario engine owns time; this
    function owns propagation.

    Raises :class:`PropagationError` on a non-finite ``minutes``, on any non-zero SGP4 code,
    and on a non-finite result.

    **Both ends are guarded, and the second one took two attempts to get right.** The security
    review found that `sgp4_tsince(float("inf"))` returns code **0** with an all-NaN state, so
    the exact thing this wrapper exists to prevent - a fabricated state passing an unchecked
    success code - arrives THROUGH the code check rather than around it.

    I first added an output check, then measured it against sixteen extreme finite values of
    ``minutes`` on a good element set, found nothing, and removed it as dead code. That
    measurement varied one axis and I concluded from it. Varying the ELEMENT SET instead: a
    line that passes the column and charset check but carries meaningless fields propagates at
    code 0 with an all-NaN state. The branch is reachable, and it is reachable by the input a
    content author is most likely to produce by accident. The check is back.

    **The library is not dependably deterministic for a meaningless element set, and that is
    the more serious finding.** Three identical consecutive calls in one process, on a line of
    the right width and charset but meaningless fields, returned an all-NaN state, then a
    finite and entirely plausible one, then all-NaN again. `twoline2rv` leaves the object
    partially initialised and the propagated values come from whatever was in memory. This
    trainer's determinism requirement is that the same seed yields an identical event log
    twice, so an element set that propagates differently on each call cannot be allowed near a
    scenario at all.

    The finiteness guard here catches the NaN outcome. It cannot catch the plausible one - a
    finite wrong number is indistinguishable from a finite right one at this layer. What
    catches that is :func:`element_line_checksum_ok`, called by the scenario engine's
    solvability check at authoring time: every meaningless line tried failed the checksum.
    Two layers, because neither is sufficient alone, and neither is claimed to be.
    """
    if not math.isfinite(minutes):
        raise PropagationError.from_input(f"minutes since epoch must be finite, got {minutes!r}")
    code, position, velocity = elements.sgp4_tsince(minutes)
    if code != 0:
        raise PropagationError(code)
    state = StateVector(
        position_km=(float(position[0]), float(position[1]), float(position[2])),
        velocity_km_s=(float(velocity[0]), float(velocity[1]), float(velocity[2])),
    )
    if not all(
        math.isfinite(component) for component in (*state.position_km, *state.velocity_km_s)
    ):
        raise PropagationError.from_input(
            f"SGP4 reported success with a non-finite state at t={minutes!r};"
            " the element set is well-shaped but meaningless"
        )
    return state
