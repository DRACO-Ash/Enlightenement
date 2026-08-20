"""Authentication: the shared team token, compared in constant time.

The single-sign-on seam. This module is the one place a per-user identity provider
would later attach; the shared-token model is a recorded, accepted limitation
(see docs/SECURITY.md). A client-side check is never a boundary; this is.
"""

from __future__ import annotations

import hmac

#: Header carrying the shared team token.
TOKEN_HEADER = "x-team-token"  # noqa: S105 - a header name, not a credential


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
