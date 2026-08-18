"""The store is atomic, serialised, revision-guarded, anti-shrink, capped, and backed up."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from enlightenment.storage import (
    BACKUP_RETENTION,
    SCHEMA_VERSION,
    STORE_FILENAME,
    StaleRevisionError,
    TrainingStore,
    UnknownSessionError,
    empty_snapshot,
    merge_session,
    migrate,
    probe_writable,
)

SESSION = {"id": "alpha", "title": "Alpha", "scenario": "TBC, re-verify"}


def fixed_now() -> datetime:
    return datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> TrainingStore:
    return TrainingStore(tmp_path / "data", now=fixed_now)


# --- seeding and reading ------------------------------------------------------------


def test_seed_creates_the_snapshot_and_is_idempotent(store: TrainingStore) -> None:
    first = store.seed()
    assert first == empty_snapshot()
    assert store.path.exists()
    assert store.seed() == first


def test_load_returns_an_empty_snapshot_when_absent(store: TrainingStore) -> None:
    assert store.load() == empty_snapshot()


def test_write_is_atomic_leaving_no_temporary_file(store: TrainingStore) -> None:
    store.upsert_session(dict(SESSION))
    assert list(store.path.parent.glob(".snapshot-*")) == []
    assert json.loads(store.path.read_text(encoding="utf-8"))["schemaVersion"] == SCHEMA_VERSION


def test_a_failed_write_leaves_no_temporary_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TrainingStore(tmp_path / "data", now=fixed_now)
    store.seed()

    def refuse(self: Path, target: object) -> Path:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="No space left on device"):
        store.upsert_session(dict(SESSION))
    assert list((tmp_path / "data").glob(".snapshot-*")) == []


# --- the revision guard --------------------------------------------------------------


def test_every_write_advances_the_revision(store: TrainingStore) -> None:
    assert store.revision() == 0
    first = store.upsert_session(dict(SESSION))
    assert first.rev == 1
    second = store.upsert_session({**SESSION, "id": "bravo"})
    assert second.rev == 2
    assert store.revision() == 2


def test_a_stale_expected_revision_is_refused_rather_than_overwriting(
    store: TrainingStore,
) -> None:
    store.upsert_session(dict(SESSION))
    with pytest.raises(StaleRevisionError) as raised:
        store.upsert_session({**SESSION, "title": "Clobber"}, expected_rev=0)
    assert raised.value.expected == 0
    assert raised.value.current == 1
    assert store.sessions()[0]["title"] == "Alpha"


def test_a_matching_expected_revision_is_accepted(store: TrainingStore) -> None:
    store.upsert_session(dict(SESSION))
    result = store.upsert_session({**SESSION, "title": "Renamed"}, expected_rev=1)
    assert result.session["title"] == "Renamed"


def test_the_write_result_counts_are_measured_inside_the_lock(store: TrainingStore) -> None:
    first = store.upsert_session(dict(SESSION))
    assert (first.count_before, first.count_after) == (0, 1)
    same = store.upsert_session({**SESSION, "title": "Renamed"})
    assert (same.count_before, same.count_after) == (1, 1)


# --- concurrency: the property two workers destroyed ---------------------------------


def test_two_processes_writing_at_once_lose_no_record(tmp_path: Path) -> None:
    """The regression test for the measured data-loss defect.

    Before the exclusive lock, two processes each loaded the same snapshot, each appended,
    and the second rename silently discarded the first process's writes: half of all
    acknowledged records vanished. The atomic rename is precisely why the loss left no
    torn file and no error.
    """
    data_dir = tmp_path / "data"
    writer = tmp_path / "writer.py"
    writer.write_text(
        textwrap.dedent(
            """
            import sys
            from pathlib import Path
            from enlightenment.storage import TrainingStore

            store = TrainingStore(Path(sys.argv[1]))
            offset = int(sys.argv[2])
            for index in range(40):
                store.upsert_session({
                    "id": f"s{offset + index}",
                    "title": "t",
                    "scenario": "TBC, re-verify",
                })
            """
        ),
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    processes = [
        subprocess.Popen(  # noqa: S603 - a fixed interpreter and a test-authored script
            [sys.executable, str(writer), str(data_dir), str(offset)], env=env
        )
        for offset in (0, 1000)
    ]
    for process in processes:
        assert process.wait(timeout=120) == 0

    store = TrainingStore(data_dir)
    stored = store.sessions()
    assert len(stored) == 80, f"expected 80 sessions, store holds {len(stored)}"
    assert store.revision() == 80


# --- anti-shrink ---------------------------------------------------------------------


def test_a_partial_update_never_deletes_an_unsent_field(store: TrainingStore) -> None:
    store.upsert_session({**SESSION, "notes": "keep me"})
    store.upsert_session({"id": "alpha", "title": "Alpha renamed"})
    stored = store.sessions()
    assert len(stored) == 1
    assert stored[0]["title"] == "Alpha renamed"
    assert stored[0]["notes"] == "keep me"
    assert stored[0]["scenario"] == "TBC, re-verify"


def test_merge_session_keeps_existing_values_absent_from_the_update() -> None:
    assert merge_session({"a": 1, "b": 2}, {"b": 3, "c": None}) == {"a": 1, "b": 3}


# --- malformed stored data ------------------------------------------------------------


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
    assert migrated["rev"] == 0


def test_migrate_rejects_a_malformed_sessions_field() -> None:
    with pytest.raises(ValueError, match="'sessions' is not a list"):
        migrate({"sessions": "nope"})


@pytest.mark.parametrize("bad_rev", ["1", 1.5, True, None, []])
def test_migrate_rejects_a_non_integer_revision(bad_rev: object) -> None:
    with pytest.raises(ValueError, match="'rev' is not an integer"):
        migrate({"sessions": [], "rev": bad_rev})


# --- caps and backups ----------------------------------------------------------------


def test_the_cap_keeps_the_newest_and_never_drops_the_fresh_entry(tmp_path: Path) -> None:
    store = TrainingStore(tmp_path / "data", now=fixed_now, max_sessions=3)
    for index in range(5):
        store.upsert_session({"id": f"s{index}", "title": "t", "scenario": "TBC, re-verify"})
    assert [session["id"] for session in store.sessions()] == ["s2", "s3", "s4"]


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


# --- the real-write probe ------------------------------------------------------------


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


def test_a_must_exist_write_is_refused_when_the_id_is_absent(store: TrainingStore) -> None:
    """The existence check runs INSIDE the lock. Checking before taking the lock left a
    window in which a concurrent write could trip the session cap and evict the id, turning
    an intended merge into an append of a partial record with a fresh createdAt.
    """
    with pytest.raises(UnknownSessionError):
        store.upsert_session({"id": "never-created", "title": "x"}, must_exist=True)
    assert store.sessions() == []
    assert store.revision() == 0


def test_a_must_exist_write_merges_when_the_id_is_present(store: TrainingStore) -> None:
    store.upsert_session({**SESSION, "notes": "keep me"})
    result = store.upsert_session({"id": "alpha", "title": "Renamed"}, must_exist=True)
    assert result.session["notes"] == "keep me"
    assert result.session["title"] == "Renamed"


def test_the_cap_cannot_turn_a_must_exist_merge_into_a_partial_append(tmp_path: Path) -> None:
    """The concrete failure the locked check closes: the id is evicted by the cap, so the
    'merge' would create a record carrying only the patched fields.
    """
    store = TrainingStore(tmp_path / "data", now=fixed_now, max_sessions=2)
    for index in range(3):
        store.upsert_session({"id": f"s{index}", "title": "t", "scenario": "TBC, re-verify"})
    assert [session["id"] for session in store.sessions()] == ["s1", "s2"]
    with pytest.raises(UnknownSessionError):
        store.upsert_session({"id": "s0", "title": "only this field"}, must_exist=True)


def test_the_snapshot_and_its_backups_share_the_same_restrictive_mode(tmp_path: Path) -> None:
    """A backup holding identical data under a weaker mode, on a volume that may be shared
    with an add-on, is a downgrade.
    """
    stamps = iter([datetime(2026, 8, 18, 12, 0, second, tzinfo=UTC) for second in range(1, 10)])
    store = TrainingStore(tmp_path / "data", now=lambda: next(stamps))
    store.upsert_session(dict(SESSION))
    store.upsert_session({**SESSION, "title": "Renamed"})
    snapshot_mode = store.path.stat().st_mode & 0o777
    backups = list(store.path.parent.glob(f"{STORE_FILENAME}.*.bak"))
    assert backups, "no backup was taken"
    for backup in backups:
        assert backup.stat().st_mode & 0o777 == snapshot_mode


def test_the_lock_file_is_not_followed_through_a_symlink(tmp_path: Path) -> None:
    """A principal with write access to the volume could otherwise plant the lock path as a
    symlink and de-serialise every writer.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.touch()
    (data_dir / "training.lock").symlink_to(elsewhere)
    store = TrainingStore(data_dir, now=fixed_now)
    with pytest.raises(OSError, match=r"symbolic link|Too many levels|ELOOP|loop"):
        store.upsert_session(dict(SESSION))


def test_the_snapshot_is_not_read_through_a_symlink(tmp_path: Path) -> None:
    """The lock path is opened O_NOFOLLOW against a principal holding write access to the
    volume. The snapshot it guards needs the same defence: otherwise that principal plants
    `training.json` as a symlink and has the target's content served through the API and
    copied into a backup inside the data directory.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    foreign = tmp_path / "foreign.json"
    foreign.write_text(
        '{"schemaVersion": 1, "rev": 99, "sessions": [{"id": "not-ours"}]}', encoding="utf-8"
    )
    (data_dir / STORE_FILENAME).symlink_to(foreign)
    store = TrainingStore(data_dir, now=fixed_now)
    with pytest.raises(OSError, match=r"symbolic link|Too many levels|ELOOP|loop"):
        store.load()


def test_a_symlinked_snapshot_cannot_be_copied_into_a_backup(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    foreign = tmp_path / "foreign.json"
    foreign.write_text("secret-content", encoding="utf-8")
    (data_dir / STORE_FILENAME).symlink_to(foreign)
    store = TrainingStore(data_dir, now=fixed_now)
    with pytest.raises(OSError, match=r"symbolic link|Too many levels|ELOOP|loop"):
        store.upsert_session(dict(SESSION))
    for backup in data_dir.glob(f"{STORE_FILENAME}.*.bak"):
        assert "secret-content" not in backup.read_text(encoding="utf-8")
