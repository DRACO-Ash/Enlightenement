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
    assert len(sanitise_log_value("x" * 5000)) == MAX_LOG_VALUE_LENGTH


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
