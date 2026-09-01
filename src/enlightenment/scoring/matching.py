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

#: Suffixes a direction word may legitimately carry in prose. Bounded on purpose: an open `\w*`
#: accepted "eastwest" and "eastasdfgh" as a correct reading of an eastward drift.
DIRECTION_SUFFIXES: Final = r"(?:ward|wards|erly|ern)?"
#: The same suffixes as plain words, for reducing a token to its stem.
DIRECTION_SUFFIX_WORDS: Final = ("wards", "ward", "erly", "ern")

#: How many words may sit between a negation and the direction it denies. Small on purpose: the
#: unscoped version searched the whole response and refused correct answers whose negation was
#: about something else entirely.
NEGATION_WINDOW_WORDS: Final = 2

#: The compass vocabulary a drift direction is stated in. Domain fact, not content: used to notice
#: that a response names a direction which was NOT drawn.
COMPASS_DIRECTIONS: Final = (
    "north",
    "south",
    "east",
    "west",
    "northeast",
    "northwest",
    "southeast",
    "southwest",
)

#: Words that deny whatever follows them. "not east" named the right token and meant the opposite.
NEGATIONS: Final = ("not", "isnt", "arent", "no", "never", "neither", "rather than", "instead of")

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


def _compass_stem(word: str) -> str:
    """A direction word reduced to its compass stem, hyphens closed up.

    Two things this fixes, both measured. A generator emitting `("eastward",)` was compared
    literally against the eight canonical words, so it matched none of them and EVERY correct
    answer was refused as naming a direction that was not drawn. And "north-east" typed against
    a drawn "northeast" matched both halves as separate directions and was refused, because
    normalisation keeps the hyphen.
    """
    closed = word.casefold().replace("-", "").replace(" ", "")
    for suffix in DIRECTION_SUFFIX_WORDS:
        if closed.endswith(suffix) and closed[: -len(suffix)] in COMPASS_DIRECTIONS:
            return closed[: -len(suffix)]
    return closed


def _closed(typed: str) -> str:
    """The response with hyphens closed up, so "north-east" reads as the compound it is.

    Hyphens only. Removing spaces as well would destroy the word boundaries every pattern here
    relies on, and "drifting east" would stop matching "east".
    """
    return typed.replace("-", "")


def _directions_named(typed: str) -> set[str]:
    """Which compass directions the response names.

    A compound absorbs its halves: with word boundaries "northeast" cannot match `\bnorth\b`,
    and the filter below is belt and braces for any vocabulary added later. Counting a compound
    as two directions made every correct compound answer look self-contradictory.
    """
    closed = _closed(typed)
    found = {
        direction
        for direction in COMPASS_DIRECTIONS
        if re.search(rf"\b{direction}{DIRECTION_SUFFIXES}\b", closed)
    }
    return {stem for stem in found if not any(stem != other and stem in other for other in found)}


def _contradicted(typed: str, tokens: tuple[str, ...]) -> bool:
    """Whether the response names a direction other than the drawn one, or denies the drawn one.

    Two rules, and the difference between them matters because the second was wrong in both
    directions and is now deliberately narrow.

    ● NAMES ANOTHER DIRECTION. Sound and exact: the compass vocabulary is domain fact, there are
      eight words, and an answer naming one that was not drawn has not read the plot. Compared on
      STEMS so "eastward" and "north-east" behave.
    ● DENIES THE DRAWN ONE. Scoped to a short window BEFORE the direction, because the first
      version searched the whole response for any "no", "not", "never" or "neither" and so
      refused "drifting east, no doubt about it", "east, definitely not stationary" and
      "0.279 deg/day west, no reversal in the trend" - correct answers, penalised, which is the
      harm this module documents at the magnitude-and-direction branch.

    **NAMED GAP, recorded rather than papered over.** The scoped rule catches "not east" and
    "isn't drifting east". It does NOT catch open-ended denial: "it doesn't drift east", "cannot
    be east", "east is wrong", "anything but east", "hardly east" all still score. Those are a
    semantics problem, not a regex problem, and two attempts at widening this check have each
    created a worse fault than the one they closed. Over-refusing a correct reading is the more
    expensive error, so the check stays narrow and this paragraph is the disclosure.
    """
    wanted = {_compass_stem(token) for token in tokens}
    if _directions_named(typed) - wanted:
        return True
    closed = _closed(typed)
    return any(
        re.search(
            rf"\b{negation}\b(?:\W+\w+){{0,{NEGATION_WINDOW_WORDS}}}\W+{re.escape(stem)}",
            closed,
        )
        for negation in NEGATIONS
        for stem in {_compass_stem(token) for token in tokens}
    )


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
    #: A token matches the word, or the word with one of a NAMED set of suffixes: "west" accepts
    #: "westwards" and "westerly", which are fully correct prose answers a strict word boundary
    #: rejected. The suffix set is bounded because an open `\w*` accepted "eastwest" and
    #: "eastasdfgh" as correct - a wrong answer scoring full credit, which is worse than the
    #: pedantry it was widening away from.
    #:
    #: And a CONTRADICTED direction is refused. An answer naming a compass direction that is not
    #: the one drawn ("east or west", "drifting west, not east") or negating the one drawn
    #: ("not east") scored full credit, because the search only asked whether the right token
    #: appeared anywhere. An operator who names two directions has not read the plot.
    if _contradicted(typed, tokens):
        return Match(
            "none",
            0.0,
            note="Name one direction. The answer given names more than one, or denies it.",
        )
    #: Matched on the token's compass STEM against the hyphen-closed response, so a generator
    #: emitting `("eastward",)` still accepts "drifting east", and a typed "north-east" still
    #: accepts against a drawn "northeast". Both were refused before, which would have marked
    #: every correct answer wrong the day a generator spelled its token differently.
    closed_response = _closed(typed)
    if any(
        re.search(rf"\b{re.escape(_compass_stem(token))}{DIRECTION_SUFFIXES}\b", closed_response)
        for token in tokens
    ):
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
