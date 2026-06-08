"""Runtime configuration for Okto Nexus.

Configuration is resolved with strict precedence: ``CLI > env > default``.
All environment variables live under the ``OKTO_NEXUS_*`` namespace. Invalid
values raise :class:`OktoNexusError` with code ``CONFIG_ERROR`` so that the
fail-closed bootstrap aborts cleanly.

This module depends only on the stdlib and :mod:`okto_nexus.errors`; it does
NOT import the MCP SDK or ``sqlite3``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .errors import ErrorCode, OktoNexusError

#: Inclusive upper bound (bytes, UTF-8) for inline content storage.
DEFAULT_MAX_INLINE_BYTES = 65536


@dataclass
class NexusConfig:
    """Resolved server configuration.

    Paths are normalised (``~`` expanded) in :meth:`__post_init__`. ``db_path``
    defaults to ``{home_dir}/nexus.db`` when not explicitly provided.
    """

    home_dir: Path = field(default_factory=lambda: Path.home() / ".okto_nexus")
    db_path: Path | None = None
    busy_timeout_ms: int = 5000
    poll_interval_ms: int = 200
    max_wait_timeout_seconds: int = 30
    handoff_lease_ttl_seconds: int = 300
    max_inline_bytes: int = DEFAULT_MAX_INLINE_BYTES

    def __post_init__(self) -> None:
        self.home_dir = Path(self.home_dir).expanduser()
        if self.db_path is None:
            self.db_path = self.home_dir / "nexus.db"
        else:
            self.db_path = Path(self.db_path).expanduser()


# Mapping: NexusConfig field -> (env var name, CLI flag).
# ``home_dir``/``db_path`` are strings; the rest are positive integers.
# All environment variables live under the ``OKTO_NEXUS_*`` namespace.
_PATH_FIELDS: dict[str, tuple[str, str]] = {
    "home_dir": ("OKTO_NEXUS_HOME", "--home"),
    "db_path": ("OKTO_NEXUS_DB_PATH", "--db-path"),
}

_INT_FIELDS: dict[str, tuple[str, str, int, int]] = {
    # field: (env var, CLI flag, default, minimum allowed)
    "busy_timeout_ms": ("OKTO_NEXUS_BUSY_TIMEOUT_MS", "--busy-timeout-ms", 5000, 0),
    "poll_interval_ms": ("OKTO_NEXUS_POLL_INTERVAL_MS", "--poll-interval-ms", 200, 1),
    "max_wait_timeout_seconds": (
        "OKTO_NEXUS_MAX_WAIT_TIMEOUT_SECONDS",
        "--max-wait-timeout-seconds",
        30,
        0,
    ),
    "handoff_lease_ttl_seconds": (
        "OKTO_NEXUS_HANDOFF_LEASE_TTL_SECONDS",
        "--handoff-lease-ttl-seconds",
        300,
        1,
    ),
    "max_inline_bytes": (
        "OKTO_NEXUS_MAX_INLINE_BYTES",
        "--max-inline-bytes",
        DEFAULT_MAX_INLINE_BYTES,
        1,
    ),
}


def _parse_cli(argv: list[str]) -> dict[str, str]:
    """Parse a flat ``--flag value`` / ``--flag=value`` argv into a flag->value map.

    Unknown flags raise ``CONFIG_ERROR`` so typos fail closed rather than being
    silently ignored.
    """
    known_flags = {flag for _, flag in _PATH_FIELDS.values()}
    known_flags |= {flag for _, flag, _, _ in _INT_FIELDS.values()}

    parsed: dict[str, str] = {}
    i = 0
    n = len(argv)
    while i < n:
        token = argv[i]
        if not token.startswith("--"):
            raise OktoNexusError(
                ErrorCode.CONFIG_ERROR,
                f"Unexpected positional argument: {token!r}",
                {"argument": token},
            )
        if "=" in token:
            flag, value = token.split("=", 1)
        else:
            flag = token
            if i + 1 >= n:
                raise OktoNexusError(
                    ErrorCode.CONFIG_ERROR,
                    f"Missing value for flag {flag!r}",
                    {"flag": flag},
                )
            value = argv[i + 1]
            i += 1
        if flag not in known_flags:
            raise OktoNexusError(
                ErrorCode.CONFIG_ERROR,
                f"Unknown configuration flag: {flag!r}",
                {"flag": flag},
            )
        parsed[flag] = value
        i += 1
    return parsed


def _resolve_int(
    field_name: str,
    flag: str,
    env_var: str,
    default: int,
    minimum: int,
    env: Mapping[str, str],
    cli: Mapping[str, str],
) -> int:
    """Resolve a single positive-integer field with CLI > env > default precedence."""
    raw: Any
    source: str
    if flag in cli:
        raw, source = cli[flag], flag
    elif env_var in env:
        raw, source = env[env_var], env_var
    else:
        return default

    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            f"Invalid integer for {field_name}: {raw!r}",
            {"field": field_name, "source": source, "value": raw},
        ) from None
    if value < minimum:
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            f"Value for {field_name} must be >= {minimum}, got {value}",
            {"field": field_name, "source": source, "value": value, "minimum": minimum},
        )
    return value


def _resolve_str(
    flag: str,
    env_var: str,
    env: Mapping[str, str],
    cli: Mapping[str, str],
) -> str | None:
    """Resolve a single optional string field with CLI > env > default precedence."""
    if flag in cli:
        return cli[flag]
    if env_var in env:
        return env[env_var]
    return None


def load_config(env: Mapping[str, str], argv: list[str] | None = None) -> NexusConfig:
    """Build a :class:`NexusConfig` from environment + CLI overrides.

    Parameters
    ----------
    env:
        Mapping of environment variables (e.g. ``os.environ``).
    argv:
        Optional list of CLI tokens (e.g. ``sys.argv[1:]``).

    Raises
    ------
    OktoNexusError
        With code ``CONFIG_ERROR`` for unknown flags or invalid values.
    """
    cli = _parse_cli(list(argv) if argv is not None else [])

    home_env, home_flag = _PATH_FIELDS["home_dir"]
    db_env, db_flag = _PATH_FIELDS["db_path"]
    home_override = _resolve_str(home_flag, home_env, env=env, cli=cli)
    db_override = _resolve_str(db_flag, db_env, env=env, cli=cli)

    kwargs: dict[str, Any] = {}
    if home_override is not None:
        kwargs["home_dir"] = Path(home_override)
    if db_override is not None:
        kwargs["db_path"] = Path(db_override)

    for field_name, (env_var, flag, default, minimum) in _INT_FIELDS.items():
        kwargs[field_name] = _resolve_int(
            field_name, flag, env_var, default, minimum, env, cli
        )

    return NexusConfig(**kwargs)
