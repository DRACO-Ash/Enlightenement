"""The drill loop over the real content package: select, serve, score.

Replaces the illustrative engine. The shape is the same because the shape was right; what changed
is that every item, key, prompt and explanation now comes from Ash's authored library rather than
from a placeholder, and every stimulus comes from a registered product renderer rather than from
one of three shaped series.

Two properties this module exists to hold, both easy to lose:

● **The served payload carries no answer.** Not the accept list, not the reject list, not the
  explanation, not the derived expected value for a numeric item. `ServedDrill.as_dict` is the
  only thing that crosses the wire and it is built by naming fields rather than by serialising an
  object, because a field added to a model would otherwise appear in the payload silently.
● **Submission is idempotent on the run id.** A second submission returns the first result rather
  than rescoring, so a double-click or a retry cannot move a rating twice.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from enlightenment.content import ContentPackage, Drill
from enlightenment.generators import GeneratorRegistry, compose
from enlightenment.scoring import Facts, Match, RubricEvaluator, match
from enlightenment.training.progress import OperatorProgress, ProgressStore, RunRecord, now_utc
from enlightenment.training.scoring import (
    brier_score,
    calibration_verdict,
    confidence_probability,
    next_interval_days,
    update_ratings,
)

#: The rubric the drill layer scores against, by id. Named here rather than inlined at the call
#: site so a content author renaming it produces one failure with one fix.
DRILL_RUBRIC_ID = "RUB-DRILL"

#: Until identity exists (flight plan step 10), every write goes to one synthetic operator and no
#: record of a named individual is created before the DPIA is closed.
DEMONSTRATION_OPERATOR = "synthetic-operator"


class DrillError(RuntimeError):
    """Raised when a drill cannot be served or scored. Carries an operator-facing reason."""


@dataclass(frozen=True, slots=True)
class ServedDrill:
    """What the operator is given. **No answer, no explanation, no derived value.**"""

    run_id: str
    item_id: str
    cue_id: str
    prompt: str
    response_format: str
    elo: int
    confidence_required: bool
    time_target_s: int
    stimuli: tuple[dict[str, Any], ...]
    content_hash: str
    seed: int

    def as_dict(self) -> dict[str, Any]:
        """The wire form, built by naming every field.

        Deliberately not `asdict`: a field added to this dataclass should NOT appear in the
        payload until somebody decides it should, and a reflexive serialiser makes that decision
        for you at the moment of least attention.
        """
        return {
            "drill_run_id": self.run_id,
            "item_id": self.item_id,
            "cue_id": self.cue_id,
            "prompt": self.prompt,
            "response_format": self.response_format,
            "elo": self.elo,
            "confidence_required": self.confidence_required,
            "time_target_s": self.time_target_s,
            "stimulus": list(self.stimuli),
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class ScoredDrill:
    """The reveal. Everything withheld above arrives here, and only here."""

    run_id: str
    item_id: str
    matched: str
    correct: bool
    credit: float
    explain: str
    note: str
    why_wrong: str
    brier: float
    calibration: str
    rating_before: int
    rating_after: int
    next_due_in_days: int
    score_components: tuple[dict[str, Any], ...]
    total: float
    unimplemented_rules: tuple[str, ...]
    content_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "drill_run_id": self.run_id,
            "item_id": self.item_id,
            "matched": self.matched,
            "correct": self.correct,
            "credit": round(self.credit, 4),
            "explain": self.explain,
            "note": self.note,
            "why_wrong": self.why_wrong,
            "brier": round(self.brier, 4),
            "calibration": self.calibration,
            "rating_delta": self.rating_after - self.rating_before,
            "rating_before": self.rating_before,
            "rating_after": self.rating_after,
            "next_due_in_days": self.next_due_in_days,
            "score_components": list(self.score_components),
            "total": round(self.total, 4),
            "unimplemented_rules": list(self.unimplemented_rules),
            "content_hash": self.content_hash,
        }


@dataclass(slots=True)
class _Pending:
    """A served drill awaiting its submission, held server-side with its derived values."""

    drill: Drill
    seed: int
    derived: dict[str, Any]
    served_at: datetime
    result: ScoredDrill | None = field(default=None)


class DrillLoop:
    """Selection, service and scoring over the content package.

    Selection is due-first then rating-matched, interleaved across procedures. The rating match
    targets the band just above the operator, because the item that teaches is the one at the
    edge of what they can already do; an item they answer without thinking produces a correct
    response and no learning.
    """

    def __init__(
        self,
        *,
        content: ContentPackage,
        registry: GeneratorRegistry,
        progress: ProgressStore,
        evaluator: RubricEvaluator | None = None,
    ) -> None:
        self._content = content
        self._registry = registry
        self._progress = progress
        self._evaluator = evaluator if evaluator is not None else RubricEvaluator()
        self._pending: dict[str, _Pending] = {}

    @property
    def ready(self) -> bool:
        return self._content.result.ok and bool(self._content.drills)

    def _seed(self, operator_id: str, item_id: str, attempt: int) -> int:
        """A stable seed per operator, item and attempt, so a debrief redraws exactly.

        Hashed rather than combined arithmetically: two operators on adjacent items must not get
        correlated stimuli, and a sum or an exclusive-or gives exactly that.
        """
        material = f"{self._content.content_hash}:{operator_id}:{item_id}:{attempt}"
        return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")

    def select(self, progress: OperatorProgress) -> Drill:
        """Due first, then the item just above the operator's rating."""
        now = now_utc()
        due = [d for d in self._content.drills if progress.cue(d.id).is_due(now)]
        pool = due or list(self._content.drills)
        # Just above, not at: the item that teaches sits at the edge of what the operator can
        # already do. One they answer without thinking produces a correct response and no
        # learning.
        target = progress.rating + 60
        return min(pool, key=lambda d: (abs(d.elo - target), d.id))

    def serve(self, *, operator_id: str) -> ServedDrill:
        if not self.ready:
            raise DrillError("the content package is not loaded")
        progress = self._progress.load(operator_id)
        item = self.select(progress)
        attempt = sum(1 for run in progress.runs if run.item_id == item.id)
        seed = self._seed(operator_id, item.id, attempt)
        try:
            rendered = compose(
                self._registry,
                item.stimulus.generator,
                item.stimulus.params,
                seed,
                item.stimulus.product_id,
            )
        except LookupError as exc:
            raise DrillError(f"{item.id}: {exc}") from None

        derived: dict[str, Any] = {}
        for stimulus in rendered:
            derived.update(stimulus.derived)

        run_id = uuid.uuid4().hex
        self._pending[run_id] = _Pending(
            drill=item, seed=seed, derived=derived, served_at=now_utc()
        )
        return ServedDrill(
            run_id=run_id,
            item_id=item.id,
            cue_id=item.cue_id,
            prompt=item.prompt,
            response_format=str(item.response_format),
            elo=item.elo,
            confidence_required=item.confidence_required,
            time_target_s=item.time_target_s,
            stimuli=tuple(s.for_client() for s in rendered),
            content_hash=self._content.content_hash,
            seed=seed,
        )

    def score(
        self, *, run_id: str, response: str, confidence: int, elapsed_ms: int, operator_id: str
    ) -> ScoredDrill:
        """Score one submission. Idempotent: a second call returns the first result."""
        pending = self._pending.get(run_id)
        if pending is None:
            raise DrillError("that drill run is unknown or has expired")
        if pending.result is not None:
            return pending.result

        item = pending.drill
        outcome = match(response, item.answer, item.response_format, pending.derived)
        result = self._record(item, outcome, confidence, elapsed_ms, operator_id, run_id)
        pending.result = result
        return result

    def _record(
        self,
        item: Drill,
        outcome: Match,
        confidence: int,
        elapsed_ms: int,
        operator_id: str,
        run_id: str,
    ) -> ScoredDrill:
        rubric = self._content.rubric(DRILL_RUBRIC_ID)
        if rubric is None:
            raise DrillError(f"{DRILL_RUBRIC_ID} is missing from the content package")
        facts = Facts(
            matched=outcome.matched,
            correct=outcome.correct,
            within_tolerance=outcome.within_tolerance,
            confidence_given=confidence > 0,
            elapsed_ms=elapsed_ms,
            time_target_s=item.time_target_s,
            numeric_expected=outcome.expected,
            partial_credit=outcome.credit,
        )
        evaluation = self._evaluator.evaluate(rubric, facts)

        progress = self._progress.load(operator_id)
        change = update_ratings(
            operator_rating=progress.rating,
            item_difficulty=item.elo,
            correct=outcome.correct,
        )
        probability = confidence_probability(confidence)
        brier = brier_score(probability, outcome.correct)
        schedule = progress.cue(item.id)
        schedule.record(correct=outcome.correct, now=now_utc())
        interval = next_interval_days(streak=schedule.streak, correct=outcome.correct)
        progress.rating = change.operator_after
        axis = progress.axis(self._competency_for(item))
        axis.attempts += 1
        axis.correct += 1 if outcome.correct else 0
        axis.brier_total += brier
        progress.runs.append(
            RunRecord(
                item_id=item.id,
                item_version=str(item.model_extra.get("version", "")) if item.model_extra else "",
                content_hash=self._content.content_hash,
                procedure_id=self._procedure_for(item),
                axis=self._competency_for(item),
                seed=self._pending_seed(run_id),
                answered_at=now_utc().isoformat(),
                classification=outcome.matched,
                first_action="",
                confidence=confidence,
                correct=outcome.correct,
                action_correct=outcome.correct,
                brier=brier,
                points=evaluation.total,
                rating_before=change.operator_before,
                rating_after=change.operator_after,
                lines=[dict(c) for c in evaluation.components()],
            )
        )
        self._progress.save(progress)

        return ScoredDrill(
            run_id=run_id,
            item_id=item.id,
            matched=outcome.matched,
            correct=outcome.correct,
            credit=outcome.credit,
            explain=item.explain,
            note=outcome.note,
            why_wrong=outcome.why_wrong,
            brier=brier,
            calibration=calibration_verdict(probability, outcome.correct),
            rating_before=change.operator_before,
            rating_after=change.operator_after,
            next_due_in_days=interval,
            score_components=evaluation.components(),
            total=evaluation.total,
            unimplemented_rules=evaluation.unimplemented,
            content_hash=self._content.content_hash,
        )

    def _pending_seed(self, run_id: str) -> int:
        pending = self._pending.get(run_id)
        return pending.seed if pending is not None else 0

    def _cue(self, item: Drill) -> Any:
        return next((c for c in self._content.cues if c.id == item.cue_id), None)

    def _procedure_for(self, item: Drill) -> str:
        """The procedure the item's cue belongs to, from content rather than from a mapping here."""
        cue = self._cue(item)
        return getattr(cue, "procedure_id", "") if cue is not None else ""

    def _competency_for(self, item: Drill) -> str:
        """The competency axis the cue measures. Empty is honest when the cue does not say."""
        cue = self._cue(item)
        return getattr(cue, "competency_id", "") if cue is not None else ""

    def dashboard(self, *, operator_id: str) -> dict[str, Any]:
        """Where the operator stands, and never a bare estimate.

        Every competency figure carries its interval, computed with an Agresti-Coull adjustment
        rather than a plain Wald one: on three attempts out of three a Wald interval reports zero
        width, which is the most confident and least true thing this could say.

        "Not measured" and "measured at zero" are rendered as different statements, because they
        are. An axis with no attempts has no figure at all.
        """
        progress = self._progress.load(operator_id)
        competencies = []
        for competency in self._content.competencies:
            axis = progress.axes.get(competency.id)
            interval = axis.interval if axis is not None else None
            competencies.append(
                {
                    "competency_id": competency.id,
                    "name": competency.name,
                    "attempts": axis.attempts if axis is not None else 0,
                    "measured": axis is not None and axis.attempts > 0,
                    "estimate": None if axis is None else axis.accuracy,
                    "interval": None
                    if interval is None
                    else [round(interval[0], 3), round(interval[1], 3)],
                    "mean_brier": None if axis is None else axis.mean_brier,
                }
            )
        now = now_utc()
        due = [d.id for d in self._content.drills if progress.cue(d.id).is_due(now)]
        return {
            "operator": operator_id,
            "drill_rating": progress.rating,
            "runs_total": len(progress.runs),
            "competencies": competencies,
            "due_now": len(due),
            "due_items": due[:20],
            "content_hash": self._content.content_hash,
            "identity": (
                "Operator identity does not exist yet (flight plan step 10). Every run is"
                " recorded against a synthetic operator, so no record of a named individual is"
                " created before the DPIA is closed."
            ),
        }

    def manifest(self) -> dict[str, Any]:
        """What is loaded, so a run record stays interpretable and a client can show provenance."""
        return {
            "ok": self._content.result.ok,
            "content_hash": self._content.content_hash,
            "counts": dict(self._content.result.counts),
            "errors": list(self._content.result.errors),
            "thresholds_source": self._content.thresholds.source,
            "scored_scenarios_ready": self._content.scored_scenarios_ready,
            "generators": sorted(self._registry.names),
            "rubric_rules_implemented": sorted(self._evaluator.implemented),
        }
