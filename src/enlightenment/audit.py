"""The audit trail: one structured JSON line per privileged action.

No secret ever appears in an audit line. Any user-supplied portion of a field is
sanitised and length-bounded, so a crafted value cannot forge a second log line through
an embedded newline or grow the log without limit. The same sanitiser is applied to
every reflected value that reaches a log sink, not only to the audit actor: relying on a
third-party parser to strip control characters as a side effect makes the escaping
incidental rather than structural.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from enlightenment.identifiers import cut_to_bytes

#: Cap on the actor field. Long enough for a real identity, short enough to bound growth.
MAX_ACTOR_LENGTH = 64

#: Cap on any other reflected value written to a log line (a request path, for example), in BYTES
#: of UTF-8. It cut CODE POINTS until V0.26.25, which left this sink the last one in the old unit
#: after `docs/SECURITY.md` had begun asserting that every ceiling here is in bytes. Measured: one
#: anonymous request whose path carried 400 emoji produced a `request.rejected` line of 2,945
#: bytes against a documented cap of 256.
#:
#: **The escaping factor is stated rather than defended.** A log line renders with
#: `ensure_ascii=True`, so one astral character becomes twelve ASCII characters on the way out: a
#: value cut to 256 bytes is at most 64 astral characters and so at most 768 rendered characters.
#: Bounded, and a constant multiple rather than content's choice, which is the property this cap
#: exists for.
MAX_LOG_VALUE_LENGTH = 256

#: Placeholder recorded when no identity could be resolved.
ANONYMOUS_ACTOR = "anonymous"

_logger = logging.getLogger("enlightenment.audit")
_event_logger = logging.getLogger("enlightenment.event")


def sanitise_log_value(raw: str | None, *, limit: int = MAX_LOG_VALUE_LENGTH) -> str:
    """Return a safe, bounded single-line rendering of an untrusted value."""
    if not raw:
        return ""
    cleaned = "".join(ch for ch in raw if ch.isprintable() and ch not in "\r\n")
    return cut_to_bytes(cleaned.strip(), limit)


def sanitise_actor(raw: str | None, *, limit: int = MAX_ACTOR_LENGTH) -> str:
    """Return a safe, bounded actor label. Control characters (a newline above all)
    are dropped so a user-supplied value cannot inject a forged log line.
    """
    return sanitise_log_value(raw, limit=limit) or ANONYMOUS_ACTOR


def audit(event: str, *, actor: str | None = None, **fields: Any) -> str:
    """Emit one JSON audit line for a privileged action and return it.

    The return value exists so a test can assert the exact record without capturing
    log output. Callers pass counts, timings, and costs; never a credential.

    **Every string field is sanitised and capped, not only the actor.** `record.update(fields)`
    merged them raw, so `audit("probe", actor="a", note="x" * 10_000)` emitted all ten thousand
    characters while the register claimed "every reflected value LENGTH-CAPPED". No caller could
    reach it - the only string field either route passes is a session id already matched against
    `SESSION_ID_PATTERN`, and a 404 raises before the call - so this closes an over-claim rather
    than an exploit. It is closed in the code because the alternative was narrowing the register
    to match a weaker control, and :func:`log_event` beside it already did the right thing.
    """
    record: dict[str, Any] = {"event": event, "actor": sanitise_actor(actor)}
    for key, value in fields.items():
        record[key] = sanitise_log_value(value) if isinstance(value, str) else value
    line = json.dumps(record, separators=(",", ":"), sort_keys=True, default=str)
    _logger.info(line)
    return line


def log_event(event: str, **fields: Any) -> str:
    """Emit one JSON operational line, sanitising every string field.

    Structural escaping, not incidental: the line is JSON, and every untrusted string is
    put through :func:`sanitise_log_value` before it gets there, so a log pipeline
    consuming these cannot be confused by a crafted request path.
    """
    record: dict[str, Any] = {"event": event}
    for key, value in fields.items():
        record[key] = sanitise_log_value(value) if isinstance(value, str) else value
    line = json.dumps(record, separators=(",", ":"), sort_keys=True, default=str)
    _event_logger.info(line)
    return line
