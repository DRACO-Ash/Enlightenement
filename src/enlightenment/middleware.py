"""Pure ASGI middleware that bounds the request body by BYTES READ.

Trusting the declared ``content-length`` is not a size cap. A ``Transfer-Encoding:
chunked`` request declares no length, so a header-only check is skipped entirely and the
body is buffered in full before any handler, dependency, or authentication runs. Measured
on this application before the fix: one unauthenticated 256 MB chunked POST took the
worker's resident set from 52 MB to 821 MB and returned 422, not 413. On a container with
a small memory budget that is a pre-authentication denial of service.

The cap is therefore enforced on bytes actually received. The body is drained here, up to
the cap and never further, and replayed to the application from that bounded buffer. Draining
rather than wrapping ``receive`` with an exception keeps the control flow ordinary: an
exception raised from inside a wrapped ``receive`` is caught and reshaped by the middleware
stack above it, which turned the intended 413 into a 400.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

#: HTTP status for a body over the cap.
HTTP_CONTENT_TOO_LARGE = 413


class BodyLimitMiddleware:
    """Reject any request whose body exceeds ``max_bytes``, however it is framed."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # An honest oversize request is refused without reading its body at all.
        if self._declared_over_cap(scope):
            await self._refuse(send)
            return

        body = bytearray()
        disconnected = False
        more = True
        while more:
            message = await receive()
            if message.get("type") == "http.disconnect":
                disconnected = True
                break
            body.extend(message.get("body", b"") or b"")
            if len(body) > self.max_bytes:
                # Stop reading here. The remaining bytes are never buffered, so a huge
                # body costs the cap, not its own size.
                await self._refuse(send)
                return
            more = bool(message.get("more_body", False))

        replayed = False
        payload = bytes(body)

        async def replay() -> Message:
            nonlocal replayed
            if disconnected:
                return {"type": "http.disconnect"}
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": payload, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    def _declared_over_cap(self, scope: Scope) -> bool:
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                declared = value.decode("latin-1").strip()
                return declared.isdigit() and int(declared) > self.max_bytes
        return False

    async def _refuse(self, send: Send) -> None:
        body = json.dumps({"error": "request body too large"}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": HTTP_CONTENT_TOO_LARGE,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
