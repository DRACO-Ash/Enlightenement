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

#: Cap on the actor field. Long enough for a real identity, short enough to bound growth.
MAX_ACTOR_LENGTH = 64

#: Cap on any other reflected value written to a log line (a request path, for example).
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
    return cleaned.strip()[:limit]


def sanitise_actor(raw: str | None, *, limit: int = MAX_ACTOR_LENGTH) -> str:
    """Return a safe, bounded actor label. Control characters (a newline above all)
    are dropped so a user-supplied value cannot inject a forged log line.
    """
    return sanitise_log_value(raw, limit=limit) or ANONYMOUS_ACTOR


def audit(event: str, *, actor: str | None = None, **fields: Any) -> str:
    """Emit one JSON audit line for a privileged action and return it.

    The return value exists so a test can assert the exact record without capturing
    log output. Callers pass counts, timings, and costs; never a credential.
    """
    record: dict[str, Any] = {"event": event, "actor": sanitise_actor(actor)}
    record.update(fields)
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
