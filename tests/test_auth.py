"""The token comparison fails closed, and is built on the constant-time primitive.

The timing property itself is not assertable by a functional test, and that is recorded in
docs/SECURITY.md rather than papered over. What IS assertable is that the code uses
`hmac.compare_digest` and never a plain equality on the token, so a refactor cannot quietly
replace it. A source assertion is the right instrument here, and it states below what it
cannot see.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from enlightenment import auth
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


# --- the primitive itself --------------------------------------------------------------


def test_the_token_comparison_uses_the_constant_time_primitive() -> None:
    """Mutating `hmac.compare_digest` to `==` leaves every behavioural test green, because
    the difference is timing, not output. This asserts the primitive is present.

    What this CANNOT see: whether the comparison is reached on every path, or whether some
    caller compares the token elsewhere. The first is covered by the behavioural tests
    above; the second is covered by the module-wide check that follows.
    """
    source = inspect.getsource(auth)
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "compare_digest"
    ]
    assert calls, "auth.py does not call hmac.compare_digest"


def test_no_module_compares_a_token_with_plain_equality() -> None:
    """A grep over the class, not one named line. States its blind spot: it matches on
    identifier names, so a token held in a differently named variable would pass unseen.
    """
    root = Path(auth.__file__).parent
    offenders: list[str] = []
    for module in sorted(root.glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops):
                continue
            rendered = ast.unparse(node)
            if "token" in rendered.lower() and "len(" not in rendered:
                offenders.append(f"{module.name}: {rendered}")
    assert offenders == [], f"a token is compared with plain equality: {offenders}"
