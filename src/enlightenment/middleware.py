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

#: The only methods whose body this middleware reads. A GET or a probe request is passed
#: straight through untouched.
#:
#: Draining unconditionally was a regression: `GET /livez` with `Content-Length: 10` and the
#: ten bytes never sent used to answer 200 in 0.01 s, because no handler reads the body, and
#: after the first version of this middleware it parked with no response at all. The
#: liveness and readiness paths are exactly the ones the deploy contract depends on, so they
#: must never wait on a client that is not talking. A body on a method that carries none is
#: left for the server to discard; nothing here buffers it.
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class BodyLimitMiddleware:
    """Reject any request whose body exceeds ``max_bytes``, however it is framed.

    ``exempt_paths`` are passed straight through without reading anything. The probe paths
    accept no body and are exempt from rate limiting by design, so draining one lets an
    unmetered caller park a connection on exactly the paths the deploy contract depends on:
    ``POST /livez`` with a declared length and one byte sent never answered.
    """

    def __init__(
        self, app: ASGIApp, *, max_bytes: int, exempt_paths: frozenset[str] | None = None
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.exempt_paths = exempt_paths or frozenset()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        if (
            scope.get("path") in self.exempt_paths
            or scope.get("method") not in BODY_METHODS
            or not self._body_framed(scope)
        ):
            # Nothing to cap, so nothing is read here. See BODY_METHODS.
            await self.app(scope, receive, send)
            return

        # An honest oversize request is refused without reading its body at all. Redundant
        # with the byte counter below, so an optimisation rather than a control.
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

    def _body_framed(self, scope: Scope) -> bool:
        """True when the request declares a body at all, by length or by chunked framing.

        EVERY header is examined before deciding. Returning from inside the loop on
        whichever header appeared first was a real bypass, and a measured one: RFC 7230
        section 3.3.3 makes ``Transfer-Encoding`` win over ``Content-Length``, and h11
        agrees, so ``Content-Length: 0`` sent BEFORE ``Transfer-Encoding: chunked`` looked
        like "no body" while the server delivered 128 MB in full. Resident set went from
        45 MB to 326 MB on an unauthenticated request that answered 422, not 413. Swapping
        the two headers gave a correct 413, and that order dependence was the whole defect.
        """
        chunked = False
        by_length = False
        for name, value in scope.get("headers", []):
            if name == b"transfer-encoding":
                chunked = True
            elif name == b"content-length":
                declared = value.decode("latin-1").strip()
                # A non-numeric length frames a body we cannot trust the header for, so the
                # byte counter must run; a zero length frames nothing.
                by_length = by_length or not declared.isdecimal() or int(declared) > 0
        return chunked or by_length

    def _declared_over_cap(self, scope: Scope) -> bool:
        """True only when a TRUSTWORTHY declared length already exceeds the cap.

        ``Content-Length`` is ignored when a transfer-encoding is present, because the
        framing header wins and the length is then not the body's size. The byte counter
        enforces the cap in that case, so nothing is lost by declining to guess here.
        """
        declared_length: int | None = None
        for name, value in scope.get("headers", []):
            if name == b"transfer-encoding":
                return False
            if name == b"content-length":
                declared = value.decode("latin-1").strip()
                declared_length = int(declared) if declared.isdecimal() else None
        return declared_length is not None and declared_length > self.max_bytes

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
