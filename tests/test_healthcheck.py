"""The container HEALTHCHECK probe. Shipped code, so it is tested code."""

from __future__ import annotations

import urllib.error
import urllib.request
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


@pytest.fixture
def recorded_url(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Capture the URL the probe builds, answering 200."""
    seen: dict[str, str] = {}

    def record(url: str, *_args: Any, **_kwargs: Any) -> FakeResponse:
        seen["url"] = url
        return FakeResponse(200)

    monkeypatch.setattr(urllib.request, "urlopen", record)
    return seen


# --- the probed path ------------------------------------------------------------------


def test_the_probe_targets_the_liveness_path_not_readiness(recorded_url: dict[str, str]) -> None:
    """A Docker HEALTHCHECK is a liveness signal, and anything acting on it restarts the
    container. Probing readiness would restart the pod on a storage fault, which is the
    coupling the split paths exist to prevent.
    """
    healthcheck.check("8080")
    assert recorded_url["url"].endswith("/livez")
    assert "/healthz" not in recorded_url["url"]


# --- status handling ------------------------------------------------------------------


def test_a_200_liveness_response_is_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: FakeResponse(200))
    assert healthcheck.check("8080") == healthcheck.HEALTHY


@pytest.mark.parametrize("status", [500, 503, 404, 301])
def test_any_non_200_liveness_response_is_unhealthy(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: FakeResponse(status))
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


# --- the port is untrusted ------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        "8080@evil.example",
        "8080/../../x",
        "8080 evil.example",
        "evil.example",
        "-1",
        "0",
        "65536",
        "8080;rm -rf /",
        "0x1f90",
    ],
)
def test_a_hostile_port_is_refused_rather_than_interpolated(hostile: str) -> None:
    """`PORT=8080@evil.example` makes urlsplit read `127.0.0.1:8080` as USERINFO and
    resolve `evil.example` as the host, so a raw interpolation would have this control
    probe an attacker-controlled server and report HEALTHY. It is also an egress channel
    out of the container.
    """
    assert healthcheck.resolve_port(hostile) is None
    assert healthcheck.check(hostile) == healthcheck.UNHEALTHY


def test_a_hostile_port_never_reaches_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def must_not_run(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the probe built a URL from an unvalidated port")

    monkeypatch.setattr(urllib.request, "urlopen", must_not_run)
    assert healthcheck.check("8080@evil.example") == healthcheck.UNHEALTHY


@pytest.mark.parametrize(("raw", "expected"), [("8080", 8080), ("1", 1), ("65535", 65535)])
def test_a_valid_port_is_accepted(raw: str, expected: int) -> None:
    assert healthcheck.resolve_port(raw) == expected


@pytest.mark.parametrize("padded", ["8080\n", " 8080 ", "8080\t", "\t8080"])
def test_a_port_padded_by_the_operator_console_is_normalised_not_refused(padded: str) -> None:
    """A trailing newline or tab smuggled in by a pasted console value is the artefact this
    project strips everywhere else. Rejecting it would be a self-inflicted outage.
    """
    assert healthcheck.resolve_port(padded) == 8080


def test_an_absent_port_falls_back_to_the_documented_default() -> None:
    assert healthcheck.resolve_port(None) == healthcheck.DEFAULT_PORT
    assert healthcheck.resolve_port("") == healthcheck.DEFAULT_PORT


def test_the_probe_reads_the_injected_port(
    monkeypatch: pytest.MonkeyPatch, recorded_url: dict[str, str]
) -> None:
    monkeypatch.setenv("PORT", "9310")
    assert healthcheck.check() == healthcheck.HEALTHY
    assert recorded_url["url"] == "http://127.0.0.1:9310/livez"


def test_the_probe_defaults_to_8080_when_no_port_is_injected(
    monkeypatch: pytest.MonkeyPatch, recorded_url: dict[str, str]
) -> None:
    monkeypatch.delenv("PORT", raising=False)
    healthcheck.check()
    assert recorded_url["url"] == "http://127.0.0.1:8080/livez"


def test_the_timeout_is_shorter_than_a_platform_probe_window() -> None:
    """A probe that can hang converts an infrastructure fault into a silent liveness kill."""
    assert 0 < healthcheck.TIMEOUT_SECONDS < 10
