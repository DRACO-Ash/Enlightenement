"""The HTTP application factory.

``create_app(...)`` wires routes, middleware, and injected dependencies and returns the
app WITHOUT listening, so the suite can mount it in-process with fakes. The listener
lives in :mod:`enlightenment.__main__` (local) and :mod:`enlightenment.asgi` (container).

The request pipeline, outermost first: cross-origin policy, the coarse rate limit, the
byte-counting body cap, then per-route authentication on every cost-incurring or
state-changing route, then boundary validation of the body, then the handler, then a
generic error response with the detail kept server-side.

``add_middleware`` PREPENDS, so the registration order at the bottom of this module is the
reverse of that list. The order is load-bearing twice over: the limiter must sit OUTSIDE the
body cap, or an oversize request is read in full while spending no limiter budget, and the
cross-origin layer must be outermost, or a 413 or a 429 reaches a browser with no
``Access-Control-Allow-Origin`` header and reads as an opaque network error. Both were wrong
in the first version and both are now asserted by tests.

Route registration is split into small ``_register_*`` helpers rather than one long
factory, so no function approaches the cognitive-complexity cap the quality gate enforces.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
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
from enlightenment.middleware import BodyLimitMiddleware, NoSniffMiddleware
from enlightenment.models import SessionPatch, SessionUpsert
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import (
    SCHEMA_VERSION,
    ProbeResult,
    StaleRevisionError,
    TrainingStore,
    UnknownSessionError,
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
#: then trips the probe's own timeout, so the pod flips unready and is restarted.
#:
#: Caching alone is NOT sufficient, and the first version of this was not. A cache with an
#: await between the read and the write bounds nothing under concurrency: every request
#: arriving while a probe is in flight misses and starts its own. Measured at 17 400
#: concurrent requests producing 228 real probes, and worse, queued probes on a slow volume
#: exceeded the probe timeout so a majority of responses were 503 against storage that was
#: fine. So probes are ALSO single-flight (below): concurrent callers await the one probe
#: already running. Cost is then bounded by time AND by concurrency.
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

#: Longest revision a validator may declare. Comfortably past any real revision (a 64-bit
#: counter is 19 digits) and far below CPython's 4300-digit integer conversion limit, which a
#: longer value would trip as a ValueError.
MAX_REVISION_DIGITS = 19

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
    #: The one probe currently running, if any. Concurrent callers await this rather than
    #: starting their own.
    inflight: asyncio.Task[ProbeResult] | None = field(default=None)
    #: A dedicated single-thread executor for the probe, so a burst of probes can never
    #: starve the store's own thread-pool work. Sharing the default executor was measured
    #: taking a legitimate listing from 1.4 ms to 109 ms at the median.
    #:
    #: Built eagerly, and lazily on purpose no longer. Two rounds of review went into an
    #: attempt to create it on first probe, on the theory that an unserved app would otherwise
    #: hold an idle thread. That theory is wrong twice over: a ThreadPoolExecutor starts no
    #: worker until work is submitted, and a dereferenced executor's worker exits when the
    #: executor is collected. So laziness saved no thread, no test could distinguish the two
    #: variants, and the branch was unassertable code inside a control. It is gone. The
    #: control that does matter is the lifespan release, which stops the worker of the pool the
    #: runtime still holds a reference to, and that IS asserted.
    probe_pool: ThreadPoolExecutor | None = field(default=None)


def _client_key(request: Request) -> str:
    """Rate-limit key for a caller. Behind the platform gateway many callers can share
    one address; that is an accepted coarseness, recorded in docs/SECURITY.md.
    """
    client = request.client
    return client.host if client is not None else "unknown"


async def _probe_storage(runtime: _Runtime) -> ProbeResult:
    """Return a storage verdict, reusing a recent one and never running two at once.

    TWO properties, and the first version had only the second:

    1. **Single-flight.** A caller arriving while a probe runs awaits THAT probe. Without
       this, concurrency defeats the cache entirely and the queued probes then exceed their
       own timeout, so an unauthenticated burst makes healthy storage report 503 and takes
       the pod out of rotation.
    2. **Time-bounded.** A verdict is reused for ``cache_seconds``, well under the
       platform's probe interval, so a real fault is still noticed promptly.

    Publication ordering deliberately has no separate guard, and single-flight is NOT what
    makes that safe. Two probe tasks CAN coexist: cancel a starter at its ``shield`` and the
    ``finally`` clears ``inflight`` while the shielded task keeps running, so the next caller
    starts a second one. Two independent reviewers reproduced exactly that. The invariants
    the code actually relies on are narrower:

    ● Only the caller that STARTED a probe publishes it, and a cancelled starter never
      reaches the publication lines at all.
    ● The probe pool has ONE worker, so a second probe's executor round trip cannot finish
      before the first starter's two remaining loop hops.

    Together those make a stale verdict overwriting a newer one non-constructible, which is
    why an explicit ordering check would be unreachable, and unreachable code inside a
    security control invites a wrong mental model of how the control behaves. A consequence
    worth knowing: a cancelled starter abandons its probe holding the single worker, so the
    next caller's probe queues behind it and may return the fail-closed timeout verdict.
    """
    now = runtime.clock()
    cached = runtime.cached_probe
    if (
        cached is not None
        and runtime.cached_at is not None
        and now - runtime.cached_at < runtime.probe_settings.cache_seconds
    ):
        return cached

    inflight = runtime.inflight
    if inflight is not None and not inflight.done():
        # Join the probe already running. `shield` so a cancelled waiter cannot cancel the
        # shared probe out from under the others.
        return await asyncio.shield(inflight)

    task: asyncio.Task[ProbeResult] = asyncio.ensure_future(_run_probe(runtime))
    runtime.inflight = task
    try:
        result = await asyncio.shield(task)
    finally:
        if runtime.inflight is task:
            runtime.inflight = None

    runtime.cached_probe = result
    runtime.cached_at = runtime.clock()
    return result


async def _run_probe(runtime: _Runtime) -> ProbeResult:
    """Race one storage probe against a hard timeout on the dedicated pool, converting
    every rejection into a value. A probe that can hang turns an infrastructure fault into
    an undiagnosable silent liveness kill.
    """
    data_dir = runtime.settings.data_dir
    if runtime.probe_pool is None:
        # Only reachable after the lifespan released the pool. Passing None to
        # run_in_executor would silently fall back to the DEFAULT executor, which is the exact
        # starvation the dedicated pool exists to prevent (a legitimate listing measured at
        # 1.4 ms against 109 ms). Fail closed instead of degrading quietly.
        return ProbeResult(
            ok=False, resolved=str(data_dir), detail="probe pool released; app is shutting down"
        )
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(runtime.probe_pool, runtime.probe, data_dir),
            runtime.probe_settings.timeout,
        )
    except TimeoutError:
        return ProbeResult(
            ok=False,
            resolved=str(data_dir),
            detail=f"storage probe timed out after {runtime.probe_settings.timeout}s",
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
    runtime.cached_probe = result
    runtime.cached_at = runtime.clock()
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


def _install_error_handlers(app: FastAPI, runtime: _Runtime) -> None:
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
        """The one response class no user middleware can reach, so it sets its own headers.

        Starlette installs `ServerErrorMiddleware` ABOVE every user middleware, and that is what
        renders this handler's response. So `NoSniffMiddleware`, registered outermost among user
        middleware, never sees a 500: measured, an unhandled exception answered with neither
        `x-content-type-options` nor `access-control-allow-origin`, while the code and three
        documents claimed the header was on "every response".

        "Outermost" was true and meant less than it sounded. Both headers are set here explicitly
        rather than by widening the middleware, because there is nowhere above
        `ServerErrorMiddleware` for a user layer to go.
        """
        _logger.exception("unhandled error serving %s", sanitise_log_value(request.url.path))
        headers = {"x-content-type-options": "nosniff"}
        # The cross-origin header too, and its absence here was the more consequential half: a
        # browser that cannot read a 500 reports an opaque network error, which is exactly the
        # case an operator most needs to see. Echoed only for the configured origin, never `*`.
        origin = request.headers.get("origin")
        if origin and origin == runtime.settings.allowed_origin:
            headers["access-control-allow-origin"] = origin
            headers["vary"] = "Origin"
        return JSONResponse(
            {"error": "internal error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers=headers,
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
    # ASCII decimal digits only, AND a length bound, AND a guarded conversion. Each closes a
    # different way this has already returned 500 from a path documented to IGNORE an
    # unparsable validator:
    #
    # ● `isdigit()` accepts characters `int()` rejects (a superscript two), fixed first.
    # ● Even all-ASCII digits raise: CPython caps integer string conversion at 4300 digits, so
    #   a 4301-digit validator raised `ValueError: Exceeds the limit`. A reviewer found that on
    #   a real socket AFTER the first fix was recorded as closing this class, which is why the
    #   guard is now three-layered rather than one more predicate.
    # ● The try/except is the backstop for whatever the next spelling turns out to be. A
    #   documented fail-safe should not depend on having enumerated every hostile input.
    if not (candidate.isascii() and candidate.isdecimal()):
        return None
    if len(candidate) > MAX_REVISION_DIGITS:
        return None
    try:
        return int(candidate)
    except ValueError:
        return None


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
        update = payload.model_dump(exclude_none=True)
        # must_exist is checked INSIDE the store's lock. Checking it here first left a
        # window in which a concurrent new-id write could trip the session cap and evict
        # this id, so the "merge" would append a partial record with only the patched
        # fields and a fresh createdAt.
        result = await _write(
            runtime, {"id": session_id, **update}, _expected_rev(if_match), must_exist=True
        )
        audit(
            "session.patch",
            actor=actor,
            sessionId=session_id,
            rev=result.rev,
            fields=sorted(update),
        )
        response.headers["etag"] = f'W/"{result.rev}"'
        return {"session": result.session, "rev": result.rev}


async def _write(
    runtime: _Runtime,
    record: dict[str, Any],
    expected_rev: int | None,
    *,
    must_exist: bool = False,
) -> Any:
    """Perform a guarded write off the event loop, mapping the store's refusals to statuses."""
    try:
        return await asyncio.to_thread(
            runtime.store.upsert_session,
            record,
            expected_rev=expected_rev,
            must_exist=must_exist,
        )
    except UnknownSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no such session"
        ) from exc
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
        probe_pool=ThreadPoolExecutor(max_workers=1, thread_name_prefix="probe"),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Release the pool the runtime holds.

        Constructing the pool starts no worker; this stops the one a probe started. An app
        built and never served therefore holds no thread whether or not this ever runs, which
        is a property of ``ThreadPoolExecutor`` and not of when the pool is created. An earlier
        version of this docstring credited lazy creation for it, three lines above the code
        that builds the pool eagerly.
        """
        try:
            yield
        finally:
            if runtime.probe_pool is not None:
                runtime.probe_pool.shutdown(wait=False)
                runtime.probe_pool = None
            # Cleared in the same breath as the release. Leaving the published reference
            # pointing at a shut-down executor while the runtime's own is None publishes two
            # facts that disagree, and a later reader can take the stale one as live.
            app.state.probe_pool = None
            # Published so a test can assert the precondition it depends on, rather than
            # assuming the release happened and then testing what follows from it.
            app.state.runtime_probe_pool_released = True

    app = FastAPI(
        title="Enlightenment",
        version=__version__,
        description="Orbital warfare training application.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    # Registered innermost FIRST, because add_middleware prepends. The resulting order from
    # the wire inwards is: nosniff, CORS, rate limit, body cap, routes - and note that
    # Starlette's own ServerErrorMiddleware sits outside all of these, which is why the 500
    # handler sets its own headers rather than relying on the layer named first here. Asserted by
    # test_the_middleware_order_puts_the_limiter_outside_the_body_cap, because getting it
    # backwards let an oversize request be read in full while spending no limiter budget.
    app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_BODY_BYTES, exempt_paths=UNLIMITED_PATHS)
    _install_rate_limit(app, runtime)
    _install_cors(app, runtime)
    # Outermost among USER middleware, so the header is on every response this stack produces,
    # including one a middleware answers itself: a 413 from the body cap and a 429 from the limiter
    # are responses a browser can be pointed at too, and a header installed inside them would miss
    # both. It does NOT reach the unhandled-exception 500 - `ServerErrorMiddleware` sits above
    # every user layer - which is why `on_unhandled` sets its own headers.
    app.add_middleware(NoSniffMiddleware)

    # An IN-PROCESS inspection seam, so a test can assert the constructed wiring rather than
    # grep the source for it. Deliberately narrow: publishing the whole runtime put
    # `settings.team_token` within reach of any handler or third-party ASGI middleware through
    # `request.app.state`, where before it was only closure-captured. Nothing read it, but reach
    # is the thing to avoid, so only the pool is published.
    app.state.probe_pool = runtime.probe_pool
    app.state.runtime_probe_pool_released = False

    _install_error_handlers(app, runtime)
    _boot(runtime)
    _register_probe_routes(app, runtime)
    _register_diagnostics_route(app, runtime)
    _register_session_routes(app, runtime)
    return app
