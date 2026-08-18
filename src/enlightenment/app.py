"""The HTTP application factory.

``create_app(...)`` wires routes, middleware, and injected dependencies and returns the
app WITHOUT listening, so the suite can mount it in-process with fakes. The listener
lives in :mod:`enlightenment.__main__` (local) and :mod:`enlightenment.asgi` (container).

The request pipeline, outermost first: cross-origin policy, the coarse rate limit, the
byte-counting body cap, then per-route authentication on every cost-incurring or
state-changing route, then boundary validation of the body, then the handler, then a
generic error response with the detail kept server-side.

Route registration is split into small ``_register_*`` helpers rather than one long
factory, so no function approaches the cognitive-complexity cap the quality gate enforces.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from enlightenment import __version__
from enlightenment.audit import ANONYMOUS_ACTOR, audit, log_event, sanitise_log_value
from enlightenment.auth import TOKEN_HEADER, token_ok
from enlightenment.config import Config, load_config, token_length_bucket
from enlightenment.middleware import BodyLimitMiddleware
from enlightenment.models import SessionPatch, SessionUpsert
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import (
    SCHEMA_VERSION,
    ProbeResult,
    StaleRevisionError,
    TrainingStore,
    probe_writable,
)

#: Liveness paths. Cheap, dependency-free, always 200: a downstream outage must never
#: restart a healthy container.
LIVENESS_PATHS = ("/livez", "/ping", "/health")

#: Readiness paths. 200 when storage accepts a real write, 503 with the diagnosis when not.
READINESS_PATHS = ("/healthz", "/readyz")

#: Paths exempt from rate limiting. The platform probes these; a 429 would read as unhealthy.
UNLIMITED_PATHS = frozenset(LIVENESS_PATHS + READINESS_PATHS + ("/",))

#: Hard probe timeout, strictly shorter than the platform's probe timeout, so a stalled
#: mount fails loudly instead of hanging and being killed silently by the kubelet.
PROBE_TIMEOUT_SECONDS = 2.0

#: How long a storage probe verdict is reused. The readiness paths are unauthenticated and
#: exempt from rate limiting BY DESIGN, so without this an unauthenticated flood turns into
#: one real create-write-fsync-unlink cycle per request against the volume: measured at
#: about 265 per second from a single client, which exhausts a network volume's IOPS and
#: then trips the probe's own timeout, so the pod flips unready and is restarted. Caching
#: bounds probe cost by TIME rather than by request rate, and stays well under the
#: platform's probe interval so a real fault is still noticed promptly.
PROBE_CACHE_SECONDS = 5.0

#: Coarse limiter: protects the process on every non-probe route.
GLOBAL_LIMIT = 240
GLOBAL_WINDOW_SECONDS = 60.0

#: Strict limiter: protects the state-changing routes.
WRITE_LIMIT = 20
WRITE_WINDOW_SECONDS = 60.0

#: Request body cap, enforced on bytes actually read (see :mod:`enlightenment.middleware`).
MAX_BODY_BYTES = 64 * 1024

#: Actor label for a call authenticated with the shared team token.
TEAM_ACTOR = "team"

_logger = logging.getLogger("enlightenment.app")

ProbeFn = Callable[[Path], ProbeResult]


@dataclass(frozen=True, slots=True)
class ProbeSettings:
    """Tuning for the storage probe.

    Bundled rather than passed as two separate injection points, so ``create_app`` stays
    within the seven-parameter cap the platform's quality gate enforces (Sonar S107).
    """

    timeout: float = PROBE_TIMEOUT_SECONDS
    cache_seconds: float = PROBE_CACHE_SECONDS


@dataclass(slots=True)
class _Runtime:
    """The resolved dependencies one app instance serves from."""

    settings: Config
    store: TrainingStore
    probe: ProbeFn
    probe_settings: ProbeSettings
    coarse: RateLimiter
    strict: RateLimiter
    started: float
    clock: Callable[[], float]
    ready: bool | None = field(default=None)
    cached_probe: ProbeResult | None = field(default=None)
    cached_at: float | None = field(default=None)


def _client_key(request: Request) -> str:
    """Rate-limit key for a caller. Behind the platform gateway many callers can share
    one address; that is an accepted coarseness, recorded in docs/SECURITY.md.
    """
    client = request.client
    return client.host if client is not None else "unknown"


async def _probe_storage(runtime: _Runtime) -> ProbeResult:
    """Return a storage verdict, reusing a recent one rather than writing again.

    The probe is raced against a hard timeout and every rejection is converted into a
    value: a probe that can hang turns an infrastructure fault into an undiagnosable
    silent liveness kill.
    """
    now = runtime.clock()
    if (
        runtime.cached_probe is not None
        and runtime.cached_at is not None
        and now - runtime.cached_at < runtime.probe_settings.cache_seconds
    ):
        return runtime.cached_probe

    data_dir = runtime.settings.data_dir
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(runtime.probe, data_dir), runtime.probe_settings.timeout
        )
    except TimeoutError:
        result = ProbeResult(
            ok=False,
            resolved=str(data_dir),
            detail=f"storage probe timed out after {runtime.probe_settings.timeout}s",
        )
    except Exception as exc:
        # Fail closed: any probe failure at all is an unready state, never a pass.
        _logger.exception("storage probe raised")
        result = ProbeResult(ok=False, resolved=str(data_dir), detail=exc.__class__.__name__)

    runtime.cached_probe = result
    runtime.cached_at = now
    return result


def _identity() -> dict[str, Any]:
    """This process's own identity only. Enough to show a non-root container is non-root,
    with nothing about any other principal.
    """
    return {"uid": os.getuid(), "gid": os.getgid()}


def _boot(runtime: _Runtime) -> None:
    """Record the access posture and the storage verdict in decisive log lines.

    Fail closed for security AND to a RECOVERABLE state for operations: a storage fault
    must make the app unready, never unstartable. An app that refuses to boot cannot serve
    the readiness diagnosis that says why, which is how a mount permission problem becomes
    an undiagnosable outage. Both the probe and the seed are therefore guarded.
    """
    settings = runtime.settings
    log_event(
        "boot.access",
        authRequired=settings.auth_required,
        writesOpen=settings.writes_open,
        allowedOriginSet=bool(settings.allowed_origin),
        buildId=settings.build_id,
    )
    if settings.writes_open:
        _logger.warning(
            "ANONYMOUS WRITES ARE ENABLED. ENLIGHTENMENT_ALLOW_ANONYMOUS is set and no "
            "team token is configured, so every write route is open to any caller that "
            "can reach this process. This is intended for single-user local work only."
        )

    try:
        result = runtime.probe(settings.data_dir)
        if result.ok:
            runtime.store.seed()
    except Exception as exc:
        _logger.exception("boot storage check raised; starting unready")
        result = ProbeResult(
            ok=False, resolved=str(settings.data_dir), detail=exc.__class__.__name__
        )

    runtime.ready = result.ok
    log_event(
        "boot.storage",
        writable=result.ok,
        dataDir=result.resolved,
        errno=result.errno,
        detail=result.detail,
    )


def _install_cors(app: FastAPI, runtime: _Runtime) -> None:
    """Allow exactly the one configured origin, or none at all.

    A wildcard never reaches here: :func:`enlightenment.config.load_config` refuses to
    start on one, unconditionally, so the guard lives where it is tested rather than as an
    unasserted condition on this line. Registered LAST so it is the outermost middleware,
    which is what puts the cross-origin headers on a 413 or a 429 as well as on a handler
    response; without that a browser client sees an opaque network error instead of a status.
    """
    if runtime.settings.allowed_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[runtime.settings.allowed_origin],
            # Every method the API actually exposes. Kept in one place with a test that
            # parametrises over the real route table, so the two cannot drift.
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=[TOKEN_HEADER, "content-type", "if-match", "if-none-match"],
        )


def _install_rate_limit(app: FastAPI, runtime: _Runtime) -> None:
    """The coarse tier, ahead of every handler and of the body cap."""

    @app.middleware("http")
    async def limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        limited = request.url.path not in UNLIMITED_PATHS
        if limited and not runtime.coarse.allow(_client_key(request)):
            return JSONResponse(
                {"error": "rate limit exceeded"}, status_code=status.HTTP_429_TOO_MANY_REQUESTS
            )
        return await call_next(request)


def _install_error_handlers(app: FastAPI) -> None:
    """The client gets a generic message; the cause is logged server-side.

    Every reflected value reaching a log line goes through the shared sanitiser and the
    line is emitted as JSON, so the escaping is structural rather than depending on a
    third-party parser happening to strip control characters.
    """

    @app.exception_handler(RequestValidationError)
    async def on_invalid_body(request: Request, _exc: RequestValidationError) -> JSONResponse:
        log_event("request.rejected", path=request.url.path, reason="validation")
        return JSONResponse(
            {"error": "invalid request"}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        )

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, _exc: Exception) -> JSONResponse:
        _logger.exception("unhandled error serving %s", sanitise_log_value(request.url.path))
        return JSONResponse(
            {"error": "internal error"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _register_probe_routes(app: FastAPI, runtime: _Runtime) -> None:
    """Root, liveness, and readiness. All unauthenticated and never rate-limited."""

    @app.get("/", status_code=status.HTTP_200_OK)
    async def root() -> dict[str, Any]:
        """200, never a 302: the platform router treats a redirect at root as unhealthy."""
        return {"name": "Enlightenment", "version": __version__, "status": "ok"}

    @app.get("/livez", response_class=PlainTextResponse)
    @app.get("/ping", response_class=PlainTextResponse)
    @app.get("/health", response_class=PlainTextResponse)
    async def liveness() -> str:
        """Process-alive only. Never checks a downstream, or a transient outage restarts
        a healthy container.
        """
        return "ok"

    @app.get("/healthz")
    @app.get("/readyz")
    async def readiness(response: Response) -> dict[str, Any]:
        """200 when storage accepts a real write; 503 with the resolved directory and the
        exact errno when it does not, so a screenshot is a complete diagnosis.
        """
        result = await _probe_storage(runtime)
        if runtime.ready != result.ok:
            log_event("readiness.transition", ready=result.ok, detail=result.detail)
            runtime.ready = result.ok
        response.status_code = (
            status.HTTP_200_OK if result.ok else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return {"status": "ok" if result.ok else "unready", "storage": result.as_diagnostic()}


def _register_diagnostics_route(app: FastAPI, runtime: _Runtime) -> None:
    """The secret-free read-out. Every field that could answer a plausible deploy failure
    is present at once, so a deploy cycle is never spent on a question a boolean answers.

    The team token is reported as a boolean and a coarse size BAND, never an exact length:
    the read-out is unauthenticated by design, and an exact count tells an attacker how
    many characters to attack. A minimum token length is enforced at boot, so the band is
    enough to tell a stale value from a correct one.
    """

    @app.get("/api/v1/diagnostics")
    async def diagnostics() -> dict[str, Any]:
        result = await _probe_storage(runtime)
        settings = runtime.settings
        return {
            "buildId": settings.build_id,
            "version": __version__,
            "schemaVersion": SCHEMA_VERSION,
            "pythonVersion": sys.version.split()[0],
            "port": settings.port,
            "host": settings.host,
            "uptimeSeconds": round(runtime.clock() - runtime.started, 3),
            "identity": _identity(),
            "storage": result.as_diagnostic(),
            "config": {
                "teamToken": {
                    "set": bool(settings.team_token),
                    "lengthBucket": token_length_bucket(settings.team_token),
                },
                "allowedOrigin": {
                    "set": bool(settings.allowed_origin),
                    "length": len(settings.allowed_origin),
                },
                "authRequired": settings.auth_required,
                "anonymousWritesEnabled": settings.writes_open,
            },
        }


def _token_dependency(runtime: _Runtime) -> Callable[[str | None], str]:
    """Build the auth dependency for privileged routes.

    This is the single-sign-on seam: the one place a per-user identity provider would
    later attach.

    Fails CLOSED on an absent token. An unset ``ENLIGHTENMENT_TEAM_TOKEN`` is the
    container default and the operator console is documented as empty, so treating "no
    token" as "open" would put unauthenticated write endpoints on a public ingress by
    omission. Anonymous writes require the explicit ``ENLIGHTENMENT_ALLOW_ANONYMOUS``
    opt-in, and then the actor is recorded as anonymous, not as a local user.
    """

    def require_token(x_team_token: str | None = Header(default=None)) -> str:
        settings = runtime.settings
        if settings.writes_open:
            return ANONYMOUS_ACTOR
        if not settings.auth_required or not token_ok(x_team_token, settings.team_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
            )
        return TEAM_ACTOR

    return require_token


def _expected_rev(if_match: str | None) -> int | None:
    """Parse an ``If-Match`` revision, ignoring an unparsable one rather than failing.

    A caller that sends no usable validator simply gets no concurrency guard; the store's
    exclusive lock still prevents a lost update either way.
    """
    if not if_match:
        return None
    candidate = if_match.strip().removeprefix("W/").strip('"')
    return int(candidate) if candidate.isdigit() else None


def _guard_write_rate(runtime: _Runtime, request: Request) -> None:
    """Apply the strict tier. Shared by both write routes so neither can drift from it."""
    if not runtime.strict.allow(_client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded"
        )


def _register_session_routes(app: FastAPI, runtime: _Runtime) -> None:
    """Training sessions: an open read of low-sensitivity data, and gated writes.

    Every store call runs in a worker thread. The store does blocking file input and
    output including an ``fsync``, and running that directly in an ``async`` handler
    blocks the event loop, which would stall the liveness and readiness paths on that
    worker whenever the volume is slow: the silent-liveness-kill class again.
    """
    require_token = _token_dependency(runtime)

    @app.get("/api/v1/sessions")
    async def list_sessions(
        response: Response, if_none_match: str | None = Header(default=None)
    ) -> Any:
        snapshot = await asyncio.to_thread(runtime.store.load)
        etag = f'W/"{snapshot["rev"]}"'
        response.headers["etag"] = etag
        if if_none_match and if_none_match.strip() == etag:
            response.status_code = status.HTTP_304_NOT_MODIFIED
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"etag": etag})
        sessions = [dict(session) for session in snapshot["sessions"]]
        return {"count": len(sessions), "rev": snapshot["rev"], "sessions": sessions}

    @app.post("/api/v1/sessions", status_code=status.HTTP_201_CREATED)
    async def upsert_session(
        payload: SessionUpsert,
        request: Request,
        response: Response,
        actor: str = Depends(require_token),
        if_match: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Create or fully upsert a session. Gated, strictly rate-limited, boundary
        validated, revision guarded, and audited.
        """
        _guard_write_rate(runtime, request)
        result = await _write(
            runtime, payload.model_dump(exclude_none=True), _expected_rev(if_match)
        )
        audit(
            "session.upsert",
            actor=actor,
            sessionId=result.session.get("id"),
            rev=result.rev,
            countBefore=result.count_before,
            countAfter=result.count_after,
        )
        response.headers["etag"] = f'W/"{result.rev}"'
        return {"session": result.session, "rev": result.rev}

    @app.patch("/api/v1/sessions/{session_id}")
    async def patch_session(
        session_id: str,
        payload: SessionPatch,
        request: Request,
        response: Response,
        actor: str = Depends(require_token),
        if_match: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Apply a partial update. The merge is anti-shrink: a field the caller did not
        send keeps its stored value rather than being deleted.
        """
        _guard_write_rate(runtime, request)
        known = {session.get("id") for session in await asyncio.to_thread(runtime.store.sessions)}
        if session_id not in known:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such session")
        update = payload.model_dump(exclude_none=True)
        result = await _write(runtime, {"id": session_id, **update}, _expected_rev(if_match))
        audit(
            "session.patch",
            actor=actor,
            sessionId=session_id,
            rev=result.rev,
            fields=sorted(update),
        )
        response.headers["etag"] = f'W/"{result.rev}"'
        return {"session": result.session, "rev": result.rev}


async def _write(runtime: _Runtime, record: dict[str, Any], expected_rev: int | None) -> Any:
    """Perform a guarded write off the event loop, mapping a stale revision to a 409."""
    try:
        return await asyncio.to_thread(
            runtime.store.upsert_session, record, expected_rev=expected_rev
        )
    except StaleRevisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"stale revision: store is at {exc.current}",
        ) from exc


def create_app(
    *,
    config: Config | None = None,
    store: TrainingStore | None = None,
    probe: ProbeFn | None = None,
    probe_settings: ProbeSettings | None = None,
    global_limiter: RateLimiter | None = None,
    write_limiter: RateLimiter | None = None,
    clock: Callable[[], float] | None = None,
) -> FastAPI:
    """Build the application without listening.

    Every dependency is injectable, so the suite needs no network, no real clock, and no
    filesystem beyond a temporary directory.
    """
    settings = config if config is not None else load_config()
    ticks = clock if clock is not None else time.monotonic
    runtime = _Runtime(
        settings=settings,
        store=store if store is not None else TrainingStore(settings.data_dir),
        probe=probe if probe is not None else probe_writable,
        probe_settings=probe_settings if probe_settings is not None else ProbeSettings(),
        coarse=global_limiter or RateLimiter(GLOBAL_LIMIT, GLOBAL_WINDOW_SECONDS),
        strict=write_limiter or RateLimiter(WRITE_LIMIT, WRITE_WINDOW_SECONDS),
        started=ticks(),
        clock=ticks,
    )

    app = FastAPI(
        title="Enlightenment",
        version=__version__,
        description="Orbital warfare training application.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Registered innermost first: add_middleware puts each new layer OUTSIDE the last, so
    # the resulting order from the wire inwards is CORS, rate limit, body cap, routes.
    _install_rate_limit(app, runtime)
    app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_BODY_BYTES)
    _install_cors(app, runtime)

    _install_error_handlers(app)
    _boot(runtime)
    _register_probe_routes(app, runtime)
    _register_diagnostics_route(app, runtime)
    _register_session_routes(app, runtime)
    return app
