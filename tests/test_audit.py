"""Audit and event lines are one JSON object each, sanitised, bounded, and secret-free."""

from __future__ import annotations

import json

import pytest

from enlightenment.audit import (
    ANONYMOUS_ACTOR,
    MAX_ACTOR_LENGTH,
    MAX_LOG_VALUE_LENGTH,
    audit,
    log_event,
    sanitise_actor,
    sanitise_log_value,
)


def test_newline_injection_cannot_forge_a_second_line() -> None:
    forged = 'ada\n{"event":"deploy","actor":"root"}'
    assert "\n" not in sanitise_actor(forged)
    assert sanitise_actor(forged).startswith("ada")


def test_actor_is_length_bounded() -> None:
    assert len(sanitise_actor("a" * 500)) == MAX_ACTOR_LENGTH


def test_missing_or_blank_actor_becomes_anonymous() -> None:
    assert sanitise_actor(None) == ANONYMOUS_ACTOR
    assert sanitise_actor("   ") == ANONYMOUS_ACTOR
    assert sanitise_actor("\r\n") == ANONYMOUS_ACTOR


@pytest.mark.parametrize("hostile", ["a\nb", "a\rb", "a\tb", "a\x00b"])
def test_no_control_character_survives_a_reflected_value(hostile: str) -> None:
    cleaned = sanitise_log_value(hostile)
    assert all(ch not in cleaned for ch in "\r\n\t\x00")


def test_a_reflected_value_is_length_bounded() -> None:
    """Bounded in BYTES, which is the unit the log line is measured in.

    This sink cut CODE POINTS until V0.26.25, and it was the last one left in the old unit after
    the served caps moved to bytes. Measured by the security gate: one anonymous request whose
    path carried 400 emoji produced a `request.rejected` line of 2,945 bytes against a documented
    cap of 256, because a log line renders with `ensure_ascii=True` and one astral character
    becomes twelve ASCII characters.

    The escaping factor is asserted rather than described: a value cut to 256 bytes is at most 64
    astral characters and so at most 768 rendered characters. A constant multiple of the cap, never
    content's choice, which is the whole property.
    """
    assert len(sanitise_log_value("x" * 5000)) == MAX_LOG_VALUE_LENGTH

    astral = sanitise_log_value("\U0001f600" * 5000)
    assert len(astral.encode("utf-8")) <= MAX_LOG_VALUE_LENGTH, (
        f"the log sink cut {len(astral.encode('utf-8'))} bytes against a bound of"
        f" {MAX_LOG_VALUE_LENGTH}, so it is counting code points"
    )
    assert "\ufffd" not in astral, "the cut split a code point"
    #: The RENDERED line, which is where the amplification lands, asserted at the REAL ratio.
    #: This was `12 * MAX_LOG_VALUE_LENGTH` = 3072, four times looser than the 768 the code
    #: claims - and under the code-point revert it fired only because 256 emoji render as 3074
    #: against 3072, so a cap of 255 would have slipped past green. A binding test that binds
    #: less than it claims is the fault `CLAUDE.md` names as worse than no test.
    #:
    #: 3.0 rendered characters per UTF-8 byte is the GLOBAL worst case, brute-forced over all
    #: 1,114,112 code points: attained by an astral character (4 bytes to 12) and equally by any
    #: 2-byte BMP character (U+00A1 renders as `\u00a1`, 2 bytes to 6). Plus the two quotes
    #: `json.dumps` adds.
    rendered = len(json.dumps(astral))
    assert rendered <= 3 * MAX_LOG_VALUE_LENGTH + 2, rendered


def test_an_empty_reflected_value_stays_empty_rather_than_becoming_anonymous() -> None:
    assert sanitise_log_value(None) == ""
    assert sanitise_log_value("") == ""


def test_audit_emits_one_parsable_json_line_with_the_given_fields() -> None:
    line = audit("session.upsert", actor="team", sessionId="alpha", countBefore=0, countAfter=1)
    assert "\n" not in line
    assert json.loads(line) == {
        "actor": "team",
        "countAfter": 1,
        "countBefore": 0,
        "event": "session.upsert",
        "sessionId": "alpha",
    }


def test_an_audit_line_sanitises_every_string_field_not_only_the_actor() -> None:
    """`audit()` merged its extra fields raw while `log_event()` beside it sanitised every string.

    The register claimed "every reflected value LENGTH-CAPPED", and the two tests it cited assert
    the sanitiser in isolation, not `audit()`'s use of it. Measured by the security gate:
    `audit("probe", actor="a", note="x" * 10_000)` emitted all ten thousand characters.

    Unreachable from either route today - the only string field they pass is a session id already
    matched against `SESSION_ID_PATTERN`, and a 404 raises before the call - so this closed an
    over-claim rather than an exploit. Closed in the code, because the alternative was weakening
    the register to match a weaker control.
    """
    line = json.loads(audit("probe", actor="operator", note="x" * 10_000, count=3))
    assert len(line["note"]) == MAX_LOG_VALUE_LENGTH
    assert line["count"] == 3, "a non-string field must pass through untouched"

    forged = json.loads(audit("probe", actor="operator", note="a\nb\rc"))
    assert "\n" not in forged["note"]
    assert "\r" not in forged["note"]


def test_an_event_line_sanitises_every_string_field_structurally() -> None:
    """A crafted request path must not be able to confuse a JSON log pipeline."""
    line = log_event("request.rejected", path='/x\n{"event":"deploy"}', reason="validation")
    assert "\n" not in line
    record = json.loads(line)
    assert record["event"] == "request.rejected"
    assert record["reason"] == "validation"
    assert "\n" not in record["path"]


def test_an_event_line_leaves_non_string_fields_intact() -> None:
    record = json.loads(log_event("boot.storage", writable=False, errno=13, detail=""))
    assert record["writable"] is False
    assert record["errno"] == 13
