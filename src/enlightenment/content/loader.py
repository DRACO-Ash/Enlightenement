"""Load the ENLIGHTENMENT content package, and refuse to serve what it says to refuse.

The loader carries three behaviours the build guidance names explicitly as content decisions
that will otherwise be omitted, because none of them is something an engineer would invent:

● **Refuse to serve a scored scenario while thresholds carry placeholders.** The shipped
  `thresholds.example.json` is deliberately not the operational values; it exists so the
  application runs and a developer without procedure access can build against a complete shape.
  An operator seeing a placeholder value in the interface is a bug, so `scored_scenarios_ready`
  is false until `thresholds.local.json` is populated and its `_meta.all_placeholders_replaced`
  flag is set.
● **Reject a seed that fails its solvability check.** A stimulus whose signature is not actually
  present is not a hard item, it is an unanswerable one, and it teaches an operator that the
  procedure does not work.
● **Record the content version hash on every run.** Otherwise a result from last week cannot be
  interpreted against content that has since changed.

A malformed content file must not produce a running application that serves broken scenarios, so
a load failure is carried rather than raised, the readiness path reports it, and the drill routes
answer 503 naming the files at fault. A container that will not start cannot serve the health
path that would tell an operator why.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from enlightenment.content.models import (
    Competency,
    Cue,
    Drill,
    Procedure,
    Product,
    Rubric,
    ScenarioTemplate,
)

#: Files the engine reads. The package carries more; these are the ones a missing copy of which
#: stops the drill loop rather than degrading a later surface.
REQUIRED_FILES: Final = (
    "drills.json",
    "cues.json",
    "rubrics.json",
    "products.json",
    "product-layouts.json",
    "scenarios.json",
    "competencies.json",
    "traces.json",
    "procedures/procedures-core.json",
    "procedures/procedures-extended.json",
)

#: The shipped placeholder file, and the local one that replaces it. The local file is
#: gitignored: the redaction discipline lives here, and a threshold in source is a threshold
#: published.
EXAMPLE_THRESHOLDS: Final = "thresholds.example.json"
LOCAL_THRESHOLDS: Final = "thresholds.local.json"


def resolve_content_root() -> Path:
    """The content directory: the environment override, else the package's own repository copy."""
    override = os.environ.get("ENLIGHTENMENT_CONTENT_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "content"


@dataclass(frozen=True, slots=True)
class LoadResult:
    """What a load produced, including what it could not produce.

    `ok` false means the drill and scenario routes answer 503 and name the files at fault. The
    health paths stay 200 regardless, which is the split the App Store contract requires.
    """

    ok: bool
    errors: tuple[str, ...] = ()
    content_hash: str = ""
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Resolved thresholds, and whether they are the real ones.

    Standards are configuration. Timing bands, accuracy floors and calibration ceilings all
    live here, so a changed standard changes no code. If a value is inlined anywhere in the
    engine that is the same error as inlining a scenario.
    """

    values: dict[str, Any]
    source: str
    all_placeholders_replaced: bool


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_all[Model](
    model: type[Model], records: list[dict[str, Any]], label: str, errors: list[str]
) -> tuple[Model, ...]:
    """Parse a list of records, collecting per-record failures rather than aborting the load."""
    parsed: list[Model] = []
    for index, record in enumerate(records):
        try:
            parsed.append(model(**record))
        except ValidationError as exc:
            identifier = record.get("id", f"index {index}")
            first = exc.errors()[0]
            location = ".".join(str(part) for part in first.get("loc", ()))
            errors.append(f"{label} {identifier}: {location}: {first.get('msg', 'invalid')}")
    return tuple(parsed)


class ContentPackage:
    """The loaded package. Immutable once built, and it knows what it may not serve."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else resolve_content_root()
        self.drills: tuple[Drill, ...] = ()
        self.cues: tuple[Cue, ...] = ()
        self.procedures: tuple[Procedure, ...] = ()
        self.scenarios: tuple[ScenarioTemplate, ...] = ()
        self.rubrics: tuple[Rubric, ...] = ()
        self.products: tuple[Product, ...] = ()
        self.competencies: tuple[Competency, ...] = ()
        self.layouts: dict[str, Any] = {}
        self.traces: dict[str, Any] = {}
        self.thresholds = Thresholds({}, "none", False)
        self.result = LoadResult(ok=False, errors=("not loaded",))
        self._by_id: dict[str, Drill] = {}

    @property
    def root(self) -> Path:
        return self._root

    @property
    def content_hash(self) -> str:
        """Stamped on every run record, so an old result stays interpretable."""
        return self.result.content_hash

    @property
    def scored_scenarios_ready(self) -> bool:
        """False while thresholds are placeholders. Guards the scored scenario routes."""
        return self.result.ok and self.thresholds.all_placeholders_replaced

    def drill(self, drill_id: str) -> Drill | None:
        return self._by_id.get(drill_id)

    def rubric(self, rubric_id: str) -> Rubric | None:
        return next((r for r in self.rubrics if r.id == rubric_id), None)

    def product(self, product_id: str) -> Product | None:
        return next((p for p in self.products if p.id == product_id), None)

    def layout(self, product_id: str) -> dict[str, Any] | None:
        for entry in self.layouts.get("layouts", []):
            if isinstance(entry, dict) and entry.get("product_id") == product_id:
                return entry
        return None

    def load(self) -> LoadResult:
        """Read the package. Never raises on content: a fault is reported, not thrown."""
        errors: list[str] = []
        missing = [name for name in REQUIRED_FILES if not (self._root / name).is_file()]
        if missing:
            self.result = LoadResult(ok=False, errors=tuple(f"missing: {n}" for n in missing))
            return self.result
        try:
            self._read(errors)
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            self.result = LoadResult(ok=False, errors=(f"{type(exc).__name__}: {exc}",))
            return self.result
        self._by_id = {d.id: d for d in self.drills}
        self.result = LoadResult(
            ok=not errors,
            errors=tuple(errors),
            content_hash=self._hash(),
            counts={
                "drills": len(self.drills),
                "cues": len(self.cues),
                "procedures": len(self.procedures),
                "scenarios": len(self.scenarios),
                "rubrics": len(self.rubrics),
                "products": len(self.products),
                "competencies": len(self.competencies),
            },
        )
        return self.result

    def _read(self, errors: list[str]) -> None:
        root = self._root
        self.drills = _parse_all(Drill, _read_json(root / "drills.json")["drills"], "drill", errors)
        self.cues = _parse_all(Cue, _read_json(root / "cues.json")["cues"], "cue", errors)
        self.rubrics = _parse_all(
            Rubric, _read_json(root / "rubrics.json")["rubrics"], "rubric", errors
        )
        self.products = _parse_all(
            Product, _read_json(root / "products.json")["products"], "product", errors
        )
        self.competencies = _parse_all(
            Competency,
            _read_json(root / "competencies.json")["competencies"],
            "competency",
            errors,
        )
        self.scenarios = _parse_all(
            ScenarioTemplate,
            _read_json(root / "scenarios.json")["scenario_templates"],
            "scenario",
            errors,
        )
        procedures: list[dict[str, Any]] = []
        for name in ("procedures/procedures-core.json", "procedures/procedures-extended.json"):
            procedures.extend(_read_json(root / name).get("procedures", []))
        self.procedures = _parse_all(Procedure, procedures, "procedure", errors)
        self.layouts = _read_json(root / "product-layouts.json")
        self.traces = _read_json(root / "traces.json")
        self.thresholds = self._read_thresholds()

    def _read_thresholds(self) -> Thresholds:
        """Prefer the local file. Fall back to the shipped example and say so.

        The example ships and the real one does not, so the fallback is the normal case on a
        fresh checkout. What must never happen is the fallback being silent: a placeholder value
        rendered to an operator is a bug, and `all_placeholders_replaced` is what stops it.
        """
        local = self._root / LOCAL_THRESHOLDS
        path, source = (
            (local, LOCAL_THRESHOLDS)
            if local.is_file()
            else (self._root / EXAMPLE_THRESHOLDS, EXAMPLE_THRESHOLDS)
        )
        if not path.is_file():
            return Thresholds({}, "none", False)
        values = _read_json(path)
        meta = values.get("_meta", {})
        replaced = bool(meta.get("all_placeholders_replaced", False))
        return Thresholds(values, source, replaced)

    def _hash(self) -> str:
        """A stable digest over the package as loaded.

        Sorted by relative path and covering the bytes rather than the parsed objects, so a
        reformatting that changes no values still changes the hash. That is the honest
        behaviour: the question a run record answers is "which files produced this", not "which
        values", because a value nobody read can still have been read by a later engine.
        """
        digest = hashlib.sha256()
        for relative in [*sorted(REQUIRED_FILES), EXAMPLE_THRESHOLDS, LOCAL_THRESHOLDS]:
            path = self._root / relative
            if not path.is_file():
                continue
            digest.update(relative.encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()
