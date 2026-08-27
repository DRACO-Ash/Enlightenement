"""The training layer: the drill loop, its scoring, and per-operator progress.

Flight plan steps 6 and 7 (scoring engine, drill loop) for the drill surface. Scenario mode on a
running clock is step 11 and is not here yet; the scoring engine's decision-table path reads the
rubric from the content tree when that lands, and the drill's own weights stay in
:func:`~enlightenment.training.scoring.explain_score`.

Nothing in this package performs I/O except :class:`~enlightenment.training.progress.ProgressStore`,
which is the one place operator state is written, and it is deliberately narrow so the SQLite swap
the flight plan settles on is one class rather than a refactor.
"""

from __future__ import annotations

from enlightenment.training.engine import DrillEngine, DrillError, ScoredDrill, ServedDrill
from enlightenment.training.progress import (
    AXES,
    DEMONSTRATION_OPERATOR,
    OperatorProgress,
    ProgressStore,
)
from enlightenment.training.scoring import (
    CONFIDENCE_STEPS,
    DEFAULT_OPERATOR_RATING,
    ScoreLine,
    brier_score,
    calibration_verdict,
    confidence_probability,
    expected_score,
    explain_score,
    next_interval_days,
    update_ratings,
)

__all__ = [
    "AXES",
    "CONFIDENCE_STEPS",
    "DEFAULT_OPERATOR_RATING",
    "DEMONSTRATION_OPERATOR",
    "DrillEngine",
    "DrillError",
    "OperatorProgress",
    "ProgressStore",
    "ScoreLine",
    "ScoredDrill",
    "ServedDrill",
    "brier_score",
    "calibration_verdict",
    "confidence_probability",
    "expected_score",
    "explain_score",
    "next_interval_days",
    "update_ratings",
]
