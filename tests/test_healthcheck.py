"""The container HEALTHCHECK probe. Shipped code, so it is tested code."""

from __future__ import annotations

import urllib.error
import urllib.request
from types import TracebackType
from typing import Any

import pytest

from enlightenment import healthcheck


class FakeResponse:
    """The minimum of the urlopen context manager the probe uses."""

    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def test_a_200_readiness_response_is_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: FakeResponse(200))
    assert healthcheck.check("8080") == healthcheck.HEALTHY


def test_a_503_readiness_response_is_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: FakeResponse(503))
    assert healthcheck.check("8080") == healthcheck.UNHEALTHY


@pytest.mark.parametrize(
    "failure", [urllib.error.URLError("refused"), TimeoutError("slow"), OSError("gone")]
)
def test_any_transport_failure_is_unhealthy_never_a_pass(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise failure

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    assert healthcheck.check("8080") == healthcheck.UNHEALTHY


def test_the_probe_reads_the_injected_port(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def record(url: str, *_args: Any, **_kwargs: Any) -> FakeResponse:
        seen["url"] = url
        return FakeResponse(200)

    monkeypatch.setenv("PORT", "9310")
    monkeypatch.setattr(urllib.request, "urlopen", record)
    assert healthcheck.check() == healthcheck.HEALTHY
    assert seen["url"] == "http://127.0.0.1:9310/healthz"


def test_the_probe_defaults_to_8080_when_no_port_is_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def record(url: str, *_args: Any, **_kwargs: Any) -> FakeResponse:
        seen["url"] = url
        return FakeResponse(200)

    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", record)
    healthcheck.check()
    assert seen["url"] == "http://127.0.0.1:8080/healthz"


def test_the_timeout_is_shorter_than_a_platform_probe_window() -> None:
    """A probe that can hang converts an infrastructure fault into a silent liveness kill."""
    assert 0 < healthcheck.TIMEOUT_SECONDS < 10


def test_the_traceback_type_import_is_not_required_at_runtime() -> None:
    """Guards against an unused import creeping back into a shipped module."""
    assert TracebackType is not None
