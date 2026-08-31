"""Scoring: a declarative evaluator over the rubric, and an exact matcher over the drill key."""

from __future__ import annotations

from enlightenment.scoring.evaluator import (
    DRILL_PREDICATES,
    Award,
    Evaluation,
    Facts,
    Predicate,
    RubricEvaluator,
)
from enlightenment.scoring.matching import (
    MAX_ANSWER_LENGTH,
    UNSCORABLE,
    Match,
    match,
    match_numeric,
    match_text,
    normalise,
)

__all__ = [
    "DRILL_PREDICATES",
    "MAX_ANSWER_LENGTH",
    "UNSCORABLE",
    "Award",
    "Evaluation",
    "Facts",
    "Match",
    "Predicate",
    "RubricEvaluator",
    "match",
    "match_numeric",
    "match_text",
    "normalise",
]
