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
    the difference is timing, not output. This asserts the primitive is on the DECIDING path.

    **"Present in the module" was not enough, and the gap was demonstrated, not theorised.**
    The security gate rewrote the comparison to

        if len(supplied) != len(reference):
            return hmac.compare_digest(b"x", b"y")
        return supplied == reference

    and both cited tests stayed green: this one because a `compare_digest` call still existed
    somewhere in the module, and the `==` census because it matches identifier names and the
    shipped operands are `supplied` and `reference` - so the "declared blind spot" was the actual
    shipped naming, not a hypothetical rename. A decoy call satisfied the check while plain
    equality decided authentication.

    So it asserts the structure that matters: EVERY `return` in `token_ok` whose value is not a
    bare constant must have `compare_digest` in it. A decoy call on a different branch no longer
    helps, because the branch that decides is a return too and it has to carry the primitive.

    What this still cannot see: the timing property itself, which no functional test can assert,
    and a caller comparing the token elsewhere - which is the census below.
    """
    source = inspect.getsource(auth)
    tree = ast.parse(source)

    def has_compare_digest(node: ast.AST) -> bool:
        return any(
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "compare_digest"
            for inner in ast.walk(node)
        )

    assert has_compare_digest(tree), "auth.py does not call hmac.compare_digest"

    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "token_ok"
    ]
    assert len(functions) == 1, "expected exactly one token_ok in auth.py"

    deciding = [
        ast.unparse(node)
        for node in ast.walk(functions[0])
        if isinstance(node, ast.Return)
        # A bare `return False` is the fail-closed guard, not a comparison of the token.
        and node.value is not None
        and not isinstance(node.value, ast.Constant)
    ]
    assert deciding, "token_ok returns no computed value, so nothing compares the token"
    uncovered = [rendered for rendered in deciding if "compare_digest" not in rendered]
    assert not uncovered, (
        "token_ok has a computed return that does not use the constant-time primitive, so a"
        f" decoy call elsewhere in the module would satisfy this check: {uncovered}"
    )


def test_no_module_compares_a_token_with_plain_equality() -> None:
    """A census over the class, not one named line, and it had two undeclared holes.

    `glob("*.py")` scanned the package root only, so `physics/` and `scenario/` were never read -
    a package census that skipped two packages. `rglob` now.

    The other was the exclusion. `"len(" not in rendered` was there to permit the legitimate
    length guard, and it permitted a great deal more: `token == expected and len(x) > 0` renders
    with `len(` in it and passed unseen. The test asks the structural question instead - is a token
    VALUE an operand of this comparison - so `len(token) != len(reference)` is allowed because
    neither operand is the value, while `token == expected` is caught.

    **The first version of that structural question excluded EVERY call, and said it excluded a
    `len()`.** Measured by the engineering gate: `str(token) == expected` and `token.strip() ==
    expected` both survived, because both operands were calls. Any wrapper at all - `str`,
    `.strip()`, `.encode()`, a helper - hid the comparison, and the docstring claimed the only
    remaining hole was a renamed variable. `len` is now excluded by NAME rather than the whole
    `ast.Call` class.

    The declared blind spot that REMAINS: this matches on identifier names, so a token held in a
    differently named variable passes unseen. Measured by the security gate, which rewrote
    `auth.py` to `return supplied == reference` and found this test green - the sibling
    `test_the_token_comparison_uses_the_constant_time_primitive` is what caught that one. Two
    checks, two different weaknesses, which is why both are cited.
    """

    def is_token_value(operand: ast.expr) -> bool:
        """A reference to a token, whatever wraps it, as opposed to a `len()` OF one.

        Only `len` is excluded, and only when it is the call being made. Excluding every
        `ast.Call` let `str(token) == expected` through.
        """
        if (
            isinstance(operand, ast.Call)
            and isinstance(operand.func, ast.Name)
            and operand.func.id == "len"
        ):
            return False
        return "token" in ast.unparse(operand).lower()

    root = Path(auth.__file__).parent
    offenders: list[str] = []
    for module in sorted(root.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops):
                continue
            if any(is_token_value(operand) for operand in [node.left, *node.comparators]):
                offenders.append(f"{module.name}: {ast.unparse(node)}")
    assert offenders == [], f"a token is compared with plain equality: {offenders}"
