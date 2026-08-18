"""The body-cap middleware, driven directly through the ASGI interface.

These exercise the branches an HTTP client cannot reach reliably: a mid-body disconnect, a
trailing receive after the replay, and the passthrough for a method that carries no body.
The middleware runs ahead of authentication, so a gap here is a pre-authentication gap.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import pytest

from enlightenment.middleware import BODY_METHODS, BodyLimitMiddleware

Message = MutableMapping[str, Any]


#: Chunked framing: declares a body with no length, which is the case a header-only cap
#: misses entirely.
CHUNKED = [(b"transfer-encoding", b"chunked")]


def scope(method: str = "POST", headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, Any]:
    return {"type": "http", "method": method, "path": "/x", "headers": headers or list(CHUNKED)}


class Silent:
    """A terminal ASGI app that answers WITHOUT reading the request body.

    This is how the liveness and readiness handlers behave, so it is the right stand-in for
    proving that nothing upstream of them reads a body they never asked for.
    """

    def __init__(self) -> None:
        self.called = False

    async def __call__(
        self,
        _scope: MutableMapping[str, Any],
        _receive: Callable[[], Awaitable[Message]],
        send: Callable[[Message], Awaitable[None]],
    ) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


class Recorder:
    """A terminal ASGI app that records what it was handed."""

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.body = bytearray()
        self.called = False

    async def __call__(
        self,
        _scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[Message]],
        send: Callable[[Message], Awaitable[None]],
    ) -> None:
        self.called = True
        while True:
            message = await receive()
            self.messages.append(dict(message))
            if message.get("type") == "http.disconnect":
                break
            self.body.extend(message.get("body", b"") or b"")
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def collector() -> tuple[list[Message], Callable[[Message], Awaitable[None]]]:
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(dict(message))

    return sent, send


def feeder(messages: list[Message]) -> Callable[[], Awaitable[Message]]:
    queue = list(messages)

    async def receive() -> Message:
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    return receive


@pytest.mark.anyio
async def test_a_body_at_the_cap_is_passed_through_intact() -> None:
    app = Recorder()
    middleware = BodyLimitMiddleware(app, max_bytes=10)
    sent, send = collector()
    await middleware(
        scope(headers=[(b"content-length", b"10")]),
        feeder([{"type": "http.request", "body": b"0123456789", "more_body": False}]),
        send,
    )
    assert bytes(app.body) == b"0123456789"
    assert sent[0]["status"] == 200


@pytest.mark.anyio
async def test_one_byte_over_the_cap_is_refused_and_the_app_never_runs() -> None:
    app = Recorder()
    middleware = BodyLimitMiddleware(app, max_bytes=10)
    sent, send = collector()
    await middleware(
        scope(),
        feeder(
            [
                {"type": "http.request", "body": b"01234", "more_body": True},
                {"type": "http.request", "body": b"567890", "more_body": False},
            ]
        ),
        send,
    )
    assert sent[0]["status"] == 413
    assert app.called is False, "the application saw an oversize body"


@pytest.mark.anyio
async def test_a_disconnect_mid_body_reaches_the_app_and_is_not_refused() -> None:
    """A client that goes away is not an oversize request, and must not be reported as one."""
    app = Recorder()
    middleware = BodyLimitMiddleware(app, max_bytes=1024)
    sent, send = collector()
    await middleware(
        scope(),
        feeder(
            [
                {"type": "http.request", "body": b"partial", "more_body": True},
                {"type": "http.disconnect"},
            ]
        ),
        send,
    )
    assert app.called is True
    assert app.messages[0]["type"] == "http.disconnect"
    assert all(message.get("status") != 413 for message in sent)


@pytest.mark.anyio
async def test_a_receive_after_the_replay_falls_through_to_the_real_transport() -> None:
    """The app may poll again after the body; the second call must not replay the body."""
    seen: list[Message] = []

    class Poller:
        async def __call__(
            self,
            _scope: MutableMapping[str, Any],
            receive: Callable[[], Awaitable[Message]],
            send: Callable[[Message], Awaitable[None]],
        ) -> None:
            seen.append(await receive())
            seen.append(await receive())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    middleware = BodyLimitMiddleware(Poller(), max_bytes=1024)
    _sent, send = collector()
    await middleware(
        scope(),
        feeder([{"type": "http.request", "body": b"body", "more_body": False}]),
        send,
    )
    assert seen[0]["body"] == b"body"
    assert seen[1]["type"] == "http.disconnect"


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "DELETE"])
async def test_a_method_that_carries_no_body_is_never_drained(method: str) -> None:
    """`GET /livez` with a declared length and no bytes used to answer in 0.01 s and then
    parked with no response at all once the drain was unconditional. The liveness and
    readiness paths are the ones the deploy contract depends on, so they must never wait on
    a client that is not talking.
    """
    app = Silent()
    middleware = BodyLimitMiddleware(app, max_bytes=10)

    async def must_not_be_called() -> Message:
        raise AssertionError(f"the body of a {method} was read")

    sent, send = collector()
    await middleware(
        scope(method=method, headers=[(b"content-length", b"10")]), must_not_be_called, send
    )
    assert app.called is True
    assert sent[0]["status"] == 200
    assert method not in BODY_METHODS


@pytest.mark.anyio
async def test_a_body_method_declaring_no_body_is_not_drained_either() -> None:
    app = Silent()
    middleware = BodyLimitMiddleware(app, max_bytes=10)

    async def must_not_be_called() -> Message:
        raise AssertionError("a request that framed no body was read")

    sent, send = collector()
    await middleware(scope(headers=[(b"content-length", b"0")]), must_not_be_called, send)
    assert app.called is True
    assert sent[0]["status"] == 200


@pytest.mark.anyio
async def test_an_honest_oversize_declaration_is_refused_without_reading_the_body() -> None:
    app = Silent()
    middleware = BodyLimitMiddleware(app, max_bytes=10)

    async def must_not_be_called() -> Message:
        raise AssertionError("a body that was already refused got read anyway")

    sent, send = collector()
    await middleware(scope(headers=[(b"content-length", b"999")]), must_not_be_called, send)
    assert sent[0]["status"] == 413
    assert app.called is False


@pytest.mark.anyio
async def test_a_non_http_scope_is_passed_through_untouched() -> None:
    app = Silent()
    middleware = BodyLimitMiddleware(app, max_bytes=10)
    _sent, send = collector()
    await middleware({"type": "lifespan"}, feeder([{"type": "http.disconnect"}]), send)
    assert app.called is True
