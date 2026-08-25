"""Versioned, schema-validated training content: procedures, scenarios, rubrics, traces.

Flight plan step 5. The content tree is data, not code: a content author edits a procedure's
steps or thresholds and adds a new procedure WITHOUT a code deployment, which is a line in the
plan's definition of done.

**Why pydantic rather than a `jsonschema` runtime dependency.** The plan says "JSON Schema
validated on load with safe failure". Pydantic 2 is already a runtime dependency, validates
strictly with `extra="forbid"`, produces author-facing error paths, and EMITS JSON Schema from the
same models via :func:`json_schemas`. So authors still get a schema artefact to validate against in
an editor or a pre-commit hook, and the container gains no dependency. One definition, two
consumers, no drift between the schema authors read and the schema the loader enforces.

**Why JSON rather than YAML.** The plan permits either. JSON is in the standard library, so the
choice costs nothing and rules out a second parser in the image.
"""

from __future__ import annotations

from enlightenment.content.loader import (
    CONTENT_KINDS,
    ContentError,
    ContentLoadResult,
    ContentStore,
    RedactionError,
    content_hash,
    json_schemas,
)
from enlightenment.content.models import (
    CATALOGUE_NUMBER_PATTERN,
    CONTENT_ID_PATTERN,
    SPARTA_TECHNIQUE_PATTERN,
    ContentStatus,
    ExpertTrace,
    Procedure,
    ProcedureStep,
    Rubric,
    RubricCriterion,
    ScenarioTemplate,
    ThresholdCriterion,
    TraceObservation,
    TransitionRule,
)

__all__ = [
    "CATALOGUE_NUMBER_PATTERN",
    "CONTENT_ID_PATTERN",
    "CONTENT_KINDS",
    "SPARTA_TECHNIQUE_PATTERN",
    "ContentError",
    "ContentLoadResult",
    "ContentStatus",
    "ContentStore",
    "ExpertTrace",
    "Procedure",
    "ProcedureStep",
    "RedactionError",
    "Rubric",
    "RubricCriterion",
    "ScenarioTemplate",
    "ThresholdCriterion",
    "TraceObservation",
    "TransitionRule",
    "content_hash",
    "json_schemas",
]
