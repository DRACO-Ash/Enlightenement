"""The drill loop: choose an item, serve it without its answer, score what comes back.

This is the flight plan's "one creative risk" made concrete. Three properties are load-bearing and
each one is a decision rather than an implementation detail:

● **The answer never leaves the server before the operator commits.** :meth:`DrillEngine.serve`
  returns a payload built from a whitelist of fields, so adding an answer-bearing field to the
  content model cannot leak it by default. The reveal is a separate call.
● **Selection is spacing-first, then Elo.** Due items come before well-matched items, because the
  product is a memory system that happens to render orbits. Matching difficulty to a rating is how
  it stays playable; spacing is how it works.
● **Every score decomposes.** The scored answer carries the rule lines from
  :func:`~enlightenment.training.scoring.explain_score`, so the debrief names the rule and the
  evidence for every point. The plan makes that an acceptance test.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from enlightenment.content import ContentStore, DrillItem, Procedure
from enlightenment.training import answers as answer_matching
from enlightenment.training.plots import build_plot
from enlightenment.training.progress import (
    AXES,
    OperatorProgress,
    ProgressStore,
    RunRecord,
    now_utc,
)
from enlightenment.training.scoring import (
    ScoreLine,
    brier_score,
    calibration_verdict,
    confidence_probability,
    expected_score,
    explain_score,
    update_ratings,
)

#: How far from the operator's rating an item may sit and still count as well matched. Wide enough
#: that a twelve-item content set always has candidates, narrow enough that the drill does not
#: serve a 900 to a 1900 operator.
RATING_WINDOW: Final = 350


class DrillError(RuntimeError):
    """A drill request cannot be served or scored. Carries an operator-facing reason."""


@dataclass(frozen=True, slots=True)
class ServedDrill:
    """An unanswered drill instance. Contains no answer key, by construction."""

    instance_id: str
    item_id: str
    item_version: str
    content_hash: str
    procedure_id: str
    procedure_title: str
    axis: str
    title: str
    prompt: str
    seed: int
    difficulty: int
    operator_rating: int
    expected_success: float
    plot: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "item_id": self.item_id,
            "item_version": self.item_version,
            "content_hash": self.content_hash,
            "procedure_id": self.procedure_id,
            "procedure_title": self.procedure_title,
            "axis": self.axis,
            "title": self.title,
            "prompt": self.prompt,
            "difficulty": self.difficulty,
            "operator_rating": self.operator_rating,
            "expected_success": round(self.expected_success, 3),
            "plot": self.plot,
        }


@dataclass(frozen=True, slots=True)
class ScoredDrill:
    """The reveal: what the operator said, what was right, and why the score is the score."""

    item_id: str
    correct: bool
    action_correct: bool
    confused_with: str | None
    points: float
    brier: float
    calibration: str
    rating_before: int
    rating_after: int
    accepted_classifications: list[str]
    accepted_first_actions: list[str]
    expert_cue: str
    procedure_id: str
    procedure_title: str
    first_step: str
    lines: list[ScoreLine]
    next_due_in_days: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "correct": self.correct,
            "action_correct": self.action_correct,
            "confused_with": self.confused_with,
            "points": self.points,
            "brier": round(self.brier, 4),
            "calibration": self.calibration,
            "rating_before": self.rating_before,
            "rating_after": self.rating_after,
            "rating_delta": self.rating_after - self.rating_before,
            "accepted_classifications": self.accepted_classifications,
            "accepted_first_actions": self.accepted_first_actions,
            "expert_cue": self.expert_cue,
            "procedure_id": self.procedure_id,
            "procedure_title": self.procedure_title,
            "first_step": self.first_step,
            "next_due_in_days": self.next_due_in_days,
            "lines": [
                {
                    "rule": line.rule,
                    "axis": line.axis,
                    "awarded": line.awarded,
                    "available": line.available,
                    "fired": line.fired,
                    "evidence": line.evidence,
                }
                for line in self.lines
            ],
        }


class DrillEngine:
    """Serves and scores drill items against loaded content and stored progress."""

    def __init__(
        self,
        *,
        content: ContentStore,
        progress: ProgressStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._content = content
        self._progress = progress
        self._clock = clock if clock is not None else now_utc

    def _items(self) -> dict[str, DrillItem]:
        """Active drill items only. A draft item never scores a run, per the content model."""
        return {
            key: item
            for key, item in self._content.active("drills").items()
            if isinstance(item, DrillItem)
        }

    def _procedure(self, item: DrillItem) -> Procedure | None:
        found = self._content.get("procedures", f"{item.procedure_id}@{item.procedure_version}")
        return found if isinstance(found, Procedure) else None

    def _instance_seed(self, operator_id: str, item_id: str, attempt: int) -> int:
        """A seed that is reproducible from the run record and different on every attempt.

        Derived rather than random: the debrief redraws the exact surface the operator saw from the
        stored seed, and a seed nobody can regenerate makes a run uninterpretable later. Attempt
        number is in the hash so a repeat of the same item is a different instantiation, which is
        the template-versus-instance split the plan requires.
        """
        material = f"{operator_id}|{item_id}|{attempt}".encode()
        return int.from_bytes(hashlib.sha256(material).digest()[:6], "big")

    def select(self, progress: OperatorProgress) -> DrillItem:
        """The next item: due first, then closest to the operator's rating.

        Ties broken by item id rather than at random, so the same state yields the same next item.
        A drill whose selection is unreproducible cannot be reasoned about when an operator says it
        keeps giving them the same thing.
        """
        items = self._items()
        if not items:
            raise DrillError(
                "no active drill items are loaded. Check the content tree loaded without errors"
            )
        now = self._clock()
        due = [item for item in items.values() if progress.cue(item.meta.id).is_due(now)]
        pool = due or list(items.values())
        return min(
            pool,
            key=lambda item: (abs(item.difficulty - progress.rating), item.meta.id),
        )

    def serve(self, *, operator_id: str) -> ServedDrill:
        """Build the next unanswered drill. The answer key is not in the return value."""
        progress = self._progress.load(operator_id)
        item = self.select(progress)
        procedure = self._procedure(item)
        attempt = sum(1 for run in progress.runs if run.item_id == item.meta.id)
        seed = self._instance_seed(operator_id, item.meta.id, attempt)
        content_hash = self._content.hash_of("drills", f"{item.meta.id}@{item.meta.version}") or ""
        plot = build_plot(
            item_id=item.meta.id,
            plot_kind=item.plot_kind,
            seed=seed,
            description=item.plot_description,
        )
        return ServedDrill(
            instance_id=f"{item.meta.id}:{attempt}",
            item_id=item.meta.id,
            item_version=item.meta.version,
            content_hash=content_hash,
            procedure_id=item.procedure_id,
            procedure_title=procedure.meta.title if procedure else item.procedure_id,
            axis=item.axis,
            title=item.meta.title,
            prompt=item.prompt,
            seed=seed,
            difficulty=item.difficulty,
            operator_rating=progress.rating,
            expected_success=expected_score(progress.rating, item.difficulty),
            plot=plot.as_dict(),
        )

    def score(
        self,
        *,
        operator_id: str,
        item_id: str,
        classification: str,
        first_action: str,
        confidence: int,
    ) -> ScoredDrill:
        """Score one answer, persist the consequences, and return the full decomposition."""
        items = self._items()
        item = items.get(f"{item_id}@v1") or next(
            (candidate for candidate in items.values() if candidate.meta.id == item_id), None
        )
        if item is None:
            raise DrillError(f"drill item {item_id!r} is not loaded or is not active")
        try:
            probability = confidence_probability(confidence)
        except ValueError as exc:
            raise DrillError(str(exc)) from None

        classification_match = answer_matching.matches(
            classification, item.accepted_classifications
        )
        action_match = answer_matching.matches(first_action, item.accepted_first_actions)
        confused = (
            None
            if classification_match
            else answer_matching.near_miss(classification, item.confusable_with)
        )
        correct = classification_match is not None

        lines, points = explain_score(
            classification_match=classification_match,
            action_match=action_match,
            confused_with=confused,
            probability=probability,
            expert_cue=item.expert_cue,
        )
        progress = self._progress.load(operator_id)
        change = update_ratings(
            operator_rating=progress.rating, item_difficulty=item.difficulty, correct=correct
        )
        brier = brier_score(probability, correct)
        now = self._clock()

        progress.rating = change.operator_after
        # Both the item's own axis and the axes the rules fired on are credited. The item's axis is
        # what it was authored to train; the rule axes are what the answer actually demonstrated,
        # and an answer that names the first action demonstrates procedure recall whatever the item
        # was authored for.
        for line in lines:
            if line.available <= 0.0 or line.axis not in AXES:
                continue
            axis = progress.axis(line.axis)
            axis.attempts += 1
            axis.correct += 1 if line.fired else 0
            axis.brier_total += brier if line.axis == "uncertainty-calibration" else 0.0
        progress.cue(item.meta.id).record(correct=correct, now=now)

        procedure = self._procedure(item)
        progress.runs.append(
            RunRecord(
                item_id=item.meta.id,
                item_version=item.meta.version,
                content_hash=self._content.hash_of("drills", f"{item.meta.id}@{item.meta.version}")
                or "",
                procedure_id=item.procedure_id,
                axis=item.axis,
                seed=self._instance_seed(
                    operator_id,
                    item.meta.id,
                    sum(1 for run in progress.runs if run.item_id == item.meta.id),
                ),
                answered_at=now.isoformat(),
                # The operator's own words are stored, capped. Needed for the debrief and for the
                # scorer-validation set the plan gates on; capped because an unbounded free-text
                # field in a file read whole on every request is a denial of service with a
                # keyboard.
                classification=classification[: answer_matching.MAX_ANSWER_LENGTH],
                first_action=first_action[: answer_matching.MAX_ANSWER_LENGTH],
                confidence=confidence,
                correct=correct,
                action_correct=action_match is not None,
                brier=brier,
                points=points,
                rating_before=change.operator_before,
                rating_after=change.operator_after,
                lines=[
                    {"rule": line.rule, "axis": line.axis, "awarded": line.awarded}
                    for line in lines
                ],
            )
        )
        self._progress.save(progress)

        return ScoredDrill(
            item_id=item.meta.id,
            correct=correct,
            action_correct=action_match is not None,
            confused_with=confused,
            points=points,
            brier=brier,
            calibration=calibration_verdict(probability, correct),
            rating_before=change.operator_before,
            rating_after=change.operator_after,
            accepted_classifications=list(item.accepted_classifications),
            accepted_first_actions=list(item.accepted_first_actions),
            expert_cue=item.expert_cue,
            procedure_id=item.procedure_id,
            procedure_title=procedure.meta.title if procedure else item.procedure_id,
            first_step=procedure.steps[0].action if procedure else "",
            lines=lines,
            next_due_in_days=max(
                0, (self._due_date(progress, item.meta.id) - now).days if progress else 0
            ),
        )

    @staticmethod
    def _due_date(progress: OperatorProgress, item_id: str) -> datetime:
        cue = progress.cue(item_id)
        return datetime.fromisoformat(cue.due_at)

    def dashboard(self, *, operator_id: str) -> dict[str, Any]:
        """Where the operator stands, what has decayed, and what is recommended next.

        Every axis reports an interval rather than a bare number, per the plan. An axis with no
        attempts reports `null` rather than zero: "not measured" and "measured at zero" are
        different facts and collapsing them is how a dashboard lies about coverage.
        """
        progress = self._progress.load(operator_id)
        items = self._items()
        now = self._clock()

        axes = []
        for name in AXES:
            axis = progress.axes.get(name)
            interval = axis.interval if axis else None
            axes.append(
                {
                    "axis": name,
                    "attempts": axis.attempts if axis else 0,
                    "accuracy": round(axis.accuracy, 3)
                    if axis and axis.accuracy is not None
                    else None,
                    "interval": [round(interval[0], 3), round(interval[1], 3)]
                    if interval
                    else None,
                    "mean_brier": round(axis.mean_brier, 4)
                    if axis and axis.mean_brier is not None
                    else None,
                }
            )

        due_now = [
            item.meta.id for item in items.values() if progress.cue(item.meta.id).is_due(now)
        ]
        procedures: dict[str, dict[str, int]] = {}
        for item in items.values():
            seen = [run for run in progress.runs if run.item_id == item.meta.id]
            bucket = procedures.setdefault(
                item.procedure_id, {"items": 0, "attempted": 0, "correct": 0}
            )
            bucket["items"] += 1
            bucket["attempted"] += 1 if seen else 0
            bucket["correct"] += 1 if any(run.correct for run in seen) else 0

        recent = progress.runs[-10:]
        return {
            "operator_id": progress.operator_id,
            "rating": progress.rating,
            "runs_total": len(progress.runs),
            "axes": axes,
            "due_now": sorted(due_now),
            "items_total": len(items),
            "coverage": [
                {
                    "procedure_id": key,
                    "items": value["items"],
                    "attempted": value["attempted"],
                    "demonstrated": value["correct"],
                }
                for key, value in sorted(procedures.items())
            ],
            "recent": [
                {
                    "item_id": run.item_id,
                    "answered_at": run.answered_at,
                    "correct": run.correct,
                    "points": run.points,
                    "confidence": run.confidence,
                    "rating_after": run.rating_after,
                }
                for run in reversed(recent)
            ],
        }
