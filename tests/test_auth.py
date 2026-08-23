"""The token comparison fails closed, and is built on the constant-time primitive.

The timing property itself is not assertable by a functional test, and that is recorded in
docs/SECURITY.md rather than papered over. What IS assertable is that the code uses
`hmac.compare_digest` and never a plain equality on the token, so a refactor cannot quietly
replace it. A source assertion is the right instrument here, and it states below what it
cannot see.
"""

from __future__ import annotations

import ast
import hmac as stdlib_hmac
import inspect
import textwrap
import types
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


#: `token_ok`'s reviewed implementation, statement by statement, docstring excluded because prose
#: must be free to change and the code under it must not. Pinned by
#: `test_the_token_comparison_uses_the_constant_time_primitive`, which explains in full why an
#: allowlist and not another denylist of equality spellings.
CANONICAL_TOKEN_OK_BODY = [
    "if not expected:\n    return False",
    "supplied = (given or '').encode('utf-8')",
    "reference = expected.encode('utf-8')",
    "return len(supplied) == len(reference) and hmac.compare_digest(supplied, reference)",
]


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

    **Four denylists were defeated in four rounds, so this is an allowlist.** The history is the
    argument, and each position was measured green against the full suite before it was closed:

    1. "A `compare_digest` call exists in the module" - defeated by a decoy call on a branch that
       never decides, with plain `==` deciding.
    2. "Every computed `return` contains `compare_digest`" - defeated by moving the decoy INSIDE
       the deciding return: `... and (supplied == reference or compare_digest(...))`. The primitive
       is in the rendered return, and `or` short-circuits.
    3. "No `ast.Compare` with `Eq`/`NotEq` compares anything but two `len(...)` calls" - defeated
       by `operator.eq(supplied, reference)`, which is an `ast.Call`, not an `ast.Compare`. So are
       `supplied.__eq__(reference)` and `supplied in (reference,)`.
    4. Any of the above - defeated without a comparison at all, by a LEAKY GUARD ahead of an
       untouched canonical return: `if not supplied.startswith(reference[:8]): return False`
       returns a bare constant, so it is excluded from any "deciding return" rule by design, and
       it leaks a prefix oracle while `compare_digest` still ships and is still reached.

    The set of ways to compare two byte strings in Python is open, so a denylist over it can only
    ever name the spellings somebody has already thought of. The body of this function is four
    statements. Requiring it to BE those four statements is the only version of this check that is
    not a prediction about the next spelling.

    The cost is deliberate and worth stating: any legitimate change to `token_ok` fails this test
    until `CANONICAL_TOKEN_OK_BODY` is updated in the same commit. For a function that decides
    authentication in four lines, a human re-reading it on every edit is the point, not friction to
    be engineered away.

    **This pin covers the STATEMENTS, not the names they resolve to, and that was a real hole.**
    The engineering gate kept the body byte-identical to the literal and defeated the control twice
    anyway: it deleted `import hmac` and bound the name to a class whose `compare_digest` is
    `a == b`, and it decorated `token_ok` with a `startswith` prefix oracle that returns before the
    function is reached. Both measured with the whole loop green, no lint warning. An AST pin over
    a function body is blind to one frame out in either direction - what its names mean, and what
    wraps it. Two sibling tests below name those two frames and are cited separately in the
    register, because each says which frame moved when it fires.

    **And "two frames" undercounted: there were four.** `hmac.compare_digest` can be REASSIGNED
    while `auth.hmac` remains the standard library module, and the name `token_ok` can be rebound to
    a wrapper that spoofs `__qualname__` while the canonical `def` sits untouched in the file - the
    second of those measured by the engineering gate as an unconditional authentication bypass at
    776 passed, with ruff and mypy silent. Enumerating frames was the wrong method, for the same
    reason enumerating equality spellings was. The pin now follows the CODE OBJECT the public name
    reaches, via `inspect.getsource(auth.token_ok)`, which closes the naked wrapper, the
    `functools.wraps` wrapper, the qualname spoof, the name rebind and a `__code__` swap at once;
    and the primitive is checked by TYPE rather than by module identity.

    What this still cannot see, and this list is bounded by the mechanism rather than offered as a
    complete account of the risk: the TIMING property itself, which no functional test can assert;
    a caller comparing the token somewhere else in the package, which is the census below; a change
    to `compare_digest`'s own semantics, which is the standard library's business; and whether
    `CANONICAL_TOKEN_OK_BODY` is itself the right four lines, which is a human reading with its
    reasoning in `auth.py`'s own docstring.

    **The division of labour with the census, stated honestly.** An earlier docstring said the
    census "is what caught that one" for the decoy defeat. It did not and cannot: the census
    matches identifier names and the shipped operands are `supplied` and `reference`, so every
    decoy variant passed it. THIS test is the only thing standing between `token_ok` and a
    non-constant-time comparison; the census covers a DIFFERENT risk, a token compared elsewhere
    in the package.
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

    # An ALLOWLIST of the whole body, not a denylist of equality spellings. See the docstring:
    # four rounds of denylist each closed the spellings named and left the next one open, because
    # the ways to compare two byte strings in Python are an open set - `==`, `operator.eq`,
    # `.__eq__`, `in (x,)` - and a leaky guard AHEAD of an honest return needs no comparison at
    # all. The body of this one function is four statements; requiring it to be those four
    # statements is the only form of this check that is not a guess about what comes next.
    #
    # **Pinned through the OBJECT, not through the module's source.** Reading `functions[0]` above
    # pins whichever `def token_ok` appears in the file, which is not necessarily the callable the
    # name reaches. The engineering gate proved that a full authentication bypass: it left the
    # canonical `def` untouched, appended a naked wrapper with `given == "break-glass"`, assigned
    # `__qualname__ = "token_ok"`, and rebound the module-level name. Body pin green, `hmac` probe
    # green, both wrapper assertions green, census green, ruff and mypy silent, 776 passed - and
    # any request could authenticate. `inspect.getsource` follows `__code__.co_filename` and
    # `co_firstlineno`, so pinning the source of `auth.token_ok` ITSELF closes the naked wrapper,
    # the `functools.wraps` wrapper, the qualname spoof, the name rebind and a `__code__` swap in
    # one assertion. `functions[0]` stays as the belt: exactly one `def token_ok` in the file.
    reached = ast.parse(textwrap.dedent(inspect.getsource(auth.token_ok))).body[0]
    assert isinstance(reached, (ast.FunctionDef, ast.AsyncFunctionDef)), (
        f"the name auth.token_ok does not reach a function definition: {reached!r}"
    )
    assert not reached.decorator_list, (
        "auth.token_ok is decorated at source level, so something runs before the pinned body:"
        f" {[ast.unparse(node) for node in reached.decorator_list]}"
    )
    statements = reached.body
    # The docstring is prose and must be free to change; the code under it must not be.
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    body = [ast.unparse(statement) for statement in statements]
    assert body == CANONICAL_TOKEN_OK_BODY, (
        "token_ok's body is not the reviewed constant-time implementation. This is deliberately"
        " strict: the function decides authentication, so a change here needs a human to re-read"
        " it and update CANONICAL_TOKEN_OK_BODY in the same commit, with the reasoning in the"
        f" message.\n  shipped:   {body}\n  canonical: {CANONICAL_TOKEN_OK_BODY}"
    )


def test_the_primitive_name_resolves_to_the_standard_library_module() -> None:
    """`hmac` in `auth.py` must BE the standard library's `hmac`, not something named it.

    The AST pin on `token_ok`'s body is satisfied by the text `hmac.compare_digest(...)`. It says
    nothing about what `hmac` means. Measured by the engineering gate: delete `import hmac`, define

        class _Hmac:
            @staticmethod
            def compare_digest(a: bytes, b: bytes) -> bool:
                return a == b

        hmac = _Hmac()

    and the constant-time control is entirely gone while the body still matches the literal, the
    full loop is green, and lint is silent. A pin over statements is blind to what their names
    resolve to; this is that frame.
    """
    assert auth.hmac is stdlib_hmac, (
        "auth.hmac is not the standard library module, so `hmac.compare_digest` in token_ok is"
        f" whatever this name now points at: {auth.hmac!r}"
    )
    # Module identity is not enough: `hmac.compare_digest = _compare` inside `auth.py` leaves both
    # sides the SAME module object and still removes the control - measured green at 776 passed,
    # and it poisons the primitive process-wide for every other importer too. An identity check
    # against `stdlib_hmac.compare_digest` would be vacuous for the same reason, so the assertion
    # is on the TYPE: the real primitive is a C builtin, and no Python-level replacement is.
    assert isinstance(auth.hmac.compare_digest, types.BuiltinFunctionType), (
        "hmac.compare_digest is no longer the C builtin, so the comparison token_ok reaches is a"
        f" Python-level replacement: {auth.hmac.compare_digest!r}"
    )


def test_token_ok_is_neither_wrapped_nor_decorated() -> None:
    """Nothing may run before `token_ok`, because a guard in front of it never needs to compare.

    The other frame the body pin cannot see. Measured by the engineering gate: decorate `token_ok`
    with a wrapper that returns `False` when `given` does not share a four-character prefix with
    `expected`. Behaviour-preserving on every test vector, green at 774, and a prefix oracle -
    `compare_digest` still ships, still matches the literal, and is never reached for a wrong
    prefix. Five defeat positions were inside the function; this is one of the ones outside it.

    Both assertions are needed and neither is redundant. `functools.wraps` copies `__qualname__`,
    so a wrapped function passes the name check and fails the unwrap check; a naked wrapper sets no
    `__wrapped__`, so it passes the unwrap check and fails the name check.

    **Neither is what closes the wrapping frame, and an earlier version of this docstring read as
    though they were.** A naked wrapper that ASSIGNS `__qualname__ = "token_ok"` and rebinds the
    module-level name passes both, and the engineering gate demonstrated exactly that as an
    unconditional authentication bypass with the whole loop green. What closes the frame is the body
    pin in `test_the_token_comparison_uses_the_constant_time_primitive`, which parses
    `inspect.getsource(auth.token_ok)` and so follows the code object the NAME reaches. These two
    assertions remain as cheap, specifically-named diagnostics: when one fires it says which frame
    moved, which a body diff does not.
    """
    assert inspect.unwrap(auth.token_ok) is auth.token_ok, (
        "token_ok is wrapped, so something runs before the constant-time comparison:"
        f" {inspect.unwrap(auth.token_ok)!r}"
    )
    assert auth.token_ok.__qualname__ == "token_ok", (
        "the name token_ok is bound to a different function, so the pinned body may never run:"
        f" {auth.token_ok.__qualname__}"
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
