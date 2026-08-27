"""Rating, calibration and scheduling. Pure functions, no I/O, no state.

Three mechanisms the plan names explicitly, kept together because they are the same subject
(how one drill answer changes what the operator sees next) and kept pure because the debrief has
to be able to recompute any of them from a stored run months later.

● **Elo** rates the operator and the item against each other, so difficulty tracks the operator
  rather than being authored once and drifting.
● **The Brier score** grades stated confidence by a proper scoring rule. This is the mechanism
  against the plan's stated target: "confident errors are the thing this is built to remove."
● **A spacing scheduler** decides when a missed cue class comes back. Modelled on the FSRS
  family: stability grows on success and collapses on a miss.

**Every function here returns its own reasoning, not just a number.** `explain_score` produces a
decomposition naming which rule fired on which evidence, because the plan makes explainability an
acceptance test rather than a nicety: "no scoring decision the debrief cannot explain".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: Standard Elo scale constant. 400 points is one order of magnitude of odds.
ELO_SCALE: Final = 400.0

#: How far one answer can move a rating. Higher for the operator than the item, because an
#: operator's true skill moves (they are learning) while an item's difficulty is a fixed property
#: being estimated. Using one K for both would let a handful of answers shove an item's difficulty
#: around and corrupt every later operator's rating with it.
OPERATOR_K: Final = 32.0
ITEM_K: Final = 8.0

#: Where an operator starts. Mid-scale, so the first few items move them quickly in either
#: direction rather than making a strong operator climb from the floor.
DEFAULT_OPERATOR_RATING: Final = 1200

#: Rating bounds. Not cosmetic: an unbounded rating lets one pathological streak put an operator
#: outside the range where any authored item can match them, and the drill then has nothing to
#: serve. Matches the authored `difficulty` band in the content model.
MIN_RATING: Final = 600
MAX_RATING: Final = 2400

#: Confidence is offered as five steps rather than a free percentage. Five is enough to be
#: informative and few enough to answer in under a second, which the 100ms feedback budget needs;
#: and a discrete scale stops an operator hedging at 50% on everything, which would game a proper
#: scoring rule by refusing to commit.
CONFIDENCE_STEPS: Final[dict[int, float]] = {
    1: 0.15,
    2: 0.35,
    3: 0.55,
    4: 0.75,
    5: 0.93,
}

#: Never 0.0 or 1.0, even at the extremes. A stated certainty that turns out wrong should cost a
#: lot, but a scoring rule that can return an infinite penalty is one that stops being readable.
#: 0.93 rather than 1.0 is also honest: an operator who is certain is not certain.

#: Spacing intervals in days, indexed by how many times this cue class has been answered correctly
#: in a row. A miss resets to the front. Roughly the FSRS shape, with the first three intervals
#: short because the plan's target is recall under time pressure rather than long-term retention
#: of a fact.
SPACING_DAYS: Final[tuple[int, ...]] = (1, 2, 4, 9, 21, 45, 90)

#: What counts as a CONFIDENT claim and an UNSURE one, for the plain-language calibration
#: reading. Named because the confident-and-wrong case is the failure mode the whole product
#: exists to remove, and a threshold that matters that much should not be a literal in a branch.
CONFIDENT_AT: Final = 0.75
UNSURE_AT: Final = 0.35


def expected_score(operator_rating: float, item_difficulty: float) -> float:
    """Probability the operator answers this item correctly, on the Elo model."""
    odds: float = 10.0 ** ((item_difficulty - operator_rating) / ELO_SCALE)
    return 1.0 / (1.0 + odds)


def _clamp_rating(value: float) -> int:
    return round(max(MIN_RATING, min(MAX_RATING, value)))


@dataclass(frozen=True, slots=True)
class RatingChange:
    """What one answer did to both ratings, and the expectation it was judged against."""

    operator_before: int
    operator_after: int
    item_before: int
    item_after: int
    expected: float

    @property
    def operator_delta(self) -> int:
        return self.operator_after - self.operator_before


def update_ratings(*, operator_rating: int, item_difficulty: int, correct: bool) -> RatingChange:
    """Move both ratings by one answer. Symmetric, so the pool cannot inflate.

    The operator gains what the item loses in proportion to the two K factors, which is what keeps
    a rating comparable across a content set that is itself being rated.
    """
    expected = expected_score(operator_rating, item_difficulty)
    outcome = 1.0 if correct else 0.0
    return RatingChange(
        operator_before=operator_rating,
        operator_after=_clamp_rating(operator_rating + OPERATOR_K * (outcome - expected)),
        item_before=item_difficulty,
        item_after=_clamp_rating(item_difficulty - ITEM_K * (outcome - expected)),
        expected=expected,
    )


def confidence_probability(step: int) -> float:
    """The probability a confidence step asserts. Refuses an off-scale step rather than clamping.

    Clamping would silently score a client bug as a real answer, and a stated confidence is the
    input to the calibration measure the plan puts second in its priority list.
    """
    if step not in CONFIDENCE_STEPS:
        raise ValueError(
            f"confidence step {step!r} is not on the scale; expected one of"
            f" {sorted(CONFIDENCE_STEPS)}"
        )
    return CONFIDENCE_STEPS[step]


def brier_score(probability: float, correct: bool) -> float:
    """Squared error of a probabilistic claim. Zero is perfect, one is maximally wrong.

    A PROPER scoring rule, which is the whole reason for using it: an operator minimises it by
    stating what they actually believe, so there is no confidence they can report to game it.
    """
    outcome = 1.0 if correct else 0.0
    return (probability - outcome) ** 2


def calibration_verdict(probability: float, correct: bool) -> str:
    """A plain-language reading of one calibration outcome, for the debrief.

    Named cases rather than a number, because "you were confident and wrong" is actionable and
    "your Brier score was 0.72" is not. The confident-and-wrong case is called out specifically:
    it is the failure mode the plan built this product to remove.
    """
    if correct and probability >= CONFIDENT_AT:
        return "confident and right, which is the target"
    if correct and probability <= UNSURE_AT:
        return "right but unsure, so trust the read a little more"
    if not correct and probability >= CONFIDENT_AT:
        return "confident and wrong, which is the costliest combination on a real watch"
    if not correct and probability <= UNSURE_AT:
        return "wrong but you said so, which is the honest and useful answer"
    return "middling confidence, matched to a middling read"


def next_interval_days(*, streak: int, correct: bool) -> int:
    """When this cue class should come back.

    A miss returns the FRONT interval rather than a reduced one. The plan re-injects a missed cue
    class into future work, and a miss means the operator does not have it yet; treating a miss as
    a partial success is how a gap survives a scheduler.
    """
    if not correct:
        return SPACING_DAYS[0]
    index = min(max(streak, 0), len(SPACING_DAYS) - 1)
    return SPACING_DAYS[index]


@dataclass(frozen=True, slots=True)
class ScoreLine:
    """One rule, whether it fired, on what evidence, and what it was worth.

    The unit of the plan's explainability requirement. A score is a list of these, never a single
    total with the reasoning discarded, because the debrief has to name the rule and the evidence
    for every point gained or lost.
    """

    rule: str
    axis: str
    awarded: float
    available: float
    fired: bool
    evidence: str


def explain_score(
    *,
    classification_match: str | None,
    action_match: str | None,
    confused_with: str | None,
    probability: float,
    expert_cue: str,
) -> tuple[list[ScoreLine], float]:
    """Decompose one drill answer into named rules, and total them.

    Weights mirror the rubric shape in the content tree: naming the event is worth most, the first
    procedural action next, calibration next. They are stated here rather than read from the rubric
    because a drill answer is scored on three axes and a full scenario run is scored on six; when
    scenario mode lands (plan step 11) it reads the rubric and this function stays the drill's.
    """
    correct = classification_match is not None
    lines = [
        ScoreLine(
            rule="event-named",
            axis="event-classification",
            awarded=45.0 if correct else 0.0,
            available=45.0,
            fired=correct,
            evidence=(
                f"answer matched the accepted classification {classification_match!r}"
                if correct
                else (
                    f"answer matched {confused_with!r}, which is the look-alike this item"
                    " discriminates against"
                    if confused_with
                    else "answer matched no accepted classification for this item"
                )
            ),
        ),
        ScoreLine(
            rule="first-action-named",
            axis="procedure-recall",
            awarded=35.0 if action_match else 0.0,
            available=35.0,
            fired=action_match is not None,
            evidence=(
                f"first action matched {action_match!r}"
                if action_match
                else "first action matched no accepted action for the governing procedure"
            ),
        ),
        ScoreLine(
            rule="confidence-calibrated",
            axis="uncertainty-calibration",
            # A proper scoring rule turned into points: full marks for a perfect claim, zero for a
            # maximally wrong one. Linear in the Brier score, so the penalty for being confidently
            # wrong is quadratic in the confidence, which is the intended incentive.
            awarded=round(20.0 * (1.0 - brier_score(probability, correct)), 2),
            available=20.0,
            fired=True,
            evidence=(
                f"stated confidence {probability:.0%}, outcome"
                f" {'correct' if correct else 'incorrect'}:"
                f" {calibration_verdict(probability, correct)}"
            ),
        ),
        ScoreLine(
            rule="expert-cue",
            axis="cue-detection",
            awarded=0.0,
            available=0.0,
            fired=False,
            evidence=expert_cue,
        ),
    ]
    return lines, round(sum(line.awarded for line in lines), 2)
