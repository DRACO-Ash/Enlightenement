"""Persistence: an atomic, lock-serialised JSON store on the file-storage add-on.

Three properties make a write safe here, and all three are needed:

1. **Atomic.** Temp-write then rename, so a crash never leaves a half-written file and a
   reader never sees a partial one.
2. **Serialised.** An exclusive ``fcntl.flock`` is held across load, merge, and rename.
   Atomicity alone does NOT prevent lost updates: two processes can each load the same
   snapshot, each append, and the second rename silently discards the first write. That
   was measured at half of all records lost with two workers, and the atomic rename is
   exactly why the loss is invisible. POSIX only, which the Linux container satisfies.
3. **Revision-guarded.** Each snapshot carries a monotonic ``rev``. A caller may pass the
   revision it expects, and a mismatch is a visible 409 rather than a silent overwrite.
   This is the backstop for a filesystem where advisory locking does not hold, such as
   some network mounts.

Every merge is anti-shrink: a partial update never deletes a field the caller did not
send. A destructive overwrite takes a backup first and records that it did, which is what
makes a rollback real rather than assumed.
"""

from __future__ import annotations

import errno as errno_module
import fcntl
import json
import logging
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Stamped into every snapshot. Bump it with a forward, idempotent migration.
SCHEMA_VERSION = 1

#: The snapshot filename inside the data directory.
STORE_FILENAME = "training.json"

#: The advisory lock file guarding every write. Never holds data.
LOCK_FILENAME = "training.lock"

#: Cap on stored sessions. The newest are kept; a fresh entry is never the one dropped.
MAX_SESSIONS = 500

#: How many timestamped backups to retain, so storage does not grow without limit.
BACKUP_RETENTION = 5

_logger = logging.getLogger("enlightenment.storage")

Snapshot = dict[str, Any]
Session = dict[str, Any]


class UnknownSessionError(LookupError):
    """Raised when a caller required an existing session and none was found.

    Checked INSIDE the exclusive lock. Checking existence before taking the lock left a
    window in which a concurrent write could trip the session cap and evict the id, turning
    an intended merge into an append of a partial record.
    """

    def __init__(self, session_id: object) -> None:
        super().__init__(f"no session with id {session_id!r}")
        self.session_id = session_id


class StaleRevisionError(RuntimeError):
    """Raised when a caller's expected revision no longer matches the stored one."""

    def __init__(self, expected: int, current: int) -> None:
        super().__init__(f"expected revision {expected}, store is at {current}")
        self.expected = expected
        self.current = current


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


@dataclass(frozen=True, slots=True)
class WriteResult:
    """What a completed write did, measured inside the lock rather than re-read after it."""

    session: Session
    rev: int
    count_before: int
    count_after: int


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
    return {"schemaVersion": SCHEMA_VERSION, "rev": 0, "sessions": []}


def migrate(snapshot: Snapshot) -> Snapshot:
    """Migrate a snapshot forward additively. Unrecognised fields are preserved, never
    dropped, so an older reader's data survives a newer writer.
    """
    migrated = dict(snapshot)
    migrated.setdefault("schemaVersion", SCHEMA_VERSION)
    migrated.setdefault("sessions", [])
    migrated.setdefault("rev", 0)
    if not isinstance(migrated["sessions"], list):
        # ValueError, not TypeError: this is a data-validation failure at the store
        # boundary, which every caller already handles, not a programming type error.
        raise ValueError("stored snapshot is malformed: 'sessions' is not a list")  # noqa: TRY004
    if not isinstance(migrated["rev"], int) or isinstance(migrated["rev"], bool):
        raise ValueError("stored snapshot is malformed: 'rev' is not an integer")  # noqa: TRY004
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
    """The serialised writer for the training snapshot in ``data_dir``.

    "Serialised", not "single": correctness does not depend on there being one process,
    because the deploy target can restart or scale the pod at will.
    """

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

    @property
    def lock_path(self) -> Path:
        """Absolute path of the advisory lock file."""
        return self._data_dir / LOCK_FILENAME

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        """Hold an exclusive advisory lock for the whole read-modify-write."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # O_NOFOLLOW: a principal with write access to the volume could otherwise plant the
        # lock path as a symlink and de-serialise every writer. Cheap to close, so closed.
        handle = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            os.close(handle)

    def seed(self) -> Snapshot:
        """Create the snapshot if absent and return it. Idempotent on re-run."""
        with self._exclusive():
            if self.path.exists():
                return self.load()
            snapshot = empty_snapshot()
            self._write_atomic(snapshot, backup=False)
            return snapshot

    def _read_snapshot_bytes(self) -> bytes:
        """Read the snapshot without following a symlink.

        The lock path is opened ``O_NOFOLLOW`` against a principal holding write access to
        the volume; the snapshot it guards needs the same defence, or that principal can
        plant ``training.json`` as a symlink and have its target served through the API and
        copied into a backup inside the data directory.
        """
        handle = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(handle, "rb") as stream:
            return stream.read()

    def load(self) -> Snapshot:
        """Read and migrate the snapshot, returning an empty one when none exists."""
        try:
            raw = self._read_snapshot_bytes().decode("utf-8")
        except FileNotFoundError:
            return empty_snapshot()
        except UnicodeDecodeError as exc:
            # Not valid data, and the caller distinguishes invalid data from a caller fault. A
            # snapshot that is not UTF-8 is exactly as unusable as one that is not JSON.
            raise ValueError(f"stored snapshot is not valid UTF-8: {exc.reason}") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"stored snapshot is not valid JSON: {exc.msg}") from exc
        except RecursionError as exc:
            raise ValueError("stored snapshot is nested too deeply to parse") from exc
        if not isinstance(parsed, dict):
            # ValueError for the same reason as in migrate(): a malformed snapshot is
            # invalid data, not a caller type error.
            raise ValueError(  # noqa: TRY004
                "stored snapshot is malformed: top level is not an object"
            )
        return migrate(parsed)

    def revision(self) -> int:
        """The stored revision, for a caller that wants to guard its next write."""
        return int(self.load()["rev"])

    def sessions(self) -> list[Session]:
        """Every stored session, oldest first."""
        stored = self.load()["sessions"]
        return [dict(session) for session in stored]

    def upsert_session(
        self,
        record: Session,
        *,
        expected_rev: int | None = None,
        must_exist: bool = False,
    ) -> WriteResult:
        """Insert or anti-shrink-merge ``record`` by its ``id`` and persist the result.

        The whole read-modify-write runs under the exclusive lock, so a concurrent writer
        in another process cannot lose this update. When ``expected_rev`` is given and no
        longer matches, :class:`StaleRevisionError` is raised instead of overwriting. When
        ``must_exist`` is set and the id is absent, :class:`UnknownSessionError` is raised
        rather than creating a partial record.
        """
        with self._exclusive():
            snapshot = self.load()
            current_rev = int(snapshot["rev"])
            if expected_rev is not None and expected_rev != current_rev:
                raise StaleRevisionError(expected_rev, current_rev)

            stored: list[Session] = list(snapshot["sessions"])
            if must_exist and not any(item.get("id") == record.get("id") for item in stored):
                raise UnknownSessionError(record.get("id"))
            count_before = len(stored)
            stamped = self._apply(stored, record)
            stored = self._enforce_cap(stored)

            snapshot["sessions"] = stored
            snapshot["rev"] = current_rev + 1
            self._write_atomic(snapshot, backup=True)
            return WriteResult(
                session=stamped,
                rev=current_rev + 1,
                count_before=count_before,
                count_after=len(stored),
            )

    def _apply(self, stored: list[Session], record: Session) -> Session:
        """Insert or merge ``record`` into ``stored`` in place, returning the result."""
        stamped = dict(record)
        stamped["updatedAt"] = self._now().isoformat()
        index = next(
            (i for i, item in enumerate(stored) if item.get("id") == stamped.get("id")),
            None,
        )
        if index is None:
            stamped.setdefault("createdAt", stamped["updatedAt"])
            stored.append(stamped)
            return stamped
        stamped = merge_session(stored[index], stamped)
        stored[index] = stamped
        return stamped

    def _enforce_cap(self, stored: list[Session]) -> list[Session]:
        """Keep the newest within the cap. The fresh entry is at the end, never the loss."""
        dropped = max(0, len(stored) - self._max_sessions)
        if not dropped:
            return stored
        _logger.warning(
            "session cap reached, pruned %d oldest record(s) to stay within %d",
            dropped,
            self._max_sessions,
        )
        return stored[dropped:]

    def _write_atomic(self, snapshot: Snapshot, *, backup: bool) -> None:
        """Write ``snapshot`` durably: back up the current file, write a sibling temp
        file, fsync it, then rename over the target. Called only under the lock.
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
        # Same mode as the snapshot itself (0600). A backup holding identical data under a
        # weaker mode, on a volume that may be shared with an add-on, is a downgrade.
        handle = os.open(target, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(handle, "wb") as stream:
            stream.write(self._read_snapshot_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        _logger.info("pre-write backup taken: %s", target.name)
        backups = sorted(self._data_dir.glob(f"{STORE_FILENAME}.*.bak"))
        for stale in backups[:-BACKUP_RETENTION]:
            stale.unlink(missing_ok=True)
