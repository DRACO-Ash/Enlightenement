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
    6: "the orbital radius is below one Earth radius, which indicates the satellite has decayed",
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

    **The width check is stricter than the library, deliberately, and the caller must know it.**
    The 33 line-2 records in `SGP4-VER.TLE` are 103 or 104 columns as they appear in the file:
    the harness appends start, stop and step values after the checksum. Those are refused here,
    and the golden-vector suite passes only because its parser truncates to 69 first. Anything
    reading raw records from that file, or from a similar harness format, must truncate before
    calling. Correct per the element-set format, and previously unstated at the boundary, which
    is how a caller learns it from a failure instead of from the docstring.
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


def element_line_checksum_ok(line: object) -> bool:
    """Return whether ``line`` satisfies the published TLE checksum in column 69.

    The rule is part of the element-set format, not something invented here: sum the digits in
    columns 1 to 68, counting a minus sign as 1 and every other character as 0, and the last
    digit is that total modulo ten.

    **Returns False for anything that is not a 69-column string, rather than raising.** The
    first version indexed column 69 directly, so an empty line raised `IndexError` and a
    non-string raised `TypeError` - the exact defect class fixed in :func:`load_elements` in the
    same commit, reintroduced in the function beside it, in the validator nominated as the gate
    on author-supplied content. Both binding gates found it independently. A predicate that
    raises is not a predicate, and a validator that raises on the input it exists to reject is
    the fail-open shape wearing a fail-closed name.

    Trailing whitespace is stripped first, so a line read from a file with its line ending
    intact is handled. Callers holding the raw `SGP4-VER.TLE` records must truncate the harness
    span columns appended after column 69 themselves; this function judges what it is given.

    **Enforced by default in :func:`load_elements`, with three documented opt-outs, all in the
    test suite.** Five of the sixty-six element-set lines in Vallado's own verification file
    fail this check - both lines of satellites 33333 and 33335, and line 1 of 33334 - so the
    golden-vector suite passes ``verify_checksum=False``. A default that refused the reference
    data would be a control that refuses its own authority. See :func:`load_elements` for the
    second opt-out and the repo-wide census that bounds them.

    For one commit this function had no call site while a docstring described a scenario-engine
    caller in the present tense. Both binding gates found that. It is wired now.
    """
    if not isinstance(line, str):
        return False
    stripped = line.rstrip()
    if len(stripped) != TLE_LINE_LENGTH:
        return False
    total = 0
    for character in stripped[: TLE_LINE_LENGTH - 1]:
        # `isascii()` before `isdigit()`, in BOTH loops. `str.isdigit()` is True for characters
        # like the superscript two, and `int()` then raises `ValueError` - so the predicate
        # documented above as returning False rather than raising did exactly that, from either
        # the body or the checksum column. Latent, because `_check_element_line` screens to
        # printable ASCII first, but the docstring's promise is made to DIRECT callers, and this
        # function is the one nominated as the authoring-time content gate.
        if character.isascii() and character.isdigit():
            total += int(character)
        elif character == "-":
            total += 1
    checksum = stripped[TLE_LINE_LENGTH - 1]
    return checksum.isascii() and checksum.isdigit() and total % 10 == int(checksum)


def load_elements(line1: str, line2: str, *, verify_checksum: bool = True) -> Satrec:
    """Build a propagator from the two element-set lines.

    Kept as its own function so a scenario template can be validated at authoring time
    without propagating, and so the library type appears in exactly one place.

    Raises :class:`PropagationError` for anything the library will not accept, including the
    third-party exception types it would otherwise raise itself.

    ``verify_checksum`` defaults to True because the alternative is a silent hazard. A line of
    the right width and charset but meaningless fields is accepted by the library, which then
    reports success and returns a state built from uninitialised memory - measured in
    :func:`propagate_minutes_since_epoch`. The checksum is the only cheap control that sees it.

    Pass ``verify_checksum=False`` only to load a line that is deliberately not a real element
    set. Three callers do, all in the test suite, and the count is asserted over every tracked
    Python file so it cannot grow unnoticed:

    ● the golden-vector propagator, because five of the sixty-six lines in Vallado's own
      verification file fail the checksum - both lines of satellites 33333 and 33335, and line 1
      of 33334. They are synthetic test vectors, and a default that refused the reference data
      would be a control that refuses its own authority.
    ● the meaningless-element-set test, which exercises the layer BELOW this gate and so has to
      get past it.
    ● the control for the fail-closed test, which proves a literal ``False`` DOES disable the
      gate - without it, a gate that refused every value would look correct.

    An earlier version of this paragraph said "exactly one caller" while the test asserted three
    and the changelog said three. The function was telling a maintainer the wrong thing about
    itself.
    """
    first = _check_element_line(line1, 1)
    second = _check_element_line(line2, 2)
    # `is not False`, not truthiness. A parameter documented as a strict fail-closed default
    # should not be disabled by `None`, `0`, `""` or an empty container, and a bare `Any` from a
    # future `json.loads` scenario field is exactly the caller that would arrive holding one.
    # mypy strict rejects those at every in-repo call site today; `Any` it waves through.
    if verify_checksum is not False:
        for position, line in ((1, first), (2, second)):
            if not element_line_checksum_ok(line):
                raise PropagationError.from_input(
                    f"element-set line {position} fails the TLE checksum in column"
                    f" {TLE_LINE_LENGTH}"
                )
    try:
        return Satrec.twoline2rv(first, second)
    except Exception as exc:  # pragma: no cover - see below
        # No test covers this line, and that is stated rather than papered over. Sixty thousand
        # well-shaped printable-ASCII lines were fed to the library directly - thirty thousand
        # random, thirty thousand structured mutations of a real line - and it raised for none
        # of them: it reads fixed columns and accepts whatever it finds.
        #
        # It stays anyway, unlike the other dead branch this release removed. The difference is
        # what can be proved. There, the measurement was exhaustive over the input axis. Here,
        # sixty thousand samples of a compiled third-party surface are not an enumeration of it,
        # and claiming otherwise is the error. A caller told to expect PropagationError should
        # get PropagationError even from a case nobody found.
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
    finite wrong number is indistinguishable from a finite right one at this layer. What catches
    most of that is the checksum check inside :func:`load_elements`, on by default.

    **Most, not all, and the residual depends on the input, so both rates are given.** A single
    mod-10 digit is a weak check. Over 200,000 samples of each shape:

    ● fully random printable-ASCII lines: 1.05 per cent pass, about one in 94, because column 69
      must happen to be a digit at all before it can happen to be the right one;
    ● lines whose column 69 IS a digit - the shape a mistyped field produces, and therefore the
      realistic authoring error: 9.79 per cent pass, about one in ten.

    So the gate leaks roughly one meaningless line in ten of the kind actually likely to be
    written. Every leaked line measured was caught here, which is why this guard is not
    redundant.

    Two earlier versions of this paragraph were wrong. The first said a meaningless element set
    "never reaches this function at all", two lines above a sentence saying neither layer is
    sufficient alone. The second quoted "one in ten" alongside "517 of 50,000", which is one in
    97: a rate and a characterisation that contradict each other, both copied rather than run.

    That second layer was, for one commit, a function with no call site described in the present
    tense as though it were wired. Both binding gates found it. It is wired now.
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
