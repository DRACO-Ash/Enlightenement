"""Match an operator's produced answer against the drill key.

**No fuzzy matching, and the refusals are the load-bearing half.** The key carries accept values,
partial values with the credit each earns, and reject values with the reason each is wrong. A
matcher that scored on string similarity would award a reject value for looking like an accept
value, and the reject list exists precisely because those two are often one word apart:
"separation" and "fragmentation" share almost nothing analytically and a great deal
orthographically.

So matching is exact after normalisation, and normalisation is narrow and bounded: case, spacing,
punctuation, and a fixed list of leading fillers. Anything more clever admits a class of false
positive that this content is built to catch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

from enlightenment.content import Answer, ResponseFormat, Tolerance

#: An operator types a sentence, not a token. Longer than this is not an answer, it is an essay,
#: and the formats that want prose have their own path.
MAX_ANSWER_LENGTH = 300

#: The outcome of an item that could NOT be marked, as distinct from one marked wrong. Named
#: because the two are opposite facts and the caller must be able to tell them apart without
#: matching a string literal: a wrong answer moves a rating and an unscorable item must not.
UNSCORABLE: Final = "unscorable"

#: The content's marker for a numeric answer the RENDERER must compute. Never matched as a
#: literal string: an operator typing it must not be marked correct.
COMPUTED_SENTINEL: Final = "computed_from_params"
UNSCORABLE_NOTE: Final = "This item's expected value could not be resolved."

#: Credit for a numeric answer that is right in magnitude and silent on the direction, where the
#: prompt asked for both. ENGINE POLICY, named rather than hidden in a branch: the content states
#: partial credit per authored answer and says nothing about this composition.
PARTIAL_DIRECTION_CREDIT: Final = 0.5

#: Stripped from the front of a response, once, then again. Two bounded passes rather than a loop,
#: because an unbounded strip on attacker-controlled input is a denial of service in a regex.
_FILLERS = (
    "i think",
    "i would say",
    "probably",
    "possibly",
    "it looks like",
    "it is",
    "its",
    "this is",
    "that is",
    "the answer is",
    "maybe",
)

_PUNCTUATION = re.compile(r"[^\w\s-]+")
_WHITESPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def normalise(text: str) -> str:
    """Case-fold, strip punctuation, collapse whitespace, then drop up to two leading fillers."""
    value = _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", text.casefold())).strip()
    for _ in range(2):
        for filler in _FILLERS:
            if value.startswith(filler + " "):
                value = value[len(filler) + 1 :].strip()
                break
    return value


@dataclass(frozen=True, slots=True)
class Match:
    """What the response matched, and everything the reveal needs to explain it."""

    matched: str
    credit: float
    note: str = ""
    why_wrong: str = ""
    within_tolerance: bool | None = None
    expected: float | None = None

    @property
    def correct(self) -> bool:
        return self.matched == "accept"


def _within(value: float, expected: float, tolerance: Tolerance | None) -> bool:
    """Whether a numeric response is close enough, by the tolerance the content states.

    An absolute tolerance of zero means exactly right, which several counting items intend: asked
    how many manoeuvres, the only correct answer is the number of manoeuvres.
    """
    if tolerance is None:
        return value == expected
    if tolerance.absolute is not None:
        return abs(value - expected) <= tolerance.absolute
    if tolerance.relative is not None:
        return abs(value - expected) <= abs(expected) * tolerance.relative
    return value == expected


def _numeric(text: str) -> float | None:
    found = _NUMBER.search(text.replace(",", ""))
    return float(found.group(0)) if found else None


def match_numeric(response: str, answer: Answer, derived: dict[str, Any]) -> Match:
    """Match a numeric estimate, resolving `computed_from_params` against the generator's output.

    The sentinel is not an answer and must never be treated as one. Where the content says the
    expected value is computed from the params, it is the generator that computed the stimulus
    which knows it, and if the generator did not supply it the item is REFUSED rather than
    guessed at. An item scored against a value nobody computed is worse than an item not served.
    """
    given = _numeric(response)
    expected: float | None = answer.value
    if expected is None:
        for candidate in answer.accept:
            if candidate == COMPUTED_SENTINEL:
                supplied = derived.get("expected_value")
                expected = None if supplied is None else float(supplied)
                break
            numeric_candidate = _numeric(candidate)
            if numeric_candidate is not None:
                expected = numeric_candidate
                break
    if expected is None:
        return Match(UNSCORABLE, 0.0, note=UNSCORABLE_NOTE)
    if given is None:
        return Match("none", 0.0, note="No number found in the response.", expected=expected)

    #: **Where the direction is a WORD, the number is a magnitude.** DRL-0004 asks the operator to
    #: "estimate the resulting longitude drift rate in degrees per day, and state the direction",
    #: and the generator's expected value is signed - negative for a westward drift. So
    #: "0.12 deg/day west" was marked WRONG for omitting a minus sign the prompt never asked for,
    #: while the direction word the prompt did ask for was not scored at all. Before the value was
    #: wired this item refused harmlessly; wiring it turned a harmless refusal into an active
    #: penalty on the correct answer, which is the same harm one drill along.
    #:
    #: So when the generator also supplies a direction, the magnitudes are compared and the
    #: direction is required separately. A signed answer still passes: its magnitude matches.
    if derived.get("expected_text"):
        return _match_magnitude_and_direction(response, answer, derived, given, expected)

    inside = _within(given, expected, answer.tolerance)
    if inside:
        return Match("accept", 1.0, within_tolerance=True, expected=expected)
    rejected = _match_reject(response, answer)
    if rejected is not None:
        return Match("reject", 0.0, why_wrong=rejected, within_tolerance=False, expected=expected)
    return Match("none", 0.0, within_tolerance=False, expected=expected)


def _match_magnitude_and_direction(
    response: str, answer: Answer, derived: dict[str, Any], given: float, expected: float
) -> Match:
    """Score a rate whose prompt asks for a magnitude AND a direction.

    The generator's expected value is signed, and the direction is a WORD the prompt asks for
    separately, so comparing the signed number marked "0.12 deg/day west" wrong for omitting a
    minus sign nobody requested - while the direction went unscored. Magnitudes are compared and
    the direction is required on top; a signed answer still passes on its magnitude.
    """
    if not _within(abs(given), abs(expected), answer.tolerance):
        return Match("none", 0.0, within_tolerance=False, expected=expected)
    if match_derived_text(response, derived, answer).matched != "accept":
        return Match(
            "partial",
            PARTIAL_DIRECTION_CREDIT,
            note="The rate is right. State which way it drifts.",
            within_tolerance=True,
            expected=expected,
        )
    return Match("accept", 1.0, within_tolerance=True, expected=expected)


def _match_partial(response: str, answer: Answer) -> Match | None:
    """One authored partial answer, matched exactly as `match_text` matches it."""
    wanted = normalise(response)
    for candidate in answer.partial:
        if normalise(candidate.value) == wanted:
            return Match("partial", candidate.credit, note=candidate.note)
    return None


def _match_reject(response: str, answer: Answer) -> str | None:
    wanted = normalise(response)
    for rejected in answer.reject:
        if normalise(rejected.value) == wanted:
            return rejected.why_wrong
    return None


def match_text(response: str, answer: Answer) -> Match:
    """Match a produced text answer: accept, then partial, then reject, then nothing.

    Order matters. A response is checked against accept first so a value that appears in both
    lists resolves generously, and against reject last so a named wrong answer gets its reason
    rather than a bare miss.
    """
    wanted = normalise(response)
    for candidate in answer.accept:
        if normalise(candidate) == wanted:
            return Match("accept", 1.0)
    for partial in answer.partial:
        if normalise(partial.value) == wanted:
            return Match("partial", partial.credit, note=partial.note)
    why = _match_reject(response, answer)
    if why is not None:
        return Match("reject", 0.0, why_wrong=why)
    return Match("none", 0.0)


def match_derived_text(
    response: str, derived: dict[str, Any], answer: Answer | None = None
) -> Match:
    """A non-numeric answer the RENDERER computed, matched against what it actually drew.

    DRL-0030 asks the operator to find the drifting object and state its direction, and its key
    is the `computed_from_params` sentinel: the direction is a fact about the surface, not a
    value anybody could write into content without fixing the stimulus. The generator records
    what it drew in `derived["expected_text"]` and this matches against that.

    Without it the item reached the ordinary text matcher and compared the operator's prose to
    the literal string "computed_from_params": every real answer was marked WRONG, the rating
    dropped and the cue reset. Refusing to score is the fail-closed case; scoring against a
    sentinel is neither closed nor honest.
    """
    expected = derived.get("expected_text")
    if not expected:
        return Match(UNSCORABLE, 0.0, note=UNSCORABLE_NOTE)
    typed = normalise(response)
    #: A bare string is ONE token, not a sequence of letters. `tuple("east")` is
    #: `('e','a','s','t')`, so typing a single letter matched and scored full credit. Both
    #: generators emit tuples today, and a mapping is the natural thing for the next author to
    #: write, so the shape is normalised here rather than trusted at every call site.
    tokens = (expected,) if isinstance(expected, str) else tuple(str(v) for v in expected)
    #: A token matches the START of a word, so "west" accepts "westwards" and "westerly" - a
    #: fully correct prose answer that a strict word boundary rejected. It still will not match
    #: inside a word, so "west" does not accept "southwest".
    if any(re.search(rf"\b{re.escape(token)}\w*", typed) for token in tokens):
        return Match("accept", 1.0)

    #: **The item's authored partial and reject entries still apply.** This matcher consulted
    #: neither, so on DRL-0030 "there is a drifting object" - which the content awards 0.5 credit
    #: with a note explaining that the direction comes from the gradient - scored zero and got a
    #: generic string instead of the authored teaching text, and both authored misconceptions
    #: lost their `why_wrong`. A content instruction silently ignored is the fault the
    #: aggregation reporting exists to prevent, in a matcher added the same week.
    if answer is not None:
        partial = _match_partial(response, answer)
        if partial is not None:
            return partial
        rejected = _match_reject(response, answer)
        if rejected is not None:
            return Match("reject", 0.0, why_wrong=rejected)
    return Match("none", 0.0, note="Not the direction shown on the surface.")


def match(
    response: str, answer: Answer, response_format: ResponseFormat, derived: dict[str, Any]
) -> Match:
    """Dispatch to the matcher the response format needs.

    Two cases: a numeric estimate goes to the tolerance matcher, everything else to the text
    matcher. `no_action_correct` is deliberately NOT a third case, and this docstring used to
    claim it was. The four items using that format author full-sentence accept values, so the
    text matcher is the right one; a separate branch that only recognised "no action" would mark
    an operator correct for typing two words without the reasoning the accept values require.
    """
    if len(response) > MAX_ANSWER_LENGTH:
        return Match("none", 0.0, note=f"Answers are capped at {MAX_ANSWER_LENGTH} characters.")
    #: The sentinel is refused whatever the response format says. It was checked only inside
    #: `match_numeric`, and DRL-0030 carries `computed_from_params` on a `free_classification`
    #: item: the text matcher then compared the operator's prose against the literal string, so
    #: everything except typing the sentinel itself was marked WRONG, dropping the rating and
    #: resetting the cue. That is the exact harm the unscorable branch exists to prevent, reached
    #: by a route that branch could not see.
    if COMPUTED_SENTINEL in answer.accept:
        if response_format is ResponseFormat.NUMERIC_ESTIMATE:
            return match_numeric(response, answer, derived)
        return match_derived_text(response, derived, answer)
    if response_format is ResponseFormat.NUMERIC_ESTIMATE:
        return match_numeric(response, answer, derived)
    return match_text(response, answer)
