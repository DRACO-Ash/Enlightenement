"""HTTP behaviour, mounted in-process through the factory with injected fakes."""

from __future__ import annotations

import asyncio
import gc
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from conftest import TEST_ORIGIN, TEST_TOKEN, failing_probe, ok_probe
from enlightenment.app import (
    MAX_BODY_BYTES,
    MAX_REVISION_DIGITS,
    ProbeSettings,
    _expected_rev,
    create_app,
)
from enlightenment.auth import TOKEN_HEADER
from enlightenment.config import Config
from enlightenment.middleware import DRAIN_TIMEOUT_SECONDS, BodyLimitMiddleware
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import ProbeResult, TrainingStore

VALID_SESSION = {"id": "alpha-one", "title": "Alpha One", "scenario": "TBC, re-verify"}
AUTH = {TOKEN_HEADER: TEST_TOKEN}

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
    assert TEST_TOKEN not in response.text
    assert str(len(TEST_TOKEN)) not in str(body["config"]["teamToken"])


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
    wrong = TEST_TOKEN[:-1] + "X"
    response = gated_client.post(
        "/api/v1/sessions", json=VALID_SESSION, headers={TOKEN_HEADER: wrong}
    )
    assert response.status_code == 401


def test_a_write_with_the_right_token_succeeds(gated_client: TestClient) -> None:
    response = gated_client.post("/api/v1/sessions", json=VALID_SESSION, headers=AUTH)
    assert response.status_code == 201
    assert response.json()["session"]["id"] == "alpha-one"


def test_health_paths_stay_public_when_a_token_is_configured(gated_client: TestClient) -> None:
    for path in ("/", "/livez", "/ping", "/health", "/healthz", "/readyz"):
        assert gated_client.get(path).status_code == 200, path


def test_local_anonymous_mode_allows_the_write_and_records_the_actor_as_anonymous(
    client: TestClient,
) -> None:
    assert client.post("/api/v1/sessions", json=VALID_SESSION).status_code == 201


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
    app = create_app(config=config, store=store, probe=ok_probe, write_limiter=RateLimiter(2, 60.0))
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
    app = create_app(config=config, store=store, probe=ok_probe, write_limiter=RateLimiter(3, 60.0))
    with TestClient(app) as client:
        assert client.post("/api/v1/sessions", json=VALID_SESSION).status_code == 201
        first = client.patch("/api/v1/sessions/alpha-one", json={"title": "one"})
        second = client.patch("/api/v1/sessions/alpha-one", json={"title": "two"})
        third = client.patch("/api/v1/sessions/alpha-one", json={"title": "three"})
    assert [first.status_code, second.status_code] == [200, 200]
    assert third.status_code == 429


def test_the_coarse_tier_returns_429_after_its_limit(config: Config, store: TrainingStore) -> None:
    app = create_app(
        config=config, store=store, probe=ok_probe, global_limiter=RateLimiter(2, 60.0)
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/sessions").status_code == 200
        assert client.get("/api/v1/sessions").status_code == 200
        assert client.get("/api/v1/sessions").status_code == 429


def test_probe_paths_are_never_rate_limited(config: Config, store: TrainingStore) -> None:
    app = create_app(
        config=config, store=store, probe=ok_probe, global_limiter=RateLimiter(1, 3600.0)
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
            "access-control-request-headers": TOKEN_HEADER,
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
        config=token_config, store=store, probe=ok_probe, global_limiter=RateLimiter(1, 3600.0)
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


def test_the_middleware_order_puts_the_limiter_outside_the_body_cap(
    token_config: Config, store: TrainingStore
) -> None:
    """Order is load-bearing twice. The limiter must be OUTSIDE the cap, or an oversize
    request is read in full while spending no limiter budget; and the cross-origin layer
    must be outermost, or a 413 or 429 reaches a browser with no header and reads as an
    opaque network error. Both were wrong in the first version.
    """
    app = create_app(config=token_config, store=store, probe=ok_probe)
    order = [layer.cls.__name__ for layer in app.user_middleware]
    assert order == ["CORSMiddleware", "BaseHTTPMiddleware", "BodyLimitMiddleware"], order


def test_an_oversize_request_still_spends_rate_limit_budget(
    config: Config, store: TrainingStore
) -> None:
    """With the cap outside the limiter, oversize requests were free: twelve of them left
    the limiter's key table empty, so an unauthenticated caller could send unlimited
    64 KB-body requests without ever being refused.
    """
    limiter = RateLimiter(2, 60.0)
    app = create_app(config=config, store=store, probe=ok_probe, global_limiter=limiter)
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
        assert TEST_TOKEN not in rendered, f"app.state.{name} renders the team token"
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
