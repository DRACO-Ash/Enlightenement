"""Flight plan step 5: the content schemas and loader.

Every fixture here is SYNTHETIC and obviously so. No real Protect and Defend procedure text, no
real catalogue number, no real channel or tool name appears in this file or anywhere under
`content/`. That is not caution for its own sake: the plan's redaction discipline forbids it, and a
test fixture that looked like real procedure content would be exactly the aggregation the discipline
exists to prevent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from enlightenment.content import (
    CONTENT_KINDS,
    ContentStatus,
    ContentStore,
    Procedure,
    RedactionError,
    content_hash,
    json_schemas,
)


def _meta(item_id: str, *, version: str = "v1", status: str = "active") -> dict[str, Any]:
    return {
        "id": item_id,
        "version": version,
        "status": status,
        "title": "Synthetic fixture",
        "authored_by": "test fixture",
        "authored_on": "2026-08-24",
        "change_reason": "created for the loader tests",
    }


def _procedure(
    item_id: str = "synthetic-manoeuvre", *, steps: int = 2, **over: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "meta": _meta(item_id, **{k: v for k, v in over.items() if k in {"version", "status"}}),
        "purpose": "Exercise the loader against a shape the real library will use.",
        "entry_conditions": ["A synthetic cue is present in the synthetic feed."],
        "roles": ["analyst", "supervisor"],
        "steps": [
            {
                "ordinal": index,
                "action": f"Take synthetic action {index}.",
                "responsible_role": "analyst",
            }
            for index in range(1, steps + 1)
        ],
        "threshold_criteria": [
            {"name": "synthetic-threshold", "condition": "A synthetic condition is met."}
        ],
        "reporting_requirements": ["Report the synthetic finding."],
        "transition_rules": [],
        "closure_criteria": ["The synthetic event is closed."],
        "sparta_technique_ids": ["SPARTA-REC-0001"],
    }
    payload.update({k: v for k, v in over.items() if k not in {"version", "status"}})
    return payload


def _scenario(
    item_id: str = "synthetic-scenario", procedure: str = "synthetic-manoeuvre"
) -> dict[str, Any]:
    return {
        "meta": _meta(item_id),
        "procedure_id": procedure,
        "procedure_version": "v1",
        "event_class": "synthetic-manoeuvre",
        "briefing": "A synthetic briefing for a synthetic event.",
        "expected_response": ["Classify the synthetic event."],
        "seeded_parameters": ["regime", "event_timing"],
        "sparta_technique_ids": [],
    }


def _rubric(
    item_id: str = "synthetic-rubric", procedure: str = "synthetic-manoeuvre"
) -> dict[str, Any]:
    return {
        "meta": _meta(item_id),
        "procedure_id": procedure,
        "procedure_version": "v1",
        "criteria": [
            {
                "name": "named-the-event",
                "axis": "event-classification",
                "weight": 1.0,
                "evidence": "The operator named the synthetic event class.",
            }
        ],
    }


def _trace(
    item_id: str = "synthetic-trace", scenario: str = "synthetic-scenario"
) -> dict[str, Any]:
    return {
        "meta": _meta(item_id),
        "scenario_id": scenario,
        "scenario_version": "v1",
        "observations": [
            {
                "tick": 4,
                "cue": "A synthetic cue appears.",
                "inference": "The synthetic event has begun.",
                "axis": "cue-detection",
            }
        ],
    }


def _write(root: Path, kind: str, name: str, payload: object) -> Path:
    directory = root / kind
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _seeded_tree(root: Path) -> None:
    """A tree whose every cross-reference resolves."""
    _write(root, "procedures", "synthetic-manoeuvre", _procedure())
    _write(root, "scenarios", "synthetic-scenario", _scenario())
    _write(root, "rubrics", "synthetic-rubric", _rubric())
    _write(root, "traces", "synthetic-trace", _trace())


# --- the happy path ------------------------------------------------------------------


def test_a_complete_tree_loads_and_every_item_is_addressable(tmp_path: Path) -> None:
    _seeded_tree(tmp_path)
    store = ContentStore(tmp_path)
    result = store.reload()

    assert result.ok, result.errors
    assert store.get("procedures", "synthetic-manoeuvre@v1") is not None
    assert store.get("scenarios", "synthetic-scenario@v1") is not None
    assert store.get("rubrics", "synthetic-rubric@v1") is not None
    assert store.get("traces", "synthetic-trace@v1") is not None


def test_every_loaded_item_carries_a_content_hash_a_run_can_record(tmp_path: Path) -> None:
    """The plan requires a run to record the exact content version hash it scored under."""
    _seeded_tree(tmp_path)
    store = ContentStore(tmp_path)
    assert store.reload().ok
    digest = store.hash_of("procedures", "synthetic-manoeuvre@v1")
    assert digest is not None
    assert len(digest) == 64


def test_the_hash_is_over_the_canonical_form_not_the_raw_bytes(tmp_path: Path) -> None:
    """Reformatting a file must not change what its content hash says about its content.

    A hash over raw bytes makes every reindentation look like a content change, and makes a run's
    recorded hash unreproducible from the file a reader is looking at.
    """
    payload = _procedure()
    compact = content_hash(json.loads(json.dumps(payload, separators=(",", ":"))))
    reordered = content_hash(dict(reversed(list(payload.items()))))
    assert compact == reordered

    changed = _procedure()
    changed["purpose"] = "A different purpose."
    assert content_hash(changed) != compact


def test_a_draft_is_loaded_but_never_counted_as_active(tmp_path: Path) -> None:
    _write(tmp_path, "procedures", "draft-one", _procedure("draft-one", status="draft"))
    store = ContentStore(tmp_path)
    assert store.reload().ok
    assert store.get("procedures", "draft-one@v1") is not None
    assert store.active("procedures") == {}


# --- safe failure --------------------------------------------------------------------


def test_malformed_json_is_rejected_with_a_line_and_column_not_a_traceback(tmp_path: Path) -> None:
    (tmp_path / "procedures").mkdir(parents=True)
    (tmp_path / "procedures" / "broken.json").write_text("{ not json", encoding="utf-8")
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any("is not valid JSON at line" in error for error in result.errors)


def test_a_schema_failure_names_the_field_path_for_the_author(tmp_path: Path) -> None:
    payload = _procedure()
    del payload["closure_criteria"]
    _write(tmp_path, "procedures", "no-closure", payload)
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any("closure_criteria" in error for error in result.errors)


def test_an_unknown_key_is_rejected_rather_than_ignored(tmp_path: Path) -> None:
    """`extra="forbid"` made mechanical: a typo is a rejected file, not a dropped field."""
    _write(tmp_path, "procedures", "typo", _procedure(closure_critera=["typo"]))
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any("closure_critera" in error or "Extra inputs" in error for error in result.errors)


def test_one_bad_file_yields_no_store_rather_than_a_partial_library(tmp_path: Path) -> None:
    """The whole point of safe failure, and the thing a per-file try/except would get wrong.

    A partially loaded procedure library scores runs against the rules that happened to parse. So a
    single unusable file means the load produces errors and no items at all.
    """
    _seeded_tree(tmp_path)
    (tmp_path / "procedures" / "broken.json").write_text("{", encoding="utf-8")
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert result.items == {}
    assert result.hashes == {}


def test_a_failed_reload_keeps_the_last_good_tree_serving(tmp_path: Path) -> None:
    """An authoring typo must not become an outage."""
    _seeded_tree(tmp_path)
    store = ContentStore(tmp_path)
    assert store.reload().ok
    before = store.get("procedures", "synthetic-manoeuvre@v1")

    (tmp_path / "procedures" / "broken.json").write_text("{", encoding="utf-8")
    assert not store.reload().ok
    assert store.get("procedures", "synthetic-manoeuvre@v1") is before


def test_two_files_claiming_one_version_is_refused(tmp_path: Path) -> None:
    """A version is immutable and pointed at, so two files cannot both define it."""
    _write(tmp_path, "procedures", "first", _procedure())
    _write(tmp_path, "procedures", "second", _procedure())
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any("already defined by another file" in error for error in result.errors)


def test_step_ordinals_must_be_a_contiguous_run_from_one(tmp_path: Path) -> None:
    payload = _procedure()
    payload["steps"][1]["ordinal"] = 7
    _write(tmp_path, "procedures", "gapped", payload)
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any("contiguous run" in error for error in result.errors)


# --- cross references ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "name", "payload_factory", "expected"),
    [
        (
            "scenarios",
            "orphan",
            lambda: _scenario(procedure="absent-procedure"),
            "absent-procedure@v1",
        ),
        ("rubrics", "orphan", lambda: _rubric(procedure="absent-procedure"), "absent-procedure@v1"),
        ("traces", "orphan", lambda: _trace(scenario="absent-scenario"), "absent-scenario@v1"),
    ],
)
def test_a_reference_to_content_that_is_not_loaded_is_refused(
    tmp_path: Path, kind: str, name: str, payload_factory: Any, expected: str
) -> None:
    _write(tmp_path, "procedures", "synthetic-manoeuvre", _procedure())
    _write(tmp_path, "scenarios", "synthetic-scenario", _scenario())
    _write(tmp_path, kind, name, payload_factory())
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any(expected in error for error in result.errors)


def test_a_rubric_pinned_to_an_older_version_does_not_float_to_the_newer_one(
    tmp_path: Path,
) -> None:
    """A rubric that floated to the latest version would silently rescore history."""
    _write(tmp_path, "procedures", "p-v2", _procedure(version="v2"))
    _write(tmp_path, "rubrics", "pinned-v1", _rubric())
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any("synthetic-manoeuvre@v1" in error for error in result.errors)


# --- the redaction gate --------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_value", "rule"),
    [
        ("Exclude object 25544 from the sweep.", "catalogue-number"),
        ("Open https://internal.example.invalid/tool to continue.", "url"),
        ("Run C:\\Tools\\Sweep\\run.exe and wait.", "windows-path"),
        ("Post the result to #synthetic-ops-channel.", "chat-channel"),
    ],
)
def test_the_redaction_gate_refuses_a_forbidden_shape_anywhere_in_the_file(
    tmp_path: Path, field_value: str, rule: str
) -> None:
    """The plan's discipline, made mechanical for the shapes a pattern can see.

    ENLIGHTENMENT teaches that a protected-object exclusion list exists and must be checked; it
    never holds the list. A human reviewer is still the other half of this gate and is not replaced
    by it.
    """
    _write(tmp_path, "procedures", "leaky", _procedure(purpose=field_value))
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any(rule in error for error in result.errors), result.errors


def test_a_redaction_finding_never_echoes_the_offending_text(tmp_path: Path) -> None:
    """Reporting a disclosure risk must not repeat the disclosure into a log or a console."""
    secret_shaped = "Exclude object 25544 from the sweep."
    _write(tmp_path, "procedures", "leaky", _procedure(purpose=secret_shaped))
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    joined = " ".join(result.errors)
    assert "25544" not in joined
    assert "deliberately not echoed" in joined


def test_the_redaction_gate_runs_before_schema_validation(tmp_path: Path) -> None:
    """A file that both leaks and fails validation reports the leak, which is what matters."""
    payload = _procedure(purpose="Exclude object 25544.")
    del payload["closure_criteria"]
    _write(tmp_path, "procedures", "both-wrong", payload)
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any("redaction gate" in error for error in result.errors)
    assert not any("closure_criteria" in error for error in result.errors)


def test_a_plausible_operational_sentence_is_not_refused(tmp_path: Path) -> None:
    """The gate must not be so eager that authoring becomes impossible.

    Real procedure prose carries numbers: degrees, minutes, tolerances. Only a BARE five-to-eight
    digit run is refused, so a decimal, a shorter number and a dotted designator all pass.
    """
    _write(
        tmp_path,
        "procedures",
        "clean",
        _procedure(
            purpose=(
                "Assess drift against a 0.05 degree per day tolerance over 90 minutes, and"
                " compare with the 2026-08-24 baseline at 1200Z."
            )
        ),
    )
    assert ContentStore(tmp_path).reload().ok


def test_a_catalogue_number_at_the_end_of_a_sentence_is_still_refused(tmp_path: Path) -> None:
    """The regression that the first pattern let through, pinned so it cannot come back.

    The first version excluded a following full stop outright, to let `0.05` pass, and so let
    `object 25544.` pass too. Sentence-final is the MORE likely way an exclusion list actually gets
    written, so this case is the one worth a test of its own.
    """
    _write(tmp_path, "procedures", "trailing", _procedure(purpose="Do not task object 25544."))
    result = ContentStore(tmp_path).reload()

    assert not result.ok
    assert any("catalogue-number" in error for error in result.errors), result.errors


def test_a_five_digit_altitude_is_refused_a_known_and_accepted_false_positive(
    tmp_path: Path,
) -> None:
    """A stated limit of the gate, not a hidden one.

    `35786 km` is the geostationary altitude and is refused, because a bare five-digit run is
    indistinguishable from a catalogue number by shape alone. The gate fails CLOSED and the author's
    workaround is a thousands separator (`35,786 km`) or words. This test exists so the limit is
    documented and measured rather than discovered by an author with no explanation, and so a later
    change that quietly widens the pattern has to change a test that says why.
    """
    _write(tmp_path, "procedures", "geo", _procedure(purpose="Hold the belt at 35786 km altitude."))
    assert not ContentStore(tmp_path).reload().ok

    _write(
        tmp_path, "procedures", "geo", _procedure(purpose="Hold the belt at 35,786 km altitude.")
    )
    assert ContentStore(tmp_path).reload().ok


# --- the schema artefact -------------------------------------------------------------


def test_a_json_schema_is_emitted_for_every_content_kind(tmp_path: Path) -> None:
    """Authors validate against the schema the loader enforces, generated from one source."""
    schemas = json_schemas()
    assert set(schemas) == set(CONTENT_KINDS)
    for kind, schema in schemas.items():
        assert schema["type"] == "object", kind
        assert "properties" in schema, kind


def test_the_loaded_model_type_matches_the_directory_it_came_from(tmp_path: Path) -> None:
    _seeded_tree(tmp_path)
    store = ContentStore(tmp_path)
    assert store.reload().ok
    assert isinstance(store.get("procedures", "synthetic-manoeuvre@v1"), Procedure)


def test_an_absent_content_root_loads_empty_rather_than_raising(tmp_path: Path) -> None:
    """A missing tree is a deployment with no content yet, not a crash."""
    result = ContentStore(tmp_path / "nothing-here").reload()
    assert result.ok
    assert result.items == {kind: {} for kind in CONTENT_KINDS}


def test_the_store_returns_copies_so_a_caller_cannot_mutate_the_library(tmp_path: Path) -> None:
    _seeded_tree(tmp_path)
    store = ContentStore(tmp_path)
    assert store.reload().ok
    snapshot = store.all_of("procedures")
    snapshot.clear()
    assert store.all_of("procedures") != {}


def test_redaction_error_is_a_content_error_so_one_except_clause_covers_both() -> None:
    """A caller that only cares 'is this content usable' must not need two handlers."""
    from enlightenment.content import ContentError

    assert issubclass(RedactionError, ContentError)


def test_content_status_is_exactly_the_three_the_plan_names() -> None:
    assert {status.value for status in ContentStatus} == {"draft", "active", "deprecated"}
