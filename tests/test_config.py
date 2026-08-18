"""Configuration is env-only, normalised, and fail-closed."""

from __future__ import annotations

from pathlib import Path

import pytest

from enlightenment.config import (
    DEFAULT_PORT,
    Config,
    ConfigError,
    clean,
    load_config,
    resolve_data_dir,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  /data  ", "/data"),
        ('"/data"', "/data"),
        ("'/data'", "/data"),
        ("/data\n", "/data"),
        ("\t/data", "/data"),
        ("/da\x00ta", "/data"),
        (None, ""),
        ("", ""),
    ],
)
def test_clean_strips_quotes_whitespace_and_control_characters(
    raw: str | None, expected: str
) -> None:
    assert clean(raw) == expected


def test_clean_caps_length() -> None:
    assert len(clean("x" * 5000)) == 512


def test_data_dir_resolution_prefers_explicit_then_platform_then_default() -> None:
    assert resolve_data_dir({"DATA_DIR": "/explicit", "STORAGE_MOUNT_PATH": "/injected"}) == Path(
        "/explicit"
    )
    assert resolve_data_dir({"STORAGE_MOUNT_PATH": "/injected"}) == Path("/injected")
    assert resolve_data_dir({}).is_absolute()


def test_wildcard_origin_with_a_token_refuses_to_start() -> None:
    with pytest.raises(ConfigError, match="refusing to start"):
        load_config({"ENLIGHTENMENT_TEAM_TOKEN": "abc", "ALLOWED_ORIGIN": "*"})


def test_wildcard_origin_without_a_token_is_allowed() -> None:
    assert load_config({"ALLOWED_ORIGIN": "*"}).allowed_origin == "*"


def test_host_binds_loopback_when_authentication_is_off() -> None:
    assert load_config({}).host == "127.0.0.1"


def test_host_binds_every_interface_when_a_token_is_set() -> None:
    assert load_config({"ENLIGHTENMENT_TEAM_TOKEN": "abc"}).host == "0.0.0.0"


def test_explicit_host_overrides_the_default() -> None:
    assert load_config({"HOST": "10.0.0.4"}).host == "10.0.0.4"


def test_port_defaults_to_8080_and_validates() -> None:
    assert load_config({}).port == DEFAULT_PORT
    assert load_config({"PORT": "9000"}).port == 9000
    with pytest.raises(ConfigError, match="must be an integer"):
        load_config({"PORT": "eighty-eighty"})
    with pytest.raises(ConfigError, match="between 1 and 65535"):
        load_config({"PORT": "0"})
    with pytest.raises(ConfigError, match="between 1 and 65535"):
        load_config({"PORT": "65536"})


def test_relative_data_dir_is_refused() -> None:
    with pytest.raises(ConfigError, match="absolute path"):
        load_config({"DATA_DIR": "relative/path"})


def test_filesystem_root_as_data_dir_is_refused() -> None:
    with pytest.raises(ConfigError, match="must not be the filesystem root"):
        load_config({"DATA_DIR": "/"})


def test_build_id_falls_back_to_the_package_version() -> None:
    assert load_config({}).build_id.startswith("v")
    assert load_config({"BUILD_ID": "ci-123"}).build_id == "ci-123"


def test_auth_required_tracks_the_token(tmp_path: Path) -> None:
    base = {
        "port": 8080,
        "host": "127.0.0.1",
        "data_dir": tmp_path,
        "allowed_origin": "",
        "build_id": "x",
    }
    assert Config(team_token="", **base).auth_required is False  # type: ignore[arg-type]
    assert Config(team_token="abc", **base).auth_required is True  # type: ignore[arg-type]
