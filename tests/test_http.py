"""HTTP behaviour, mounted in-process through the factory with injected fakes."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import failing_probe, ok_probe
from enlightenment.app import MAX_BODY_BYTES, create_app
from enlightenment.auth import TOKEN_HEADER
from enlightenment.config import Config
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import ProbeResult, TrainingStore

VALID_SESSION = {"id": "alpha-one", "title": "Alpha One", "scenario": "TBC, re-verify"}


def token_config(data_dir: Path) -> Config:
    """A hosted configuration: a team token and a real allowed origin."""
    return Config(
        port=8080,
        host="0.0.0.0",
        data_dir=data_dir,
        team_token="a-real-length-token",
        allowed_origin="https://enlightenment.apps.bluestaq.com",
        build_id="test-build",
    )


@pytest.fixture
def gated_client(data_dir: Path, store: TrainingStore) -> Iterator[TestClient]:
    with TestClient(create_app(config=token_config(data_dir), store=store)) as client:
        yield client


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

    app = create_app(config=config, store=store, probe=stalled_probe, probe_timeout=0.05)
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

    app = create_app(config=config, store=store, probe=exploding_probe)
    with TestClient(app) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["storage"]["writable"] is False


# --- diagnostics --------------------------------------------------------------------


def test_diagnostics_reports_booleans_and_lengths_but_never_a_secret_value(
    gated_client: TestClient,
) -> None:
    body = gated_client.get("/api/v1/diagnostics").json()
    assert body["config"]["teamToken"] == {"set": True, "length": len("a-real-length-token")}
    assert body["config"]["authRequired"] is True
    assert "a-real-length-token" not in gated_client.get("/api/v1/diagnostics").text


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


# --- authentication -----------------------------------------------------------------


def test_a_write_without_a_token_is_refused_when_a_token_is_configured(
    gated_client: TestClient,
) -> None:
    assert gated_client.post("/api/v1/sessions", json=VALID_SESSION).status_code == 401


def test_a_write_with_a_wrong_token_is_refused(gated_client: TestClient) -> None:
    response = gated_client.post(
        "/api/v1/sessions", json=VALID_SESSION, headers={TOKEN_HEADER: "wrong-length-token!"}
    )
    assert response.status_code == 401


def test_a_write_with_the_right_token_succeeds(gated_client: TestClient) -> None:
    response = gated_client.post(
        "/api/v1/sessions", json=VALID_SESSION, headers={TOKEN_HEADER: "a-real-length-token"}
    )
    assert response.status_code == 201
    assert response.json()["session"]["id"] == "alpha-one"


def test_health_paths_stay_public_when_a_token_is_configured(gated_client: TestClient) -> None:
    for path in ("/", "/livez", "/ping", "/health", "/healthz", "/readyz"):
        assert gated_client.get(path).status_code == 200, path


def test_local_mode_with_no_token_allows_the_write(client: TestClient) -> None:
    assert client.post("/api/v1/sessions", json=VALID_SESSION).status_code == 201


# --- boundary validation ------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"id": "alpha", "title": "A"},
        {"id": "alpha", "title": "A", "scenario": "s", "unexpected": "key"},
        {"id": "Alpha-Upper", "title": "A", "scenario": "s"},
        {"id": "double--hyphen", "title": "A", "scenario": "s"},
        {"id": "", "title": "A", "scenario": "s"},
        {"id": "alpha", "title": "", "scenario": "s"},
        {"id": "alpha", "title": "A", "scenario": "s", "notes": "n" * 2001},
        {"id": "a" * 65, "title": "A", "scenario": "s"},
    ],
)
def test_a_malformed_body_is_rejected_generically(client: TestClient, body: dict[str, str]) -> None:
    response = client.post("/api/v1/sessions", json=body)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid request"}


def test_an_oversize_body_is_refused_before_it_is_parsed(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"error": "request body too large"}


def test_an_unhandled_error_returns_a_generic_message_and_no_stack_trace(
    config: Config, data_dir: Path
) -> None:
    class ExplodingStore(TrainingStore):
        def sessions(self) -> list[dict[str, object]]:
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
    """POST is a full upsert, so a missing required field is a rejection, not a merge."""
    client.post("/api/v1/sessions", json=VALID_SESSION)
    response = client.post("/api/v1/sessions", json={"id": "alpha-one", "title": "Renamed"})
    assert response.status_code == 422


def test_a_patch_to_an_unknown_session_is_a_404_not_a_silent_create(
    client: TestClient,
) -> None:
    response = client.patch("/api/v1/sessions/never-created", json={"title": "x"})
    assert response.status_code == 404


def test_a_patch_with_an_unknown_key_is_rejected(client: TestClient) -> None:
    client.post("/api/v1/sessions", json=VALID_SESSION)
    response = client.patch("/api/v1/sessions/alpha-one", json={"unexpected": "key"})
    assert response.status_code == 422


def test_a_patch_without_a_token_is_refused_when_a_token_is_configured(
    gated_client: TestClient,
) -> None:
    assert gated_client.patch("/api/v1/sessions/alpha-one", json={"title": "x"}).status_code == 401


# --- rate limiting ------------------------------------------------------------------


def test_the_strict_tier_returns_429_after_its_limit(config: Config, store: TrainingStore) -> None:
    app = create_app(config=config, store=store, probe=ok_probe, write_limiter=RateLimiter(2, 60.0))
    with TestClient(app) as client:
        first = client.post("/api/v1/sessions", json=VALID_SESSION)
        second = client.post("/api/v1/sessions", json=VALID_SESSION)
        third = client.post("/api/v1/sessions", json=VALID_SESSION)
    assert [first.status_code, second.status_code] == [201, 201]
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


def test_the_allowed_origin_is_echoed_and_another_origin_is_not(
    gated_client: TestClient,
) -> None:
    allowed = gated_client.get("/", headers={"origin": "https://enlightenment.apps.bluestaq.com"})
    assert (
        allowed.headers["access-control-allow-origin"] == "https://enlightenment.apps.bluestaq.com"
    )
    other = gated_client.get("/", headers={"origin": "https://attacker.example"})
    assert "access-control-allow-origin" not in other.headers


def test_no_cors_header_is_emitted_when_no_origin_is_configured(client: TestClient) -> None:
    response = client.get("/", headers={"origin": "https://anything.example"})
    assert "access-control-allow-origin" not in response.headers
