"""Configuration, read from the environment only, validated fail-closed at boot.

No value is hard-coded and no value is read from a committed config file. Every
operator-supplied string is normalised before use: the operator console routinely
smuggles invisible characters into a pasted value (a trailing newline, a tab) and
quotes around a path, and a raw value has turned a save into ``mkdir "\\t"`` and left
an auth token that never matched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from enlightenment import __version__

#: Default listen port. The platform injects PORT; this is the documented fallback.
DEFAULT_PORT = 8080

#: Cap on an operator-supplied value, so a pasted document cannot become a config value.
MAX_VALUE_LENGTH = 512

#: Highest valid TCP port.
MAX_PORT = 65535

#: Shortest string that can be a quoted value (an opening and a closing quote).
MIN_QUOTED_LENGTH = 2


class ConfigError(RuntimeError):
    """Raised when configuration is invalid. The app refuses to start rather than guess."""


def clean(raw: str | None) -> str:
    """Return ``raw`` with surrounding whitespace, wrapping quotes, and control
    characters removed. An empty string means "not set".
    """
    if raw is None:
        return ""
    value = raw.strip()[:MAX_VALUE_LENGTH]
    for quote in ('"', "'"):
        if len(value) >= MIN_QUOTED_LENGTH and value.startswith(quote) and value.endswith(quote):
            value = value[1:-1]
            break
    value = "".join(ch for ch in value if ch.isprintable())
    return value.strip()


def resolve_data_dir(env: dict[str, str] | None = None) -> Path:
    """Resolve the storage directory: explicit variable, then the platform-injected
    variable, then an absolute local default.

    Read at call time rather than at import, because the file-storage add-on injects
    ``STORAGE_MOUNT_PATH`` after the process image is built; capturing it at module
    load records an empty value.
    """
    source = env if env is not None else dict(os.environ)
    for name in ("DATA_DIR", "STORAGE_MOUNT_PATH"):
        candidate = clean(source.get(name))
        if candidate:
            return Path(candidate)
    return Path.cwd() / "var" / "data"


def _validate_data_dir(path: Path) -> Path:
    """Fail closed on a storage path that cannot be honest. Writability is not asserted
    here: it is proved with a real write by the readiness probe, because an existence
    check passes on a read-only or root-owned mount and fails the first real write.
    """
    if not path.is_absolute():
        raise ConfigError(f"data directory must be an absolute path, got {path!r}")
    if path == Path(path.anchor):
        raise ConfigError("data directory must not be the filesystem root")
    return path


@dataclass(frozen=True, slots=True)
class Config:
    """Validated runtime configuration. Never logged, never returned to a client."""

    port: int
    host: str
    data_dir: Path
    team_token: str
    allowed_origin: str
    build_id: str

    @property
    def auth_required(self) -> bool:
        """True when a team token is configured, which gates every privileged route."""
        return bool(self.team_token)


def _resolve_port(raw: str) -> int:
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise ConfigError(f"PORT must be an integer, got {raw!r}") from exc
    if not 1 <= port <= MAX_PORT:
        raise ConfigError(f"PORT must be between 1 and {MAX_PORT}, got {port}")
    return port


def _resolve_host(raw: str, *, auth_required: bool) -> str:
    """Bind loopback when authentication is off, every interface when it is on.

    With no team token the app is in single-user local mode, so it must not be
    reachable off the machine. The container does not rely on this: its launch command
    binds ``0.0.0.0`` explicitly, and the platform gateway sits in front.
    """
    if raw:
        return raw
    return "0.0.0.0" if auth_required else "127.0.0.1"  # noqa: S104


def load_config(env: dict[str, str] | None = None) -> Config:
    """Build a validated :class:`Config` from the environment. Raises
    :class:`ConfigError` on anything it cannot honour.
    """
    source = env if env is not None else dict(os.environ)
    team_token = clean(source.get("ENLIGHTENMENT_TEAM_TOKEN"))
    allowed_origin = clean(source.get("ALLOWED_ORIGIN"))

    if team_token and allowed_origin == "*":
        raise ConfigError(
            "refusing to start: ALLOWED_ORIGIN is '*' with a team token set. "
            "Set ALLOWED_ORIGIN to the application's real origin."
        )

    return Config(
        port=_resolve_port(clean(source.get("PORT"))),
        host=_resolve_host(clean(source.get("HOST")), auth_required=bool(team_token)),
        data_dir=_validate_data_dir(resolve_data_dir(source)),
        team_token=team_token,
        allowed_origin=allowed_origin,
        build_id=clean(source.get("BUILD_ID")) or f"v{__version__}",
    )
