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
            if candidate == "computed_from_params":
                supplied = derived.get("expected_value")
                expected = None if supplied is None else float(supplied)
                break
            numeric_candidate = _numeric(candidate)
            if numeric_candidate is not None:
                expected = numeric_candidate
                break
    if expected is None:
        return Match(UNSCORABLE, 0.0, note="This item's expected value could not be resolved.")
    if given is None:
        return Match("none", 0.0, note="No number found in the response.", expected=expected)
    inside = _within(given, expected, answer.tolerance)
    if inside:
        return Match("accept", 1.0, within_tolerance=True, expected=expected)
    rejected = _match_reject(response, answer)
    if rejected is not None:
        return Match("reject", 0.0, why_wrong=rejected, within_tolerance=False, expected=expected)
    return Match("none", 0.0, within_tolerance=False, expected=expected)


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
    if response_format is ResponseFormat.NUMERIC_ESTIMATE:
        return match_numeric(response, answer, derived)
    return match_text(response, answer)
