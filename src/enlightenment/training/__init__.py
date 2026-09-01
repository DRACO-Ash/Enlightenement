"""The training layer: the drill loop, the rating and spacing model, and stored progress.

The drill loop moved to `drill.py` when the real content package landed. The illustrative engine,
its answer matcher and its three shaped plot generators are retired: matching now lives in
`enlightenment.scoring` against the authored key, and stimuli come from the ten registered product
renderers in `enlightenment.generators` rather than from three shapes invented here.

What survived unchanged is the part that was never about the content: the Elo pairing, the Brier
calibration score, the spacing intervals and the atomic progress store.
"""

from __future__ import annotations

from enlightenment.training.drill import (
    DEMONSTRATION_OPERATOR,
    DRILL_RUBRIC_ID,
    DrillError,
    DrillLoop,
    ScoredDrill,
    ServedDrill,
    bounded_reason,
)
from enlightenment.training.progress import (
    AxisProgress,
    CueSchedule,
    OperatorProgress,
    ProgressStore,
    RunRecord,
    now_utc,
)
from enlightenment.training.scoring import (
    CONFIDENT_AT,
    UNSURE_AT,
    RatingChange,
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
    "CONFIDENT_AT",
    "DEMONSTRATION_OPERATOR",
    "DRILL_RUBRIC_ID",
    "UNSURE_AT",
    "AxisProgress",
    "CueSchedule",
    "DrillError",
    "DrillLoop",
    "OperatorProgress",
    "ProgressStore",
    "RatingChange",
    "RunRecord",
    "ScoreLine",
    "ScoredDrill",
    "ServedDrill",
    "bounded_reason",
    "brier_score",
    "calibration_verdict",
    "confidence_probability",
    "expected_score",
    "explain_score",
    "next_interval_days",
    "now_utc",
    "update_ratings",
]
