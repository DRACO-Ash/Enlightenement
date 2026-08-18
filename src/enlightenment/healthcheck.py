"""Container HEALTHCHECK probe: ``python -m enlightenment.healthcheck``.

Runs inside the image with no extra tooling, so the runtime stage needs no curl or wget.
The timeout is hard and strictly shorter than the platform's probe timeout, so a stalled
mount produces a failed probe rather than a hanging one that the kubelet kills silently.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

#: Strictly shorter than the platform probe timeout.
TIMEOUT_SECONDS = 3.0

#: The only status the readiness path returns when it is ready.
HTTP_OK = 200

#: Exit codes Docker reads: 0 healthy, 1 unhealthy.
HEALTHY = 0
UNHEALTHY = 1


def check(port: str | None = None) -> int:
    """Return 0 when the readiness path answers 200, 1 otherwise."""
    resolved = port or os.environ.get("PORT") or "8080"
    url = f"http://127.0.0.1:{resolved}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            return HEALTHY if response.status == HTTP_OK else UNHEALTHY
    except (urllib.error.URLError, TimeoutError, OSError):
        return UNHEALTHY


if __name__ == "__main__":
    sys.exit(check())
