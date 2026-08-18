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
    cannot authorise a privileged call by accident. The comparison is constant time
    with a length guard, so it leaks neither the length nor the position of a
    mismatch through timing.
    """
    if not expected:
        return False
    supplied = (given or "").encode("utf-8")
    reference = expected.encode("utf-8")
    return len(supplied) == len(reference) and hmac.compare_digest(supplied, reference)
