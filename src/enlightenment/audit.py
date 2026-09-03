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

#: Cap on the actor field, in BYTES **by delegation**: `sanitise_actor` calls `sanitise_log_value`,
#: so the byte cut applies here too. Recorded because the reasoning that nearly left it out was
#: that the actor is server-chosen rather than content-supplied - true, but not what makes it
#: byte-bounded, and a reader told this field was deliberately left unconverted might convert it
#: again and cut it twice. Long enough for a real identity, short enough to bound growth.
MAX_ACTOR_LENGTH = 64

#: Cap on any other reflected value written to a log line (a request path, for example), in BYTES
#: of UTF-8. It cut CODE POINTS until V0.26.25, which left this sink the last one in the old unit
#: after `docs/SECURITY.md` had begun asserting that every ceiling here is in bytes. Measured: one
#: anonymous request whose path carried 400 emoji produced a `request.rejected` line of 2,945
#: bytes against a documented cap of 256.
#:
#: **The escaping factor is stated per BYTE, because that is the unit the cap is in and the worst
#: case is not astral.** A log line renders with `ensure_ascii=True`, and the global maximum is
#: **3.0 rendered ASCII characters per UTF-8 byte, over the code points that SURVIVE THE STRIP
#: ABOVE** - brute-forced over all 1,114,112 and attained twice among the printable ones: by an
#: astral character (4 bytes becoming 12) and equally by any 2-byte BMP character, since `U+00A1`
#: renders as `\u00a1`, 2 bytes becoming 6. A backslash or a quote is 2.0 and 3-byte CJK is 2.0,
#: so neither is the bound. So 256 bytes is at most 768 rendered characters.
#:
#: **The scoping is the whole claim, and two earlier versions of this comment got it wrong in
#: opposite directions.** The first gave 3.0 from the astral case alone, covering one of the two
#: characters that attain it. The second said "over all 1,114,112 code points", which is false:
#: the true global maximum is **6.0, at `U+0000`**, one byte rendering as `\u0000`. That
#: character never reaches here because `isprintable()` drops it - so the `isprintable()` filter
#: is load-bearing for this bound and not merely tidy, and a future change that relaxed it would
#: double the factor while this figure went on reading as measured.
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
