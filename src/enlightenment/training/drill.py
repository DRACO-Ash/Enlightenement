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
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from enlightenment.content import ContentPackage, Drill
from enlightenment.generators import GeneratorRegistry, compose
from enlightenment.scoring import UNSCORABLE, Facts, Match, RubricEvaluator, match
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

#: How long a served drill stays answerable, seconds, and how many may be held at once. Both are
#: bounds on an UNAUTHENTICATED route: every serve inserts an entry, so without them the map is a
#: memory-exhaustion surface. Twenty minutes is generous against the longest authored time target
#: in the library and short enough that an abandoned run does not accumulate.
PENDING_TTL_SECONDS: Final = 20 * 60
MAX_PENDING: Final = 512

#: Longest content-supplied item version stored on a run row. See `_bounded`.
MAX_ITEM_VERSION: Final = 64


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
    brier: float | None
    calibration: str
    rating_before: int | None
    rating_after: int | None
    next_due_in_days: int | None
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
            "brier": None if self.brier is None else round(self.brier, 4),
            "calibration": self.calibration,
            "rating_delta": (
                None
                if self.rating_after is None or self.rating_before is None
                else self.rating_after - self.rating_before
            ),
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


def _bounded(value: Any) -> str:
    """A content-supplied string, length-capped before it is written to the progress file.

    `extra="allow"` carries fields the engine does not model, which is the deliberate reversal
    that let the package load unedited. The residual is length: a 5000-character `version` was
    stored verbatim on every run row, and the progress file is read whole on every request.
    """
    text = str(value or "")
    return text[:MAX_ITEM_VERSION] if len(text) > MAX_ITEM_VERSION else text


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
        self._pending: OrderedDict[str, _Pending] = OrderedDict()

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

    @property
    def pending(self) -> Mapping[str, _Pending]:
        """The served drills still awaiting a submission. Read-only, and for diagnostics.

        A mapping view rather than the dictionary itself, so a caller can count and inspect but
        cannot insert: the bounds in `_evict` are the whole point of this collection and a caller
        that could add to it directly would be outside them.
        """
        return MappingProxyType(self._pending)

    def serve(self, *, operator_id: str, item_id: str | None = None) -> ServedDrill:
        """Serve the next drill, or a named one.

        `item_id` bypasses selection. It exists for a debrief redrawing a specific run and for
        tests that must reach a specific item; selection is due-and-rating driven, so a test
        that needs one particular item cannot get there by asking repeatedly.
        """
        if not self.ready:
            raise DrillError("the content package is not loaded")
        progress = self._progress.load(operator_id)
        item = self.select(progress) if item_id is None else self._named(item_id)
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
        self._evict()
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

    def _evict(self) -> None:
        """Bound the served-drill map, by age first and then by count.

        It was unbounded, and `GET /api/v1/drill/next` is unauthenticated: 4000 serves retained
        4000 entries and nothing ever removed one, so a few source addresses reached a
        container-sized heap within the hour and the outcome was an out-of-memory kill. That is
        availability loss on the very thing the split health probes exist to protect. Every other
        collection in this project is capped - sessions, run history, limiter keys - so this was
        the odd one out rather than a new principle.

        The message the caller already receives says a run "is unknown or has expired". Until
        this method existed, that expiry was advertised and not implemented.
        """
        cutoff = now_utc() - timedelta(seconds=PENDING_TTL_SECONDS)
        for run_id in [k for k, v in self._pending.items() if v.served_at < cutoff]:
            del self._pending[run_id]
        while len(self._pending) > MAX_PENDING:
            #: Oldest first. A drill served two hundred serves ago is the one least likely to be
            #: answered, and the newest must survive because it is the one on screen.
            self._pending.popitem(last=False)

    def score(
        self, *, run_id: str, response: str, confidence: int, elapsed_ms: int, operator_id: str
    ) -> ScoredDrill:
        """Score one submission. Idempotent: a second call returns the first result."""
        pending = self._pending.get(run_id)
        if pending is None:
            raise DrillError("that drill run is unknown or has expired")
        if pending.result is not None:
            return pending.result

        #: **The server's own clock decides the speed bonus, not the client's.** `elapsed_ms`
        #: arrives in the submission body, and a client posting `elapsed_ms: 0` collected
        #: `D-FAST-AND-CORRECT` every time. `served_at` was already recorded and read nowhere.
        #: The client figure is kept only as telemetry, and the smaller of the two is used so a
        #: slow network cannot cost an operator a bonus they earned.
        measured_ms = int((now_utc() - pending.served_at).total_seconds() * 1000)
        elapsed = min(measured_ms, elapsed_ms) if elapsed_ms > 0 else measured_ms

        item = pending.drill
        outcome = match(response, item.answer, item.response_format, pending.derived)
        result = self._record(item, outcome, confidence, elapsed, operator_id, run_id)
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
        if outcome.matched == UNSCORABLE:
            #: **An unscorable item must not mark an operator.** The matcher refuses when a
            #: `computed_from_params` answer has no value behind it, which is right; the loop
            #: then scored the refusal as WRONG, dropped the rating six points, reset the cue
            #: schedule as a miss and wrote a run row. Marking somebody against a question nobody
            #: could answer is worse than not serving it, and it was silent: the operator saw the
            #: note and the rating move and had no way to tell which caused which.
            return self._unscored(item, outcome, run_id)
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
                item_version=_bounded(item.model_extra.get("version") if item.model_extra else ""),
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

    def _unscored(self, item: Drill, outcome: Match, run_id: str) -> ScoredDrill:
        """A result that teaches and records nothing: no rating, no schedule, no history row.

        The reveal still carries the item's own explanation, because an operator who has thought
        about the question has earned the answer whether or not the service could mark it.
        """
        return ScoredDrill(
            run_id=run_id,
            item_id=item.id,
            matched=outcome.matched,
            correct=False,
            credit=0.0,
            explain=item.explain,
            note=outcome.note,
            why_wrong=outcome.why_wrong,
            brier=None,
            calibration="not assessed: this item could not be scored",
            rating_before=None,
            rating_after=None,
            next_due_in_days=None,
            score_components=(),
            total=0.0,
            unimplemented_rules=(),
            content_hash=self._content.content_hash,
        )

    def _named(self, item_id: str) -> Drill:
        """One drill by id, refused rather than substituted if the library does not have it."""
        item = self._content.drill(item_id)
        if item is None:
            raise DrillError(f"no drill {item_id!r} in the loaded content package")
        return item

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
            "rubric_rules_unwired": self._unwired_rules(),
            "stimulus_params_unread": self._unread_params(),
        }

    def _unwired_rules(self) -> int:
        """How many rubric rules have no predicate. The count belongs in the product, not only
        in a commit message: 61 of 67 rules are prose `when` clauses the evaluator cannot
        evaluate, and until this field existed no HTTP surface said so."""
        return sum(
            1
            for rubric in self._content.rubrics
            for rule in rubric.rules
            if rule.id not in self._evaluator.implemented
        )

    def _unread_params(self) -> dict[str, Any]:
        """Authored stimulus parameters no renderer honours, counted and named.

        The realism gap, made countable. A renderer that ignores `beta_departs` draws a plot
        that contradicts its own answer key, and the only reason that shipped is that nothing
        counted it. `drills_fully_expressed` is the number to watch: it rises as renderers learn
        the content's vocabulary, and it is a content-and-code agreement rather than a score.
        """
        names: dict[str, int] = {}
        expressed = 0
        for drill in self._content.drills:
            unread = self._registry.unread(drill.stimulus.generator, drill.stimulus.params)
            if not unread:
                expressed += 1
            for key in unread:
                names[key] = names.get(key, 0) + 1
        return {
            "drills_fully_expressed": expressed,
            "drills_total": len(self._content.drills),
            "params": dict(sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))[:25]),
        }
