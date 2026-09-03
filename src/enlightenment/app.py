"""The HTTP application factory.

``create_app(...)`` wires routes, middleware, and injected dependencies and returns the
app WITHOUT listening, so the suite can mount it in-process with fakes. The listener
lives in :mod:`enlightenment.__main__` (local) and :mod:`enlightenment.asgi` (container).

The request pipeline, outermost first: the nosniff header, cross-origin policy, the coarse
rate limit, the byte-counting body cap, then per-route authentication on every cost-incurring
or state-changing route, then boundary validation of the body, then the handler, then a
generic error response with the detail kept server-side.

``add_middleware`` PREPENDS, so the registration order at the bottom of this module is the
reverse of that list. The order is load-bearing twice over: the limiter must sit OUTSIDE the
body cap, or an oversize request is read in full while spending no limiter budget, and the
cross-origin layer must sit outside the limiter and the cap, or a 413 or a 429 reaches a
browser with no ``Access-Control-Allow-Origin`` header and reads as an opaque network error.
Both were wrong in the first version.

**The single authority for this ordering is
``test_the_middleware_order_puts_the_limiter_outside_the_body_cap``, which asserts
``app.user_middleware`` directly.** Cited here rather than described, because a prose claim
about ordering with no anchor is how this docstring came to say "the cross-origin layer must
be outermost" and stay that way for three releases after the nosniff layer overtook it. Note
also what NO user layer reaches: Starlette's ``ServerErrorMiddleware`` renders the
unhandled-exception 500 above all of them, which is why ``on_unhandled`` sets its own
headers.

Route registration is split into small ``_register_*`` helpers rather than one long
factory, so no function approaches the cognitive-complexity cap the quality gate enforces.
"""

# NO `from __future__ import annotations` in this module, deliberately, and it is load-bearing.
# That import turns every annotation into a STRING, which FastAPI then resolves against module
# globals. The route dependencies here close over `require_token`, a local built inside
# `create_app`, so the string cannot be resolved from module scope: FastAPI stopped seeing `actor`
# as a dependency and treated it as a request field, and every gated write returned 422 instead of
# 201. Measured across six tests the moment the annotations were converted.
#
# Python 3.12 needs no future import for `X | None`, `list[str]` or any syntax used here, so the
# only thing it bought was lazy evaluation - and lazy evaluation is exactly what broke.

import asyncio
import json
import logging
import os
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from enlightenment import __version__
from enlightenment.audit import ANONYMOUS_ACTOR, audit, log_event, sanitise_log_value
from enlightenment.auth import AUTH_HEADER, token_ok
from enlightenment.config import Config, load_config, token_length_bucket
from enlightenment.content import ContentPackage
from enlightenment.generators import build_registry
from enlightenment.identifiers import served_identifier
from enlightenment.middleware import BodyLimitMiddleware, NoSniffMiddleware
from enlightenment.models import SessionPatch, SessionUpsert
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import (
    MAX_REVISION_DIGITS as STORED_MAX_REVISION_DIGITS,
)
from enlightenment.storage import (
    SCHEMA_VERSION,
    ProbeResult,
    StaleRevisionError,
    TrainingStore,
    UnknownSessionError,
    probe_writable,
)
from enlightenment.training import DrillLoop, ProgressStore
from enlightenment.training.drill import bounded_reason
from enlightenment.training_api import register_training_routes, resolve_content_root

#: Liveness paths. Cheap, dependency-free, always 200: a downstream outage must never
#: restart a healthy container.
LIVENESS_PATHS = ("/livez", "/ping", "/health")

#: Readiness paths. 200 when storage accepts a real write, 503 with the diagnosis when not.
READINESS_PATHS = ("/healthz", "/readyz")

#: Paths exempt from rate limiting. The platform probes these; a 429 would read as unhealthy.
UNLIMITED_PATHS = frozenset(LIVENESS_PATHS + READINESS_PATHS + ("/",))

#: Hard probe timeout. **`TBC, re-verify`: the claim that this is strictly shorter than the
#: platform's own probe timeout has no figure in this repository to rest on** - the App Store
#: publishes no `timeoutSeconds` in `docs/DEPLOYMENT.md` or anywhere else here, and a Kubernetes
#: default of 1 s would make 2.0 s longer, not shorter. Requested from the owner by name rather
#: than inferred around, which is this project's rule for a missing document. What is not in
#: doubt is the property this constant exists for: the probe cannot hang, so a stalled
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

#: The drill scorer's own budget, deliberately NOT the one the gated writes share.
#: `POST /api/v1/drill/answer` is unauthenticated on purpose until operator identity exists
#: (flight plan step 10), and while it shared the strict limiter an unauthenticated caller could
#: spend the whole strict budget in twenty requests and leave the token-authenticated session
#: writes answering 429. Measured, in the security gate's round on V0.23.16: twenty unauthenticated
#: answers, then an authenticated `POST /api/v1/sessions` refused. An open route must not be able
#: to shut a gated one. Same shape and same numbers; a separate bucket is the whole point.
DRILL_LIMIT = 20
DRILL_WINDOW_SECONDS = 60.0

#: Request body cap, enforced on bytes actually read (see :mod:`enlightenment.middleware`).
MAX_BODY_BYTES = 64 * 1024

#: How many stored sessions the ANONYMOUS listing serves, newest first, and the byte ceiling that
#: number is sized against. `GET /api/v1/sessions` is unauthenticated by the decision recorded in
#: `docs/SECURITY.md` accepted risk 5, and it was excluded from the anonymous-body sweep on the
#: claim that the session routes are token-gated. **That claim was false for the read**, and the
#: size claim beside it - that `storage.MAX_SESSIONS` and the field caps govern the body, "which
#: their own tests hold" - was held by nothing: `MAX_SESSIONS` appeared in the suite only in that
#: comment.
#:
#: Measured on the wire, filling the store to `MAX_SESSIONS` through the token-gated write route
#: with every field inside its declared cap (title 200, scenario 120, notes 2000, all accepted
#: with 201): **1,231,926 bytes of ASCII and 4,711,926 bytes with astral characters**, from one
#: unauthenticated request, uncached. The second figure is past this project's own 4 MB
#: `MAX_PAYLOAD_BYTES`, so the collection was bounded by nothing the server chose.
#:
#: 25 matches the sibling served-count caps (`MAX_SERVED_PARAMS`, `MAX_SERVED_WITHHELD`) rather
#: than being picked, and it holds the astral worst case at about 236 kB against the ceiling
#: below. The UNTRUNCATED total is served beside the list, and `truncated` says outright that the
#: listing is short, because a shortened disclosure must never read as a complete one.
MAX_SERVED_SESSIONS = 25
MAX_SERVED_SESSIONS_BYTES = 256 * 1024

#: Actor label for a call authenticated with the shared team token.
TEAM_ACTOR = "team"

#: Longest revision a validator may declare. Re-exported from `storage`, which is where it now
#: lives, because the STORED side needed the same figure and `storage` cannot import from here.
#: One constant for one number: the two sides of a revision disagreed for as long as there were
#: two places to put it, and a planted 4,000-digit `rev` reached an anonymous `ETag` header.
MAX_REVISION_DIGITS = STORED_MAX_REVISION_DIGITS

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


@dataclass(frozen=True, slots=True)
class Limiters:
    """The two rate limiters one app instance shares.

    Grouped rather than passed separately, and the reason is the same one recorded on
    `ProbeSettings`: `create_app` sits at the seven-parameter cap the platform's quality gate
    enforces (Sonar S107), and the training layer needed a parameter. Grouping two values that
    are always supplied together is the honest way to make room; a suppression would not have
    made the signature any easier to read.
    """

    coarse: RateLimiter | None = None
    strict: RateLimiter | None = None
    drill: RateLimiter | None = None


@dataclass(frozen=True, slots=True)
class TrainingPaths:
    """Where the training layer reads content and writes progress.

    One parameter object rather than two more keyword arguments on `create_app`, which was
    already at the seven-parameter cap the platform's quality gate enforces (Sonar S107). Both
    default to None and resolve at registration, so a test overrides one without naming the
    other.
    """

    content_root: Path | None = None
    progress_path: Path | None = None


@dataclass(slots=True)
class _Runtime:
    """The resolved dependencies one app instance serves from."""

    settings: Config
    store: TrainingStore
    probe: ProbeFn
    probe_settings: ProbeSettings
    coarse: RateLimiter
    strict: RateLimiter
    drill: RateLimiter
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
    unasserted condition on this line. Registered outside the limiter and the body cap, which
    is what puts the cross-origin headers on a 413 or a 429 as well as on a handler response;
    without that a browser client sees an opaque network error instead of a status.

    **This said "Registered LAST so it is the outermost middleware" until round eleven.** It was
    true when written and stopped being true the moment `NoSniffMiddleware` was registered after
    it - in the same commit that created the 500-header defect the three previous rounds were
    spent correcting. The ordering is asserted by
    `test_the_middleware_order_puts_the_limiter_outside_the_body_cap`, which was passing green on
    the correct four-layer order the whole time this sentence was wrong. A prose claim about
    ordering that does not cite that test is a claim with no anchor, which is exactly how this one
    survived.

    Neither this layer nor the nosniff layer reaches the unhandled-exception 500;
    `ServerErrorMiddleware` is above both, so `on_unhandled` sets those headers itself.
    """
    if runtime.settings.allowed_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[runtime.settings.allowed_origin],
            # Every method the API actually exposes. Kept in one place with a test that
            # parametrises over the real route table, so the two cannot drift.
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=[AUTH_HEADER, "content-type", "if-match", "if-none-match"],
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
        middleware, an order asserted by
        `test_the_middleware_order_puts_the_limiter_outside_the_body_cap` and by nothing else,
        never sees a 500: measured, an unhandled exception answered with neither
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
    """Apply the strict tier. Shared by the two GATED write routes so neither can drift from it.

    The drill scorer is deliberately not among them; see `_guard_drill_rate`.
    """
    if not runtime.strict.allow(_client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded"
        )


def _guard_drill_rate(runtime: _Runtime, request: Request) -> None:
    """The drill scorer's own budget, so an open route cannot shut a gated one.

    Same tier and same numbers as the gated writes, and a SEPARATE bucket. The scorer is
    unauthenticated until operator identity exists, so anyone can spend its budget; sharing one
    limiter with the token-gated session writes meant anyone could spend theirs too. Measured
    before this split: twenty unauthenticated answers, then an authenticated session write
    refused with 429.
    """
    if not runtime.drill.allow(_client_key(request)):
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
        if_none_match: Annotated[str | None, Header()] = None,
    ) -> Response:
        try:
            snapshot = await asyncio.to_thread(runtime.store.load)
        except ValueError as exc:
            #: FAIL CLOSED on a snapshot this process cannot read, rather than 500. Every
            #: malformed shape the store already refuses - not JSON, not UTF-8, not an object,
            #: nested too deep, and now a string that cannot be encoded - arrived here as an
            #: unhandled exception and a generic 500 on an UNAUTHENTICATED route. Measured on all
            #: four. A 503 naming the fault is diagnosable from a screenshot; a 500 is not, and
            #: the App Store contract asks for exactly that distinction on the health paths.
            #:
            #: The detail is the store's own message, which names the fault and a JSON pointer and
            #: never a stored value, and it is length-bounded on the way out for the same reason
            #: every other content-derived string on an anonymous route is.
            _logger.exception("stored snapshot is unreadable")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "store_unavailable", "message": bounded_reason(str(exc))},
            ) from None
        etag = f'W/"{snapshot["rev"]}"'
        #: The injected `response: Response` parameter is GONE, with both assignments that used
        #: it. Every path now returns an explicit `Response`, and FastAPI merges a sub-response's
        #: headers only on the branch that returns a plain object - so `response.headers["etag"]`
        #: and `response.status_code = 304` were dead on both paths. Proved rather than reasoned:
        #: deleting each one individually left all 1,010 tests green while the ETag stayed
        #: correct, because the explicit `Response` objects below carry it. Dead code that looks
        #: load-bearing is worse than absent code: a header added on that line later would be
        #: silently dropped, and a reader would believe line 681 is what sets the ETag.
        if if_none_match and if_none_match.strip() == etag:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"etag": etag})
        stored = snapshot["sessions"]
        #: The newest 25, in stored order, so the newest row is LAST: `storage._enforce_cap`
        #: keeps the newest and appends the fresh entry at the end, and the slice preserves that
        #: ascending order rather than reversing it. `count` keeps its meaning - how many rows
        #: are in this response - and `total` is the honest untruncated figure, so a short
        #: listing cannot read as the whole dataset. Same shape as the withheld collections.
        sessions = [dict(session) for session in stored[-MAX_SERVED_SESSIONS:]]
        body = {
            "count": len(sessions),
            "total": len(stored),
            "truncated": len(sessions) < len(stored),
            "rev": snapshot["rev"],
            "sessions": sessions,
        }
        #: The byte ceiling ENFORCED, not merely asserted in a test. `MAX_SERVED_SESSIONS_BYTES`
        #: appeared nowhere in `src/` except its own definition, so it bounded what the write path
        #: accepts and nothing else: measured, a 5 MB field value planted on the volume produced a
        #: 5,000,082-byte anonymous response, nineteen times the documented ceiling and past
        #: `MAX_PAYLOAD_BYTES`. The count cap cannot see that, because the fault is one row's size
        #: rather than the number of rows.
        #:
        #: FAIL CLOSED rather than truncate, the same choice as an oversized library document: a
        #: silently shortened listing reads as the whole dataset, which is the fault `total` and
        #: `truncated` exist to prevent.
        #:
        #: **The message states the figures and makes NO claim about how the rows got there.** It
        #: said "a row was not written through this API", and that was provably false: the write
        #: boundary accepted C0 control characters, which `json.dumps` escapes as six rendered
        #: bytes per code point even with `ensure_ascii=False`, so twenty legitimate authenticated
        #: writes at the declared caps reached 281,353 bytes and twenty-five rows 351,327. A 503
        #: exists here so a screenshot is a complete diagnosis; one that names the wrong CAUSE
        #: sends the operator hunting an out-of-band volume write that never happened. The cause is
        #: closed at `models.py` now, and this message no longer asserts one.
        #:
        #: **MEASURE THE BYTES THIS ROUTE ACTUALLY SENDS, and then send exactly those.** Two
        #: earlier versions measured a re-serialisation of the same object and both drifted from
        #: the wire in a different way. The first used `json.dumps`'s default `ensure_ascii=True`,
        #: which escapes an astral character to twelve ASCII characters rather than four bytes, so
        #: it over-counted multi-byte content threefold and refused the anonymous-body sweep's own
        #: legitimate astral fixture. The second fixed the encoding and still under-counted a
        #: planted `NaN` by one byte each, because pydantic rewrites `NaN` to `null` before
        #: Starlette renders: measured, a NaN-dense snapshot served 289,199 bytes with HTTP 200
        #: against this ceiling, 10.3% past it.
        #:
        #: A ceiling measured on anything other than the bytes leaving the socket is a ceiling
        #: that can drift, and it drifted twice. Serialising once and returning that exact
        #: `Response` removes the second serialisation as well as the basis, so there is no longer
        #: a second thing to keep in step. `allow_nan=False` refuses the shape rather than
        #: silently rewriting it, because a stored `NaN` cannot arrive through this API - every
        #: float form is a 422 - so its presence means the volume was written past the boundary.
        try:
            payload = json.dumps(
                jsonable_encoder(body), separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
        except ValueError as exc:
            _logger.exception("stored sessions cannot be serialised")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "store_unavailable",
                    "message": (f"the stored sessions cannot be serialised ({type(exc).__name__})"),
                },
            ) from None
        if len(payload) > MAX_SERVED_SESSIONS_BYTES:
            _logger.error(
                "session listing is %d bytes against a ceiling of %d",
                len(payload),
                MAX_SERVED_SESSIONS_BYTES,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "store_unavailable",
                    "message": (
                        f"the stored sessions render to {len(payload)} bytes against a ceiling of"
                        f" {MAX_SERVED_SESSIONS_BYTES}"
                    ),
                },
            )
        return Response(
            content=payload,
            media_type="application/json",
            headers={"etag": etag},
        )

    @app.post("/api/v1/sessions", status_code=status.HTTP_201_CREATED)
    async def upsert_session(
        payload: SessionUpsert,
        request: Request,
        response: Response,
        actor: Annotated[str, Depends(require_token)],
        if_match: Annotated[str | None, Header()] = None,
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
        actor: Annotated[str, Depends(require_token)],
        if_match: Annotated[str | None, Header()] = None,
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
    except ValueError as exc:
        #: The SAME fail-closed branch the anonymous read got, because a corrupt snapshot is one
        #: fault and answering it two ways is the asymmetry this release exists to remove. Measured
        #: before this: every malformed shape gave a generic 500 on `POST` and `PATCH` while the
        #: read had already been fixed to 503. No write happened and nothing leaked either way, so
        #: this is diagnosability rather than exposure - but a caller who cannot tell "your request
        #: was wrong" from "my stored state is unreadable" cannot act on either.
        _logger.exception("stored snapshot is unreadable on a write")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "store_unavailable", "message": bounded_reason(str(exc))},
        ) from None
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
    limiters: Limiters | None = None,
    clock: Callable[[], float] | None = None,
    training: TrainingPaths | None = None,
) -> FastAPI:
    """Build the application without listening.

    Every dependency is injectable, so the suite needs no network, no real clock, and no
    filesystem beyond a temporary directory. `content_root` and `progress_path` extend that to the
    training layer: a test points them at a temporary tree and never touches the shipped content
    or an operator's stored progress.
    """
    settings = config if config is not None else load_config()
    ticks = clock if clock is not None else time.monotonic
    runtime = _Runtime(
        settings=settings,
        store=store if store is not None else TrainingStore(settings.data_dir),
        probe=probe if probe is not None else probe_writable,
        probe_settings=probe_settings if probe_settings is not None else ProbeSettings(),
        coarse=(limiters.coarse if limiters else None)
        or RateLimiter(GLOBAL_LIMIT, GLOBAL_WINDOW_SECONDS),
        strict=(limiters.strict if limiters else None)
        or RateLimiter(WRITE_LIMIT, WRITE_WINDOW_SECONDS),
        drill=(limiters.drill if limiters else None)
        or RateLimiter(DRILL_LIMIT, DRILL_WINDOW_SECONDS),
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
    _register_training(app, runtime, paths=training or TrainingPaths())
    return app


def _register_training(app: FastAPI, runtime: _Runtime, *, paths: TrainingPaths) -> None:
    """Mount the training layer, and never let a content fault stop the container starting.

    The content tree is loaded HERE, at construction, and a failure is logged and carried rather
    than raised. That is the plan's safe-failure rule applied at the right altitude: a malformed
    procedure file must produce an author-facing error on the drill endpoints, not a container that
    will not boot. A container that refuses to start over a content typo cannot serve the health
    paths that would tell an operator why.
    """
    root = paths.content_root if paths.content_root is not None else resolve_content_root()
    package = ContentPackage(root)
    result = package.load()
    if not result.ok:
        log_event("content.load_failed", root=str(root), errors=len(result.errors))
    else:
        log_event(
            "content.loaded",
            root=str(root),
            content_hash=result.content_hash,
            counts=dict(result.counts),
            thresholds=package.thresholds.source,
            scored_scenarios_ready=package.scored_scenarios_ready,
        )
    registry = build_registry()
    # The registry check runs HERE, at load, because content pointing at a product nobody built
    # is a content-and-code disagreement and the cheapest place to catch one is the moment both
    # sides are present. This LOGS the disagreement; the binding check is
    # `tests/test_generators.py::test_every_product_the_content_references_has_a_renderer`
    # in the verification loop, and a request for an unbuilt product still 503s. Saying
    # "caught at load" of a log line overstated what this does.
    unbuilt = registry.unbuilt({d.stimulus.product_id for d in package.drills})
    if unbuilt:
        log_event(
            "content.unbuilt_products",
            #: `log_event` sanitises only string fields, so a LIST of content ids reached the line
            #: raw and at full length. Boot-only and not the collapse class, since nothing is cut,
            #: but "a log line is a wire too" is this codebase's own principle.
            products=[served_identifier(product) for product in unbuilt],
        )
    loop = DrillLoop(
        content=package,
        registry=registry,
        progress=ProgressStore(
            paths.progress_path
            if paths.progress_path is not None
            else runtime.settings.data_dir / "progress.json"
        ),
    )
    register_training_routes(
        app,
        content=package,
        loop=loop,
        guard_write=lambda request: _guard_drill_rate(runtime, request),
    )
