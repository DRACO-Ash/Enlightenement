"""Typed views over the ENLIGHTENMENT content package.

**The content is the asset and it is never code.** These models are a read boundary, not a
schema of record: `schemas/enlightenment.schema.json` and `tools/validate_content.py` are
authoritative, and the validator runs as a leg of the verification loop. So every model here
sets ``extra="allow"``. The package carries far more per record than the engine consumes today,
and a model that rejected an unmodelled field would turn a content author's new field into a
build failure, which is precisely the coupling the package exists to avoid.

What IS validated here is the shape the engine depends on. A drill with no accept list, a
generator name outside the canonical twelve, or an Elo outside the rated band is a content fault
the engine cannot serve, and it fails at load rather than at the request that needs it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResponseFormat(StrEnum):
    """How the operator answers, which decides how the response is matched and scored.

    Ten formats, all ten in live use in the drill bank. Four of them
    (`cross_product_reconciliation`, `reasoned_argument`, `anatomy_question`,
    `no_action_correct`) were being used while undeclared in the schema, and the content
    validator passed because it never checked. That is the blind spot a validator exists to
    prevent, and `response_formats_declared` now closes it upstream of this file.
    """

    FREE_CLASSIFICATION = "free_classification"
    ORDERED_ACTIONS = "ordered_actions"
    YES_NO_WITH_REASON = "yes_no_with_reason"
    CROSS_PRODUCT_RECONCILIATION = "cross_product_reconciliation"
    REASONED_ARGUMENT = "reasoned_argument"
    NUMERIC_ESTIMATE = "numeric_estimate"
    PRODUCT_REQUEST = "product_request"
    ANATOMY_QUESTION = "anatomy_question"
    NO_ACTION_CORRECT = "no_action_correct"
    THRESHOLD_CALL = "threshold_call"


#: The canonical twelve, from the `_generator_contract` block at the top of `drills.json`. Ten
#: product renderers and two composition modes. Earlier drill authoring accumulated 58 ad-hoc
#: names, one per stimulus shape; they survive as `_legacy_generator` in each drill's params for
#: traceability and MUST NOT be implemented. An engineer reading the drill bank without this
#: block would have set out to build 58 renderers, which the package calls its single biggest
#: handover risk.
PRODUCT_RENDERERS: frozenset[str] = frozenset(
    {
        "waterfall",
        "residual",
        "dc_table",
        "light_curve",
        "tric",
        "neighbourhood",
        "coco",
        "pass_schedule",
        "ephemeris",
        "gabbard",
    }
)

#: The two composition modes. They orchestrate renderers and render nothing themselves.
COMPOSITION_MODES: frozenset[str] = frozenset({"composite", "probe"})

CANONICAL_GENERATORS: frozenset[str] = PRODUCT_RENDERERS | COMPOSITION_MODES

#: The rated band. Matches the operator rating bounds in `training.scoring`, so an item cannot
#: be authored outside the range the pairing algorithm can reach.
MIN_ELO = 600
MAX_ELO = 2400


class _Record(BaseModel):
    """Common configuration: frozen, and tolerant of fields the engine does not read."""

    model_config = ConfigDict(frozen=True, extra="allow")


class Stimulus(_Record):
    """What the operator is shown. `rendered` is filled by the generator, never by content."""

    product_id: str
    generator: str
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("generator")
    @classmethod
    def _canonical(cls, value: str) -> str:
        if value not in CANONICAL_GENERATORS:
            raise ValueError(
                f"generator {value!r} is outside the canonical twelve declared in the"
                " _generator_contract block of drills.json. If this is a legacy name it belongs"
                " in params as _legacy_generator and must not be implemented."
            )
        return value


class PartialAnswer(_Record):
    """A right-but-imprecise answer, with the credit it earns and why it is not full marks."""

    value: str
    credit: float = 0.5
    note: str = ""


class RejectAnswer(_Record):
    """A wrong answer worth naming, with the reason. The refusals carry the teaching."""

    value: str
    why_wrong: str = ""


class Tolerance(_Record):
    """How close a numeric answer has to be, and in what units.

    Either a relative fraction or an absolute amount, never both, and the unit is carried so the
    interface can say "within 0.25 degrees per day" rather than "within 0.25". An absolute
    tolerance of zero is not a mistake: several items ask for a count of manoeuvres, where the
    only right answer is the right number.
    """

    relative: float | None = None
    absolute: float | None = None
    unit: str = ""


class Answer(_Record):
    """The key. **Never leaves the server before the operator has submitted.**

    The production-format rule is architectural rather than cosmetic: a drill payload carries
    the stimulus and the prompt, and this object reaches the client only in the response to a
    submission. It is easy to defeat by building a convenient combined endpoint, so the test
    suite asserts on the raw response body rather than on a parsed object.
    """

    #: `("computed_from_params",)` is a sentinel, not an answer: for those items the expected
    #: value is derived from the stimulus the generator produced, because stating it in content
    #: would fix the stimulus too. The evaluator asks the generator, and refuses the item rather
    #: than guessing if the generator cannot supply it.
    accept: tuple[str, ...] = ()
    partial: tuple[PartialAnswer, ...] = ()
    reject: tuple[RejectAnswer, ...] = ()
    tolerance: Tolerance | None = None
    value: float | None = None


class Drill(_Record):
    """One drill item: a stimulus, a prompt, a key, and the numbers that place it."""

    id: str
    cue_id: str = ""
    stimulus: Stimulus
    prompt: str
    response_format: ResponseFormat
    answer: Answer
    elo: int = 1200
    confidence_required: bool = True
    time_target_s: int = 30
    explain: str = ""

    @field_validator("elo")
    @classmethod
    def _rated_band(cls, value: int) -> int:
        if not MIN_ELO <= value <= MAX_ELO:
            raise ValueError(f"elo {value} is outside the rated band {MIN_ELO} to {MAX_ELO}")
        return value


class Cue(_Record):
    """A named signature an experienced analyst reads. The vocabulary the drills collect."""

    id: str
    name: str = ""
    procedure_id: str = ""
    competency_id: str = ""


class Procedure(_Record):
    """A procedure, its steps and its status. Read-only in the library, never gated."""

    id: str
    name: str = ""
    status: str = ""


class ScenarioTemplate(_Record):
    """A scenario template. Scored scenarios are refused while thresholds carry placeholders."""

    id: str
    name: str = ""
    procedure_id: str = ""
    difficulty_band: str = ""


class RubricRule(_Record):
    """One scoring rule.

    `when` is **prose**, not a machine-evaluable predicate, and that is a real limitation of the
    package rather than a defect in it: the design note says rules are "evaluated against the run
    event log", which is the right intent, but nothing in the content carries a machine key. The
    evaluator therefore keys its predicate registry on `id` and fails closed on a rule it cannot
    evaluate, so an unimplemented rule is reported rather than silently scoring zero.

    `explain` is used verbatim in the debrief. No score appears without naming the rule that
    fired and the evidence for it, because a scorer that cannot be challenged will not be
    trusted by this audience.
    """

    id: str
    when: str
    award: float
    competency_id: str = ""
    explain: str = ""
    cap: float | None = None


class Rubric(_Record):
    """A named set of rules and what they apply to."""

    id: str
    applies_to: tuple[str, ...] = ()
    rules: tuple[RubricRule, ...] = ()


class Product(_Record):
    """A provider product: what it is for, what it must contain, and how it reads."""

    id: str
    name: str = ""
    purpose: str = ""
    regime: tuple[str, ...] = ()
    must_contain: tuple[str, ...] = ()
    reads_as: str = ""


class Competency(_Record):
    """One competency axis. Reported with a confidence interval, never as a bare estimate."""

    id: str
    name: str = ""
