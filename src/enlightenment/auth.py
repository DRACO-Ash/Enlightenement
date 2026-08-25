"""Authentication: the shared team token, compared in constant time.

The single-sign-on seam. This module is the one place a per-user identity provider
would later attach; the shared-token model is a recorded, accepted limitation
(see docs/SECURITY.md). A client-side check is never a boundary; this is.
"""

from __future__ import annotations

import hmac

#: Header carrying the shared team token.
#: The header NAME the shared team token arrives in. Not a credential.
#:
#: There is no suppression comment on this line, and getting there took two attempts. The constant
#: was named after the token, which trips ruff's hardcoded-password rule (it keys on a variable name
#: containing "token"), so the line carried a ruff suppression directive with a trailing reason.
#: SonarQube flags a suppression directive with trailing prose as malformed syntax; trimming the
#: prose did not satisfy it either. Renaming solved both at once: this name trips no ruff rule, so
#: the line needs no directive and leaves nothing for either analyser to parse. Writing the old
#: directive out in this comment then tripped ruff's unused-directive rule, which is why it is
#: described here rather than quoted. The wire value is unchanged: it is all a client can see.
AUTH_HEADER = "x-team-token"


def token_ok(given: str | None, expected: str) -> bool:
    """Return True only when ``given`` matches ``expected`` exactly.

    Fails closed on an unconfigured expected token: an app with no token configured
    cannot authorise a privileged call by accident.

    **What the comparison does and does not hide, stated precisely.** `hmac.compare_digest`
    takes time independent of WHERE the first differing byte is, so the position of a mismatch is
    not leaked. The length guard in front of it short-circuits, so a wrong-length token returns
    early and its length IS distinguishable by timing. That is deliberate and harmless here: the
    length of the configured token is not treated as a secret, and `/api/v1/diagnostics` already
    publishes a coarse length bucket unauthenticated by design.

    An earlier version of this docstring claimed the comparison "leaks neither the length nor the
    position", which is false for the first half. A crypto claim that overstates itself is worse
    than none, because this is exactly the comment a reader trusts instead of reading the code.
    """
    if not expected:
        return False
    supplied = (given or "").encode("utf-8")
    reference = expected.encode("utf-8")
    return len(supplied) == len(reference) and hmac.compare_digest(supplied, reference)
