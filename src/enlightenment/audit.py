"""The audit trail: one structured JSON line per privileged action.

No secret ever appears in an audit line. Any user-supplied portion of a field is
sanitised and length-bounded, so a crafted actor cannot forge a second log line
through an embedded newline or grow the log without limit.
"""

from __future__ import annotations

import json
import logging
from typing import Any

#: Cap on the actor field. Long enough for a real identity, short enough to bound growth.
MAX_ACTOR_LENGTH = 64

#: Placeholder recorded when no identity could be resolved.
ANONYMOUS_ACTOR = "anonymous"

_logger = logging.getLogger("enlightenment.audit")


def sanitise_actor(raw: str | None, *, limit: int = MAX_ACTOR_LENGTH) -> str:
    """Return a safe, bounded actor label. Control characters (a newline above all)
    are dropped so a user-supplied value cannot inject a forged log line.
    """
    if not raw:
        return ANONYMOUS_ACTOR
    cleaned = "".join(ch for ch in raw if ch.isprintable() and ch not in "\r\n")
    cleaned = cleaned.strip()[:limit]
    return cleaned or ANONYMOUS_ACTOR


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
