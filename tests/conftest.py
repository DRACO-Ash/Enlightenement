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


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated storage directory, also exported so request-time resolution finds it."""
    target = tmp_path / "data"
    target.mkdir()
    monkeypatch.setenv("DATA_DIR", str(target))
    monkeypatch.delenv("STORAGE_MOUNT_PATH", raising=False)
    return target


@pytest.fixture
def config(data_dir: Path) -> Config:
    """A valid configuration with authentication off (single-user local mode)."""
    return Config(
        port=8080,
        host="127.0.0.1",
        data_dir=data_dir,
        team_token="",
        allowed_origin="",
        build_id="test-build",
    )


@pytest.fixture
def store(data_dir: Path) -> TrainingStore:
    """A store over the isolated directory."""
    return TrainingStore(data_dir)


@pytest.fixture
def client(config: Config, store: TrainingStore) -> Iterator[TestClient]:
    """The app mounted in-process, authentication off."""
    with TestClient(create_app(config=config, store=store)) as test_client:
        yield test_client


def ok_probe(path: Path) -> ProbeResult:
    """A probe that reports storage as writable."""
    return ProbeResult(ok=True, resolved=str(path))


def failing_probe(path: Path) -> ProbeResult:
    """A probe that reports a root-owned mount refusing a write."""
    return ProbeResult(ok=False, resolved=str(path), errno=13, detail="Permission denied")
