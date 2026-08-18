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

import asyncio
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

#: Total time the middleware will spend waiting for a body before giving up with 408.
#:
#: Without a bound, 200 unauthenticated requests declaring a body and sending one byte took a
#: listener from 8 to 207 file descriptors and none ever answered. The coarse rate limiter
#: allows a caller to keep doing that indefinitely, and gunicorn's own request timeout does
#: not bound it because the worker keeps notifying the arbiter while the loop is alive.
DRAIN_TIMEOUT_SECONDS = 15.0

#: HTTP status for a client that framed a body and then stopped sending it.
HTTP_REQUEST_TIMEOUT = 408

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
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        exempt_paths: frozenset[str] | None = None,
        drain_timeout: float = DRAIN_TIMEOUT_SECONDS,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.exempt_paths = exempt_paths or frozenset()
        self.drain_timeout = drain_timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # The method token is NOT normalised by the server: uvicorn lowercases header names
        # but passes the method exactly as sent, so `post` in lower case would skip the cap
        # entirely. Not exploitable today, because Starlette's route match is case sensitive
        # and no handler would read the body, but this is the third time this cap has decided
        # NOT to run based on a scope value that the layers behind it normalise differently,
        # and the first two shipped as exploitable.
        method = str(scope.get("method", "")).upper()
        if (
            scope.get("path") in self.exempt_paths
            or method not in BODY_METHODS
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

        drained = await self._drain(receive, send)
        if drained is None:
            # Already answered: the body was over the cap, or it stopped arriving.
            return
        payload, disconnected = drained
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if disconnected:
                return {"type": "http.disconnect"}
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": payload, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _drain(self, receive: Receive, send: Send) -> tuple[bytes, bool] | None:
        """Read the body up to the cap, bounded in time.

        Returns the buffered payload and whether the client disconnected, or ``None`` when
        the request has already been answered (over the cap, or it stopped arriving).
        """
        body = bytearray()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.drain_timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                await self._timed_out(send)
                return None
            try:
                message = await asyncio.wait_for(receive(), remaining)
            except TimeoutError:
                await self._timed_out(send)
                return None
            if message.get("type") == "http.disconnect":
                return bytes(body), True
            body.extend(message.get("body", b"") or b"")
            if len(body) > self.max_bytes:
                # Stop reading here. The remaining bytes are never buffered, so a huge body
                # costs the cap, not its own size.
                await self._refuse(send)
                return None
            if not message.get("more_body", False):
                return bytes(body), False

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

    async def _timed_out(self, send: Send) -> None:
        """Answer a client that framed a body and then stopped sending it."""
        await self._answer(send, HTTP_REQUEST_TIMEOUT, "request body was not sent in time")

    async def _refuse(self, send: Send) -> None:
        await self._answer(send, HTTP_CONTENT_TOO_LARGE, "request body too large")

    async def _answer(self, send: Send, status: int, message: str) -> None:
        body = json.dumps({"error": message}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
