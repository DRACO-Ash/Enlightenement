"""Load the content tree, validate it, hash it, and fail SAFELY on a malformed file.

"Safe failure" is the plan's word and it means something specific: a malformed file is rejected
with an author-facing error and never serves a broken scenario. So a load either yields a store
whose every item validated, or it yields the errors and NO store. There is no partial store, because
a partially loaded procedure library is a library that silently scores against the rules that
happened to parse.

Hot reload follows from the same rule: :meth:`ContentStore.reload` swaps the whole tree atomically
or keeps the previous one. A reload that fails leaves the running application serving the last good
content, which is the only behaviour that does not turn an authoring typo into an outage.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ValidationError

from enlightenment.content.models import (
    CATALOGUE_NUMBER_PATTERN,
    ContentStatus,
    ExpertTrace,
    Procedure,
    Rubric,
    ScenarioTemplate,
)

#: Sub-directory per content kind, and the model each holds. The directory name IS the kind, so
#: adding a kind is one entry here rather than a branch in the loader.
CONTENT_KINDS: Final[dict[str, type[BaseModel]]] = {
    "procedures": Procedure,
    "scenarios": ScenarioTemplate,
    "rubrics": Rubric,
    "traces": ExpertTrace,
}

#: Patterns the redaction gate refuses anywhere in an authored file. Each is the mechanical half of
#: a prohibition the plan states in prose; the human reviewer is the other half and is not replaced
#: by this.
_REDACTION_RULES: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "catalogue-number",
        CATALOGUE_NUMBER_PATTERN,
        "a bare 5-to-8 digit run, which is the shape of a satellite catalogue number. The content"
        " tree never holds a real protected-object identifier; describe the class of object or use"
        " a clearly synthetic designator",
    ),
    (
        "url",
        r"\b[a-z][a-z0-9+.-]*://\S+",
        "a URL. An internal tool click-path or endpoint does not belong in training content;"
        " describe the action rather than the address",
    ),
    (
        "windows-path",
        r"(?:\b[A-Za-z]:\\|\\\\)[^\s\"']+",
        "a Windows or UNC path, which is a click-path by another name; describe the action",
    ),
    (
        "chat-channel",
        r"(?<![\w#])#[a-z0-9][a-z0-9._-]{2,}\b",
        "something shaped like a chat channel. Channel and product naming conventions are"
        " OPSEC-relevant and are generalised, never named",
    ),
)

_REDACTION_COMPILED: Final[tuple[tuple[str, re.Pattern[str], str], ...]] = tuple(
    (name, re.compile(pattern), why) for name, pattern, why in _REDACTION_RULES
)


class ContentError(Exception):
    """A content file is unusable. Carries the author-facing detail, never a stack trace."""


class RedactionError(ContentError):
    """A content file holds something the redaction discipline forbids.

    A distinct type from :class:`ContentError` because the two need different handling: a schema
    error is an authoring mistake, and a redaction hit is a disclosure risk that must be reported
    without echoing the offending text.
    """


@dataclass(frozen=True, slots=True)
class ContentLoadResult:
    """What one load attempt produced: either every item, or every error.

    Both lists are always present and exactly one is empty on a decided outcome, which makes the
    caller's branch a truth about the load rather than a guess about which field to read.
    """

    items: dict[str, dict[str, BaseModel]] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    hashes: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when nothing failed. An empty tree is a valid, if useless, load."""
        return not self.errors


def content_hash(payload: object) -> str:
    """The content version hash a run records, over the CANONICAL form of the payload.

    Canonical means sorted keys and no insignificant whitespace, so reformatting an authored file
    does not change the hash of what it says. A hash over the raw bytes would make every
    reindentation look like a content change and every run's recorded hash unreproducible from the
    file a reader is looking at.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def json_schemas() -> dict[str, dict[str, Any]]:
    """JSON Schema for each content kind, generated from the models the loader enforces.

    Emitted so an author can validate a file in an editor or a pre-commit hook against exactly the
    schema the loader will apply. Generated rather than hand-written for the obvious reason: a
    hand-written copy is a second definition, and a second definition drifts.
    """
    return {kind: model.model_json_schema() for kind, model in CONTENT_KINDS.items()}


def _redaction_findings(text: str) -> Iterator[str]:
    """Names of the redaction rules this text trips. Never yields the matched text itself."""
    for name, pattern, why in _REDACTION_COMPILED:
        if pattern.search(text):
            yield f"{name}: {why}"


def _validate_step_ordinals(procedure: Procedure) -> str | None:
    """Ordinals must be a contiguous run from one, or a step is unreachable or duplicated."""
    ordinals = [step.ordinal for step in procedure.steps]
    expected = list(range(1, len(ordinals) + 1))
    if sorted(ordinals) != expected:
        return (
            f"step ordinals are {sorted(ordinals)}, expected a contiguous run {expected}."
            " A gap or a duplicate means a step is unreachable or ambiguous"
        )
    return None


class ContentStore:
    """The loaded content tree, reloadable without dropping the last good version.

    Construction does NOT load: :meth:`reload` does, and returns its result, so a caller decides
    what to do about a failure rather than catching an exception from a constructor. The application
    can therefore start with an empty store and report itself unready, which is the same
    fail-closed posture the storage probe uses.
    """

    __slots__ = ("_hashes", "_items", "_root")

    def __init__(self, root: Path) -> None:
        self._root = root
        self._items: dict[str, dict[str, BaseModel]] = {kind: {} for kind in CONTENT_KINDS}
        self._hashes: dict[str, str] = {}

    @property
    def root(self) -> Path:
        """The directory this store loads from."""
        return self._root

    def hash_of(self, kind: str, key: str) -> str | None:
        """The content version hash of one loaded item, for a run to record."""
        return self._hashes.get(f"{kind}/{key}")

    def get(self, kind: str, key: str) -> BaseModel | None:
        """One loaded item by kind and `id@version` key, or None."""
        return self._items.get(kind, {}).get(key)

    def all_of(self, kind: str) -> dict[str, BaseModel]:
        """Every loaded item of one kind, keyed `id@version`. A copy: the store stays immutable."""
        return dict(self._items.get(kind, {}))

    def active(self, kind: str) -> dict[str, BaseModel]:
        """Only items whose status is ACTIVE. A draft never scores a run."""
        return {
            key: item
            for key, item in self._items.get(kind, {}).items()
            if getattr(item, "meta", None) is not None and item.meta.status is ContentStatus.ACTIVE  # type: ignore[attr-defined]
        }

    def reload(self) -> ContentLoadResult:
        """Re-read the tree. Swap it in only if EVERY file validated.

        The atomicity is the point. A reload that half-succeeded would leave the library in a state
        no author intended and no test covers, so a failed reload changes nothing and the caller
        keeps serving the previous content.
        """
        result = self._read_tree()
        if result.ok:
            self._items = result.items
            self._hashes = result.hashes
        return result

    def _read_tree(self) -> ContentLoadResult:
        items: dict[str, dict[str, BaseModel]] = {kind: {} for kind in CONTENT_KINDS}
        hashes: dict[str, str] = {}
        errors: list[str] = []

        for kind, model in CONTENT_KINDS.items():
            directory = self._root / kind
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                try:
                    item, key, digest = self._read_file(path, model)
                except ContentError as exc:
                    errors.append(str(exc))
                    continue
                if key in items[kind]:
                    errors.append(
                        f"{kind}/{path.name}: {key} is already defined by another file."
                        " A version is immutable, so two files cannot claim the same one"
                    )
                    continue
                items[kind][key] = item
                hashes[f"{kind}/{key}"] = digest

        errors.extend(self._cross_reference_errors(items))
        return ContentLoadResult(
            items=items if not errors else {},
            errors=tuple(errors),
            hashes=hashes if not errors else {},
        )

    def _read_file(self, path: Path, model: type[BaseModel]) -> tuple[BaseModel, str, str]:
        """Parse, redaction-check, then validate one file. Errors name the file and the reason.

        Every re-raise below is `from None` rather than `from exc`, deliberately. The audience is a
        CONTENT AUTHOR, and each message already carries the diagnosis the original exception held:
        the decode error's type, the JSON error's line and column, the validator's field paths. A
        chained traceback through `json` or pydantic internals adds nothing an author can act on and
        buries the sentence that tells them which file and which field to fix.
        """
        label = f"{path.parent.name}/{path.name}"
        try:
            raw_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ContentError(
                f"{label}: cannot be read as UTF-8 text ({type(exc).__name__})"
            ) from None

        # Redaction BEFORE schema validation, deliberately. A file that holds a protected-object
        # identifier is a disclosure risk whether or not it also parses, and reporting the schema
        # error first would bury the finding that matters.
        findings = sorted(set(_redaction_findings(raw_text)))
        if findings:
            raise RedactionError(
                f"{label}: refused by the redaction gate. "
                + "; ".join(findings)
                + ". The offending text is deliberately not echoed here"
            )

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ContentError(
                f"{label}: is not valid JSON at line {exc.lineno} column {exc.colno}"
            ) from None

        if not isinstance(payload, dict):
            raise ContentError(
                f"{label}: top level is {type(payload).__name__}, expected a JSON object"
            )

        try:
            item = model.model_validate(payload)
        except ValidationError as exc:
            detail = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()[:8]
            )
            raise ContentError(f"{label}: failed validation. {detail}") from None

        if isinstance(item, Procedure):
            ordinal_error = _validate_step_ordinals(item)
            if ordinal_error is not None:
                raise ContentError(f"{label}: {ordinal_error}")

        meta = item.meta  # type: ignore[attr-defined]
        return item, f"{meta.id}@{meta.version}", content_hash(payload)

    @staticmethod
    def _cross_reference_errors(items: dict[str, dict[str, BaseModel]]) -> list[str]:
        """Every reference must resolve to a loaded version.

        The plan requires it in one direction ("every rubric references a resolvable procedure
        version") and the same argument covers the others: a scenario naming a procedure that is not
        there, or a trace naming a scenario that is not there, is a run that cannot be scored or
        debriefed. Caught at load rather than at run, because the author is here now.
        """
        errors: list[str] = []
        procedures = items.get("procedures", {})
        scenarios = items.get("scenarios", {})

        for key, scenario in scenarios.items():
            target = f"{scenario.procedure_id}@{scenario.procedure_version}"  # type: ignore[attr-defined]
            if target not in procedures:
                errors.append(f"scenarios/{key}: names procedure {target}, which is not loaded")

        for key, rubric in items.get("rubrics", {}).items():
            target = f"{rubric.procedure_id}@{rubric.procedure_version}"  # type: ignore[attr-defined]
            if target not in procedures:
                errors.append(f"rubrics/{key}: names procedure {target}, which is not loaded")

        for key, trace in items.get("traces", {}).items():
            target = f"{trace.scenario_id}@{trace.scenario_version}"  # type: ignore[attr-defined]
            if target not in scenarios:
                errors.append(f"traces/{key}: names scenario {target}, which is not loaded")

        return errors
