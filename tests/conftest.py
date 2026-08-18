"""Shared fixtures. Every test runs against a temporary data directory and injected
fakes, so no test touches the network, a real clock, or shared state.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from enlightenment.app import create_app
from enlightenment.config import Config
from enlightenment.storage import ProbeResult, TrainingStore

#: A token at or above the enforced minimum length, used wherever a hosted app is built.
TEST_TOKEN = "a-token-of-sufficient-length"

#: The origin a hosted deployment is configured with.
TEST_ORIGIN = "https://enlightenment.apps.bluestaq.com"


@pytest.fixture
def anyio_backend() -> str:
    """Run the `@pytest.mark.anyio` tests on asyncio only; the app has no trio support."""
    return "asyncio"


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated storage directory, with the environment cleared of any real values."""
    target = tmp_path / "data"
    target.mkdir()
    monkeypatch.setenv("DATA_DIR", str(target))
    for name in (
        "STORAGE_MOUNT_PATH",
        "ENLIGHTENMENT_TEAM_TOKEN",
        "ENLIGHTENMENT_ALLOW_ANONYMOUS",
        "ALLOWED_ORIGIN",
        "HOST",
        "PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    return target


@pytest.fixture
def config(data_dir: Path) -> Config:
    """Single-user local mode: no token, anonymous writes EXPLICITLY opted in."""
    return Config(
        port=8080,
        host="127.0.0.1",
        data_dir=data_dir,
        team_token="",
        allowed_origin="",
        build_id="test-build",
        allow_anonymous_writes=True,
    )


@pytest.fixture
def closed_config(data_dir: Path) -> Config:
    """The CONTAINER DEFAULT: no token and no opt-in, so writes must be refused."""
    return Config(
        port=8080,
        host="127.0.0.1",
        data_dir=data_dir,
        team_token="",
        allowed_origin="",
        build_id="test-build",
    )


@pytest.fixture
def token_config(data_dir: Path) -> Config:
    """A hosted deployment: a team token and a real allowed origin."""
    return Config(
        port=8080,
        host="0.0.0.0",
        data_dir=data_dir,
        team_token=TEST_TOKEN,
        allowed_origin=TEST_ORIGIN,
        build_id="test-build",
    )


@pytest.fixture
def store(data_dir: Path) -> TrainingStore:
    """A store over the isolated directory."""
    return TrainingStore(data_dir)


@pytest.fixture
def client(config: Config, store: TrainingStore) -> Iterator[TestClient]:
    """The app in explicit local anonymous mode."""
    with TestClient(create_app(config=config, store=store)) as test_client:
        yield test_client


@pytest.fixture
def closed_client(closed_config: Config, store: TrainingStore) -> Iterator[TestClient]:
    """The app as the container ships it with an empty operator environment tab."""
    with TestClient(create_app(config=closed_config, store=store)) as test_client:
        yield test_client


@pytest.fixture
def gated_client(token_config: Config, store: TrainingStore) -> Iterator[TestClient]:
    """The app with the shared team token configured."""
    with TestClient(create_app(config=token_config, store=store)) as test_client:
        yield test_client


def ok_probe(path: Path) -> ProbeResult:
    """A probe that reports storage as writable."""
    return ProbeResult(ok=True, resolved=str(path))


def failing_probe(path: Path) -> ProbeResult:
    """A probe that reports a root-owned mount refusing a write."""
    return ProbeResult(ok=False, resolved=str(path), errno=13, detail="Permission denied")
