"""HTTP behaviour, mounted in-process through the factory with injected fakes."""

from __future__ import annotations

import ast
import asyncio
import gc
import json
import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.routing import WebSocketRoute

from conftest import TEST_ORIGIN, TEST_PLACEHOLDER, failing_probe, ok_probe
from enlightenment.app import (
    MAX_BODY_BYTES,
    MAX_REVISION_DIGITS,
    MAX_SERVED_SESSIONS_BYTES,
    WRITE_LIMIT,
    Limiters,
    ProbeSettings,
    TrainingPaths,
    _expected_rev,
    create_app,
)
from enlightenment.auth import AUTH_HEADER
from enlightenment.config import Config
from enlightenment.middleware import DRAIN_TIMEOUT_SECONDS, BodyLimitMiddleware
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import STORE_FILENAME, ProbeResult, TrainingStore
from enlightenment.training.drill import MAX_WITHHOLD_REASON

ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = ROOT / "content"


def _nested(levels: int) -> Any:
    """A value nested `levels` deep, for the serialiser-depth fixture."""
    node: Any = 1
    for _ in range(levels):
        node = {"d": node}
    return node


VALID_SESSION = {"id": "alpha-one", "title": "Alpha One", "scenario": "TBC, re-verify"}
AUTH = {AUTH_HEADER: TEST_PLACEHOLDER}

#: Every method the API exposes, so the cross-origin policy cannot silently omit one.
EXPOSED_METHODS = ("GET", "POST", "PATCH")


# --- root and liveness -------------------------------------------------------------


def test_root_returns_200_and_never_a_redirect(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/livez", "/ping", "/health"])
def test_liveness_paths_return_200_unauthenticated(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.text == "ok"


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_readiness_paths_return_200_unauthenticated_when_storage_is_writable(
    client: TestClient, path: str
) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["storage"]["writable"] is True


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_readiness_returns_503_with_the_resolved_dir_and_errno(
    config: Config, store: TrainingStore, path: str
) -> None:
    with TestClient(create_app(config=config, store=store, probe=failing_probe)) as client:
        response = client.get(path)
    assert response.status_code == 503
    storage = response.json()["storage"]
    assert storage["writable"] is False
    assert storage["errno"] == 13
    assert storage["errnoName"] == "EACCES"
    assert storage["resolvedDataDir"]


def test_a_hanging_probe_times_out_rather_than_hanging_the_request(
    config: Config, store: TrainingStore
) -> None:
    def stalled_probe(path: Path) -> ProbeResult:
        time.sleep(5)
        return ok_probe(path)

    app = create_app(
        config=config,
        store=store,
        probe=stalled_probe,
        probe_settings=ProbeSettings(timeout=0.05, cache_seconds=0.0),
    )
    with TestClient(app) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert "timed out" in response.json()["storage"]["detail"]


def test_a_probe_that_raises_reads_as_unready_never_as_a_pass(
    config: Config, store: TrainingStore
) -> None:
    """Fail closed: a control that cannot be verified is treated as failed."""

    def exploding_probe(path: Path) -> ProbeResult:
        raise RuntimeError("probe blew up")

    # cache_seconds=0.0 deliberately. Boot publishes its own verdict into the cache, so with
    # the default window this request was served from the boot-time result and the ASYNC
    # fail-closed handler never ran: inverting that handler to ok=True left the whole suite
    # green. The test was passing for the wrong reason.
    app = create_app(
        config=config,
        store=store,
        probe=exploding_probe,
        probe_settings=ProbeSettings(cache_seconds=0.0),
    )
    with TestClient(app) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["storage"]["writable"] is False


def test_the_app_still_starts_and_diagnoses_itself_when_the_snapshot_is_corrupt(
    config: Config, data_dir: Path
) -> None:
    """Unready, never unstartable. A worker that refuses to boot cannot serve the
    readiness diagnosis explaining why, which turns a mount problem into a crash loop.
    """
    (data_dir / "training.json").write_text("{truncated", encoding="utf-8")
    app = create_app(config=config, store=TrainingStore(data_dir))
    with TestClient(app) as client:
        assert client.get("/livez").status_code == 200
        assert client.get("/api/v1/diagnostics").status_code == 200


def test_the_readiness_probe_uses_the_validated_config_not_a_fresh_environment_read(
    config: Config, store: TrainingStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Probing a directory the store never writes to would prove the wrong thing."""
    seen: list[Path] = []

    def recording_probe(path: Path) -> ProbeResult:
        seen.append(path)
        return ok_probe(path)

    monkeypatch.setenv("DATA_DIR", "/somewhere/else/entirely")
    app = create_app(
        config=config,
        store=store,
        probe=recording_probe,
        probe_settings=ProbeSettings(cache_seconds=0.0),
    )
    with TestClient(app) as client:
        client.get("/readyz")
    assert seen, "the probe was never called"
    assert all(path == config.data_dir for path in seen)


def test_a_readiness_flood_causes_one_real_write_not_one_per_request(
    config: Config, store: TrainingStore
) -> None:
    """The readiness paths are unauthenticated and exempt from rate limiting by design, so
    an uncached real-write probe turns a flood into one create-write-fsync cycle per
    request against the volume, which then trips the probe's own timeout and restarts the
    pod. Probe cost must be bounded by time, not by request rate.
    """
    calls = {"count": 0}

    def counting_probe(path: Path) -> ProbeResult:
        calls["count"] += 1
        return ok_probe(path)

    app = create_app(
        config=config,
        store=store,
        probe=counting_probe,
        probe_settings=ProbeSettings(cache_seconds=60.0),
    )
    with TestClient(app) as client:
        for _ in range(50):
            assert client.get("/readyz").status_code == 200
    # One at boot, one for the first request, none after that inside the window.
    assert calls["count"] <= 2, f"probe ran {calls['count']} times for 50 requests"


def test_a_stale_probe_verdict_is_refreshed_once_the_window_passes(
    config: Config, store: TrainingStore
) -> None:
    ticks = {"now": 1000.0}
    calls = {"count": 0}

    def counting_probe(path: Path) -> ProbeResult:
        calls["count"] += 1
        return ok_probe(path)

    app = create_app(
        config=config,
        store=store,
        probe=counting_probe,
        probe_settings=ProbeSettings(cache_seconds=5.0),
        clock=lambda: ticks["now"],
    )
    with TestClient(app) as client:
        client.get("/readyz")
        before = calls["count"]
        client.get("/readyz")
        assert calls["count"] == before
        ticks["now"] += 6.0
        client.get("/readyz")
    assert calls["count"] == before + 1


# --- diagnostics --------------------------------------------------------------------


def test_diagnostics_never_exposes_a_token_value_or_an_exact_length(
    gated_client: TestClient,
) -> None:
    response = gated_client.get("/api/v1/diagnostics")
    body = response.json()
    assert body["config"]["teamToken"] == {"set": True, "lengthBucket": "adequate"}
    assert "length" not in body["config"]["teamToken"]
    assert TEST_PLACEHOLDER not in response.text
    assert str(len(TEST_PLACEHOLDER)) not in str(body["config"]["teamToken"])


def test_diagnostics_answers_every_plausible_deploy_question_at_once(
    gated_client: TestClient,
) -> None:
    body = gated_client.get("/api/v1/diagnostics").json()
    for field in (
        "buildId",
        "version",
        "schemaVersion",
        "pythonVersion",
        "port",
        "host",
        "uptimeSeconds",
        "identity",
        "storage",
        "config",
    ):
        assert field in body, f"diagnostics is missing {field}"
    assert set(body["identity"]) == {"uid", "gid"}
    assert body["config"]["anonymousWritesEnabled"] is False


def test_diagnostics_reports_the_anonymous_write_posture(client: TestClient) -> None:
    body = client.get("/api/v1/diagnostics").json()
    assert body["config"]["authRequired"] is False
    assert body["config"]["anonymousWritesEnabled"] is True
    assert body["config"]["teamToken"]["lengthBucket"] == "unset"


# --- the closed default: no token and no opt-in ---------------------------------------


#: Routes that change state and are deliberately NOT gated by the team token, each with the
#: reason it is here. An entry is a decision on the record, not a way to make a test pass.
#:
#: `POST /api/v1/drill/answer`: flight plan step 10, operator identity, does not exist yet, so
#: every drill write goes to the synthetic DEMONSTRATION_OPERATOR and no record of a named
#: individual is created before the DPIA is closed. Compensated by its OWN rate budget
#: (`DRILL_LIMIT`, not the gated writes' bucket) and an audit line whose key set is closed over
#: so neither answer text nor any score can reach it. Recorded as accepted risk 5 in
#: `docs/SECURITY.md`, and this entry goes when identity lands.
UNGATED_WRITES = frozenset({("POST", "/api/v1/drill/answer")})

#: Path parameters get a concrete value so the route resolves rather than 404ing, which would
#: pass this test for entirely the wrong reason.
PATH_PARAMETER_VALUES = {"session_id": "alpha-one"}


#: A WebSocket cannot be probed with an HTTP verb, so each one is reasoned about by hand and
#: named here with how its writes are gated. Empty: the application mounts no WebSocket route.
REVIEWED_WEBSOCKETS: frozenset[str] = frozenset()

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _walk_routes(routes: Any, prefix: str, found: list[tuple[str, str]]) -> None:
    """Walk every routing idiom, and FAIL on one this closure has not been taught.

    The first version of this closure read `route.methods` and silently skipped anything that
    did not have it. Both binding gates defeated it the same way, independently: on the pinned
    FastAPI, `include_router` appends an `_IncludedRouter` whose `path` and `methods` are both
    `None`, and `app.mount` appends a `Mount` with no `methods` either. An unauthenticated
    `POST` behind either one answered 200 in the closed default while the suite stayed green.

    That is the SAME enumeration-versus-closure failure this test exists to close, one level
    down, and it failed OPEN, which CLAUDE.md forbids outright: a control that cannot be
    verified is treated as failed. So the unknown case now raises rather than continuing. The
    day somebody reaches for a routing idiom this cannot see, the suite goes red and they have
    to teach it before the route can ship. That is the intended cost.
    """
    for route in routes:
        methods = getattr(route, "methods", None)
        if methods:
            path = getattr(route, "path", None)
            assert path is not None, f"{type(route).__name__} carries methods but no path"
            for method in methods:
                if method.upper() in IDEMPOTENT_METHODS:
                    continue
                found.append((method.upper(), prefix + path))
            continue

        if methods is not None:  # an EMPTY method set, which is not the same as none at all
            raise AssertionError(
                f"{type(route).__name__} at {getattr(route, 'path', '?')!r} declares an empty"
                " method set. Starlette treats a falsy `methods` as matching EVERY verb, so this"
                " route serves POST while looking like it serves nothing. The first version of"
                " this walk tested `is not None`, entered the loop, iterated zero methods and"
                " continued, which let an ungated 200 POST through with the suite green."
            )

        included = getattr(route, "original_router", None)
        if included is not None:  # FastAPI's _IncludedRouter, from include_router()
            context = getattr(route, "include_context", None)
            _walk_routes(included.routes, prefix + getattr(context, "prefix", ""), found)
            continue

        if hasattr(route, "routes"):  # a Mount, or a mounted sub-application
            mounted = getattr(route, "app", None)
            assert mounted is None or hasattr(mounted, "routes"), (
                f"{prefix + getattr(route, 'path', '?')} mounts an opaque ASGI application whose"
                " routes cannot be enumerated, so its writes cannot be checked. Gate it at the"
                " mount, or make it introspectable."
            )
            _walk_routes(route.routes, prefix + getattr(route, "path", ""), found)
            continue

        if isinstance(route, WebSocketRoute):
            found.append(("WEBSOCKET", prefix + getattr(route, "path", "")))
            continue

        raise AssertionError(
            f"{type(route).__name__} at {getattr(route, 'path', '?')!r} carries no methods and"
            " this closure does not know how to walk it. Teach it before the route ships: a"
            " routing idiom the gating test cannot see is one that can carry an unauthenticated"
            " write straight past it."
        )


#: Every READ route the application serves, and what each is allowed to disclose. A read route is
#: the shape that leaks an answer key, and the state-change closure below cannot see one: it
#: `continue`s past every idempotent method by design. So this is the second closure, and the
#: column that matters is the last one: a route that can reach `Drill.answer` must say so.
#:
#: path -> (audience, may it reach an answer key)
REVIEWED_READ_ROUTES: dict[str, tuple[str, bool]] = {
    "/": ("unauthenticated", False),
    "/healthz": ("unauthenticated", False),
    "/readyz": ("unauthenticated", False),
    "/livez": ("unauthenticated", False),
    "/ping": ("unauthenticated", False),
    "/health": ("unauthenticated", False),
    "/version": ("unauthenticated", False),
    "/api/v1/diagnostics": ("unauthenticated", False),
    "/ui": ("unauthenticated", False),
    "/ui/": ("unauthenticated", False),
    "/ui/{filename}": ("unauthenticated", False),
    "/api/v1/content/manifest": ("unauthenticated", False),
    "/api/v1/content/procedure/{procedure_id}": ("unauthenticated", False),
    "/api/v1/content/product/{product_id}": ("unauthenticated", False),
    "/api/v1/drill/next": ("unauthenticated", False),
    "/api/v1/me": ("unauthenticated", False),
    "/api/v1/sessions/{session_id}": ("team token", False),
    "/api/v1/sessions": ("team token", False),
    "/openapi.json": ("unauthenticated", False),
    "/docs": ("unauthenticated", False),
    "/docs/oauth2-redirect": ("unauthenticated", False),
    "/redoc": ("unauthenticated", False),
}


def _read_routes(app: Any) -> list[str]:
    """Every path the application serves with an idempotent method."""
    paths: set[str] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        if {m.upper() for m in methods} & IDEMPOTENT_METHODS:
            paths.add(str(getattr(route, "path", "")))
    return sorted(paths)


def test_every_read_route_is_reviewed_and_none_may_reach_an_answer_key() -> None:
    """The closure the answer-key rule actually needs.

    The state-change closure skips every GET, so a future `GET /api/v1/drill/{id}` returning a
    whole `Drill` - answer key included - would have shipped with the suite green. Today's read
    routes are individually asserted elsewhere; this is the gate that makes the NEXT one
    deliberate. Adding a read route means adding a row here and stating its audience.
    """
    application = create_app()
    served = _read_routes(application)
    unreviewed = [path for path in served if path not in REVIEWED_READ_ROUTES]
    assert not unreviewed, (
        "these read routes are not in REVIEWED_READ_ROUTES, so nobody has said what they"
        f" disclose: {unreviewed}. Add a row naming the audience, and state whether the route can"
        " reach Drill.answer."
    )
    leaky = [path for path, (_, answers) in REVIEWED_READ_ROUTES.items() if answers]
    assert not leaky, (
        f"these read routes are recorded as able to reach an answer key: {leaky}. The production"
        " format forbids it: the key crosses the wire only after the operator has committed."
    )


def _state_changing_routes(app: Any) -> list[tuple[str, str]]:
    """Every non-idempotent route the application actually serves, however it was registered.

    DERIVED, not enumerated. The gating tests below used to list two paths by hand, and a third
    state-changing route - `POST /api/v1/drill/answer` - shipped past them without turning
    anything red, because a list cannot notice what is not on it.
    """
    # `APIRouter.frontend()` puts routes in `_low_priority_routes`, which is NOT in `app.routes`,
    # so the walk below cannot see them at all. Harmless today - `_FrontendRoute` hardcodes
    # GET and HEAD - and that is a promise of the pinned FastAPI, not of this project. Assert the
    # bucket is empty so a version that admits a non-idempotent low-priority route fails loudly
    # rather than routing around the closure.
    low_priority = getattr(getattr(app, "router", None), "_low_priority_routes", [])
    assert not low_priority, (
        f"{len(low_priority)} low-priority route(s) sit outside app.routes and outside this"
        " closure. Teach the walk to reach them before any of them can change state."
    )
    found: list[tuple[str, str]] = []
    _walk_routes(app.routes, "", found)
    assert found, "no state-changing route was found, so this test proves nothing"
    return sorted(set(found))


def _concrete(path: str) -> str:
    for name, value in PATH_PARAMETER_VALUES.items():
        path = path.replace("{" + name + "}", value)
    assert "{" not in path, f"no test value for the path parameter in {path}"
    return path


def test_every_state_changing_route_is_gated_or_explicitly_excepted(
    closed_client: TestClient,
) -> None:
    """The closure itself: a new write route is refused, or it is named and reasoned about.

    A fourth unauthenticated write endpoint used to be able to ship with the suite green. Now it
    either answers 401 in the closed default, or its absence from UNGATED_WRITES fails here and
    somebody has to write down why it is open.
    """
    for method, path in _state_changing_routes(closed_client.app):
        if method == "WEBSOCKET":
            assert path in REVIEWED_WEBSOCKETS, (
                f"{path} is a WebSocket route, which changes state and cannot be probed with an"
                " HTTP verb. Gate it in the handler and name it in REVIEWED_WEBSOCKETS with the"
                " reason, or this test cannot tell you anything about it."
            )
            continue
        response = getattr(closed_client, method.lower())(_concrete(path), json=VALID_SESSION)
        if (method, path) in UNGATED_WRITES:
            assert response.status_code != 401, (
                f"{method} {path} is listed as ungated but is refused; remove the exception"
            )
            continue
        assert response.status_code == 401, (
            f"{method} {path} changes state, is not in UNGATED_WRITES, and answered"
            f" {response.status_code} with no token configured"
        )


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/api/v1/sessions"), ("patch", "/api/v1/sessions/alpha-one")],
)
def test_writes_are_refused_by_default_with_no_token_configured(
    closed_client: TestClient, method: str, path: str
) -> None:
    """The container default with an empty operator environment tab. Treating an absent
    token as "open" put an unauthenticated write endpoint on a public ingress by omission.
    """
    response = getattr(closed_client, method)(path, json=VALID_SESSION)
    assert response.status_code == 401


def test_reads_and_probes_stay_open_in_the_closed_default(closed_client: TestClient) -> None:
    """Recoverability: the operator can still diagnose an app whose writes are shut."""
    for path in ("/", "/livez", "/healthz", "/api/v1/sessions", "/api/v1/diagnostics"):
        assert closed_client.get(path).status_code == 200, path


# --- authentication -----------------------------------------------------------------


def test_a_write_without_a_token_is_refused_when_a_token_is_configured(
    gated_client: TestClient,
) -> None:
    assert gated_client.post("/api/v1/sessions", json=VALID_SESSION).status_code == 401


def test_a_write_with_a_wrong_token_of_the_same_length_is_refused(
    gated_client: TestClient,
) -> None:
    wrong = TEST_PLACEHOLDER[:-1] + "X"
    response = gated_client.post(
        "/api/v1/sessions", json=VALID_SESSION, headers={AUTH_HEADER: wrong}
    )
    assert response.status_code == 401


def test_a_write_with_the_right_token_succeeds(gated_client: TestClient) -> None:
    response = gated_client.post("/api/v1/sessions", json=VALID_SESSION, headers=AUTH)
    assert response.status_code == 201
    assert response.json()["session"]["id"] == "alpha-one"


def test_health_paths_stay_public_when_a_token_is_configured(gated_client: TestClient) -> None:
    for path in ("/", "/livez", "/ping", "/health", "/healthz", "/readyz"):
        assert gated_client.get(path).status_code == 200, path


def _audit_lines(records: list[logging.LogRecord]) -> list[dict[str, Any]]:
    """The audit records emitted, parsed. Only `enlightenment.audit`, never the event log."""
    return [
        json.loads(record.getMessage())
        for record in records
        if record.name == "enlightenment.audit"
    ]


def test_local_anonymous_mode_allows_the_write_and_records_the_actor_as_anonymous(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """**This test asserted only `201` for four releases, while its name promised the actor.**

    Under a shared team token the audit line IS the accountability control: accepted risk 1
    records that the token cannot distinguish who wrote, so the actor field and the fact a line
    is emitted at all are what the register is standing on. Nothing asserted either. Measured by
    the security gate: replacing the `audit(...)` call in the write route with a no-op left the
    whole suite green, and no test in `tests/` used `caplog`.
    """
    with caplog.at_level(logging.INFO, logger="enlightenment.audit"):
        assert client.post("/api/v1/sessions", json=VALID_SESSION).status_code == 201

    lines = _audit_lines(caplog.records)
    assert len(lines) == 1, f"expected exactly one audit line, got {lines}"
    assert lines[0]["event"] == "session.upsert"
    assert lines[0]["actor"] == "anonymous"
    assert lines[0]["sessionId"] == VALID_SESSION["id"]


def test_a_gated_write_emits_one_audit_line_naming_the_token_actor(
    gated_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The other half: a token-authenticated write records the actor the token resolves to.

    Both routes, because both carried an unasserted `audit(...)` call. `session.patch` records
    the FIELDS touched rather than the values, which is the whole point of an audit line on a
    partial update: what changed, by whom, at which revision, without copying the payload into
    the log.
    """
    with caplog.at_level(logging.INFO, logger="enlightenment.audit"):
        created = gated_client.post("/api/v1/sessions", json=VALID_SESSION, headers=AUTH)
        assert created.status_code == 201
        patched = gated_client.patch(
            f"/api/v1/sessions/{VALID_SESSION['id']}", json={"title": "Renamed"}, headers=AUTH
        )
        assert patched.status_code == 200

    lines = _audit_lines(caplog.records)
    assert [line["event"] for line in lines] == ["session.upsert", "session.patch"], lines
    assert {line["actor"] for line in lines} == {"team"}, lines
    assert lines[1]["fields"] == ["title"], lines[1]
    assert lines[1]["rev"] > lines[0]["rev"], lines
    # The audit line carries no credential, which is the rule the whole log posture rests on.
    for line in lines:
        assert TEST_PLACEHOLDER not in json.dumps(line)


# --- boundary validation ------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"id": "alpha", "title": "A"},
        {"id": "alpha", "title": "A", "scenario": "s", "unexpected": "key"},
        {"id": "alpha", "title": "A", "scenario": "s", "__proto__": {"x": 1}},
        {"id": "Alpha-Upper", "title": "A", "scenario": "s"},
        {"id": "double--hyphen", "title": "A", "scenario": "s"},
        {"id": "", "title": "A", "scenario": "s"},
        {"id": "alpha", "title": "", "scenario": "s"},
        {"id": "alpha", "title": "A", "scenario": "s", "notes": "n" * 2001},
        {"id": "a" * 65, "title": "A", "scenario": "s"},
        # `title` and `scenario` are capped in `models.py` too, and both caps were deletable
        # with the whole suite green while `notes` and `id` above were covered. Measured by the
        # security gate: one model, four capped fields, two asserted.
        {"id": "alpha", "title": "A" * 201, "scenario": "s"},
        {"id": "alpha", "title": "A", "scenario": "s" * 121},
        {"id": {"nested": "object"}, "title": "A", "scenario": "s"},
    ],
)
def test_a_malformed_body_is_rejected_generically(client: TestClient, body: dict[str, Any]) -> None:
    response = client.post("/api/v1/sessions", json=body)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid request"}


def test_an_oversize_body_with_a_declared_length_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"error": "request body too large"}


def test_an_oversize_chunked_body_is_refused_on_bytes_read(client: TestClient) -> None:
    """A chunked request declares no content-length, so a header-only cap is skipped and
    the whole body is buffered before any handler or dependency runs. Measured before the
    fix: 256 MB streamed took the worker from 52 MB to 821 MB resident and returned 422.
    """

    def chunks() -> Iterator[bytes]:
        for _ in range(40):
            yield b"x" * 8192

    response = client.post(
        "/api/v1/sessions", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json() == {"error": "request body too large"}


def test_an_oversize_chunked_body_is_refused_before_authentication(
    closed_client: TestClient,
) -> None:
    """The cap must run ahead of the auth dependency, or an unauthenticated caller can
    still make the worker buffer an unbounded body.
    """

    def chunks() -> Iterator[bytes]:
        for _ in range(40):
            yield b"x" * 8192

    response = closed_client.post(
        "/api/v1/sessions", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


def test_a_body_within_the_cap_is_accepted_when_sent_chunked(client: TestClient) -> None:
    """The boundary in the other direction: the cap must not reject a legitimate body."""
    import json as json_module

    payload = json_module.dumps({**VALID_SESSION, "notes": "n" * 1000}).encode("utf-8")

    def chunks() -> Iterator[bytes]:
        yield payload

    response = client.post(
        "/api/v1/sessions", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 201


def test_an_unhandled_error_returns_a_generic_message_and_no_stack_trace(
    config: Config, data_dir: Path
) -> None:
    class ExplodingStore(TrainingStore):
        def load(self) -> dict[str, Any]:
            raise RuntimeError("internal detail that must not reach the client")

    app = create_app(config=config, store=ExplodingStore(data_dir), probe=ok_probe)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/sessions")
    assert response.status_code == 500
    assert response.json() == {"error": "internal error"}
    assert "internal detail" not in response.text


@pytest.mark.parametrize(
    ("origin", "expect_cors"),
    [(TEST_ORIGIN, True), ("https://not-the-origin.invalid", False), (None, False)],
    ids=["the configured origin", "a foreign origin", "no origin header"],
)
def test_a_500_carries_its_own_headers_because_no_user_middleware_reaches_it(
    token_config: Config, data_dir: Path, origin: str | None, expect_cors: bool
) -> None:
    """THE response class `NoSniffMiddleware` cannot touch, so the handler sets both headers.

    Starlette installs `ServerErrorMiddleware` above every user middleware, and that is what
    renders the unhandled-exception response. So registering `NoSniffMiddleware` outermost among
    user middleware, an order asserted by
    `test_the_middleware_order_puts_the_limiter_outside_the_body_cap` and by nothing else,
    still misses a 500: measured before the fix, an unhandled exception answered
    with neither `x-content-type-options` nor `access-control-allow-origin`, while the code and
    three documents claimed the header was on "every response". "Outermost" was true and bought
    less than it sounded.

    The cross-origin half is the more consequential one. A browser that cannot read a 500 reports
    an opaque network error, which is exactly the case an operator most needs to see - and it is
    still echoed only for the configured origin, never `*`, which is what the three cases here
    pin.
    """

    class ExplodingStore(TrainingStore):
        def load(self) -> dict[str, Any]:
            raise RuntimeError("internal detail that must not reach the client")

    app = create_app(config=token_config, store=ExplodingStore(data_dir), probe=ok_probe)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/sessions", headers={"Origin": origin} if origin else {})
    assert response.status_code == 500
    assert response.headers.get("x-content-type-options") == "nosniff", (
        "a 500 is the response class most worth a content-type guarantee, and the only one no"
        " user middleware can reach"
    )
    allowed = response.headers.get("access-control-allow-origin")
    if expect_cors:
        assert allowed == TEST_ORIGIN
        assert response.headers.get("vary") == "Origin"
    else:
        assert allowed is None, f"a 500 echoed {allowed!r} for origin {origin!r}"


# --- persistence through HTTP -------------------------------------------------------


def test_a_partial_patch_keeps_every_field_the_caller_did_not_send(client: TestClient) -> None:
    client.post("/api/v1/sessions", json={**VALID_SESSION, "notes": "keep me"})
    patched = client.patch("/api/v1/sessions/alpha-one", json={"title": "Renamed"})
    assert patched.status_code == 200
    listed = client.get("/api/v1/sessions").json()
    assert listed["count"] == 1
    assert listed["sessions"][0]["notes"] == "keep me"
    assert listed["sessions"][0]["scenario"] == "TBC, re-verify"
    assert listed["sessions"][0]["title"] == "Renamed"


def test_a_post_still_requires_every_mandatory_field(client: TestClient) -> None:
    client.post("/api/v1/sessions", json=VALID_SESSION)
    response = client.post("/api/v1/sessions", json={"id": "alpha-one", "title": "Renamed"})
    assert response.status_code == 422


def test_a_patch_to_an_unknown_session_is_a_404_not_a_silent_create(client: TestClient) -> None:
    assert client.patch("/api/v1/sessions/never-created", json={"title": "x"}).status_code == 404


def test_a_patch_with_an_unknown_key_is_rejected(client: TestClient) -> None:
    client.post("/api/v1/sessions", json=VALID_SESSION)
    assert client.patch("/api/v1/sessions/alpha-one", json={"unexpected": "k"}).status_code == 422


# --- concurrency validators -----------------------------------------------------------


def test_a_listing_carries_an_etag_and_answers_304_when_unchanged(client: TestClient) -> None:
    first = client.get("/api/v1/sessions")
    etag = first.headers["etag"]
    assert etag
    again = client.get("/api/v1/sessions", headers={"if-none-match": etag})
    assert again.status_code == 304


def test_the_etag_changes_after_a_write(client: TestClient) -> None:
    before = client.get("/api/v1/sessions").headers["etag"]
    client.post("/api/v1/sessions", json=VALID_SESSION)
    after = client.get("/api/v1/sessions").headers["etag"]
    assert before != after


def test_a_stale_if_match_is_a_409_rather_than_a_silent_overwrite(client: TestClient) -> None:
    client.post("/api/v1/sessions", json=VALID_SESSION)
    response = client.post(
        "/api/v1/sessions",
        json={**VALID_SESSION, "title": "Clobber"},
        headers={"if-match": 'W/"0"'},
    )
    assert response.status_code == 409
    listed = client.get("/api/v1/sessions").json()
    assert listed["sessions"][0]["title"] == "Alpha One"


def test_a_matching_if_match_is_accepted(client: TestClient) -> None:
    created = client.post("/api/v1/sessions", json=VALID_SESSION)
    rev = created.json()["rev"]
    response = client.post(
        "/api/v1/sessions",
        json={**VALID_SESSION, "title": "Renamed"},
        headers={"if-match": f'W/"{rev}"'},
    )
    assert response.status_code == 201


def test_an_unparsable_if_match_is_ignored_rather_than_failing_the_request(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/sessions", json=VALID_SESSION, headers={"if-match": "not-a-revision"}
    )
    assert response.status_code == 201


# --- rate limiting ------------------------------------------------------------------


def test_the_strict_tier_returns_429_after_its_limit_on_a_post(
    config: Config, store: TrainingStore
) -> None:
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        limiters=Limiters(strict=RateLimiter(2, 60.0)),
    )
    with TestClient(app) as client:
        codes = [client.post("/api/v1/sessions", json=VALID_SESSION).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


def test_the_strict_tier_returns_429_after_its_limit_on_a_patch(
    config: Config, store: TrainingStore
) -> None:
    """Without this the limiter on the PATCH handler could be deleted and the suite would
    stay green, which means it asserts nothing. Each PATCH is a full snapshot
    read-modify-write plus a backup copy, so an unlimited one is real volume churn.
    """
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        limiters=Limiters(strict=RateLimiter(3, 60.0)),
    )
    with TestClient(app) as client:
        assert client.post("/api/v1/sessions", json=VALID_SESSION).status_code == 201
        first = client.patch("/api/v1/sessions/alpha-one", json={"title": "one"})
        second = client.patch("/api/v1/sessions/alpha-one", json={"title": "two"})
        third = client.patch("/api/v1/sessions/alpha-one", json={"title": "three"})
    assert [first.status_code, second.status_code] == [200, 200]
    assert third.status_code == 429


def test_the_coarse_tier_returns_429_after_its_limit(config: Config, store: TrainingStore) -> None:
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        limiters=Limiters(coarse=RateLimiter(2, 60.0)),
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/sessions").status_code == 200
        assert client.get("/api/v1/sessions").status_code == 200
        assert client.get("/api/v1/sessions").status_code == 429


def test_probe_paths_are_never_rate_limited(config: Config, store: TrainingStore) -> None:
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        limiters=Limiters(coarse=RateLimiter(1, 3600.0)),
    )
    with TestClient(app) as client:
        for path in ("/", "/livez", "/ping", "/health", "/healthz", "/readyz"):
            for _ in range(3):
                assert client.get(path).status_code == 200, path


# --- cross-origin -------------------------------------------------------------------


@pytest.mark.parametrize("method", EXPOSED_METHODS)
def test_every_exposed_method_survives_a_preflight_from_the_allowed_origin(
    gated_client: TestClient, method: str
) -> None:
    """PATCH was omitted from allow_methods while being a shipped route, so the partial
    update was unreachable from a browser. Parametrised over the real method list so the
    policy and the route table cannot drift apart again.
    """
    response = gated_client.options(
        "/api/v1/sessions",
        headers={
            "origin": TEST_ORIGIN,
            "access-control-request-method": method,
            "access-control-request-headers": AUTH_HEADER,
        },
    )
    assert response.status_code == 200, response.text
    assert method in response.headers["access-control-allow-methods"]


def test_the_allowed_origin_is_echoed_and_another_origin_is_not(gated_client: TestClient) -> None:
    allowed = gated_client.get("/", headers={"origin": TEST_ORIGIN})
    assert allowed.headers["access-control-allow-origin"] == TEST_ORIGIN
    other = gated_client.get("/", headers={"origin": "https://attacker.example"})
    assert "access-control-allow-origin" not in other.headers


def test_no_cors_header_is_emitted_when_no_origin_is_configured(client: TestClient) -> None:
    response = client.get("/", headers={"origin": "https://anything.example"})
    assert "access-control-allow-origin" not in response.headers


def test_a_rate_limited_response_still_carries_the_cross_origin_header(
    token_config: Config, store: TrainingStore
) -> None:
    """Without the header a browser client sees an opaque network error rather than a 429."""
    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        limiters=Limiters(coarse=RateLimiter(1, 3600.0)),
    )
    with TestClient(app) as client:
        client.get("/api/v1/sessions", headers={"origin": TEST_ORIGIN})
        limited = client.get("/api/v1/sessions", headers={"origin": TEST_ORIGIN})
    assert limited.status_code == 429
    assert limited.headers["access-control-allow-origin"] == TEST_ORIGIN


def test_an_oversize_response_still_carries_the_cross_origin_header(
    token_config: Config, store: TrainingStore
) -> None:
    app = create_app(config=token_config, store=store, probe=ok_probe)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sessions",
            content=b"x" * (MAX_BODY_BYTES + 1),
            headers={"content-type": "application/json", "origin": TEST_ORIGIN},
        )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == TEST_ORIGIN


# --- controls the first two gate rounds found unasserted -------------------------------


class LoopWatchingStore(TrainingStore):
    """A store that records whether it was executed ON the event loop thread.

    A coroutine running inside the loop has a running loop; a function handed to a worker
    thread does not. So `asyncio.get_running_loop()` raising is the direct, precise proof
    that the call was offloaded, with no reliance on thread names.
    """

    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir)
        self.on_loop: list[str] = []

    def _record(self, name: str) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self.on_loop.append(name)

    def load(self) -> dict[str, Any]:
        self._record("load")
        return super().load()

    def sessions(self) -> list[dict[str, Any]]:
        self._record("sessions")
        return super().sessions()

    def upsert_session(self, record: dict[str, Any], **kwargs: Any) -> Any:
        self._record("upsert_session")
        return super().upsert_session(record, **kwargs)


def test_no_store_call_runs_on_the_event_loop(config: Config, data_dir: Path) -> None:
    """The store does blocking file input and output including an fsync. Running it inline
    in an async handler blocks the loop, which stalls the liveness and readiness paths on
    that worker whenever the volume is slow: measured at 4 ms offloaded against 792 ms
    inline. With one worker, a stalled loop is a silent liveness kill.
    """
    watcher = LoopWatchingStore(data_dir)
    app = create_app(config=config, store=watcher, probe=ok_probe)
    with TestClient(app) as client:
        assert client.get("/api/v1/sessions").status_code == 200
        assert client.post("/api/v1/sessions", json=VALID_SESSION).status_code == 201
        assert client.patch("/api/v1/sessions/alpha-one", json={"title": "x"}).status_code == 200
    assert watcher.on_loop == [], f"store calls ran on the event loop: {watcher.on_loop}"


@pytest.mark.parametrize(
    ("configured_origin", "expected"),
    [
        (
            True,
            ["NoSniffMiddleware", "CORSMiddleware", "BaseHTTPMiddleware", "BodyLimitMiddleware"],
        ),
        (False, ["NoSniffMiddleware", "BaseHTTPMiddleware", "BodyLimitMiddleware"]),
    ],
    ids=["hosted-with-origin", "local-no-origin"],
)
def test_the_middleware_order_puts_the_limiter_outside_the_body_cap(
    token_config: Config,
    config: Config,
    store: TrainingStore,
    configured_origin: bool,
    expected: list[str],
) -> None:
    """Order is load-bearing three times now, and this test is the ONLY authority on it.

    Five sites in source, tests and the security policy assert which layer is outermost. Every one
    of them now names this test, because the previous arrangement had `_install_cors` claiming to be
    outermost - true when written, false from the moment `NoSniffMiddleware` was registered after
    it - while this assertion sat green on the correct order the whole time. A prose claim about
    ordering with no anchor is how that survived a release.

    The limiter must be OUTSIDE the cap, or an oversize request is read in full while spending no
    limiter budget. The cross-origin layer must be outside that, or a 413 or 429 reaches a browser
    with no header and reads as an opaque network error. Both were wrong in the first version.

    And `NoSniffMiddleware` is outermost, for the same reason as the second: a response a
    middleware answers ITSELF - a 413 from the cap, a 429 from the limiter - never reaches a layer
    registered inside it, so a header installed beside the routes would miss exactly the responses
    an operator is most likely to open in a browser.

    Both postures, because only the hosted one was exercised and the local one is the default a
    developer runs. `CORSMiddleware` is installed only when an origin is configured, so the local
    stack is three layers; what must hold in BOTH is that nosniff is outermost and the cap is
    innermost, which is the claim the five citing sites actually depend on.
    """
    app = create_app(
        config=token_config if configured_origin else config, store=store, probe=ok_probe
    )
    order = [layer.cls.__name__ for layer in app.user_middleware]
    assert order == expected, order
    assert order[0] == "NoSniffMiddleware", order
    assert order[-1] == "BodyLimitMiddleware", order
    assert ("CORSMiddleware" in order) is configured_origin, order


def test_an_oversize_request_still_spends_rate_limit_budget(
    config: Config, store: TrainingStore
) -> None:
    """With the cap outside the limiter, oversize requests were free: twelve of them left
    the limiter's key table empty, so an unauthenticated caller could send unlimited
    64 KB-body requests without ever being refused.
    """
    limiter = RateLimiter(2, 60.0)
    app = create_app(config=config, store=store, probe=ok_probe, limiters=Limiters(coarse=limiter))
    with TestClient(app) as client:
        oversize = b"x" * (MAX_BODY_BYTES + 1)
        headers = {"content-type": "application/json"}
        first = client.post("/api/v1/sessions", content=oversize, headers=headers)
        second = client.post("/api/v1/sessions", content=oversize, headers=headers)
        third = client.post("/api/v1/sessions", content=oversize, headers=headers)
    assert [first.status_code, second.status_code] == [413, 413]
    assert third.status_code == 429, "an oversize request spent no limiter budget"
    assert limiter.tracked_keys() > 0


def test_a_liveness_request_declaring_a_body_that_never_arrives_still_answers(
    config: Config, store: TrainingStore
) -> None:
    """`GET /livez` with a declared length and no bytes must not park. The liveness and
    readiness paths are the ones the deploy contract depends on.
    """
    app = create_app(config=config, store=store, probe=ok_probe)
    with TestClient(app) as client:
        response = client.request("GET", "/livez", headers={"content-length": "10"})
    assert response.status_code == 200


def test_concurrent_readiness_requests_run_one_probe_between_them(
    config: Config, store: TrainingStore
) -> None:
    """Single-flight. A cache with an await between its read and its write bounds nothing
    under concurrency: 17 400 concurrent requests were measured producing 228 real probes,
    and the queued probes then exceeded their own timeout so healthy storage reported 503.
    """
    calls = {"count": 0}

    def slow_probe(path: Path) -> ProbeResult:
        calls["count"] += 1
        time.sleep(0.15)
        return ok_probe(path)

    async def drive() -> list[int]:
        app = create_app(
            config=config,
            store=store,
            probe=slow_probe,
            probe_settings=ProbeSettings(timeout=5.0, cache_seconds=0.0),
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://probe") as client:
            calls["count"] = 0
            responses = await asyncio.gather(*(client.get("/readyz") for _ in range(40)))
            return [response.status_code for response in responses]

    codes = asyncio.run(drive())
    assert set(codes) == {200}, f"healthy storage reported {sorted(set(codes))}"
    assert calls["count"] <= 2, f"40 concurrent requests ran {calls['count']} probes"


def test_concurrent_callers_all_receive_the_same_verdict(
    config: Config, store: TrainingStore
) -> None:
    """Concurrent callers must agree, and one probe must serve them all.

    Note what this does NOT claim: single-flight alone does not make a publication race
    impossible, because a cancelled starter clears the in-flight slot while its shielded task
    keeps running. What orders publication is that a cancelled starter never publishes and the
    pool has one worker. See `_probe_storage` for the full reasoning.
    """
    verdicts: list[ProbeResult] = []

    def slow_failing_probe(path: Path) -> ProbeResult:
        time.sleep(0.1)
        result = failing_probe(path)
        verdicts.append(result)
        return result

    async def drive() -> list[int]:
        app = create_app(
            config=config,
            store=store,
            probe=slow_failing_probe,
            probe_settings=ProbeSettings(timeout=5.0, cache_seconds=0.0),
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://probe") as client:
            verdicts.clear()
            responses = await asyncio.gather(*(client.get("/readyz") for _ in range(20)))
            return [response.status_code for response in responses]

    codes = asyncio.run(drive())
    assert set(codes) == {503}, f"callers disagreed: {sorted(set(codes))}"
    assert len(verdicts) <= 2, f"20 concurrent callers produced {len(verdicts)} verdicts"


def test_the_probe_runs_on_its_own_dedicated_thread_pool(
    config: Config, store: TrainingStore
) -> None:
    """Sharing the default executor with the store was measured taking a legitimate listing
    from 1.4 ms to 109 ms at the median, so the dedicated pool is a control, not a detail.
    Replacing it with None used to leave the whole suite green.
    """
    threads: list[str] = []

    def thread_recording_probe(path: Path) -> ProbeResult:
        threads.append(threading.current_thread().name)
        return ok_probe(path)

    app = create_app(
        config=config,
        store=store,
        probe=thread_recording_probe,
        probe_settings=ProbeSettings(cache_seconds=0.0),
    )
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 200
    served = [name for name in threads if name.startswith("probe")]
    assert served, f"no probe ran on the dedicated pool; threads seen: {threads}"


def test_the_shipped_drain_budget_is_finite_and_wired_into_the_app(
    config: Config, store: TrainingStore
) -> None:
    """Both drain tests inject `drain_timeout`, so the CONSTANT the container runs with was
    asserted by nothing: setting it to 86400 left every test green while the deployed drain
    was effectively unbounded again. This walks the application's own middleware stack.
    """
    assert 0 < DRAIN_TIMEOUT_SECONDS <= 30.0, "the shipped drain budget is not a bound"
    app = create_app(config=config, store=store, probe=ok_probe)
    caps = [layer for layer in app.user_middleware if layer.cls is BodyLimitMiddleware]
    assert len(caps) == 1, "the body cap is not wired exactly once"
    wired = caps[0].kwargs.get("drain_timeout", DRAIN_TIMEOUT_SECONDS)
    assert 0 < wired <= 30.0, f"the wired drain budget is not a bound: {wired}"


def test_a_probe_path_declaring_a_body_answers_even_for_a_body_method(
    config: Config, store: TrainingStore
) -> None:
    """POST /livez with a declared length and no bytes must not park the connection."""
    app = create_app(config=config, store=store, probe=ok_probe)
    with TestClient(app) as client:
        response = client.request("POST", "/livez", headers={"content-length": "65000"})
    # The route accepts no POST, so the honest answer is 405. What matters is that it ANSWERS.
    assert response.status_code in {405, 200}


def test_the_apps_body_cap_exempts_the_probe_paths(config: Config, store: TrainingStore) -> None:
    """Drives the REAL app at the ASGI layer with a receive that refuses to be called.

    The previous version of this test built its own middleware with explicit exempt paths,
    so removing them from the application's own wiring left the suite green. A test of a
    control must exercise the control as the application assembles it.
    """
    app = create_app(config=config, store=store, probe=ok_probe)
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def receive() -> dict[str, Any]:
        raise AssertionError("the application drained the body of a probe path")

    async def drive() -> None:
        for path in ("/livez", "/healthz", "/readyz", "/ping", "/health", "/"):
            sent.clear()
            await app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "path": path,
                    "raw_path": path.encode(),
                    "query_string": b"",
                    "root_path": "",
                    "scheme": "http",
                    "headers": [(b"host", b"probe"), (b"content-length", b"65000")],
                    "client": ("127.0.0.1", 5000),
                    "server": ("127.0.0.1", 8080),
                },
                receive,
                send,
            )
            starts = [message for message in sent if message["type"] == "http.response.start"]
            assert starts, f"{path} never answered"

    asyncio.run(drive())


def probe_threads() -> set[int | None]:
    """Identities of the live threads belonging to a dedicated probe pool.

    Keyed by IDENTITY, not by name: every pool names its single worker `probe_0`, so a set of
    names silently deduplicates across apps and made this assertion vacuous.
    """
    return {t.ident for t in threading.enumerate() if t.name.startswith("probe")}


def test_building_an_app_spawns_no_thread_however_the_pool_is_created(
    config: Config, store: TrainingStore
) -> None:
    """Asserts the property that is actually TRUE, having had the previous version disproved.

    An earlier test here claimed lazy pool creation saved threads, citing "40 apps, 40
    threads". Two reviewers measured otherwise: a ThreadPoolExecutor starts no worker until
    work is submitted, so 40 constructed pools hold 0 threads, and the test passed whether the
    pool was built lazily or eagerly. It therefore asserted nothing, and the lazy branch has
    since been removed rather than defended.

    What holds regardless is this: constructing an application spawns no probe thread, which
    is what makes an unserved app free. The thread CONTROL is the lifespan release, asserted
    separately below.
    """
    before = probe_threads()
    apps = [create_app(config=config, store=store, probe=ok_probe) for _ in range(5)]
    assert apps
    gc.collect()
    # SUBTRACTION, not equality, and this was a real flake. Equality fails whenever a probe
    # thread from an EARLIER test exits between the two snapshots - no new thread required, and
    # nothing this test is about. Demonstrated directly: start a `probe_`-named thread, snapshot,
    # let it exit, snapshot again; `after == before` is False while `after - before` is empty.
    #
    # It failed once in a full loop run and then not in 15 bare runs plus 8 loop runs, which is
    # the worst shape a failure can have: rare enough to look like noise, and certain to appear
    # eventually in the platform's test stage, where a red suite skips every later gate.
    #
    # Subtraction asserts exactly the property claimed - no NEW probe thread - and is immune to
    # an unrelated one exiting.
    assert probe_threads() - before == set(), "building apps spawned probe threads"


def test_repeated_probes_hold_exactly_one_probe_thread(
    config: Config, store: TrainingStore
) -> None:
    """The pool is built once, eagerly, and four probes do not multiply its worker.

    This deliberately does NOT claim to assert lazy-versus-eager creation. Nothing can: a
    ThreadPoolExecutor starts no worker until work is submitted, and a dereferenced executor's
    worker exits when the executor is collected, so both variants hold exactly one thread at
    any moment. Two review rounds went into discovering that, and the lazy branch was removed
    rather than defended with a test that could not tell the difference.
    """
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        probe_settings=ProbeSettings(cache_seconds=0.0),
    )
    before = probe_threads()
    with TestClient(app) as client:
        for _ in range(4):
            assert client.get("/readyz").status_code == 200
        assert len(probe_threads() - before) == 1, "the probe pool multiplied its worker"


def test_the_lifespan_releases_the_probe_thread_it_created(
    config: Config, store: TrainingStore
) -> None:
    before = probe_threads()
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        probe_settings=ProbeSettings(cache_seconds=0.0),
    )
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 200
        assert probe_threads() - before, "the probe did not run on a dedicated pool thread"
    for _ in range(60):
        if not probe_threads() - before:
            break
        time.sleep(0.05)
    assert probe_threads() - before == set(), "the lifespan did not release the pool"


def test_the_probe_pool_serialises_its_work(config: Config, store: TrainingStore) -> None:
    """Serialisation is one of the TWO invariants `_probe_storage` names as what keeps
    publication ordered, so it is a control and not a tuning choice.

    Asserted as BEHAVIOUR, not as configuration. Raising the pool to eight workers was a
    surviving mutant, and thread counts cannot catch it because single-flight means one probe
    runs at a time either way. Reading `_max_workers` would kill the mutant but assert a
    private CPython attribute rather than the property named; this submits two blocking
    callables and asserts the second cannot start until the first returns.
    """
    app = create_app(config=config, store=store, probe=ok_probe)
    pool = app.state.probe_pool
    assert pool is not None, "no dedicated probe pool was constructed"

    order: list[str] = []
    first_running = threading.Event()
    release_first = threading.Event()

    def blocker() -> None:
        order.append("first-start")
        first_running.set()
        release_first.wait(timeout=5)
        order.append("first-end")

    def follower() -> None:
        order.append("second-start")

    try:
        first = pool.submit(blocker)
        assert first_running.wait(timeout=5), "the pool never started the first task"
        second = pool.submit(follower)
        # A second worker would run this immediately, while the first is still blocked.
        time.sleep(0.2)
        assert "second-start" not in order, "the pool ran two tasks at once"
        release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)
    finally:
        release_first.set()
    assert order == ["first-start", "first-end", "second-start"], order


def test_a_probe_after_shutdown_fails_closed_rather_than_using_the_shared_executor(
    config: Config, store: TrainingStore
) -> None:
    """Once the lifespan releases the pool, a further probe must NOT quietly fall back.

    `loop.run_in_executor(None, ...)` uses the shared default executor, which is the exact
    starvation the dedicated pool exists to prevent: a legitimate listing was measured at
    1.4 ms against 109 ms when the two shared a pool. Not reachable in production, because
    shutdown follows the last request, but a silent degradation inside a control is worth a
    test rather than a comment.
    """
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        probe_settings=ProbeSettings(cache_seconds=0.0),
    )
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 200
    assert app.state.runtime_probe_pool_released is True

    async def probe_after_shutdown() -> tuple[int, dict[str, Any]]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://probe") as after:
            response = await after.get("/readyz")
            return response.status_code, response.json()

    status, body = asyncio.run(probe_after_shutdown())
    assert status == 503, "a probe after shutdown did not fail closed"
    assert "shutting down" in body["storage"]["detail"]


@pytest.mark.parametrize(
    "validator",
    [
        'W/"\u00b2"',  # superscript two: isdigit() is True, int() raises
        '"\u00b2"',
        "\u00b2",
        '"\u0660"',  # Arabic-Indic zero: isdecimal() is True, so int() would succeed
        '"0x1"',
        '"1.5"',
        '"+1"',
        # CPython caps integer string conversion at 4300 digits, so all-ASCII digits still
        # raise past that. A reviewer found this on a real socket AFTER the character-class fix
        # was recorded as closing this class.
        '"' + "1" * 4301 + '"',
        '"' + "9" * 5000 + '"',
        '"  "',
        "W/",
        '""',
        "garbage",
    ],
)
def test_an_exotic_if_match_parses_to_no_revision_rather_than_raising(validator: str) -> None:
    """The parser directly, because a client library will not put these bytes on the wire.

    An exotic-digit If-Match returned 500 from a path documented to IGNORE an unparsable
    validator, because `isdigit()` accepts characters `int()` rejects. A reviewer reached it on
    a raw socket: uvicorn latin-1 decodes header bytes, so byte 0xB2 arrives as that character.
    httpx refuses to encode it, so the wire case is covered separately below and the whole
    hostile set is covered here.
    """
    assert _expected_rev(validator) is None, f"{validator!r} was not ignored"


@pytest.mark.parametrize(("validator", "expected"), [('W/"7"', 7), ('"7"', 7), ("7", 7)])
def test_a_well_formed_if_match_still_parses(validator: str, expected: int) -> None:
    """The boundary in the other direction: the guard must not reject a real validator."""
    assert _expected_rev(validator) == expected


def test_a_latin1_if_match_byte_on_the_wire_is_ignored_rather_than_raising(
    client: TestClient,
) -> None:
    """End to end with the byte a real client can actually send."""
    response = client.post(
        "/api/v1/sessions", json=VALID_SESSION, headers={b"if-match": b'W/"\xb2"'}
    )
    assert response.status_code == 201, response.text


def test_the_published_pool_reference_is_cleared_with_the_pool(
    config: Config, store: TrainingStore
) -> None:
    """The seam must not publish two facts that disagree. Leaving the reference pointing at a
    shut-down executor while the runtime's own is None invites a later reader to take the
    stale one as live.
    """
    app = create_app(config=config, store=store, probe=ok_probe)
    with TestClient(app) as client:
        assert client.get("/livez").status_code == 200
        assert app.state.probe_pool is not None
    assert app.state.probe_pool is None
    assert app.state.runtime_probe_pool_released is True


def test_nothing_on_app_state_exposes_the_configuration(
    token_config: Config, store: TrainingStore
) -> None:
    """The inspection seam must stay narrow.

    Publishing the whole runtime put `settings.team_token` within reach of any handler or
    third-party ASGI middleware through `request.app.state`. It was narrowed to the pool and a
    boolean, but nothing asserted the narrowness: adding `app.state.runtime = runtime` back left
    the entire suite green.
    """
    app = create_app(config=token_config, store=store, probe=ok_probe)
    published = vars(app.state).get("_state", vars(app.state))
    for name, value in published.items():
        assert not isinstance(value, Config), f"app.state.{name} exposes the configuration"
        rendered = repr(value)
        assert TEST_PLACEHOLDER not in rendered, f"app.state.{name} renders the team token"
    assert "runtime" not in published, f"app.state publishes the whole runtime: {sorted(published)}"


def test_the_revision_digit_bound_stays_well_below_the_interpreter_limit() -> None:
    """The bound is a deliberate value, and raising it silently weakens the first layer.

    A 64-bit counter is 19 digits, so 19 is generous for any real revision, and it is three
    orders of magnitude below CPython's 4300-digit integer conversion limit. Raising it to
    something past that limit left the suite green, because the guarded conversion then absorbed
    the case: the two layers mask each other under mutation, which is what defence in depth
    looks like, so the bound is pinned here directly.
    """
    assert 0 < MAX_REVISION_DIGITS <= 19, (
        f"the revision digit bound is {MAX_REVISION_DIGITS}, which no real revision needs and "
        "which weakens the first of three layers"
    )


@pytest.mark.parametrize(
    "path", ["/", "/healthz", "/readyz", "/livez", "/ping", "/api/v1/sessions"]
)
def test_every_user_stack_response_carries_nosniff(client: TestClient, path: str) -> None:
    """The one content-type header that is not inert on this service.

    A stored `title` or `notes` comes back inside a `GET /api/v1/sessions` body, and a browser
    pointed straight at that URL decides for itself what the bytes are. FastAPI sends
    `application/json`, so a sniffing browser should not reinterpret it, and "should not" is
    exactly the reason to say so in a header.

    The other two a reviewer looks for are deliberately absent and recorded in `docs/SECURITY.md`:
    Content-Security-Policy and `Referrer-Policy` are inert on a service serving JSON and plain
    text only (`/livez` and `/ping` in this very list return `PlainTextResponse`) that sets no
    cookies, serves no HTML and refuses to start on a wildcard origin. This one is not inert, which
    is why it is here and they are not.
    """
    response = client.get(path)
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_an_error_response_carries_nosniff_too(client: TestClient) -> None:
    """Error paths are as navigable as successful ones.

    A 422 here, and equally a 413 from the body cap or a 429 from the limiter, is a response a
    browser can be pointed at. `NoSniffMiddleware` is registered outermost among USER middleware
    for this reason - `test_the_middleware_order_puts_the_limiter_outside_the_body_cap` asserts that
    order and is the only authority on it - because a header installed beside the routes would
    miss every response a middleware answers itself. The unhandled-exception 500 is outside even
    that, and
    `test_a_500_carries_its_own_headers_because_no_user_middleware_reaches_it` covers it.

    422 rather than 401, which is worth recording because I assumed the opposite when writing this:
    body validation runs BEFORE the token dependency on this route, so a malformed write is
    refused on its shape without the token ever being compared. That is the right order - it
    reveals nothing and costs nothing - but it means a test aiming at the auth refusal has to send
    a well-formed body.
    """
    refused = client.post("/api/v1/sessions", json={"id": "a", "title": "b"})
    assert refused.status_code == 422
    assert refused.headers.get("x-content-type-options") == "nosniff"


def test_an_unreadable_snapshot_fails_closed_on_the_anonymous_listing(
    token_config: Config, tmp_path: Path
) -> None:
    """A 500 on an unauthenticated route from data this process wrote itself.

    `GET /api/v1/sessions` is anonymous by the decision at accepted risk 5, and it called
    `store.load` with no handler. Every malformed shape the store already refuses arrived as an
    unhandled exception and a generic 500: not JSON, not UTF-8, top level not an object, nested
    too deep - and, found by the security gate, a string that PARSES and then cannot be encoded,
    which raises inside pydantic's serialiser while the response is rendered.

    The last of those was the reason to look: the snapshot had no equivalent of the content tree's
    encodability check, so "the snapshot is trusted stored state" and "the progress file is not"
    were two different answers to one question in adjacent modules. `TrainingStore.load` runs the
    same boundary walk now and raises `ValueError` like every other malformed shape, and the route
    answers a 503 naming the fault.

    Not reachable from the HTTP edge - a surrogate in a body is refused with a generic 422 in
    every form - so the precondition is write access to the data volume, an actor this threat
    model puts out of scope. Closed anyway: a route that 500s on its own data is a route nobody
    can diagnose from a screenshot, which is the distinction the App Store health contract is
    built on.

    **The health split is asserted alongside**, because that is the property a 503 must not break:
    `/livez`, `/ping`, `/health` and `/` are dependency-free and stay 200 while the storage-proving
    paths go 503. A downstream fault must never restart a healthy container.
    """
    #: THE SHAPES ENUMERATED BELOW, and nothing more is claimed. This list has now been wrong
    #: twice by claiming completeness: "all five" missed a `sessions` member that was not an
    #: object, and the enumeration that replaced it missed nesting depth. Two over-claims in two
    #: consecutive releases is enough evidence that a hand-written completeness claim about this
    #: store is not worth making, so the wording is now scoped to the list rather than to the
    #: store, and the member shapes have their own parametrised test.
    refusals: list[str] = []
    corrupt: dict[str, str | bytes] = {
        #: The NEWLINE, the forged object and the SURROGATE are all in the SAME key, and that
        #: matters: the walk reports the pointer of the string it found, so a fixture with the
        #: newline in one key and the surrogate in another value reported a clean pointer and the
        #: sanitiser mutant survived. The poison has to be in the string the message will quote.
        "a lone surrogate": json.dumps(
            {
                "rev": 1,
                "sessions": [{"id": "s-1", "title": "ok"}],
                'K\nENLIGHTENMENT FORGED {"event":"session.upsert","actor":"root"}Z': 1,
            }
        ).replace('Z":', '\\ud800":'),
        "not JSON": "{not json",
        "top level not an object": "[]",
        "nested too deep": "[" * 200_000,
        #: The SIXTH shape, and the one that escaped every branch: `sessions` was checked to be a
        #: LIST and its elements were not checked at all. `dict(session)` then raised `TypeError`
        #: rather than `ValueError`, so it slipped past the mapping every caller relies on and
        #: reached an anonymous caller as a 500 with `/healthz` still 200.
        "a sessions entry that is not an object": '{"rev": 1, "sessions": [1]}',
        #: And the dangerous half of it. A list of PAIRS is coerced by `dict()` into a session row
        #: NOBODY WROTE: measured, the anonymous listing served
        #: `{"id": "GHOST-ONE", "title": "Fabricated"}` with an honest-looking count and total. A
        #: fabricated record on a read boundary, which no length cap or byte ceiling can see
        #: because the row is well-formed once coerced.
        "a sessions entry coerced from a pair list": json.dumps(
            {"rev": 1, "sessions": [[["id", "GHOST-ONE"], ["title", "Fabricated"]]]}
        ),
        #: NESTING DEPTH, the shape the previous enumeration missed. It parses, it survives
        #: `migrate`, it carries no surrogate - and `pydantic_core` then raises
        #: `Circular reference detected (depth exceeded)` at about 250 WHILE THE RESPONSE IS
        #: RENDERING, outside the route's try/except, so the 503 mapping never sees it. Measured:
        #: 250 served, 252 gave a 500 with `/healthz` still 200. Refused at 32, which is four
        #: times the deepest thing this project ships.
        "a value nested past the serialiser's limit": json.dumps(
            {"rev": 1, "sessions": [{"id": "a", "deep": _nested(40)}]}
        ),
        #: A REVISION with no magnitude bound, while the request side is capped at 19 digits. The
        #: `ETag` is built from it and a header is covered by no body ceiling: measured, a
        #: 4,000-digit `rev` produced a 4,004-byte `ETag` on the anonymous listing.
        "a revision of absurd magnitude": json.dumps({"rev": int("9" * 4000), "sessions": []}),
        #: The last two shapes, added by the DERIVED check below rather than by anybody noticing.
        #: Both had unit tests in `test_storage.py` and neither had a route-level driver, so the
        #: 503 was proved for eight of the store's ten refusals and asserted for all of them.
        "a revision that is not an integer": '{"rev": "one", "sessions": []}',
        "a sessions field that is not a list": '{"rev": 1, "sessions": "nope"}',
        #: Valid bytes, not valid UTF-8. The BOM is load-bearing: bare UTF-16LE of ASCII is
        #: nothing but ASCII interleaved with NULs, and a NUL is perfectly valid UTF-8 - so
        #: without `\xff\xfe` this decoded cleanly and failed one branch further on as a JSON
        #: error, leaving the UTF-8 branch uncovered while the fixture claimed to drive it.
        "not UTF-8": b"\xff\xfe" + '{"rev": 1}'.encode("utf-16-le"),
    }
    for label, body in corrupt.items():
        data_dir = tmp_path / label.replace(" ", "-")
        data_dir.mkdir()
        target = data_dir / STORE_FILENAME
        if isinstance(body, bytes):
            target.write_bytes(body)
        else:
            target.write_text(body, encoding="utf-8")
        app = create_app(
            config=replace(token_config, data_dir=data_dir),
            store=TrainingStore(data_dir),
            probe=ok_probe,
            training=TrainingPaths(
                content_root=CONTENT_ROOT, progress_path=data_dir / "progress.json"
            ),
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            listing = client.get("/api/v1/sessions")
            assert listing.status_code == 503, (
                f"{label}: answered {listing.status_code}, so a corrupt snapshot reaches an"
                f" anonymous caller as a traceback: {listing.content[:160]!r}"
            )
            assert listing.json()["detail"]["error"] == "store_unavailable", listing.text
            refusals.append(listing.json()["detail"]["message"])
            #: The message names the fault and never a stored value.
            assert "s-1" not in listing.text, listing.text[:200]
            #: And no FABRICATED record reaches the wire. This is the assertion the pair-list
            #: shape exists for: a 503 is the point, but a 200 carrying an invented session would
            #: be the worse outcome and a status check alone cannot tell them apart.
            assert "GHOST-ONE" not in listing.text, listing.text[:200]
            #: The message names the RIGHT FAULT, not merely a fault. Inverting the depth arm in
            #: `storage.load` left the suite green while the anonymous 503 misdiagnosed a nesting
            #: fault as an encoding one - fail-closed either way, so a status assertion cannot see
            #: it, and this project treats a wrong diagnosis as load-bearing.
            if label == "a value nested past the serialiser's limit":
                assert "nests deeper than" in listing.json()["detail"]["message"], listing.text
            #: SINGLE LINE and bounded. The pointer carries stored KEY NAMES, and `app.py` logs
            #: this text with `_logger.exception`, whose traceback renders it verbatim - so a key
            #: containing a newline forged a second log line, raw surrogate and all, past the
            #: claim that every reflected value reaching a log line goes through the shared
            #: sanitiser. Bounded at the RAISE, which bounds the wire copy and the log copy at
            #: once; two sanitisers for one string is how they diverge.
            message = listing.json()["detail"]["message"]
            assert "\n" not in message, repr(message)
            assert "\r" not in message, repr(message)
            assert len(message.encode("utf-8")) <= MAX_WITHHOLD_REASON, len(message)

            for path in ("/", "/livez", "/ping", "/health"):
                assert client.get(path).status_code == 200, (
                    f"{label}: {path} is dependency-free and must stay 200"
                )

            #: The GATED WRITES answer the same 503, not 500. Before this assertion the `_write`
            #: handler survived being retargeted to an exception that cannot occur, because
            #: nothing drove a write against a corrupt snapshot - the identical "held by nothing"
            #: shape as the read it was added to match.
            #: `SessionPatch` forbids `id`, and body validation runs BEFORE the store read, so a
            #: PATCH carrying the upsert body is a legitimate 422 and would have proved nothing.
            for method, target, payload in (
                ("POST", "/api/v1/sessions", VALID_SESSION),
                ("PATCH", "/api/v1/sessions/alpha-one", {"title": "Renamed"}),
            ):
                write = client.request(method, target, json=payload, headers=AUTH)
                assert write.status_code == 503, (
                    f"{label}: {method} answered {write.status_code}, so a corrupt"
                    f" snapshot reaches a caller as a traceback: {write.content[:160]!r}"
                )
                assert write.json()["detail"]["error"] == "store_unavailable", write.text

    #: EVERY refusal the store can raise has a fixture above, DERIVED from the source rather than
    #: promised in a comment. This is the assertion that replaces three broken completeness claims
    #: - "ALL FIVE shapes", then an enumeration that missed serialise-depth, then wording scoped to
    #: the list - and it found two missing drivers the moment it existed.
    for needle in _store_refusal_needles():
        assert any(needle in message for message in refusals), (
            f"the store can refuse with {needle!r} and no fixture above drives it, so this test"
            f" asserts a 503 for a shape nothing proves; refusals seen: {refusals}"
        )


def _store_refusal_needles() -> list[str]:
    """Every refusal message `storage.migrate` and `storage.load` can raise, read from the SOURCE.

    **Derived, not written down, because the written-down version was wrong three times.** "ALL
    FIVE shapes the store refuses" missed a `sessions` member that was not an object; the
    enumeration that replaced it missed nesting too deep to SERIALISE; and the wording that
    replaced THAT was scoped to the list rather than to the store, which is honest but still
    hand-maintained. The security gate's judgement, adopted: scoping the prose was the right
    immediate move and deriving is the one that stops the fourth.

    So this walks the two functions for `raise ValueError` and returns the longest literal fragment
    of each message. A new refusal added to the store with no fixture beside it turns the test
    below red, which is a mechanical promise where there was a prose one. It found two gaps the
    moment it existed: `'rev' is not an integer` and `'sessions' is not a list` both had unit tests
    and neither had a route-level driver.
    """
    source = (ROOT / "src" / "enlightenment" / "storage.py").read_text(encoding="utf-8")

    def literals(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.JoinedStr):
            return [
                value.value
                for value in node.values
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            ]
        return []

    needles: list[str] = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, ast.FunctionDef) or function.name not in {"migrate", "load"}:
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            if getattr(node.exc.func, "id", "") != "ValueError":
                continue
            fragments = [part for argument in node.exc.args for part in literals(argument)]
            assert fragments, f"a ValueError in {function.name} carries no literal to match on"
            needles.append(max(fragments, key=len))
    assert len(needles) >= 10, f"the store's refusal sites shrank to {len(needles)}; re-read them"
    return needles


def test_a_planted_session_past_the_byte_ceiling_fails_the_read_closed(
    token_config: Config, tmp_path: Path
) -> None:
    """The served byte ceiling ENFORCED, not merely asserted in a test.

    `MAX_SERVED_SESSIONS_BYTES` appeared nowhere in `src/` except its own definition, so it
    bounded what `SessionUpsert` accepts and nothing else: measured, a 5 MB field value planted on
    the volume produced a **5,000,082-byte anonymous response**, nineteen times the documented
    ceiling and past `MAX_PAYLOAD_BYTES`. The COUNT cap cannot see it, because the fault is one
    row's size rather than the number of rows, and the register's ceiling was true only of data
    written through the API.

    **The snapshot is not corrupt here, and that is what separates this from the sibling test.**
    It parses, it migrates, every field is a string - so a WRITE legitimately succeeds and only
    the read overflows. Putting this case in the corrupt-snapshot table asserted 503 on the write
    and failed, correctly: the store had nothing to refuse.

    Fail closed rather than truncate, the same choice as an oversized library document: a silently
    shortened listing reads as the whole dataset, which is exactly what `total` and `truncated`
    exist to prevent.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / STORE_FILENAME).write_text(
        json.dumps({"rev": 1, "sessions": [{"id": "a", "title": "X" * 5_000_000}]}),
        encoding="utf-8",
    )
    app = create_app(
        config=replace(token_config, data_dir=data_dir),
        store=TrainingStore(data_dir),
        probe=ok_probe,
        training=TrainingPaths(content_root=CONTENT_ROOT, progress_path=data_dir / "progress.json"),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        listing = client.get("/api/v1/sessions")
        assert listing.status_code == 503, (
            f"answered {listing.status_code} at {len(listing.content)} bytes, so the documented"
            " ceiling bounds nothing a planted row can do"
        )
        assert listing.json()["detail"]["error"] == "store_unavailable", listing.text
        assert len(listing.content) <= MAX_SERVED_SESSIONS_BYTES, len(listing.content)
        #: The refusal states the FIGURES and claims nothing about how the rows got there. It
        #: used to say "a row was not written through this API", which was provably false: the
        #: write boundary accepted C0 control characters at six rendered bytes per code point, so
        #: twenty legitimate authenticated writes could reach 281,353 bytes. A 503 whose message
        #: names the wrong cause sends an operator hunting a volume write that never happened.
        assert str(MAX_SERVED_SESSIONS_BYTES) in listing.text, listing.text[:200]
        assert "render to" in listing.text, listing.text[:200]
        assert "through this API" not in listing.text, listing.text[:200]
        #: And the WRITE still works, because the snapshot is valid. Asserted so the fail-closed
        #: read is not mistaken for a store-wide refusal.
        write = client.request("POST", "/api/v1/sessions", json=VALID_SESSION, headers=AUTH)
        assert write.status_code == 201, write.text
        for path in ("/", "/livez", "/ping", "/health"):
            assert client.get(path).status_code == 200, path


def test_a_planted_non_json_float_fails_the_read_closed(
    token_config: Config, tmp_path: Path
) -> None:
    """A stored `NaN` is refused rather than silently rewritten, and that is what keeps the
    byte ceiling exact.

    `json.dumps` writes `NaN` by default, which is not JSON; pydantic rewrites it to `null`
    before Starlette renders. So a ceiling measured on anything but the bytes actually sent
    under-counted a planted NaN by one byte each, and the security gate measured the consequence:
    a NaN-dense snapshot served **289,199 bytes with HTTP 200** against a 262,144 ceiling, 10.3%
    past it.

    Serialising once with `allow_nan=False` and returning that exact `Response` makes the basis
    the wire by construction. The refusal is the right answer rather than a nuisance: no float of
    any form can arrive through this API - `notes=NaN`, `notes=1e400` and `notes=1.5` are all
    generic 422s - so a stored float means the volume was written past the boundary.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    rows = [{"id": f"s-{index}", "x": float("nan"), "title": "A" * 900} for index in range(25)]
    (data_dir / STORE_FILENAME).write_text(
        json.dumps({"rev": 1, "sessions": rows}), encoding="utf-8"
    )
    app = create_app(
        config=replace(token_config, data_dir=data_dir),
        store=TrainingStore(data_dir),
        probe=ok_probe,
        training=TrainingPaths(content_root=CONTENT_ROOT, progress_path=data_dir / "progress.json"),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        listing = client.get("/api/v1/sessions")
        assert listing.status_code == 503, (
            f"answered {listing.status_code} at {len(listing.content)} bytes; a stored NaN is"
            " rewritten to null by pydantic, so a ceiling not measured on the wire misses it"
        )
        assert listing.json()["detail"]["error"] == "store_unavailable", listing.text
        assert "cannot be serialised" in listing.json()["detail"]["message"], listing.text
        assert "through this API" not in listing.text, listing.text[:200]
        for path in ("/", "/livez", "/ping", "/health"):
            assert client.get(path).status_code == 200, path


def test_a_control_character_is_refused_at_the_write_boundary(
    token_config: Config, tmp_path: Path
) -> None:
    """A C0 control is refused, a line break and a tab are not, and the reason is SIZE.

    `json.dumps` escapes a C0 control as `\\u00XX` even with `ensure_ascii=False`, so one code
    point renders as SIX bytes where an astral character renders as four and a newline as two. The
    field caps count CODE POINTS, so the worst case was set by the most expensive character the
    boundary accepted - and it accepted `U+0000`. Measured by the security gate: twenty writes at
    the declared caps, every one accepted with 201, rendered to **281,353 bytes** against the
    262,144 ceiling, and twenty-five rows to **351,327**, or 134% of it. An anonymous route
    fail-closed on twenty legitimate authenticated writes, while the refusal blamed a write that
    never bypassed the API.

    **`\n`, `\r` and `\t` stay allowed**, because a note with line breaks is legitimate free text
    and each renders as two bytes, so keeping them costs nothing. That distinction is the whole
    point: the rule is not "no control characters" but "nothing that makes a code point cost more
    than the astral worst case".

    The boundary was already inconsistent with itself before this, and only incidentally:
    `U+2028` was refused because `str_strip_whitespace` strips it to empty and `min_length`
    rejects that, while `U+0000` sailed through.

    **Both write routes, and the second one is the reason this docstring grew.** The first
    version of this test drove `POST` only, while being named for "the write boundary". Deleting
    `FreeText` from the three `SessionPatch` fields then left the whole suite green at 1,011
    passed - reproduced twice - while `PATCH` accepted NUL, BEL, escape, `U+2028` and `U+00A0`
    with 200. `PATCH` alone is enough to break the served ceiling: `notes` at its 2,000 cap of
    NUL renders to 12,000 bytes a row, so the 25 SERVED rows measure 335,264 bytes against
    262,144 with the other two fields at their caps in astral characters, and 351,264 with all
    three in NUL. Both on a planted 500-row snapshot at twelve character ids and twenty character
    timestamps: **rows WRITTEN moves the figure even though only 25 are served**, because it sets
    `total`'s digit count and the `truncated` flag, so 26 rows written measures 335,262 and 25
    measures 335,263. A byte figure without its fixture is not reproducible, which is how six of
    them went stale here. Same
    shape as the fixture fault this project has now hit twice - one axis bound and reported as
    the whole - one ROUTE along instead of one field along.
    """
    app = create_app(
        config=token_config,
        store=TrainingStore(tmp_path / "store"),
        probe=ok_probe,
        #: A budget wide enough that the LIMITER never answers for the boundary. Both routes
        #: together spend eighteen accepted writes plus the seed, against a `WRITE_LIMIT` of
        #: twenty, so the default tier would pass today and 429 on the next candidate added.
        limiters=Limiters(strict=RateLimiter(200, 60.0)),
        training=TrainingPaths(content_root=CONTENT_ROOT, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        seeded = client.request(
            "POST", "/api/v1/sessions", json={**VALID_SESSION, "id": "patchee"}, headers=AUTH
        )
        assert seeded.status_code == 201, seeded.text
        #: A refused body 422s in pydantic, BEFORE `_guard_write_rate` runs inside the handler, so
        #: only the accepted writes spend budget. Counted at runtime from the real status codes,
        #: because the comment above cited `WRITE_LIMIT` as twenty while no test bound its value.
        #:
        #: **The binding is ONE-SIDED, and the first version of this comment claimed two.** It
        #: said "lower it and the default tier starts deciding this test's verdict", which cannot
        #: happen: the app above injects a 200-per-minute strict tier, so `WRITE_LIMIT` has no
        #: say here at any value. Measured, the assertion survives at 1, 5, 10, 19 and 20 and
        #: dies at 21 and above. The ceiling is the direction worth holding anyway, because only
        #: a RAISE makes the injection unnecessary; a lower limit leaves it needed. Claiming a
        #: binding the assertion does not have is this release's own thesis turned on itself.
        spent = 1
        for label, character, refused in (
            ("NUL", "\x00", True),
            ("BEL", "\x07", True),
            ("escape", "\x1b", True),
            ("newline", "\n", False),
            ("tab", "\t", False),
            ("astral", "\U0001f600", False),
        ):
            for field in ("title", "scenario", "notes"):
                value = f"a{character}b"
                for method, path, body, accepted in (
                    (
                        "POST",
                        "/api/v1/sessions",
                        {**VALID_SESSION, "id": "probe", field: value},
                        201,
                    ),
                    ("PATCH", "/api/v1/sessions/patchee", {field: value}, 200),
                ):
                    expected = 422 if refused else accepted
                    response = client.request(method, path, json=body, headers=AUTH)
                    assert response.status_code == expected, (
                        f"{label} in {field} on {method} answered {response.status_code},"
                        f" expected {expected}: {response.content[:160]!r}"
                    )
                    if refused:
                        #: Generic, and the offending character is never echoed.
                        assert response.json() == {"error": "invalid request"}, response.text
                    else:
                        spent += 1
        assert spent == 19, f"the accepted-write count moved to {spent}; re-check the budget"
        assert WRITE_LIMIT - spent <= 1, (
            f"this test spends {spent} writes against a WRITE_LIMIT of {WRITE_LIMIT}, so the"
            " default tier now has room and the injected limiter is no longer justified"
        )
