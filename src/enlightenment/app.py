"""The HTTP application factory.

``create_app(...)`` wires routes, middleware, and injected dependencies and returns the
app WITHOUT listening, so the suite can mount it in-process with fakes. The listener
lives in :mod:`enlightenment.__main__` (local) and :mod:`enlightenment.asgi` (container).

The request pipeline is: size cap, then the coarse rate limit, then authentication on
every cost-incurring or state-changing route, then boundary validation of the body, then
the handler, then a generic error response with the detail kept server-side.

Route registration is split into small ``_register_*`` helpers rather than one long
factory, so no function approaches the cognitive-complexity cap the platform's quality
gate enforces.
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
from enlightenment.audit import audit
from enlightenment.auth import TOKEN_HEADER, token_ok
from enlightenment.config import Config, load_config, resolve_data_dir
from enlightenment.models import SessionPatch, SessionUpsert
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import SCHEMA_VERSION, ProbeResult, TrainingStore, probe_writable

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

#: Coarse limiter: protects the process on every non-probe route.
GLOBAL_LIMIT = 240
GLOBAL_WINDOW_SECONDS = 60.0

#: Strict limiter: protects the state-changing route.
WRITE_LIMIT = 20
WRITE_WINDOW_SECONDS = 60.0

#: Request body cap. Anything larger is rejected before it is parsed.
MAX_BODY_BYTES = 64 * 1024

#: Actor label recorded for a call made in single-user local mode.
LOCAL_ACTOR = "local"

#: Actor label recorded for a call authenticated with the shared team token.
TEAM_ACTOR = "team"

_logger = logging.getLogger("enlightenment.app")

ProbeFn = Callable[[Path], ProbeResult]


@dataclass(slots=True)
class _Runtime:
    """The resolved dependencies one app instance serves from."""

    settings: Config
    store: TrainingStore
    probe: ProbeFn
    probe_timeout: float
    coarse: RateLimiter
    strict: RateLimiter
    started: float
    ready: bool | None = field(default=None)


def _client_key(request: Request) -> str:
    """Rate-limit key for a caller. Behind the platform gateway many callers can share
    one address; that is an accepted coarseness, recorded in docs/SECURITY.md.
    """
    client = request.client
    return client.host if client is not None else "unknown"


async def _run_probe(runtime: _Runtime, data_dir: Path) -> ProbeResult:
    """Race the storage probe against a hard timeout, converting every rejection into a
    value. The probe must never be able to hang: a hanging probe turns an infrastructure
    fault into an undiagnosable silent liveness kill.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(runtime.probe, data_dir), runtime.probe_timeout
        )
    except TimeoutError:
        return ProbeResult(
            ok=False,
            resolved=str(data_dir),
            detail=f"storage probe timed out after {runtime.probe_timeout}s",
        )
    except Exception as exc:
        # Fail closed: any probe failure at all is an unready state, never a pass.
        _logger.exception("storage probe raised")
        return ProbeResult(ok=False, resolved=str(data_dir), detail=exc.__class__.__name__)


def _identity() -> dict[str, Any]:
    """This process's own identity only. Enough to show a non-root container is non-root,
    with nothing about any other principal.
    """
    return {"uid": os.getuid(), "gid": os.getgid()}


def _secret_shape(value: str) -> dict[str, Any]:
    """A boolean AND a length for a sensitive input, never the value.

    The pair distinguishes a stale value from a correct one at a glance without leaking
    either.
    """
    return {"set": bool(value), "length": len(value)}


def _boot(runtime: _Runtime) -> None:
    """Probe storage once at boot and record the answer in one decisive log line, so a
    pod the platform later kills still leaves a narrative rather than only "listening".

    Fail closed for security AND to a RECOVERABLE state for operations: a storage fault
    must make the app unready, never make it unstartable. An app that refuses to boot
    cannot serve the readiness diagnosis that says why, which is how a simple mount
    permission problem becomes an undiagnosable outage.
    """
    try:
        result = runtime.probe(runtime.settings.data_dir)
    except Exception as exc:
        _logger.exception("boot storage probe raised; starting unready")
        result = ProbeResult(
            ok=False, resolved=str(runtime.settings.data_dir), detail=exc.__class__.__name__
        )
    _logger.info(
        "boot storage probe: writable=%s dataDir=%s errno=%s detail=%s",
        result.ok,
        result.resolved,
        result.errno,
        result.detail,
    )
    if result.ok:
        runtime.store.seed()


def _install_cors(app: FastAPI, runtime: _Runtime) -> None:
    """Allow exactly one configured origin, or none at all. A wildcard with a token set
    never reaches here: the configuration refuses to load.
    """
    origin = runtime.settings.allowed_origin
    if origin and origin != "*":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[origin],
            allow_methods=["GET", "POST"],
            allow_headers=[TOKEN_HEADER, "content-type"],
        )


def _install_guard(app: FastAPI, runtime: _Runtime) -> None:
    """Size cap, then the coarse rate limit, ahead of every handler."""

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return JSONResponse(
                {"error": "request body too large"},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        limited = request.url.path not in UNLIMITED_PATHS
        if limited and not runtime.coarse.allow(_client_key(request)):
            return JSONResponse(
                {"error": "rate limit exceeded"}, status_code=status.HTTP_429_TOO_MANY_REQUESTS
            )
        return await call_next(request)


def _install_error_handlers(app: FastAPI) -> None:
    """The client gets a generic message; the cause is logged server-side."""

    @app.exception_handler(RequestValidationError)
    async def on_invalid_body(request: Request, _exc: RequestValidationError) -> JSONResponse:
        _logger.warning("rejected a malformed request to %s", request.url.path)
        return JSONResponse(
            {"error": "invalid request"}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        )

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, _exc: Exception) -> JSONResponse:
        _logger.exception("unhandled error serving %s", request.url.path)
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
        result = await _run_probe(runtime, resolve_data_dir())
        if runtime.ready != result.ok:
            _logger.info("readiness transition: ready=%s detail=%s", result.ok, result.detail)
            runtime.ready = result.ok
        response.status_code = (
            status.HTTP_200_OK if result.ok else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return {"status": "ok" if result.ok else "unready", "storage": result.as_diagnostic()}


def _register_diagnostics_route(app: FastAPI, runtime: _Runtime) -> None:
    """The secret-free read-out. Every field that could answer a plausible deploy failure
    is present at once, so a deploy cycle is never spent on a question a boolean answers.
    """

    @app.get("/api/v1/diagnostics")
    async def diagnostics() -> dict[str, Any]:
        result = await _run_probe(runtime, resolve_data_dir())
        settings = runtime.settings
        return {
            "buildId": settings.build_id,
            "version": __version__,
            "schemaVersion": SCHEMA_VERSION,
            "pythonVersion": sys.version.split()[0],
            "port": settings.port,
            "host": settings.host,
            "uptimeSeconds": round(time.monotonic() - runtime.started, 3),
            "identity": _identity(),
            "storage": result.as_diagnostic(),
            "config": {
                "teamToken": _secret_shape(settings.team_token),
                "allowedOrigin": _secret_shape(settings.allowed_origin),
                "authRequired": settings.auth_required,
            },
        }


def _token_dependency(runtime: _Runtime) -> Callable[[str | None], str]:
    """Build the auth dependency for privileged routes.

    This is the single-sign-on seam: the one place a per-user identity provider would
    later attach. Open when no token is configured (single-user local mode); otherwise a
    valid token is mandatory.
    """

    def require_token(x_team_token: str | None = Header(default=None)) -> str:
        if not runtime.settings.auth_required:
            return LOCAL_ACTOR
        if not token_ok(x_team_token, runtime.settings.team_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
            )
        return TEAM_ACTOR

    return require_token


def _register_session_routes(app: FastAPI, runtime: _Runtime) -> None:
    """Training sessions: an open read of low-sensitivity data, and a gated write."""
    require_token = _token_dependency(runtime)

    @app.get("/api/v1/sessions")
    async def list_sessions() -> dict[str, Any]:
        sessions = runtime.store.sessions()
        return {"count": len(sessions), "sessions": sessions}

    @app.post("/api/v1/sessions", status_code=status.HTTP_201_CREATED)
    async def upsert_session(
        payload: SessionUpsert, request: Request, actor: str = Depends(require_token)
    ) -> dict[str, Any]:
        """Create or anti-shrink-merge a training session. Gated, strictly rate-limited,
        boundary-validated, and audited.
        """
        if not runtime.strict.allow(_client_key(request)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded"
            )
        before = len(runtime.store.sessions())
        stored = runtime.store.upsert_session(payload.model_dump(exclude_none=True))
        after = len(runtime.store.sessions())
        audit(
            "session.upsert",
            actor=actor,
            sessionId=stored["id"],
            countBefore=before,
            countAfter=after,
        )
        return {"session": stored}

    @app.patch("/api/v1/sessions/{session_id}")
    async def patch_session(
        session_id: str,
        payload: SessionPatch,
        request: Request,
        actor: str = Depends(require_token),
    ) -> dict[str, Any]:
        """Apply a partial update. The merge is anti-shrink: a field the caller did not
        send keeps its stored value rather than being deleted.
        """
        if not runtime.strict.allow(_client_key(request)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded"
            )
        known = {session["id"] for session in runtime.store.sessions()}
        if session_id not in known:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such session")
        update = payload.model_dump(exclude_none=True)
        stored = runtime.store.upsert_session({"id": session_id, **update})
        audit("session.patch", actor=actor, sessionId=session_id, fields=sorted(update))
        return {"session": stored}


def create_app(
    *,
    config: Config | None = None,
    store: TrainingStore | None = None,
    probe: ProbeFn | None = None,
    probe_timeout: float = PROBE_TIMEOUT_SECONDS,
    global_limiter: RateLimiter | None = None,
    write_limiter: RateLimiter | None = None,
) -> FastAPI:
    """Build the application without listening.

    Every dependency is injectable, so the suite needs no network, no real clock, and no
    filesystem beyond a temporary directory.
    """
    settings = config if config is not None else load_config()
    runtime = _Runtime(
        settings=settings,
        store=store if store is not None else TrainingStore(settings.data_dir),
        probe=probe if probe is not None else probe_writable,
        probe_timeout=probe_timeout,
        coarse=global_limiter or RateLimiter(GLOBAL_LIMIT, GLOBAL_WINDOW_SECONDS),
        strict=write_limiter or RateLimiter(WRITE_LIMIT, WRITE_WINDOW_SECONDS),
        started=time.monotonic(),
    )

    app = FastAPI(
        title="Enlightenment",
        version=__version__,
        description="Orbital warfare training application.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    _install_cors(app, runtime)
    _install_guard(app, runtime)
    _install_error_handlers(app)
    _boot(runtime)
    _register_probe_routes(app, runtime)
    _register_diagnostics_route(app, runtime)
    _register_session_routes(app, runtime)
    return app
