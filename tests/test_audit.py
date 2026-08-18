"""Audit lines are one JSON object, sanitised, bounded, and secret-free."""

from __future__ import annotations

import json

from enlightenment.audit import ANONYMOUS_ACTOR, MAX_ACTOR_LENGTH, audit, sanitise_actor


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


def test_audit_emits_one_parsable_json_line_with_the_given_fields() -> None:
    line = audit("session.upsert", actor="team", sessionId="alpha", countBefore=0, countAfter=1)
    assert "\n" not in line
    record = json.loads(line)
    assert record == {
        "actor": "team",
        "countAfter": 1,
        "countBefore": 0,
        "event": "session.upsert",
        "sessionId": "alpha",
    }
