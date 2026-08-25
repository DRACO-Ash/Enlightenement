"""The four content schemas: procedure, scenario template, rubric, expert trace.

Every model is `extra="forbid"`, so a typed key in an authored file is a rejected file rather than
a silently ignored field. A content author's mistake must surface as an author-facing error, never
as a scenario that scores against a rule nobody wrote.

Field shapes come from `docs/FLIGHT-PLAN.md`: the procedure library's own list (purpose and entry
conditions, roles, ordered steps with responsible role and notes or warnings, threshold criteria,
reporting requirements, transition rules, closure criteria, status), the scenario template's
fixed-response-and-seeded-instantiation split, the rubric's requirement to reference a resolvable
procedure version, and the expert trace's requirement to record its author and date.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

#: Slug shape for any content id: lowercase alphanumeric with single internal hyphens. The same
#: shape as a session id, deliberately - one id grammar across the product means one validator and
#: one thing for an author to remember.
CONTENT_ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

#: Content version shape: `v` then a positive integer. Versions are immutable and pointed at, per
#: the plan, so a run records the exact version it was scored under. Not semantic versioning: a
#: procedure has no notion of a backwards-compatible change, only a new version.
CONTENT_VERSION_PATTERN = r"^v[1-9][0-9]*$"

#: SPARTA technique id, pinned to matrix version 4.0 by the plan. `SPARTA` then a dotted numeric
#: path, so `SPARTA-EX-0001` and free text are both refused.
SPARTA_TECHNIQUE_PATTERN = r"^SPARTA-[A-Z]{2,4}-[0-9]{4}(\.[0-9]{3})?$"

#: A bare five-to-eight digit run, which is the shape of a satellite catalogue number. The plan's
#: redaction discipline forbids a real protected-object identifier anywhere in the content tree, so
#: the loader refuses one. Used by the loader rather than as a field validator, because the
#: prohibition is on the WHOLE authored file, not on one field.
#:
#: **The lookarounds are exact about decimals, and the first version was not.** Excluding a
#: following `.` outright, to let `0.05` through, also let `object 25544.` through - a catalogue
#: number at the end of a sentence. So `.` blocks the match only when a DIGIT follows it. Measured:
#: the first version passed the mid-sentence case and missed the sentence-final one, which is the
#: more likely way an exclusion list actually gets written.
CATALOGUE_NUMBER_PATTERN = r"(?<![0-9A-Za-z_-])(?<![0-9]\.)[0-9]{5,8}(?![0-9A-Za-z_-])(?!\.[0-9])"

_MAX_SHORT = 200
_MAX_PROSE = 2000


class ContentStatus(StrEnum):
    """Lifecycle of a content item. `DRAFT` never scores a run."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class _Content(BaseModel):
    """Fields every content item carries, so provenance is never optional.

    The plan requires attribution on content that drives scoring: "Every procedure, rubric and
    scenario edit records author, timestamp, content version hash and the reason for the change."
    The hash is computed by the loader rather than authored, because a self-declared hash is not a
    hash of anything.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    id: str = Field(min_length=1, max_length=64, pattern=CONTENT_ID_PATTERN)
    version: str = Field(pattern=CONTENT_VERSION_PATTERN)
    status: ContentStatus
    title: str = Field(min_length=1, max_length=_MAX_SHORT)
    authored_by: str = Field(min_length=1, max_length=_MAX_SHORT)
    authored_on: date
    change_reason: str = Field(min_length=1, max_length=_MAX_PROSE)


class ProcedureStep(BaseModel):
    """One ordered step, with the role that owns it.

    `ordinal` is authored rather than inferred from list position, so a diff that reorders steps is
    visible as a change to the ordinals rather than as an invisible re-index. The loader asserts
    the ordinals are a contiguous run from one.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    ordinal: int = Field(ge=1, le=200)
    action: str = Field(min_length=1, max_length=_MAX_PROSE)
    responsible_role: str = Field(min_length=1, max_length=_MAX_SHORT)
    note: str | None = Field(default=None, max_length=_MAX_PROSE)
    warning: str | None = Field(default=None, max_length=_MAX_PROSE)


class ThresholdCriterion(BaseModel):
    """A named threshold the procedure turns on.

    `condition` is prose, deliberately: a threshold in a Protect and Defend procedure is a judgement
    expressed in operational terms, and encoding it as an expression here would invent a semantics
    the source procedure does not have. The scoring engine (step 6) binds a decision table to the
    criterion by `name`, which is where machine-readable logic belongs.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    name: str = Field(min_length=1, max_length=_MAX_SHORT, pattern=CONTENT_ID_PATTERN)
    condition: str = Field(min_length=1, max_length=_MAX_PROSE)


class TransitionRule(BaseModel):
    """When this procedure hands over to another one."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    when: str = Field(min_length=1, max_length=_MAX_PROSE)
    to_procedure_id: str = Field(min_length=1, max_length=64, pattern=CONTENT_ID_PATTERN)


class Procedure(BaseModel):
    """A versioned Protect and Defend procedure.

    **What this deliberately does NOT hold**, per the plan's redaction discipline: a
    protected-object exclusion list by catalogue number, an internal tool click-path, a chat-channel
    or product-naming convention, or OPSEC guidance. ENLIGHTENMENT teaches that such a list exists
    and must be checked; it never holds the list. The loader enforces the mechanical half of that
    and a human reviewer enforces the rest.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    meta: _Content
    purpose: str = Field(min_length=1, max_length=_MAX_PROSE)
    entry_conditions: list[str] = Field(min_length=1, max_length=40)
    roles: list[str] = Field(min_length=1, max_length=20)
    steps: list[ProcedureStep] = Field(min_length=1, max_length=200)
    threshold_criteria: list[ThresholdCriterion] = Field(default_factory=list, max_length=40)
    reporting_requirements: list[str] = Field(default_factory=list, max_length=40)
    transition_rules: list[TransitionRule] = Field(default_factory=list, max_length=20)
    closure_criteria: list[str] = Field(min_length=1, max_length=20)
    sparta_technique_ids: list[str] = Field(default_factory=list, max_length=40)


class ScenarioTemplate(BaseModel):
    """A parameterised scenario: the expected response is fixed, the instantiation is seeded.

    That split is the plan's, and it is what makes a scenario reusable without becoming a
    memorisable single instance: an operator who has seen this template before still has to read
    THIS instantiation. `seeded_parameters` names which axes vary; the values come from the scenario
    engine's seeded PRNG at instantiation, never from this file.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    meta: _Content
    procedure_id: str = Field(min_length=1, max_length=64, pattern=CONTENT_ID_PATTERN)
    procedure_version: str = Field(pattern=CONTENT_VERSION_PATTERN)
    event_class: str = Field(min_length=1, max_length=_MAX_SHORT, pattern=CONTENT_ID_PATTERN)
    briefing: str = Field(min_length=1, max_length=_MAX_PROSE)
    expected_response: list[str] = Field(min_length=1, max_length=40)
    seeded_parameters: list[str] = Field(min_length=1, max_length=40)
    sparta_technique_ids: list[str] = Field(default_factory=list, max_length=40)


class RubricCriterion(BaseModel):
    """One scored criterion, bound to a competency axis.

    `axis` is a plain string rather than an enum on purpose: the plan says the six axes "are ours,
    so they are also revisable; version them like content". Pinning them in a Python enum would
    make a content revision a code deployment, which is the thing step 5 exists to prevent. The
    loader checks each axis against the axis list it loads as content.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    name: str = Field(min_length=1, max_length=_MAX_SHORT, pattern=CONTENT_ID_PATTERN)
    axis: str = Field(min_length=1, max_length=64, pattern=CONTENT_ID_PATTERN)
    weight: float = Field(gt=0.0, le=100.0)
    evidence: str = Field(min_length=1, max_length=_MAX_PROSE)


class Rubric(BaseModel):
    """How a run against one procedure version is scored.

    Every rubric names a resolvable procedure VERSION, not just an id, because the plan requires a
    run to record what it was scored under and a rubric that floats to the latest version silently
    rescores history.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    meta: _Content
    procedure_id: str = Field(min_length=1, max_length=64, pattern=CONTENT_ID_PATTERN)
    procedure_version: str = Field(pattern=CONTENT_VERSION_PATTERN)
    criteria: list[RubricCriterion] = Field(min_length=1, max_length=60)


class TraceObservation(BaseModel):
    """One thing the expert saw, when they saw it, and what it told them.

    `tick` is an integer scenario tick, not a wall-clock time, so a trace stays aligned to the
    deterministic clock the debrief replays against.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    tick: int = Field(ge=0)
    cue: str = Field(min_length=1, max_length=_MAX_PROSE)
    inference: str = Field(min_length=1, max_length=_MAX_PROSE)
    axis: str = Field(min_length=1, max_length=64, pattern=CONTENT_ID_PATTERN)


class ExpertTrace(BaseModel):
    """What an expert saw and when, for one scenario template.

    The plan concentrates the largest non-engineering dependency here: Ash authors and validates
    these. Two consequences are built in rather than hoped for. They are DATA, so they can be
    written in batches between builds; and `meta.authored_by` plus `meta.authored_on` are mandatory,
    so a second subject-matter expert can be added later without re-authoring the first set.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    meta: _Content
    scenario_id: str = Field(min_length=1, max_length=64, pattern=CONTENT_ID_PATTERN)
    scenario_version: str = Field(pattern=CONTENT_VERSION_PATTERN)
    observations: list[TraceObservation] = Field(min_length=1, max_length=200)
