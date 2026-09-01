"""Scoring: a declarative evaluator over the rubric, and an exact matcher over the drill key."""

from __future__ import annotations

from enlightenment.scoring.evaluator import (
    DRILL_PREDICATES,
    FULL_CREDIT,
    Award,
    Evaluation,
    Facts,
    Predicate,
    RubricEvaluator,
)
from enlightenment.scoring.matching import (
    COMPUTED_SENTINEL,
    MAX_ANSWER_LENGTH,
    UNSCORABLE,
    Match,
    match,
    match_derived_text,
    match_numeric,
    match_text,
    normalise,
)

__all__ = [
    "COMPUTED_SENTINEL",
    "DRILL_PREDICATES",
    "FULL_CREDIT",
    "MAX_ANSWER_LENGTH",
    "UNSCORABLE",
    "Award",
    "Evaluation",
    "Facts",
    "Match",
    "Predicate",
    "RubricEvaluator",
    "match",
    "match_derived_text",
    "match_numeric",
    "match_text",
    "normalise",
]
