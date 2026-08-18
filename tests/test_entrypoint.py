"""The local listener reads the port from the environment and binds the resolved host."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import enlightenment.__main__ as entrypoint


def test_main_binds_the_resolved_host_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(app: object, **kwargs: Any) -> None:
        captured.update(kwargs)
        captured["app"] = app

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PORT", "9101")
    monkeypatch.delenv("ENLIGHTENMENT_TEAM_TOKEN", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.setattr(entrypoint.uvicorn, "run", fake_run)

    entrypoint.main()

    assert captured["port"] == 9101
    assert captured["host"] == "127.0.0.1"
    assert captured["app"] is not None
