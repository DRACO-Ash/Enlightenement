"""The content package: Ash's authored training library, loaded at runtime and never compiled in.

**The content is the asset; this application is the delivery mechanism.** 140 drills, 127 cues,
13 procedures, 12 scenario templates, 67 rubric rules and five expert traces, all validated JSON,
built from a corpus of 3,124 released reports, nine exercise sources, eleven procedures and two
years of weekly reporting. If the application goes badly it can be rebuilt. If the content is
absorbed into code, everything has to be.

So nothing in here is a hardcoded scenario, a switch over event types, or a scoring rule expressed
in Python. What IS code, deliberately: the product generators, the physics core, the scoring
evaluator and the scheduler. The test that draws the line is whether the count changes when a
content author does their job. Ten product generators does not. 140 drills does.
"""

from __future__ import annotations

from enlightenment.content.loader import (
    CONTENT_DIR_VARIABLE,
    EXAMPLE_THRESHOLDS,
    LOCAL_THRESHOLDS,
    REQUIRED_FILES,
    ContentPackage,
    LoadResult,
    Thresholds,
    resolve_content_root,
)
from enlightenment.content.models import (
    CANONICAL_GENERATORS,
    COMPOSITION_MODES,
    MAX_ELO,
    MIN_ELO,
    PRODUCT_RENDERERS,
    Answer,
    Competency,
    Cue,
    Drill,
    PartialAnswer,
    Procedure,
    Product,
    RejectAnswer,
    ResponseFormat,
    Rubric,
    RubricRule,
    ScenarioTemplate,
    Stimulus,
    Tolerance,
)

__all__ = [
    "CANONICAL_GENERATORS",
    "COMPOSITION_MODES",
    "CONTENT_DIR_VARIABLE",
    "EXAMPLE_THRESHOLDS",
    "LOCAL_THRESHOLDS",
    "MAX_ELO",
    "MIN_ELO",
    "PRODUCT_RENDERERS",
    "REQUIRED_FILES",
    "Answer",
    "Competency",
    "ContentPackage",
    "Cue",
    "Drill",
    "LoadResult",
    "PartialAnswer",
    "Procedure",
    "Product",
    "RejectAnswer",
    "ResponseFormat",
    "Rubric",
    "RubricRule",
    "ScenarioTemplate",
    "Stimulus",
    "Thresholds",
    "Tolerance",
    "resolve_content_root",
]
