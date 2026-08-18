"""The body-cap middleware, driven directly through the ASGI interface.

These exercise the branches an HTTP client cannot reach reliably: a mid-body disconnect, a
trailing receive after the replay, and the passthrough for a method that carries no body.
The middleware runs ahead of authentication, so a gap here is a pre-authentication gap.
"""

from __future__ import annotations

import asyncio
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


# --- header framing, in every order -------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("label", "headers"),
    [
        ("transfer-encoding only", [(b"transfer-encoding", b"chunked")]),
        (
            "content-length ZERO first, then transfer-encoding",
            [(b"content-length", b"0"), (b"transfer-encoding", b"chunked")],
        ),
        (
            "transfer-encoding first, then content-length zero",
            [(b"transfer-encoding", b"chunked"), (b"content-length", b"0")],
        ),
        (
            "content-length small first, then transfer-encoding",
            [(b"content-length", b"5"), (b"transfer-encoding", b"chunked")],
        ),
        (
            "a non-numeric content-length",
            [(b"content-length", b"0x100")],
        ),
    ],
)
async def test_the_cap_holds_whatever_order_the_framing_headers_arrive_in(
    label: str, headers: list[tuple[bytes, bytes]]
) -> None:
    """RFC 7230 section 3.3.3 makes transfer-encoding win over content-length, and h11
    agrees, so `Content-Length: 0` sent BEFORE `Transfer-Encoding: chunked` used to read as
    "no body" while the server delivered the whole thing: 45 MB to 326 MB resident on an
    unauthenticated request that answered 422 rather than 413. Swapping the two headers gave
    a correct 413, and that order dependence was the entire defect.
    """
    app = Recorder()
    middleware = BodyLimitMiddleware(app, max_bytes=10)
    sent, send = collector()
    await middleware(
        scope(headers=headers),
        feeder(
            [
                {"type": "http.request", "body": b"x" * 8, "more_body": True},
                {"type": "http.request", "body": b"x" * 8, "more_body": False},
            ]
        ),
        send,
    )
    assert sent[0]["status"] == 413, f"the cap was bypassed with {label}"
    assert app.called is False, f"the application saw an oversize body with {label}"


@pytest.mark.anyio
async def test_a_declared_length_is_not_trusted_when_a_transfer_encoding_is_present() -> None:
    """The framing header wins, so the length is not the body's size. Refusing early on it
    would be guessing; the byte counter is what decides.
    """
    app = Recorder()
    middleware = BodyLimitMiddleware(app, max_bytes=100)
    sent, send = collector()
    await middleware(
        scope(headers=[(b"content-length", b"999999"), (b"transfer-encoding", b"chunked")]),
        feeder([{"type": "http.request", "body": b"small", "more_body": False}]),
        send,
    )
    assert sent[0]["status"] == 200
    assert bytes(app.body) == b"small"


# --- exempt paths are never drained ---------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/livez", "/healthz", "/readyz", "/ping", "/health", "/"])
async def test_a_probe_path_is_never_drained_even_for_a_body_method(path: str) -> None:
    """`POST /livez` with a declared length and one byte sent never answered: the drain
    awaits with no timeout and the probe paths are exempt from rate limiting by design, so
    an unmetered caller could park connections on exactly the paths the deploy contract
    depends on.
    """
    app = Silent()
    middleware = BodyLimitMiddleware(
        app,
        max_bytes=10,
        exempt_paths=frozenset({"/livez", "/healthz", "/readyz", "/ping", "/health", "/"}),
    )

    async def must_not_be_called() -> Message:
        raise AssertionError(f"the body of a request to {path} was read")

    sent, send = collector()
    probe_scope = scope(headers=[(b"content-length", b"65000")])
    probe_scope["path"] = path
    await middleware(probe_scope, must_not_be_called, send)
    assert sent[0]["status"] == 200


# --- the method token, and the drain bound --------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["post", "Post", "pAtCh", "put"])
async def test_a_lower_case_method_token_does_not_skip_the_cap(method: str) -> None:
    """uvicorn lowercases header names but passes the method token exactly as sent, so an
    un-normalised comparison let `post` skip the cap entirely. Not exploitable today, but
    this cap has now twice decided NOT to run on a scope value the layers behind it
    normalise differently, and both earlier instances shipped as exploitable.
    """
    app = Recorder()
    middleware = BodyLimitMiddleware(app, max_bytes=10)
    sent, send = collector()
    await middleware(
        scope(method=method),
        feeder([{"type": "http.request", "body": b"x" * 20, "more_body": False}]),
        send,
    )
    assert sent[0]["status"] == 413, f"the cap was skipped for method {method!r}"
    assert app.called is False


@pytest.mark.anyio
async def test_an_unknown_method_is_passed_through_rather_than_drained() -> None:
    app = Silent()
    middleware = BodyLimitMiddleware(app, max_bytes=10)

    async def must_not_be_called() -> Message:
        raise AssertionError("an unknown method was drained")

    sent, send = collector()
    await middleware(scope(method="BREW"), must_not_be_called, send)
    assert sent[0]["status"] == 200


@pytest.mark.anyio
async def test_a_client_that_frames_a_body_and_stops_sending_is_timed_out() -> None:
    """Without a bound, 200 such requests took a listener from 8 to 207 file descriptors and
    none ever answered. The coarse limiter lets a caller keep doing that indefinitely.
    """
    app = Recorder()
    middleware = BodyLimitMiddleware(app, max_bytes=1024, drain_timeout=0.05)
    started = asyncio.get_running_loop().time()

    async def one_byte_then_silence() -> Message:
        if not hasattr(one_byte_then_silence, "sent"):
            one_byte_then_silence.sent = True  # type: ignore[attr-defined]
            return {"type": "http.request", "body": b"x", "more_body": True}
        await asyncio.sleep(30)
        raise AssertionError("unreachable")

    sent, send = collector()
    await middleware(scope(), one_byte_then_silence, send)
    elapsed = asyncio.get_running_loop().time() - started
    assert sent[0]["status"] == 408
    assert app.called is False
    assert elapsed < 5, f"the drain was not bounded: {elapsed:.2f}s"


@pytest.mark.anyio
async def test_a_body_arriving_within_the_budget_is_not_timed_out() -> None:
    """The boundary in the other direction: a slow but honest client must still be served."""
    app = Recorder()
    middleware = BodyLimitMiddleware(app, max_bytes=1024, drain_timeout=5.0)

    async def slow_but_honest() -> Message:
        await asyncio.sleep(0.01)
        return {"type": "http.request", "body": b"payload", "more_body": False}

    sent, send = collector()
    await middleware(scope(), slow_but_honest, send)
    assert sent[0]["status"] == 200
    assert bytes(app.body) == b"payload"
