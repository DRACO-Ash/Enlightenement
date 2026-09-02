"""Load the ENLIGHTENMENT content package, and refuse to serve what it says to refuse.

The loader carries three behaviours the build guidance names explicitly as content decisions
that will otherwise be omitted, because none of them is something an engineer would invent:

● **Refuse to serve a scored scenario while thresholds carry placeholders.** The shipped
  `thresholds.example.json` is deliberately not the operational values; it exists so the
  application runs and a developer without procedure access can build against a complete shape.
  An operator seeing a placeholder value in the interface is a bug, so `scored_scenarios_ready`
  is false until `thresholds.local.json` is populated and its `_meta.all_placeholders_replaced`
  flag is set.
● **Report a content fault rather than raising it.** A malformed or misshapen file is carried in
  `LoadResult.errors`, so the container starts and the health paths answer while the drill routes
  return 503 naming the files at fault.

**A NAMED GAP, not a behaviour: there is no solvability check.** This docstring claimed one -
"reject a seed that fails its solvability check" - and no such check has ever existed here. The
claim was not harmless: the item it describes is exactly the fault that shipped in V0.24.0, where
renderers ignored the authored scene and drew a stimulus whose signature was not present, and
DRL-0034 drew the OPPOSITE of its own answer key. What exists instead, and is honest about its
scope, is `GeneratorRegistry.unread` plus the agreement table in `tests/test_generators.py`: the
first counts authored parameters no renderer honours, the second fails the loop when a rendered
surface contradicts its own key. Neither is a general solvability proof.
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
from enlightenment.identifiers import served_identifier

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
#: The ONE environment variable naming the content tree. Read here and in the route module, set
#: nowhere in the Dockerfile: platform injection wins, the same rule this project holds for
#: `PORT` and `DATA_DIR`.
CONTENT_DIR_VARIABLE: Final = "CONTENT_DIR"

EXAMPLE_THRESHOLDS: Final = "thresholds.example.json"
LOCAL_THRESHOLDS: Final = "thresholds.local.json"


def resolve_content_root() -> Path:
    """The content directory: the `CONTENT_DIR` override, else the package's own repository copy.

    ONE environment name. This read `ENLIGHTENMENT_CONTENT_DIR` while the server read
    `CONTENT_DIR`, so an operator who set the former got the baked-in tree served over HTTP while
    the validator checked a different one: loop leg 2 could pass green against content the server
    never loads. Two names for one knob is a name too many.
    """
    override = os.environ.get(CONTENT_DIR_VARIABLE, "").strip()
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


class ContentShapeError(ValueError):
    """A content file whose TOP LEVEL is not a JSON object.

    Its own class because it must be caught with the other content faults and reported, never
    escape as an `AttributeError` from a `.get` three call sites away. That is what happened: a
    `procedures-core.json` or a `thresholds.local.json` shaped as an array raised
    `'list' object has no attribute 'get'` out of `_read`, past a handler that did not name
    `AttributeError`, and out of `create_app` itself - so the container never started and NO
    health path answered. The realistic trigger is not hostile content but a typo in
    `thresholds.local.json`, the one file an operator writes by hand, and the outcome was a crash
    loop instead of the 503 with a resolved directory and an errno that this project's health
    contract exists to produce.
    """


def _read_json(path: Path) -> dict[str, Any]:
    """Read one content file, asserting the shape and the ENCODABILITY every caller then assumes.

    Every call site subscripts or calls `.get` on the result. Checking here means one check
    rather than six, and a fault that is reported through `LoadResult` like every other.

    **A lone surrogate is rejected here, at the boundary, because it fail-OPENED four routes.**
    `"\\ud800"` is legal JSON and `json.loads` returns a `str` holding a code point that
    `str.encode("utf-8")` refuses. Nothing downstream expected that: measured, three drills whose
    ids carried one produced a **500 on the anonymous `/api/v1/me`**, and a surrogate in an
    unvalidated prose leaf of a procedure produced a **500 on the anonymous
    `/api/v1/content/procedure/{id}`** through pydantic's own serialiser, which raises while
    rendering the response. A traceback on an unauthenticated route from authored data breaks two
    rules at once: every untrusted value is validated at the boundary, and a control that cannot
    be verified is treated as failed.

    Sanitising at each serve site was the wrong shape and was tried first - the identifier path
    was fixed and the 500 simply moved to the next unvalidated field, because a per-field defence
    holds the fields somebody thought of. This is the ONE place content enters the process, so
    this is where the check belongs, and the whole tree fails closed to the documented
    `content_unavailable` 503 rather than one route crashing.

    The offending value is NOT named, per the boundary rule this project holds everywhere: the
    message gives the file, the count and the JSON pointer to the first instance, which is what an
    author needs to find it.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ContentShapeError(
            f"{path.name}: expected a JSON object at the top level, found {type(document).__name__}"
        )
    if surrogates := _unencodable_strings(document):
        where, total = surrogates
        raise ContentShapeError(
            f"{path.name}: {total} string(s) carry a lone surrogate, which is legal JSON and"
            f" cannot be encoded as UTF-8 or served; one is at {where}"
        )
    return document


def _unencodable_strings(node: Any, pointer: str = "") -> tuple[str, int] | None:
    """A JSON pointer to ONE string that cannot be encoded as UTF-8, and how many there are.

    A separate walk rather than a try around `json.dumps`, because the diagnosis an author needs is
    WHERE, and a serialiser exception gives a character position in a rendering they never saw.

    "One" rather than "the first": this walks with an explicit stack, so the pointer returned is
    the first the traversal reaches and not the first in document order. Stated because the
    message is what an author acts on, and an ordering claim the code does not make is the kind of
    small false precision this project has had to correct in prose four times.
    """
    first: str | None = None
    total = 0
    stack: list[tuple[Any, str]] = [(node, pointer)]
    while stack:
        current, where = stack.pop()
        if isinstance(current, str):
            try:
                current.encode("utf-8")
            except UnicodeEncodeError:
                total += 1
                first = where or "/" if first is None else first
        elif isinstance(current, dict):
            stack.extend((value, f"{where}/{key}") for key, value in current.items())
        elif isinstance(current, list):
            stack.extend((value, f"{where}/{index}") for index, value in enumerate(current))
    return (first, total) if first is not None else None


def _parse_all[Model](
    model: type[Model], records: list[dict[str, Any]], label: str, errors: list[str]
) -> tuple[Model, ...]:
    """Parse a list of records, collecting per-record failures rather than aborting the load."""
    parsed: list[Model] = []
    for index, record in enumerate(records):
        try:
            parsed.append(model(**record))
        except ValidationError as exc:
            #: SHORTENED BEFORE COMPOSING. The composite is cut at 256 on two anonymous surfaces,
            #: so a raw id longer than that ate the whole message: two distinct authored ids served
            #: one identical string, naming neither, with `location` and `msg` - the only actionable
            #: part - truncated away. Verbatim the fault `training/drill.py` documents and fixed at
            #: `_serve_one`, one module along, which is why the function now lives in
            #: `enlightenment.identifiers` where every layer can reach it.
            identifier = served_identifier(str(record.get("id", f"index {index}")))
            first = exc.errors()[0]
            location = ".".join(str(part) for part in first.get("loc", ()))
            errors.append(f"{label} {identifier}: {location}: {first.get('msg', 'invalid')}")
    return tuple(parsed)


class ContentPackage:
    """The loaded package. Immutable once built, and it knows what it may not serve."""

    def __init__(self, root: Path | str | None = None) -> None:
        #: Coerced, not assumed. A string root raised `TypeError` from the `/` operator three
        #: methods later, which is neither the module's stated contract ("never raises on
        #: content") nor a fault the caller could read.
        self._root = Path(root) if root is not None else resolve_content_root()
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
        layouts = self.layouts.get("layouts", []) if isinstance(self.layouts, dict) else []
        for entry in layouts if isinstance(layouts, list) else []:
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
        except (
            OSError,
            KeyError,
            TypeError,
            AttributeError,
            RecursionError,
            #: `ValueError` covers `json.JSONDecodeError` AND `UnicodeDecodeError`, and naming
            #: only the first left the second escaping `create_app`, so the container did not
            #: start and no health path answered. The trigger is not exotic: CLAUDE.md records
            #: that the owner's workstation is Windows PowerShell, whose `Out-File` and `>`
            #: write UTF-16LE by default, and `thresholds.local.json` is the one content file an
            #: operator writes by hand. The documented workflow produced the crash loop.
            #: `RecursionError` is the same fault at depth: `json.loads` raises it on a deeply
            #: nested document, and it is not a `ValueError`.
            ValueError,
        ) as exc:
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
        #: `_meta` as a scalar took the container down the same way the file shape did. A
        #: malformed marker means the placeholders are NOT known to be replaced, which is the
        #: fail-closed reading: it withholds scored scenarios rather than serving placeholders.
        replaced = (
            bool(meta.get("all_placeholders_replaced", False)) if isinstance(meta, dict) else False
        )
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
