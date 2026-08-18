"""The store is atomic, anti-shrink, capped, backed up, and honest about writability."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from enlightenment.storage import (
    BACKUP_RETENTION,
    SCHEMA_VERSION,
    STORE_FILENAME,
    TrainingStore,
    empty_snapshot,
    merge_session,
    migrate,
    probe_writable,
)


def fixed_now() -> datetime:
    return datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> TrainingStore:
    return TrainingStore(tmp_path / "data", now=fixed_now)


def test_seed_creates_the_snapshot_and_is_idempotent(store: TrainingStore) -> None:
    first = store.seed()
    assert first == empty_snapshot()
    assert store.path.exists()
    assert store.seed() == first


def test_load_returns_an_empty_snapshot_when_absent(store: TrainingStore) -> None:
    assert store.load() == empty_snapshot()


def test_write_is_atomic_leaving_no_temporary_file(store: TrainingStore) -> None:
    store.upsert_session({"id": "alpha", "title": "Alpha", "scenario": "TBC, re-verify"})
    leftovers = list(store.path.parent.glob(".snapshot-*"))
    assert leftovers == []
    assert json.loads(store.path.read_text(encoding="utf-8"))["schemaVersion"] == SCHEMA_VERSION


def test_a_partial_update_never_deletes_an_unsent_field(store: TrainingStore) -> None:
    store.upsert_session(
        {"id": "alpha", "title": "Alpha", "scenario": "TBC, re-verify", "notes": "keep me"}
    )
    store.upsert_session({"id": "alpha", "title": "Alpha renamed"})
    stored = store.sessions()
    assert len(stored) == 1
    assert stored[0]["title"] == "Alpha renamed"
    assert stored[0]["notes"] == "keep me"
    assert stored[0]["scenario"] == "TBC, re-verify"


def test_merge_session_keeps_existing_values_absent_from_the_update() -> None:
    merged = merge_session({"a": 1, "b": 2}, {"b": 3, "c": None})
    assert merged == {"a": 1, "b": 3}


def test_malformed_json_is_rejected_not_coerced(store: TrainingStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        store.load()


def test_a_non_object_snapshot_is_rejected(store: TrainingStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="top level is not an object"):
        store.load()


def test_migrate_preserves_unrecognised_fields() -> None:
    migrated = migrate({"sessions": [], "futureField": "keep"})
    assert migrated["futureField"] == "keep"
    assert migrated["schemaVersion"] == SCHEMA_VERSION


def test_migrate_rejects_a_malformed_sessions_field() -> None:
    with pytest.raises(ValueError, match="'sessions' is not a list"):
        migrate({"sessions": "nope"})


def test_the_cap_keeps_the_newest_and_never_drops_the_fresh_entry(tmp_path: Path) -> None:
    store = TrainingStore(tmp_path / "data", now=fixed_now, max_sessions=3)
    for index in range(5):
        store.upsert_session(
            {"id": f"s{index}", "title": f"Session {index}", "scenario": "TBC, re-verify"}
        )
    ids = [session["id"] for session in store.sessions()]
    assert ids == ["s2", "s3", "s4"]


def test_the_cap_boundary_holds_in_both_directions(tmp_path: Path) -> None:
    store = TrainingStore(tmp_path / "data", now=fixed_now, max_sessions=3)
    for index in range(3):
        store.upsert_session({"id": f"s{index}", "title": "t", "scenario": "TBC, re-verify"})
    assert len(store.sessions()) == 3
    store.upsert_session({"id": "s3", "title": "t", "scenario": "TBC, re-verify"})
    assert len(store.sessions()) == 3


def test_a_backup_is_taken_before_an_overwrite_and_pruned_to_the_retention(
    tmp_path: Path,
) -> None:
    stamps = iter([datetime(2026, 8, 18, 12, 0, second, tzinfo=UTC) for second in range(1, 40)])
    store = TrainingStore(tmp_path / "data", now=lambda: next(stamps))
    for index in range(BACKUP_RETENTION + 4):
        store.upsert_session({"id": f"s{index}", "title": "t", "scenario": "TBC, re-verify"})
    backups = list(store.path.parent.glob(f"{STORE_FILENAME}.*.bak"))
    assert len(backups) == BACKUP_RETENTION


def test_probe_writable_proves_a_usable_directory_with_a_real_write(tmp_path: Path) -> None:
    result = probe_writable(tmp_path / "fresh")
    assert result.ok is True
    assert result.errno is None
    assert list((tmp_path / "fresh").glob(".writeprobe-*")) == []


@pytest.mark.skipif(
    os.geteuid() == 0,
    reason="running as root bypasses directory permissions, so this case cannot be "
    "exercised here; the ENOTDIR case below covers the refused-write path on every uid",
)
def test_probe_writable_reports_the_errno_when_the_write_is_refused(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)
    try:
        result = probe_writable(blocked)
    finally:
        blocked.chmod(0o700)
    assert result.ok is False
    assert result.errno is not None
    diagnostic = result.as_diagnostic()
    assert diagnostic["writable"] is False
    assert diagnostic["resolvedDataDir"] == str(blocked)
    assert diagnostic["errnoName"]


def test_probe_reports_an_existing_path_that_is_a_file_not_a_directory(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.write_text("not a directory", encoding="utf-8")
    result = probe_writable(occupied)
    assert result.ok is False
    assert result.errno is not None


def test_a_failed_write_leaves_no_temporary_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temp-write-then-rename must not litter when the rename fails: a reader would
    otherwise find a partial sibling file where the store should be.
    """
    store = TrainingStore(tmp_path / "data", now=fixed_now)
    store.seed()

    def refuse(self: Path, target: object) -> Path:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="No space left on device"):
        store.upsert_session({"id": "alpha", "title": "t", "scenario": "TBC, re-verify"})
    assert list((tmp_path / "data").glob(".snapshot-*")) == []
