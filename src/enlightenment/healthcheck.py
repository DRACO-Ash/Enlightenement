"""Container HEALTHCHECK probe: ``python -m enlightenment.healthcheck``.

Runs inside the image with no extra tooling, so the runtime stage needs no curl or wget.

It probes the LIVENESS path, not readiness. A Docker HEALTHCHECK is a liveness signal:
any runtime that acts on it (Compose, Swarm, an autoheal sidecar) restarts an unhealthy
container, and restarting on a storage fault is exactly the coupling the split liveness
and readiness paths exist to prevent. The platform's own readiness probe is configured on
``/healthz``, which carries the real-write proof and the diagnostic 503.

``PORT`` is operator-supplied and therefore untrusted, so it is validated before it is put
anywhere near a URL. Interpolating it raw lets ``PORT=8080@evil.example`` turn
``127.0.0.1:8080`` into userinfo and resolve an attacker-controlled host, which would make
this control report HEALTHY while probing somewhere else entirely.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

#: Strictly shorter than the platform probe timeout.
TIMEOUT_SECONDS = 3.0

#: The only status the liveness path returns when the process is alive.
HTTP_OK = 200

#: Highest valid TCP port.
MAX_PORT = 65535

#: Documented fallback when the platform injects nothing.
DEFAULT_PORT = 8080

#: Exit codes Docker reads: 0 healthy, 1 unhealthy.
HEALTHY = 0
UNHEALTHY = 1


def resolve_port(raw: str | None) -> int | None:
    """Return a validated port, or None when the value cannot be trusted.

    None means UNHEALTHY, never "fall back and carry on": a malformed port is the same
    malformed value the application itself refuses to start on, so this probe must not
    paper over it.
    """
    if raw is None or raw == "":
        return DEFAULT_PORT
    candidate = "".join(ch for ch in raw.strip() if ch.isprintable())
    # ASCII decimal digits only, and nothing else.
    #
    # `isdigit()` accepts characters `int()` rejects (a superscript two), so it would raise
    # an uncaught ValueError out of a function documented to return None. `isdecimal()`
    # fixes that but still accepts non-ASCII decimals: `int("\u0660\u0661")` is 1, so an
    # exotic spelling would silently resolve to a different port than it looks like. A
    # platform-injected port is always ASCII, so requiring that removes the ambiguity
    # rather than reasoning about it.
    if not (candidate.isascii() and candidate.isdecimal()):
        return None
    port = int(candidate)
    return port if 1 <= port <= MAX_PORT else None


def check(port: str | None = None) -> int:
    """Return 0 when the liveness path answers 200, 1 otherwise."""
    resolved = resolve_port(port if port is not None else os.environ.get("PORT"))
    if resolved is None:
        return UNHEALTHY
    url = f"http://127.0.0.1:{resolved}/livez"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            return HEALTHY if response.status == HTTP_OK else UNHEALTHY
    except (urllib.error.URLError, TimeoutError, OSError):
        return UNHEALTHY


if __name__ == "__main__":
    sys.exit(check())
