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

#: Highest valid TCP port.
MAX_PORT = 65535

#: Cap on an operator-supplied value. Over the cap is REJECTED, never truncated: a
#: silently shortened token authenticates against nothing and gives no signal.
MAX_VALUE_LENGTH = 512

#: Shortest string that can be a quoted value (an opening and a closing quote).
MIN_QUOTED_LENGTH = 2

#: Shortest team token the app will start with. Enforced so the unauthenticated
#: diagnostics read-out never needs to publish an exact length to be useful.
MIN_TOKEN_LENGTH = 24

#: Length above which a token is reported as "long" rather than "adequate".
LONG_TOKEN_LENGTH = 64

#: Values that turn the explicit local anonymous-write mode on.
TRUTHY = frozenset({"1", "true", "yes", "on"})

#: Origins that are refused outright rather than configured.
#:
#: ``*`` is the obvious one. ``null`` is the one that was missed: it is the literal Origin a
#: sandboxed iframe or a ``file://`` page sends, so allowing it grants a named origin to callers
#: that have none. No privilege follows here today - no cookie credentials, `allow_credentials`
#: unset, and the token is a custom header a hostile page cannot obtain - but a control that
#: refuses the wildcard while accepting the anonymous origin is only half a control.
REFUSED_ORIGINS = frozenset({"*", "null"})


class ConfigError(RuntimeError):
    """Raised when configuration is invalid. The app refuses to start rather than guess."""


def clean(raw: str | None, *, name: str = "value") -> str:
    """Return ``raw`` with surrounding whitespace, wrapping quotes, and control
    characters removed. An empty string means "not set".

    Rejects a value over :data:`MAX_VALUE_LENGTH` rather than truncating it. Truncation
    turns a too-long token into a token that matches nothing, with no error and no way
    for the operator to see why authentication fails.
    """
    if raw is None:
        return ""
    if len(raw) > MAX_VALUE_LENGTH:
        raise ConfigError(
            f"{name} is longer than {MAX_VALUE_LENGTH} characters; refusing to truncate it"
        )
    value = raw.strip()
    for quote in ('"', "'"):
        if len(value) >= MIN_QUOTED_LENGTH and value.startswith(quote) and value.endswith(quote):
            value = value[1:-1]
            break
    value = "".join(ch for ch in value if ch.isprintable())
    return value.strip()


def token_length_bucket(token: str) -> str:
    """Coarse size band for the unauthenticated diagnostics read-out.

    The read-out must let an operator tell a stale value from a correct one without
    telling an unauthenticated caller exactly how many characters to attack, so the
    length is reported as a band rather than a number. A token below
    :data:`MIN_TOKEN_LENGTH` cannot occur here: the app refuses to start on one.
    """
    if not token:
        return "unset"
    return "long" if len(token) >= LONG_TOKEN_LENGTH else "adequate"


def resolve_data_dir(env: dict[str, str] | None = None) -> Path:
    """Resolve the storage directory: explicit variable, then the platform-injected
    variable, then an absolute local default.

    Read at call time rather than at import, because the file-storage add-on injects
    ``STORAGE_MOUNT_PATH`` after the process image is built; capturing it at module
    load records an empty value.
    """
    source = env if env is not None else dict(os.environ)
    for name in ("DATA_DIR", "STORAGE_MOUNT_PATH"):
        candidate = clean(source.get(name), name=name)
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
    allow_anonymous_writes: bool = False

    @property
    def auth_required(self) -> bool:
        """True when a team token is configured, which gates every privileged route."""
        return bool(self.team_token)

    @property
    def writes_open(self) -> bool:
        """True only in explicitly opted-in local anonymous mode.

        Without a token AND without the explicit opt-in, write routes return 401. An
        absent token is the container default, so treating it as "open" would put an
        unauthenticated write endpoint on a public ingress by omission.
        """
        return not self.auth_required and self.allow_anonymous_writes


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

    Only the local runner reads this. The container binds ``0.0.0.0`` from its launch
    command, which is why loopback binding is NOT relied on as an access control: the
    write routes fail closed on their own (see :meth:`Config.writes_open`).
    """
    if raw:
        return raw
    return "0.0.0.0" if auth_required else "127.0.0.1"  # noqa: S104


def _validate_access(*, team_token: str, allowed_origin: str, allow_anonymous: bool) -> None:
    """Fail closed on any access posture that cannot be justified."""
    # Case-folded, because `NULL` slipped past the first version of this check. The literal a
    # browser sends is lowercase, so an uppercase spelling is a configuration mistake rather than
    # an attack - but a refusal a one-word change defeats is not a refusal.
    if allowed_origin.strip().casefold() in REFUSED_ORIGINS:
        raise ConfigError(
            f"refusing to start: ALLOWED_ORIGIN is {allowed_origin!r}. A wildcard origin lets "
            "any web page drive this API, and 'null' is the Origin a sandboxed iframe or a "
            "file:// page sends, so allowing it names no real caller. Set it to the "
            "application's real origin, or leave it unset to emit no cross-origin header at all."
        )
    if team_token and len(team_token) < MIN_TOKEN_LENGTH:
        raise ConfigError(
            f"refusing to start: ENLIGHTENMENT_TEAM_TOKEN is shorter than "
            f"{MIN_TOKEN_LENGTH} characters."
        )
    if team_token and not allowed_origin:
        raise ConfigError(
            "refusing to start: ENLIGHTENMENT_TEAM_TOKEN is set but ALLOWED_ORIGIN is "
            "not. A hosted deployment needs both; set ALLOWED_ORIGIN to the "
            "application's real origin."
        )
    if team_token and allow_anonymous:
        raise ConfigError(
            "refusing to start: ENLIGHTENMENT_ALLOW_ANONYMOUS is set alongside a team "
            "token. Anonymous writes and a token are contradictory; unset one."
        )


def load_config(env: dict[str, str] | None = None) -> Config:
    """Build a validated :class:`Config` from the environment. Raises
    :class:`ConfigError` on anything it cannot honour.
    """
    source = env if env is not None else dict(os.environ)
    team_token = clean(source.get("ENLIGHTENMENT_TEAM_TOKEN"), name="ENLIGHTENMENT_TEAM_TOKEN")
    allowed_origin = clean(source.get("ALLOWED_ORIGIN"), name="ALLOWED_ORIGIN")
    allow_anonymous = (
        clean(
            source.get("ENLIGHTENMENT_ALLOW_ANONYMOUS"), name="ENLIGHTENMENT_ALLOW_ANONYMOUS"
        ).lower()
        in TRUTHY
    )

    _validate_access(
        team_token=team_token, allowed_origin=allowed_origin, allow_anonymous=allow_anonymous
    )

    return Config(
        port=_resolve_port(clean(source.get("PORT"), name="PORT")),
        host=_resolve_host(clean(source.get("HOST"), name="HOST"), auth_required=bool(team_token)),
        data_dir=_validate_data_dir(resolve_data_dir(source)),
        team_token=team_token,
        allowed_origin=allowed_origin,
        build_id=clean(source.get("BUILD_ID"), name="BUILD_ID") or f"v{__version__}",
        allow_anonymous_writes=allow_anonymous,
    )
