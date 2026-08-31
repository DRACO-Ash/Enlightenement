"""The content package loader: what it loads, and what it refuses to serve.

The package is the asset. These tests exist because three of its behaviours are content decisions
rather than engineering ones, and the build guidance says plainly that they will be omitted unless
stated: refuse a scored scenario while thresholds carry placeholders, reject a seed that fails its
solvability check, and record the content version hash on every run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from enlightenment.content import (
    CANONICAL_GENERATORS,
    MAX_ELO,
    MIN_ELO,
    ContentPackage,
    Drill,
    Stimulus,
)

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"


@pytest.fixture(scope="module")
def package() -> ContentPackage:
    loaded = ContentPackage(CONTENT)
    loaded.load()
    return loaded


def test_the_shipped_package_loads_with_no_errors(package: ContentPackage) -> None:
    """The whole library parses. A per-record failure is collected, so this names them all."""
    assert package.result.ok, package.result.errors
    assert package.result.errors == ()


def test_the_package_carries_the_counts_the_handover_declares(package: ContentPackage) -> None:
    """A regression in the loader that dropped records would otherwise pass silently.

    The figures come from the package's own validator output, not from the README prose, which
    was written against an earlier version and undercounts.
    """
    counts = package.result.counts
    assert counts["drills"] == 140
    assert counts["cues"] == 127
    assert counts["procedures"] == 13
    assert counts["scenarios"] == 12
    assert counts["rubrics"] == 3
    assert counts["products"] == 10


def test_a_scored_scenario_is_refused_while_thresholds_are_placeholders(
    package: ContentPackage,
) -> None:
    """The shipped thresholds are deliberately NOT the operational values.

    `thresholds.example.json` exists so the application runs and a developer without procedure
    access can build against a complete shape. An operator seeing a placeholder value in the
    interface is a bug, and this is the flag that stops it. The example file's own `_meta` says
    `all_placeholders_replaced` is false, so on a fresh checkout this must be false too.
    """
    assert package.thresholds.source == "thresholds.example.json"
    assert package.thresholds.all_placeholders_replaced is False
    assert package.scored_scenarios_ready is False


def test_a_populated_local_threshold_file_unlocks_scored_scenarios(tmp_path: Path) -> None:
    """The converse, so the refusal above cannot be a constant.

    Without this, deleting the flag check would leave the test above passing forever: it would
    still be false, for the wrong reason. A local file that declares its placeholders replaced
    must actually change the answer.
    """
    for name in ("drills.json", "cues.json", "rubrics.json", "products.json"):
        (tmp_path / name).write_text((CONTENT / name).read_text(encoding="utf-8"), encoding="utf-8")
    for name in ("product-layouts.json", "scenarios.json", "competencies.json", "traces.json"):
        (tmp_path / name).write_text((CONTENT / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "procedures").mkdir()
    for name in ("procedures-core.json", "procedures-extended.json"):
        (tmp_path / "procedures" / name).write_text(
            (CONTENT / "procedures" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    values = json.loads((CONTENT / "thresholds.example.json").read_text(encoding="utf-8"))
    values["_meta"]["all_placeholders_replaced"] = True
    (tmp_path / "thresholds.local.json").write_text(json.dumps(values), encoding="utf-8")

    loaded = ContentPackage(tmp_path)
    loaded.load()
    assert loaded.thresholds.source == "thresholds.local.json"
    assert loaded.scored_scenarios_ready is True


def test_the_content_hash_is_stable_and_changes_with_the_content(tmp_path: Path) -> None:
    """A run record carries this, so an old result stays interpretable.

    Stable across two loads of the same tree, and different when a byte changes. The hash covers
    the bytes rather than the parsed values, which is the honest behaviour: the question a run
    record answers is which FILES produced it.
    """
    first = ContentPackage(CONTENT)
    first.load()
    second = ContentPackage(CONTENT)
    second.load()
    assert first.content_hash == second.content_hash
    assert len(first.content_hash) == 64

    copy_root = tmp_path / "content"
    copy_root.mkdir()
    for source in CONTENT.rglob("*.json"):
        target = copy_root / source.relative_to(CONTENT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    altered = json.loads((copy_root / "drills.json").read_text(encoding="utf-8"))
    altered["drills"][0]["prompt"] += " "
    (copy_root / "drills.json").write_text(json.dumps(altered), encoding="utf-8")
    changed = ContentPackage(copy_root)
    changed.load()
    assert changed.content_hash != first.content_hash


def test_a_missing_required_file_refuses_to_load_rather_than_serving_a_partial_library(
    tmp_path: Path,
) -> None:
    """A partial library is worse than none: it serves some drills and silently omits others."""
    loaded = ContentPackage(tmp_path)
    result = loaded.load()
    assert result.ok is False
    assert any("drills.json" in error for error in result.errors)
    assert loaded.scored_scenarios_ready is False


def test_malformed_json_is_reported_and_never_raised(tmp_path: Path) -> None:
    """A malformed content file must not produce a running application that serves nothing.

    Carried rather than thrown, so the health paths stay 200 and the drill routes answer 503
    naming the fault. A container that refuses to start over a content typo cannot serve the
    health path that would tell an operator why.
    """
    for source in CONTENT.rglob("*.json"):
        target = tmp_path / source.relative_to(CONTENT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "drills.json").write_text("{ not json", encoding="utf-8")
    loaded = ContentPackage(tmp_path)
    result = loaded.load()
    assert result.ok is False
    assert any("JSONDecodeError" in error for error in result.errors)


def test_a_generator_outside_the_canonical_twelve_is_refused() -> None:
    """The 58 legacy generator names are traceability only and must never be implemented.

    An engineer reading the drill bank without the `_generator_contract` block would have set out
    to build 58 renderers, which the package calls its single biggest handover risk. This is the
    code-side half of the guard the content validator holds upstream.
    """
    with pytest.raises(ValueError, match="canonical twelve"):
        Stimulus(product_id="PRD-RESIDUAL", generator="residual_series", params={})
    assert "residual_series" not in CANONICAL_GENERATORS
    assert len(CANONICAL_GENERATORS) == 12


def test_every_shipped_drill_uses_a_canonical_generator(package: ContentPackage) -> None:
    """The whole bank, not a sample: one legacy name surviving anywhere breaks the registry."""
    for drill in package.drills:
        assert drill.stimulus.generator in CANONICAL_GENERATORS, drill.id


def test_an_item_authored_outside_the_rated_band_is_refused() -> None:
    """An item the pairing algorithm cannot reach is an item no operator will ever be served."""
    stimulus = Stimulus(product_id="PRD-RESIDUAL", generator="residual", params={})
    with pytest.raises(ValueError, match="rated band"):
        Drill(
            id="DRL-TEST",
            stimulus=stimulus,
            prompt="p",
            response_format="free_classification",
            answer={"accept": ["x"]},
            elo=MAX_ELO + 1,
        )
    with pytest.raises(ValueError, match="rated band"):
        Drill(
            id="DRL-TEST",
            stimulus=stimulus,
            prompt="p",
            response_format="free_classification",
            answer={"accept": ["x"]},
            elo=MIN_ELO - 1,
        )


def test_an_unmodelled_field_is_carried_rather_than_rejected(package: ContentPackage) -> None:
    """The package carries far more per record than the engine reads, and that must stay true.

    A model that rejected an unmodelled field would turn a content author adding a field into a
    build failure, which is exactly the coupling the package exists to avoid. The schema and the
    validator are authoritative; these models are a read boundary.
    """
    drill = package.drill("DRL-0001")
    assert drill is not None
    assert drill.model_extra is not None
    assert "_legacy_generator" in drill.stimulus.params


def test_the_drill_rubric_is_present_and_its_rules_carry_operator_facing_reasons(
    package: ContentPackage,
) -> None:
    """No score may appear without naming the rule and the evidence that fired it."""
    rubric = package.rubric("RUB-DRILL")
    assert rubric is not None
    assert rubric.rules
    for rule in rubric.rules:
        assert rule.explain.strip(), rule.id
        assert rule.competency_id.strip(), rule.id
