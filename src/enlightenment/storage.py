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

from enlightenment.audit import sanitise_log_value
from enlightenment.identifiers import MAX_NESTING_DEPTH, unservable_pointer

#: Stamped into every snapshot. Bump it with a forward, idempotent migration.
SCHEMA_VERSION = 1

#: The snapshot filename inside the data directory.
STORE_FILENAME = "training.json"

#: The advisory lock file guarding every write. Never holds data.
LOCK_FILENAME = "training.lock"

#: Cap on stored sessions. The newest are kept; a fresh entry is never the one dropped.
MAX_SESSIONS = 500

#: Longest revision, in digits, on either side of the wire. Comfortably past any real revision (a
#: 64-bit counter is 19 digits) and far below CPython's 4,300-digit integer conversion limit,
#: which a longer value would trip as a bare `ValueError`. It lives here rather than in `app`
#: because the STORED side needs it and `storage` cannot import from `app`; `app` re-exports it,
#: so the request cap and the storage cap can never drift apart again.
MAX_REVISION_DIGITS = 19

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
    # The ELEMENTS, not only the container. Checking the list and not its members left a shape
    # refused nowhere, and it failed two different ways:
    #
    # ● `{"rev": 1, "sessions": [1]}` loaded, and `dict(session)` then raised `TypeError` - not
    #   `ValueError` - so it escaped the 503 this module's callers map and reached an anonymous
    #   caller as a **500 on `GET /api/v1/sessions`**, with both gated writes 500 as well and
    #   `/healthz` still 200. An operator's screenshot shows a healthy pod serving tracebacks.
    # ● Worse: `[[["id", "GHOST-ONE"], ["title", "Fabricated"]]]` is a list of PAIRS, and `dict()`
    #   coerces it into a session row nobody ever wrote. Measured, `sessions()` returned
    #   `[{"id": "GHOST-ONE", "title": "Fabricated"}]` and the anonymous listing served it with an
    #   honest-looking `count` and `total`. **That is a fabricated record on a read boundary**,
    #   which breaks the hard rule against inventing data outright, and no length cap or byte
    #   ceiling can see it because the row is well-formed once coerced.
    #
    # The precondition is write access to the data volume, the actor this threat model puts out of
    # scope - the same precondition as the surrogate refusal above, and refused here for the same
    # stated reason: dataset integrity sits above its secrecy, and a route that 500s on its own
    # data cannot be diagnosed from a screenshot.
    if any(not isinstance(entry, dict) for entry in migrated["sessions"]):
        raise ValueError("stored snapshot is malformed: 'sessions' holds a non-object entry")
    if not isinstance(migrated["rev"], int) or isinstance(migrated["rev"], bool):
        raise ValueError("stored snapshot is malformed: 'rev' is not an integer")  # noqa: TRY004
    # MAGNITUDE, not only type, and bounded to the same figure the REQUEST side already uses.
    # `app.py` caps a submitted `If-Match` at `MAX_REVISION_DIGITS` and the stored value had no
    # bound at all, so the two sides of one number disagreed. The `ETag` is built from it and a
    # header is not covered by any body ceiling: measured, a planted 4,000-digit `rev` produced a
    # 4,004-byte `ETag` on the anonymous listing. Past 4,300 digits it happened to 503 anyway,
    # through CPython's integer-to-string conversion limit surfacing as a bare `ValueError` - a
    # bound by accident, which is the kind this project does not keep.
    if len(str(abs(migrated["rev"]))) > MAX_REVISION_DIGITS:
        raise ValueError(
            f"stored snapshot is malformed: 'rev' has more than {MAX_REVISION_DIGITS} digits"
        )
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
        # The SAME boundary rule the content tree gets, and it was missing here. A lone surrogate
        # is legal JSON and cannot be encoded, so it parses cleanly and then raises inside
        # pydantic's serialiser while the response is being rendered: measured, a **500 on the
        # unauthenticated `GET /api/v1/sessions`**. Not reachable from the HTTP edge - six body
        # forms all answer 422 - so the precondition is write access to the data volume, an actor
        # this threat model puts out of scope. Closed anyway, because "the snapshot is trusted
        # stored state" and "the progress file is not" were two different answers to one question
        # in adjacent modules, and because a route that 500s on data it wrote itself is a route
        # nobody can diagnose.
        if unservable := unservable_pointer(parsed):
            where, total, kind = unservable
            if kind == "depth":
                raise ValueError(
                    f"stored snapshot nests deeper than {MAX_NESTING_DEPTH}, which the response"
                    f" serialiser refuses; one is at {sanitise_log_value(where)}"
                )
            # `sanitise_log_value` at the RAISE, not at the wire. This message is the first of the
            # store's to carry FILE CONTENT - a JSON pointer contains the key names it walks
            # through - and `app.py` logs it with `_logger.exception`, whose traceback renders the
            # exception text verbatim. Measured: a snapshot key of
            # `X\nENLIGHTENMENT FORGED {"event":...}` landed in the log record as a forged second
            # line, raw surrogate included and unbounded in length, past the claim that every
            # reflected value reaching a log line goes through the shared sanitiser.
            #
            # Bounding it here bounds both copies at once, which is why it is not done at the two
            # call sites: two sanitisers for one string is how they diverge.
            raise ValueError(
                f"stored snapshot has {total} string(s) that cannot be encoded as UTF-8;"
                f" one is at {sanitise_log_value(where)}"
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
