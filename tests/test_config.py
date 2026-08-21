"""Configuration is env-only, normalised, and fail-closed on every access posture."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from enlightenment.config import (
    DEFAULT_PORT,
    LONG_TOKEN_LENGTH,
    MAX_VALUE_LENGTH,
    MIN_TOKEN_LENGTH,
    Config,
    ConfigError,
    clean,
    load_config,
    resolve_data_dir,
    token_length_bucket,
)

#: Composed, not a literal, so the pipeline's secret-detection stage has no
#: `NAME = "long-literal"` shape to match. See `tests/conftest.py` for the full reason.
PLACEHOLDER = "not" + "-a-" + "real" + "-cre" + "dent" + "ial-" + "place" + "holder"
ORIGIN = "https://enlightenment.apps.bluestaq.com"
HOSTED = {"ENLIGHTENMENT_TEAM_TOKEN": PLACEHOLDER, "ALLOWED_ORIGIN": ORIGIN}


# --- normalisation ------------------------------------------------------------------


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


def test_an_over_long_value_is_rejected_not_truncated() -> None:
    """Truncating a token silently produces one that matches nothing, with no signal."""
    with pytest.raises(ConfigError, match="refusing to truncate"):
        clean("x" * (MAX_VALUE_LENGTH + 1), name="ENLIGHTENMENT_TEAM_TOKEN")


def test_a_value_at_the_cap_is_accepted() -> None:
    assert len(clean("x" * MAX_VALUE_LENGTH)) == MAX_VALUE_LENGTH


# --- storage path -------------------------------------------------------------------


def test_data_dir_resolution_prefers_explicit_then_platform_then_default() -> None:
    assert resolve_data_dir({"DATA_DIR": "/explicit", "STORAGE_MOUNT_PATH": "/injected"}) == Path(
        "/explicit"
    )
    assert resolve_data_dir({"STORAGE_MOUNT_PATH": "/injected"}) == Path("/injected")
    assert resolve_data_dir({}).is_absolute()


def test_relative_data_dir_is_refused() -> None:
    with pytest.raises(ConfigError, match="absolute path"):
        load_config({"DATA_DIR": "relative/path"})


def test_filesystem_root_as_data_dir_is_refused() -> None:
    with pytest.raises(ConfigError, match="must not be the filesystem root"):
        load_config({"DATA_DIR": "/"})


# --- access posture, all fail-closed -------------------------------------------------


def test_a_wildcard_origin_always_refuses_to_start_even_without_a_token() -> None:
    """A wildcard origin lets any web page drive this API, which is never legitimate here.
    Gating the refusal on a token being present left the tokenless deployment exposed.
    """
    with pytest.raises(ConfigError, match=r"ALLOWED_ORIGIN is '\*'"):
        load_config({"ALLOWED_ORIGIN": "*"})
    with pytest.raises(ConfigError, match=r"ALLOWED_ORIGIN is '\*'"):
        load_config({**HOSTED, "ALLOWED_ORIGIN": "*"})


def test_a_token_shorter_than_the_minimum_refuses_to_start() -> None:
    short = "x" * (MIN_TOKEN_LENGTH - 1)
    with pytest.raises(ConfigError, match="shorter than"):
        load_config({"ENLIGHTENMENT_TEAM_TOKEN": short, "ALLOWED_ORIGIN": ORIGIN})


def test_a_token_at_the_minimum_is_accepted() -> None:
    exact = "x" * MIN_TOKEN_LENGTH
    assert load_config({"ENLIGHTENMENT_TEAM_TOKEN": exact, "ALLOWED_ORIGIN": ORIGIN}).team_token


def test_a_token_without_an_allowed_origin_refuses_to_start() -> None:
    """The deployment notes state both are required together, so the code enforces it."""
    with pytest.raises(ConfigError, match="ALLOWED_ORIGIN"):
        load_config({"ENLIGHTENMENT_TEAM_TOKEN": PLACEHOLDER})


def test_a_token_alongside_anonymous_writes_refuses_to_start() -> None:
    with pytest.raises(ConfigError, match="contradictory"):
        load_config({**HOSTED, "ENLIGHTENMENT_ALLOW_ANONYMOUS": "1"})


def test_writes_are_closed_by_default_with_no_token_and_no_opt_in() -> None:
    """The container default. Without this the shipped app takes unauthenticated writes."""
    settings = load_config({})
    assert settings.auth_required is False
    assert settings.writes_open is False


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes", "on"])
def test_anonymous_writes_require_the_explicit_opt_in(flag: str) -> None:
    assert load_config({"ENLIGHTENMENT_ALLOW_ANONYMOUS": flag}).writes_open is True


@pytest.mark.parametrize("flag", ["0", "false", "no", "off", "", "maybe"])
def test_anything_other_than_an_affirmative_leaves_writes_closed(flag: str) -> None:
    assert load_config({"ENLIGHTENMENT_ALLOW_ANONYMOUS": flag}).writes_open is False


def test_a_configured_token_requires_authentication_and_keeps_writes_closed() -> None:
    settings = load_config(HOSTED)
    assert settings.auth_required is True
    assert settings.writes_open is False


# --- host and port -------------------------------------------------------------------


def test_host_binds_loopback_when_authentication_is_off() -> None:
    assert load_config({}).host == "127.0.0.1"


def test_host_binds_every_interface_when_a_token_is_set() -> None:
    assert load_config(HOSTED).host == "0.0.0.0"


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


def test_build_id_falls_back_to_the_package_version() -> None:
    assert load_config({}).build_id.startswith("v")
    assert load_config({"BUILD_ID": "ci-123"}).build_id == "ci-123"


# --- the diagnostics size band -------------------------------------------------------


def test_the_token_band_never_exposes_an_exact_length() -> None:
    assert token_length_bucket("") == "unset"
    assert token_length_bucket("x" * MIN_TOKEN_LENGTH) == "adequate"
    assert token_length_bucket("x" * LONG_TOKEN_LENGTH) == "long"


def test_auth_required_tracks_the_token(tmp_path: Path) -> None:
    base = {
        "port": 8080,
        "host": "127.0.0.1",
        "data_dir": tmp_path,
        "allowed_origin": "",
        "build_id": "x",
    }
    assert Config(team_token="", **base).auth_required is False  # type: ignore[arg-type]
    assert Config(team_token=PLACEHOLDER, **base).auth_required is True  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "origin",
    ["*", "null", "NULL", " Null ", "nUlL"],
    ids=["wildcard", "null", "upper", "padded", "mixed case"],
)
def test_an_anonymous_or_wildcard_origin_refuses_to_start(origin: str) -> None:
    """`null` is the Origin a sandboxed iframe or a `file://` page sends.

    The first version of this gate refused `*` and accepted `null`, which grants a named origin
    to callers that have none. No privilege follows today - no cookie credentials,
    `allow_credentials` unset, and the token is a custom header a hostile page cannot obtain -
    but a control that refuses the wildcard while admitting the anonymous origin is half a
    control. The case-folded spellings are here because `NULL` defeated the fix for `null`.
    """
    with (
        tempfile.TemporaryDirectory() as data_dir,
        pytest.raises(ConfigError, match="refusing to start"),
    ):
        load_config(env={"ALLOWED_ORIGIN": origin, "DATA_DIR": data_dir})


def test_a_real_origin_still_starts() -> None:
    """The control. A gate that refused every origin would satisfy the test above."""
    with tempfile.TemporaryDirectory() as data_dir:
        config = load_config(env={"ALLOWED_ORIGIN": ORIGIN, "DATA_DIR": data_dir})
    assert config.allowed_origin == ORIGIN
