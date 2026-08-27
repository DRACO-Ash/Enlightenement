"""Per-operator training progress, persisted as one atomic JSON file.

**This is an interim store, named as such rather than quietly shipped as the design.** The flight
plan settles persistence as "SQLite on the storage add-on volume, single file, transactional, WAL
mode". That is the right answer and it is not this. What this is: the same file-per-store,
write-to-temporary-then-rename discipline the session store already uses, behind an interface
narrow enough that the SQLite swap is one class and no caller changes.

Why interim rather than SQLite now: the dashboard and the spacing scheduler need somewhere to put
state before either is worth looking at, and a store that loses progress on restart makes the
dashboard a demonstration rather than a feature. The swap is flight plan step 10 territory,
alongside identity and the supervisor audit trail, and doing it there means doing it once with the
per-operator boundary already in place.

**Personal data notice, because this is the file that holds it.** Once a real operator identity
reaches this store, its contents are personal data under UK GDPR and the plan requires a signed
DPIA before the first named-individual record is written. Until then every caller uses a synthetic
operator id, which is why :data:`DEMONSTRATION_OPERATOR` exists and why nothing here has an
identity parameter that defaults to a real user.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from enlightenment.training.scoring import DEFAULT_OPERATOR_RATING, next_interval_days

#: The only operator id used until identity lands and the DPIA is signed. A visible synthetic
#: value rather than "default" or an empty string, so a record written under it can never be
#: mistaken for a record about a person.
DEMONSTRATION_OPERATOR: Final = "synthetic-operator"

#: Runs kept per operator. Bounded because the file is read whole on every request; the plan's
#: retention rule ("detailed run artefacts age out on a defined schedule, aggregate competence
#: persists") is the same shape, and the period itself is still TBC with Ash as Data Protection
#: Lead. This bound is an engineering cap, NOT the retention policy, and must not be cited as one.
MAX_RUN_HISTORY: Final = 200

#: The six competency axes from the flight plan. Held here as the identity of a progress bucket
#: only; the plan says the axes are revisable content, so this is not the authority on them and a
#: rubric naming an axis outside this set is a content question, not a crash.
AXES: Final[tuple[str, ...]] = (
    "cue-detection",
    "event-classification",
    "procedure-recall",
    "physical-reasoning",
    "uncertainty-calibration",
    "reporting",
)


@dataclass
class AxisProgress:
    """Attempts, hits and accumulated Brier score on one competency axis.

    Kept as raw counts rather than a pre-computed score, because the plan requires every axis to be
    reported with a confidence interval and an interval cannot be recovered from a mean. The
    interval is computed at read time from `attempts`, so changing the interval method is a code
    change and never a data migration.
    """

    attempts: int = 0
    correct: int = 0
    brier_total: float = 0.0

    @property
    def accuracy(self) -> float | None:
        """Hit rate, or None when there is nothing to divide by."""
        return self.correct / self.attempts if self.attempts else None

    @property
    def mean_brier(self) -> float | None:
        return self.brier_total / self.attempts if self.attempts else None

    @property
    def interval(self) -> tuple[float, float] | None:
        """A Wald interval on the hit rate, widened for a small sample.

        Never a bare number, which is the plan's rule for every axis. The `+ 2` in the denominator
        is an Agresti-Coull style adjustment: a plain Wald interval on three attempts out of three
        reports zero width, which is the most confident and least true thing this could say.
        """
        if not self.attempts:
            return None
        n = self.attempts + 2.0
        p = (self.correct + 1.0) / n
        margin = 1.96 * (p * (1.0 - p) / n) ** 0.5
        return (max(0.0, p - margin), min(1.0, p + margin))


@dataclass
class CueSchedule:
    """When one drill item comes back, and how many consecutive hits it has.

    Keyed per item rather than per axis, because the plan re-injects a missed CUE CLASS and the
    item is the finest grain available at drill level. A miss resets the streak to zero, which
    `next_interval_days` turns into the front interval.
    """

    streak: int = 0
    due_at: str = ""

    def record(self, *, correct: bool, now: datetime) -> None:
        self.streak = self.streak + 1 if correct else 0
        days = next_interval_days(streak=self.streak, correct=correct)
        self.due_at = (now + timedelta(days=days)).isoformat()

    def is_due(self, now: datetime) -> bool:
        """An item with no recorded due date has never been seen, so it is due."""
        if not self.due_at:
            return True
        try:
            return datetime.fromisoformat(self.due_at) <= now
        except ValueError:
            # A malformed stored date is treated as due rather than as a crash. The alternative is
            # a corrupt field taking the whole drill offline, and "show the operator an item" is
            # the safe direction to fail in for a value that only schedules.
            return True


@dataclass
class RunRecord:
    """One completed drill answer, kept so a debrief months later is still interpretable.

    Carries the content version hashes it was scored under, per the plan: "every run records the
    exact content version hash it was scored under". A run whose content has since changed is
    therefore still readable against what it actually faced.
    """

    item_id: str
    item_version: str
    content_hash: str
    procedure_id: str
    axis: str
    seed: int
    answered_at: str
    classification: str
    first_action: str
    confidence: int
    correct: bool
    action_correct: bool
    brier: float
    points: float
    rating_before: int
    rating_after: int
    lines: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class OperatorProgress:
    """Everything the dashboard and the scheduler need for one operator."""

    operator_id: str
    rating: int = DEFAULT_OPERATOR_RATING
    axes: dict[str, AxisProgress] = field(default_factory=dict)
    schedule: dict[str, CueSchedule] = field(default_factory=dict)
    runs: list[RunRecord] = field(default_factory=list)

    def axis(self, name: str) -> AxisProgress:
        return self.axes.setdefault(name, AxisProgress())

    def cue(self, item_id: str) -> CueSchedule:
        return self.schedule.setdefault(item_id, CueSchedule())


class ProgressStore:
    """One JSON file, read whole and written atomically.

    Read-whole is honest at this size: ten concurrent operators is the plan's stated target and the
    file is a few kilobytes per operator. It is also exactly the property that makes the SQLite
    swap worth doing rather than optimising this.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def _read(self) -> dict[str, Any]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError:
            # A store that cannot be read yields an empty store rather than a 500. Progress is
            # valuable but it is not the training loop; an operator can still drill.
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def load(self, operator_id: str) -> OperatorProgress:
        """Progress for one operator, or a fresh record. Never raises on bad stored data.

        Every field is rebuilt through its dataclass with a type check, so a hand-edited or
        truncated file degrades to defaults for the fields it broke instead of taking down the
        request. The alternative, trusting the file's shape, turns one bad write into an outage.
        """
        blob = self._read().get(operator_id)
        if not isinstance(blob, dict):
            return OperatorProgress(operator_id=operator_id)

        rating = blob.get("rating")
        progress = OperatorProgress(
            operator_id=operator_id,
            rating=rating if isinstance(rating, int) else DEFAULT_OPERATOR_RATING,
        )
        for name, values in (blob.get("axes") or {}).items():
            if isinstance(values, dict):
                progress.axes[str(name)] = AxisProgress(
                    attempts=int(values.get("attempts", 0) or 0),
                    correct=int(values.get("correct", 0) or 0),
                    brier_total=float(values.get("brier_total", 0.0) or 0.0),
                )
        for name, values in (blob.get("schedule") or {}).items():
            if isinstance(values, dict):
                progress.schedule[str(name)] = CueSchedule(
                    streak=int(values.get("streak", 0) or 0),
                    due_at=str(values.get("due_at", "") or ""),
                )
        for values in blob.get("runs") or []:
            if isinstance(values, dict):
                try:
                    progress.runs.append(RunRecord(**values))
                except TypeError:
                    # A run written by an older or newer shape is skipped, not fatal. Losing one
                    # history row is a smaller cost than refusing to serve the dashboard.
                    continue
        return progress

    def save(self, progress: OperatorProgress) -> None:
        """Write one operator's progress, preserving every other operator's.

        Read-modify-write on the whole file, and the read is the merge: writing only this
        operator's record would drop the others, which is the anti-shrink rule the data layer
        standard states for exactly this shape of store.
        """
        blob = self._read()
        progress.runs = progress.runs[-MAX_RUN_HISTORY:]
        blob[progress.operator_id] = {
            "rating": progress.rating,
            "axes": {name: asdict(value) for name, value in progress.axes.items()},
            "schedule": {name: asdict(value) for name, value in progress.schedule.items()},
            "runs": [asdict(run) for run in progress.runs],
        }
        self._write_atomic(blob)

    def _write_atomic(self, blob: dict[str, Any]) -> None:
        """Temporary sibling, fsync, rename. A crash leaves the previous file intact.

        Mode 0o600 comes from `os.open` through `mkstemp`, which is what `tempfile` already does,
        so the file is never briefly world-readable. That matters here specifically: this is the
        file that will hold personal performance data.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".progress-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(blob, handle, indent=1, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary).replace(self._path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise


def now_utc() -> datetime:
    """One clock, injectable at the engine boundary rather than called all over the module."""
    return datetime.now(UTC)
