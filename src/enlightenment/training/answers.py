"""Matching a PRODUCED answer against an answer key.

The plan's central design choice is that the answer is never on screen: production, not
recognition. That makes this module load-bearing in a way a multiple-choice comparison never
would be, because the operator types prose and the engine has to decide whether the prose means
the right thing.

**The bar is deliberately set at "an examiner would accept it", not "the strings are equal".**
An operator who types "stationkeeping" when the key says "station keeping" knows the answer, and
marking that wrong teaches them to fight the input box instead of learning the procedure. The
tolerances below are each there for one such case:

● Case, surrounding whitespace and internal run-length of whitespace are ignored.
● Punctuation and hyphenation are ignored, so "drift-by" and "drift by" agree.
● A leading article or filler ("a", "the", "it is", "looks like") is stripped.
● British and American spellings of the words this vocabulary actually uses are folded together,
  because "maneuver" from an allied operator is not a wrong answer.

**What is NOT tolerated, and this is the important half.** No fuzzy distance, no stemming, no
substring match against the key. Fuzzy matching here would accept "not a manoeuvre" for
"manoeuvre" and "uncontrolled conjunction" for "controlled proximity operations", which are the
exact discriminations the product exists to train. A near-miss is a miss, and the debrief tells
the operator what the expert saw. Guessing in the operator's favour on a discrimination would
make the score a lie in the one place it matters most.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Anything that is not a letter, a digit or a space becomes a space. Hyphens and apostrophes
#: included, so "drift-by", "drift by" and "driftby" do not all have to be authored.
_NON_ALPHANUMERIC: Final = re.compile(r"[^a-z0-9 ]+")

#: Collapsed after punctuation removal, because removing a hyphen leaves two spaces behind.
_WHITESPACE: Final = re.compile(r"\s+")

#: Openers an operator types before the answer itself. Stripped from the FRONT only, and only as
#: whole words, so "not a manoeuvre" keeps its "not" and stays a different answer from "manoeuvre".
_LEADING_FILLER: Final = (
    "it is",
    "its",
    "this is",
    "that is",
    "looks like",
    "looks like a",
    "probably",
    "probably a",
    "i think",
    "i think its",
    "a",
    "an",
    "the",
)

#: Spelling variants folded together. Keyed on the form to replace. Confined to the words this
#: vocabulary actually uses rather than a general dictionary: a general transformation would
#: eventually fold two terms that need to stay apart, and nobody would notice until it did.
_SPELLING: Final[dict[str, str]] = {
    "maneuver": "manoeuvre",
    "maneuvre": "manoeuvre",
    "manoeuver": "manoeuvre",
    "maneuvering": "manoeuvring",
    "maneuvre ing": "manoeuvring",
    "stationkeeping": "station keeping",
    "artifact": "artefact",
    "breakup": "break up",
    "recognise": "recognize",
    "characterise": "characterize",
    "analyse": "analyze",
}

#: A produced answer longer than this is not an answer, it is an essay or a paste. Bounded before
#: any regex runs, so a pathological input costs nothing.
MAX_ANSWER_LENGTH: Final = 300


def normalise(answer: str) -> str:
    """Fold one answer to its comparable form. Pure, and safe on any input.

    Truncates before normalising rather than after: the point of the bound is to cap the work, and
    a bound applied to the output has already paid for the input.
    """
    text = answer[:MAX_ANSWER_LENGTH]
    # NFKD then ASCII-drop, so a pasted answer carrying a non-breaking space or a smart quote
    # normalises rather than failing to match for a reason the operator cannot see.
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = _NON_ALPHANUMERIC.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()

    for variant, canonical in _SPELLING.items():
        if variant in text:
            text = text.replace(variant, canonical)
    text = _WHITESPACE.sub(" ", text).strip()

    # At most TWO passes, longest filler first, front only, and the bound is the point.
    #
    # One pass was not enough: "it is a manoeuvre" strips "it is" and leaves "a manoeuvre", which
    # is not the key. Enumerating the cross product ("it is a", "this is a", "looks like a", ...)
    # would work and would also be a list nobody maintains. Two passes handles every real opener
    # in one rule.
    #
    # Bounded rather than looped to exhaustion, because an unbounded strip eventually eats a word
    # that carries meaning. Note what is safe either way: "not a manoeuvre" starts with "not",
    # which is not a filler, so the first pass matches nothing and stops - the negation survives,
    # and it has to, because it is a different answer.
    for _pass in range(2):
        for filler in sorted(_LEADING_FILLER, key=len, reverse=True):
            prefix = f"{filler} "
            if text.startswith(prefix):
                text = text[len(prefix) :]
                break
        else:
            break
    return text.strip()


def matches(answer: str, accepted: list[str]) -> str | None:
    """The accepted answer this one equals after normalising, or None.

    Returns the KEY rather than a boolean so the debrief can name the form the expert used,
    which reads better than echoing what the operator typed back at them.
    """
    if not answer.strip():
        return None
    folded = normalise(answer)
    if not folded:
        return None
    for candidate in accepted:
        if normalise(candidate) == folded:
            return candidate
    return None


def near_miss(answer: str, confusable_with: list[str]) -> str | None:
    """The look-alike the operator named instead, if they named one.

    This is what turns "wrong" into a teachable moment: the debrief can say "you called it a
    fragmentation, and the discriminator is the piece count" rather than only "incorrect". The
    author lists the confusables on the item, so this is a lookup and never a guess.
    """
    return matches(answer, confusable_with)
