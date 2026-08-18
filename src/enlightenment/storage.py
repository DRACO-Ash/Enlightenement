"""Persistence: an atomic JSON store on the file-storage add-on.

Every write is temp-write-then-rename, so a crash never leaves a half-written file.
Every merge is anti-shrink: a partial update never deletes a field the caller did not
send. The stored snapshot carries a schema version so a later shape change can migrate
forward additively. A destructive overwrite takes a backup first and records that it
did, which is what makes a rollback real rather than assumed.
"""

from __future__ import annotations

import errno as errno_module
import json
import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Stamped into every snapshot. Bump it with a forward, idempotent migration.
SCHEMA_VERSION = 1

#: The snapshot filename inside the data directory.
STORE_FILENAME = "training.json"

#: Cap on stored sessions. The newest are kept; a fresh entry is never the one dropped.
MAX_SESSIONS = 500

#: How many timestamped backups to retain, so storage does not grow without limit.
BACKUP_RETENTION = 5

_logger = logging.getLogger("enlightenment.storage")

Snapshot = dict[str, Any]
Session = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """The outcome of proving storage with a real write."""

    ok: bool
    resolved: str
    errno: int | None = None
    detail: str = ""

    def as_diagnostic(self) -> dict[str, Any]:
        """A secret-free view for the diagnostics read-out and the 503 body.

        The resolved path and the errno are operational detail, not a leak: a
        screenshot of this is a complete diagnosis, which is the whole point.
        """
        return {
            "writable": self.ok,
            "resolvedDataDir": self.resolved,
            "errno": self.errno,
            "errnoName": errno_module.errorcode.get(self.errno, "") if self.errno else "",
            "detail": self.detail,
        }


def probe_writable(data_dir: Path) -> ProbeResult:
    """Prove the storage directory with a REAL write, never an existence check.

    ``mkdir`` on an existing directory succeeds without write permission, so a
    root-owned or read-only mount passes an existence check and then fails the first
    real write. The App Store's non-root container against a root-owned volume add-on
    returns ``EACCES`` until ``securityContext.fsGroup`` is set, and this is the probe
    that says so out loud.
    """
    resolved = str(data_dir)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        handle, temp_path = tempfile.mkstemp(dir=resolved, prefix=".writeprobe-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write("probe")
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            Path(temp_path).unlink(missing_ok=True)
    except OSError as exc:
        return ProbeResult(
            ok=False,
            resolved=resolved,
            errno=exc.errno,
            detail=exc.strerror or exc.__class__.__name__,
        )
    return ProbeResult(ok=True, resolved=resolved)


def empty_snapshot() -> Snapshot:
    """A valid, empty snapshot at the current schema version."""
    return {"schemaVersion": SCHEMA_VERSION, "sessions": []}


def migrate(snapshot: Snapshot) -> Snapshot:
    """Migrate a snapshot forward additively. Unrecognised fields are preserved, never
    dropped, so an older reader's data survives a newer writer.
    """
    migrated = dict(snapshot)
    migrated.setdefault("schemaVersion", SCHEMA_VERSION)
    migrated.setdefault("sessions", [])
    if not isinstance(migrated["sessions"], list):
        # ValueError, not TypeError: this is a data-validation failure at the store
        # boundary, which every caller already handles, not a programming type error.
        raise ValueError("stored snapshot is malformed: 'sessions' is not a list")  # noqa: TRY004
    migrated["schemaVersion"] = SCHEMA_VERSION
    return migrated


def merge_session(existing: Session, update: Session) -> Session:
    """Anti-shrink merge: keys present in ``update`` win, keys absent from it keep the
    stored value. A partial payload can never delete a field it did not mention.
    """
    merged = dict(existing)
    merged.update({key: value for key, value in update.items() if value is not None})
    return merged


class TrainingStore:
    """The single writer for the training snapshot in ``data_dir``."""

    def __init__(
        self,
        data_dir: Path,
        *,
        now: Callable[[], datetime] | None = None,
        max_sessions: int = MAX_SESSIONS,
    ) -> None:
        self._data_dir = data_dir
        self._now = now if now is not None else lambda: datetime.now(tz=UTC)
        self._max_sessions = max_sessions

    @property
    def path(self) -> Path:
        """Absolute path of the snapshot file."""
        return self._data_dir / STORE_FILENAME

    def seed(self) -> Snapshot:
        """Create the snapshot if absent and return it. Idempotent on re-run."""
        if self.path.exists():
            return self.load()
        snapshot = empty_snapshot()
        self._write_atomic(snapshot, backup=False)
        return snapshot

    def load(self) -> Snapshot:
        """Read and migrate the snapshot, returning an empty one when none exists."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return empty_snapshot()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"stored snapshot is not valid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            # ValueError for the same reason as in migrate(): a malformed snapshot is
            # invalid data, not a caller type error.
            raise ValueError(  # noqa: TRY004
                "stored snapshot is malformed: top level is not an object"
            )
        return migrate(parsed)

    def sessions(self) -> list[Session]:
        """Every stored session, oldest first."""
        stored = self.load()["sessions"]
        return [dict(session) for session in stored]

    def upsert_session(self, record: Session) -> Session:
        """Insert or anti-shrink-merge ``record`` by its ``id`` and persist the result."""
        snapshot = self.load()
        stored: list[Session] = list(snapshot["sessions"])
        stamped = dict(record)
        stamped["updatedAt"] = self._now().isoformat()

        index = next(
            (i for i, item in enumerate(stored) if item.get("id") == stamped.get("id")),
            None,
        )
        if index is None:
            stamped.setdefault("createdAt", stamped["updatedAt"])
            stored.append(stamped)
        else:
            stamped = merge_session(stored[index], stamped)
            stored[index] = stamped

        dropped = max(0, len(stored) - self._max_sessions)
        if dropped:
            # Keep the newest. The fresh entry is at the end, so it is never the loss.
            stored = stored[dropped:]
            _logger.warning(
                "session cap reached, pruned %d oldest record(s) to stay within %d",
                dropped,
                self._max_sessions,
            )

        snapshot["sessions"] = stored
        self._write_atomic(snapshot, backup=True)
        return stamped

    def _write_atomic(self, snapshot: Snapshot, *, backup: bool) -> None:
        """Write ``snapshot`` durably: back up the current file, write a sibling temp
        file, fsync it, then rename over the target. Rename is atomic on one filesystem,
        so a reader never observes a partial write.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        if backup and self.path.exists():
            self._take_backup()
        payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
        handle, temp_name = tempfile.mkstemp(dir=str(self._data_dir), prefix=".snapshot-")
        temp_path = Path(temp_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temp_path.replace(self.path)
        except OSError:
            temp_path.unlink(missing_ok=True)
            raise

    def _take_backup(self) -> None:
        """Copy the current snapshot to a timestamped file and prune old backups."""
        stamp = self._now().strftime("%Y%m%dT%H%M%S%f")
        target = self._data_dir / f"{STORE_FILENAME}.{stamp}.bak"
        target.write_bytes(self.path.read_bytes())
        _logger.info("pre-write backup taken: %s", target.name)
        backups = sorted(self._data_dir.glob(f"{STORE_FILENAME}.*.bak"))
        for stale in backups[:-BACKUP_RETENTION]:
            stale.unlink(missing_ok=True)
