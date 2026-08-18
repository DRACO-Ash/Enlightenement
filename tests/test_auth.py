"""The token comparison fails closed and leaks nothing through length or timing."""

from __future__ import annotations

from enlightenment.auth import token_ok


def test_no_configured_token_cannot_authorise() -> None:
    assert token_ok("anything", "") is False
    assert token_ok(None, "") is False


def test_exact_match_passes() -> None:
    assert token_ok("s3cret-value", "s3cret-value") is True


def test_wrong_value_of_the_same_length_fails() -> None:
    assert token_ok("s3cret-valuf", "s3cret-value") is False


def test_length_mismatch_fails_without_comparing() -> None:
    assert token_ok("s3cret", "s3cret-value") is False
    assert token_ok("s3cret-value-long", "s3cret-value") is False


def test_missing_header_fails() -> None:
    assert token_ok(None, "s3cret-value") is False
    assert token_ok("", "s3cret-value") is False
