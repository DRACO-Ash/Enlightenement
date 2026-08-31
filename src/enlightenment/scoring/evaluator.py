"""The scoring evaluator: rules are data, predicates are code, and an unknown rule fails closed.

**Adding a rubric rule must add data only.** That is the architectural requirement, and it is
satisfied for the shape of a rule: `award`, `competency_id`, `explain` and `cap` are read from
`rubrics.json` and never appear in Python. Every score decomposes to a named rule and the
evidence that fired it, because a scorer that cannot be challenged will not be trusted by this
audience.

**What is NOT satisfied, and is a finding rather than a shortcut.** The `when` clause of every
rule is prose: "operator checked epoch age or observation density before making any
classification". The design note says rules are "evaluated against the run event log", which is
the right intent, but nothing in the content carries a machine-readable condition. So a predicate
cannot be derived from the content and something has to bridge the gap.

The bridge here is a registry keyed by **rule id**, which keeps the content authoritative and
makes the gap visible rather than papering over it:

● A rule whose id has a registered predicate is evaluated, and its award, cap, competency and
  explain all come from the JSON. Changing any of them changes no code.
● A rule whose id has NO predicate is reported as `unimplemented` in the result. It does not
  score zero silently, because a rule that quietly contributes nothing is indistinguishable from
  a rule that ran and found nothing, and those are opposite facts.

Six of the 67 rules are implemented, all of `RUB-DRILL`, which is the whole drill layer. The
other 61 belong to the scenario runner and the argument surface, neither of which exists yet.
The evaluator names them rather than pretending.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from enlightenment.content import Rubric, RubricRule

#: A predicate reads the facts of one submission and says whether its rule fired. Facts are a
#: flat mapping on purpose: the scenario runner will supply a much richer event log, and a
#: predicate that reached into engine objects would couple scoring to the runner's internals.
Predicate = Callable[["Facts"], bool]


@dataclass(frozen=True, slots=True)
class Facts:
    """What is known about one submission, as the evaluator sees it.

    Deliberately flat and deliberately small. Everything here is decided before scoring starts,
    so a predicate cannot accidentally re-derive a match and disagree with the matcher.
    """

    matched: str = "none"
    """One of accept, partial, reject, none."""

    correct: bool = False
    within_tolerance: bool | None = None
    confidence_given: bool = False
    elapsed_ms: int = 0
    time_target_s: int = 30
    numeric_expected: float | None = None
    numeric_response: float | None = None

    #: The credit a partial answer earns, from the DRILL rather than from the rule. The content
    #: author decides how close a given wrong-but-reasonable answer was; the rule supplies the
    #: scale and the item supplies the fraction.
    partial_credit: float = 0.5

    @property
    def inside_time_target(self) -> bool:
        return self.elapsed_ms <= self.time_target_s * 1000


@dataclass(frozen=True, slots=True)
class Award:
    """One rule that fired, what it awarded, and the operator-facing reason.

    `explain` is the rule's own string used verbatim. The evaluator never composes its own
    wording for a score, because the debrief has to be able to say "this rule, this evidence"
    and be challengeable on both.
    """

    rule_id: str
    award: float
    competency_id: str
    explain: str


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The decomposed result. `unimplemented` is part of the answer, not a footnote."""

    awards: tuple[Award, ...]
    total: float
    unimplemented: tuple[str, ...]

    def components(self) -> tuple[dict[str, Any], ...]:
        """The awards as plain records, typed, for callers that build a payload or a run row.

        Separate from `as_dict` because a caller that wants the components should not have to
        index into a loosely typed mapping and then convince a type checker the result is
        iterable.
        """
        return tuple(
            {
                "rule_id": a.rule_id,
                "award": a.award,
                "competency_id": a.competency_id,
                "explain": a.explain,
            }
            for a in self.awards
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "score_components": [
                {
                    "rule_id": a.rule_id,
                    "award": a.award,
                    "competency_id": a.competency_id,
                    "explain": a.explain,
                }
                for a in self.awards
            ],
            "total": round(self.total, 4),
            "unimplemented_rules": list(self.unimplemented),
        }


def _matched(kind: str) -> Predicate:
    return lambda facts: facts.matched == kind


#: Keyed by rule id, and the id is the contract. A rule reusing one of these conditions with a
#: different award, competency or explain is pure data. A rule with a genuinely new condition
#: needs a predicate, which is code, and the evaluator names it until somebody writes one.
DRILL_PREDICATES: Final[dict[str, Predicate]] = {
    "D-CORRECT": _matched("accept"),
    "D-PARTIAL": _matched("partial"),
    "D-MISS": _matched("reject"),
    "D-WITHIN-TOLERANCE": lambda facts: facts.within_tolerance is True,
    "D-CALIBRATION": lambda facts: facts.confidence_given,
    "D-FAST-AND-CORRECT": lambda facts: facts.correct and facts.inside_time_target,
}


class RubricEvaluator:
    """Evaluates a rubric against the facts of a submission.

    Cognitive complexity stays low by construction: the loop is flat, the branching lives in the
    predicates, and there is no dispatch over rule kinds. That matters because the cap the
    platform's quality gate enforces would otherwise push this into small helper functions,
    which is a different thing from a declarative evaluator and only one of the two is right.
    """

    def __init__(self, predicates: dict[str, Predicate] | None = None) -> None:
        self._predicates = dict(DRILL_PREDICATES if predicates is None else predicates)

    def register(self, rule_id: str, predicate: Predicate) -> None:
        """Add a predicate for a rule the content declares and this evaluator cannot yet judge."""
        self._predicates[rule_id] = predicate

    @property
    def implemented(self) -> frozenset[str]:
        return frozenset(self._predicates)

    def evaluate(self, rubric: Rubric, facts: Facts) -> Evaluation:
        awards: list[Award] = []
        unimplemented: list[str] = []
        for rule in rubric.rules:
            predicate = self._predicates.get(rule.id)
            if predicate is None:
                unimplemented.append(rule.id)
                continue
            if predicate(facts):
                awards.append(self._award(rule, facts))
        total = sum(a.award for a in awards)
        return Evaluation(tuple(awards), total, tuple(unimplemented))

    @staticmethod
    def _award(rule: RubricRule, facts: Facts) -> Award:
        """Resolve one rule's award, applying its cap and its partial credit from the content.

        A partial answer's credit comes from the drill, not from the rule, because the content
        author sets how close a given wrong-but-reasonable answer was. The rule supplies the
        scale; the item supplies the fraction.
        """
        award = rule.award
        if rule.id == "D-PARTIAL":
            award = rule.award * (facts.partial_credit / 0.5) if rule.award else 0.0
        if rule.cap is not None:
            award = min(award, rule.cap) if award >= 0 else max(award, -rule.cap)
        return Award(rule.id, award, rule.competency_id, rule.explain)
