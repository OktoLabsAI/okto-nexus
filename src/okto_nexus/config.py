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

#: Default in-flight lease TTL (seconds) for pulled inbox deliveries.
DEFAULT_INBOX_LEASE_TTL_SECONDS = 300

#: Default TTL (seconds) after which a non-heartbeating session reads ``stale``.
DEFAULT_SESSION_STALE_TTL_SECONDS = 60

#: Default presence window (seconds): a session counts as PRESENT (and thus in
#: the broadcast audience) only while its last heartbeat is within this TTL.
#: Deliberately generous (30 min) so an alive-but-busy agent is not silently
#: dropped from broadcasts; exclusion is always surfaced explicitly to the
#: sender via ``excluded_stale``.
DEFAULT_PRESENCE_TTL_SECONDS = 1800

#: Default reap threshold (seconds): sessions whose heartbeat is older than
#: this are opportunistically closed (status ``closed``, reason ``stale``) by
#: ``session_open``/``session_heartbeat`` - dead sessions that never called
#: ``session_close`` stop accumulating state forever.
DEFAULT_SESSION_REAP_SECONDS = 86400

#: Default ceiling for ``shared_md_render``'s ``limit_events``.
DEFAULT_MAX_SHARED_MD_EVENTS = 1000

#: Default ceiling for a single ``event_get``/``event_wait`` page.
DEFAULT_MAX_EVENT_LIMIT = 1000

#: Default TTL (seconds) for ephemeral poll tokens used by remote monitors.
DEFAULT_POLL_TOKEN_TTL_SECONDS = 3600

# --------------------------------------------------------------------------- #
# Anonymous usage metrics (Pulse-derived pattern). This is opt-in and keeps the
# Nexus runtime portable: the application layer owns the bounded contract while
# concrete filesystem/HTTP/AWS concerns live in outbound adapters / IaC.
# --------------------------------------------------------------------------- #
METRICS_MODE_DISABLED = "disabled"
METRICS_MODE_LOCAL_ONLY = "local_only"
METRICS_MODE_ANONYMOUS_BEACON = "anonymous_beacon"
METRICS_MODES: tuple[str, ...] = (
    METRICS_MODE_DISABLED,
    METRICS_MODE_LOCAL_ONLY,
    METRICS_MODE_ANONYMOUS_BEACON,
)
DEFAULT_METRICS_BEACON_URL = "https://nexus-metrics.oktolabs.ai"
DEFAULT_METRICS_RETENTION_DAYS = 30
DEFAULT_METRICS_PUBLISH_INTERVAL_SECONDS = 3600

#: Trust modes for sensitive verbs (M10). ``open`` keeps the cooperative
#: behaviour (credentials optional, but VALIDATED when supplied - a wrong
#: credential is never ignored); ``strict`` requires session_id+session_secret
#: on message_create, handoff claim/complete/verify/reject/cancel,
#: inbox pull/ack/extend, and memory_put when that tool is published. Poll-token
#: issue/renew/revoke always require the pair in both modes.
TRUST_MODE_OPEN = "open"
TRUST_MODE_STRICT = "strict"
TRUST_MODES: tuple[str, ...] = (TRUST_MODE_OPEN, TRUST_MODE_STRICT)

# --------------------------------------------------------------------------- #
# Retention (M7): how long prune-eligible rows are kept before
# ``RetentionService.prune`` may delete them. Events, ``read`` deliveries and
# ``closed`` sessions follow their lane windows. Messages are the deliberate
# pure-age exception and may be removed in any delivery lane together with
# their deliveries/embeddings. Handoffs and non-message live rows are excluded.
# --------------------------------------------------------------------------- #
#: Default retention window (days) for the append-only event log.
DEFAULT_RETENTION_EVENTS_KEEP_DAYS = 30

#: Default retention window (days) for acknowledged (``read``) deliveries.
#: ``unread``/``delivered``/``parked`` lanes are NEVER pruned, regardless of age.
DEFAULT_RETENTION_READ_DELIVERIES_KEEP_DAYS = 14

#: Default retention window (days) for ``closed`` sessions. ``active``/``stale``
#: sessions are NEVER pruned, regardless of age.
DEFAULT_RETENTION_CLOSED_SESSIONS_KEEP_DAYS = 7

#: Default retention window (days) for MESSAGES (spec D-EMB-6). Messages expire
#: by PURE AGE (``created_at``), independent of delivery status - deliberately
#: breaking the "Nexus never deletes an undelivered message" invariant the
#: owner chose to relax. The reaper is opportunistic (runs only under
#: ``auto_prune_on_start`` / ``admin prune``), so this window only ever applies
#: when a prune is actually invoked. HARD minimum 7 (fail-closed): a value < 7
#: is rejected at startup so a typo can never purge the bus aggressively.
DEFAULT_RETENTION_MESSAGES_KEEP_DAYS = 30

#: Minimum accepted ``retention_messages_keep_days`` (owner directive). Enforced
#: both at config parse (CONFIG_ERROR) and on any per-call override.
MIN_RETENTION_MESSAGES_KEEP_DAYS = 7

# --------------------------------------------------------------------------- #
# Semantic search over message content (spec: Frente 3 - embeddings). The
# embedding provider is selected by this closed-vocabulary knob, parsed
# fail-closed like every other enum field:
#   * ``off``   (default) - no embedding is generated and /messages/search
#     answers EMBEDDINGS_UNAVAILABLE. The bus ships embeddings-free.
#   * ``stub``  - deterministic zero-dependency provider (SHA256 -> 384 floats);
#     generation AND search both work (the CI / test mode).
#   * ``local`` - sentence-transformers/all-MiniLM-L6-v2 under the optional
#     ``okto-nexus[embeddings]`` extra. With the extra installed, generation and
#     search use the real model; WITHOUT it, generation degrades to the stub
#     (best-effort, never blocks a send) and search answers
#     EMBEDDINGS_UNAVAILABLE (the operator asked for a real model that is absent).
# --------------------------------------------------------------------------- #
EMBEDDING_MODE_OFF = "off"
EMBEDDING_MODE_STUB = "stub"
EMBEDDING_MODE_LOCAL = "local"
EMBEDDING_MODES: tuple[str, ...] = (
    EMBEDDING_MODE_OFF,
    EMBEDDING_MODE_STUB,
    EMBEDDING_MODE_LOCAL,
)


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
    inbox_lease_ttl_seconds: int = DEFAULT_INBOX_LEASE_TTL_SECONDS
    session_stale_ttl_seconds: int = DEFAULT_SESSION_STALE_TTL_SECONDS
    presence_ttl_seconds: int = DEFAULT_PRESENCE_TTL_SECONDS
    session_reap_seconds: int = DEFAULT_SESSION_REAP_SECONDS
    max_shared_md_events: int = DEFAULT_MAX_SHARED_MD_EVENTS
    max_event_limit: int = DEFAULT_MAX_EVENT_LIMIT
    poll_token_ttl_seconds: int = DEFAULT_POLL_TOKEN_TTL_SECONDS
    metrics_mode: str = METRICS_MODE_DISABLED
    metrics_dir: Path | None = None
    metrics_beacon_url: str = DEFAULT_METRICS_BEACON_URL
    metrics_retention_days: int = DEFAULT_METRICS_RETENTION_DAYS
    metrics_publish_interval_seconds: int = DEFAULT_METRICS_PUBLISH_INTERVAL_SECONDS
    trust_mode: str = TRUST_MODE_OPEN
    retention_events_keep_days: int = DEFAULT_RETENTION_EVENTS_KEEP_DAYS
    retention_read_deliveries_keep_days: int = (
        DEFAULT_RETENTION_READ_DELIVERIES_KEEP_DAYS
    )
    retention_closed_sessions_keep_days: int = (
        DEFAULT_RETENTION_CLOSED_SESSIONS_KEEP_DAYS
    )
    retention_messages_keep_days: int = DEFAULT_RETENTION_MESSAGES_KEEP_DAYS
    embedding_mode: str = EMBEDDING_MODE_OFF
    auto_prune_on_start: bool = False
    # Deliver a read receipt to the SENDER's inbox when a recipient
    # acknowledges its message (opt-out; live-tunable - no restart).
    inbox_read_receipts: bool = True
    # Expose each workspace's root_realpath on the OPERATOR surfaces
    # (GET /api/v1/workspaces + dashboard). Default OFF (defense-in-depth):
    # disclosing the absolute project path is opt-in. Independent of the
    # per-call include_paths param of the workspace_list MCP tool (agent
    # surface) - the dashboard gating is controlled ONLY by this knob.
    expose_workspace_path: bool = False
    # ----------------------------------------------------------------- #
    # Meta-harness feature flags (R-I0). All opt-in (default OFF). Most flags
    # gate behaviour inside consuming use-cases; feature_memory is the explicit
    # experimental exception that also controls MCP tool registration at
    # bootstrap.
    # ----------------------------------------------------------------- #
    feature_trace: bool = False
    feature_hitl: bool = False
    feature_verification: bool = False
    feature_dag: bool = False
    feature_memory: bool = False
    feature_health: bool = False
    feature_replay: bool = False

    def __post_init__(self) -> None:
        self.home_dir = Path(self.home_dir).expanduser()
        if self.db_path is None:
            self.db_path = self.home_dir / "nexus.db"
        else:
            self.db_path = Path(self.db_path).expanduser()
        if self.metrics_dir is not None:
            self.metrics_dir = Path(self.metrics_dir).expanduser()


# Mapping: NexusConfig field -> (env var name, CLI flag).
# ``home_dir``/``db_path`` are strings; the rest are positive integers.
# All environment variables live under the ``OKTO_NEXUS_*`` namespace.
_PATH_FIELDS: dict[str, tuple[str, str]] = {
    "home_dir": ("OKTO_NEXUS_HOME", "--home"),
    "db_path": ("OKTO_NEXUS_DB_PATH", "--db-path"),
    "metrics_dir": ("OKTO_NEXUS_METRICS_DIR", "--metrics-dir"),
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
    # The four knobs below were previously resolved ad hoc by the inbound tool
    # adapters straight from os.environ with a SILENT fallback on bad values -
    # contradicting this module's fail-closed contract. They now resolve here
    # (same env var names preserved), so an invalid value is a clear
    # CONFIG_ERROR at startup instead of a silently-applied default.
    "inbox_lease_ttl_seconds": (
        "OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS",
        "--inbox-lease-ttl-seconds",
        DEFAULT_INBOX_LEASE_TTL_SECONDS,
        1,
    ),
    "session_stale_ttl_seconds": (
        "OKTO_NEXUS_SESSION_STALE_TTL_SECONDS",
        "--session-stale-ttl-seconds",
        DEFAULT_SESSION_STALE_TTL_SECONDS,
        1,
    ),
    "presence_ttl_seconds": (
        "OKTO_NEXUS_PRESENCE_TTL_SECONDS",
        "--presence-ttl-seconds",
        DEFAULT_PRESENCE_TTL_SECONDS,
        1,
    ),
    "session_reap_seconds": (
        "OKTO_NEXUS_SESSION_REAP_SECONDS",
        "--session-reap-seconds",
        DEFAULT_SESSION_REAP_SECONDS,
        1,
    ),
    "max_shared_md_events": (
        "OKTO_NEXUS_MAX_SHARED_MD_EVENTS",
        "--max-shared-md-events",
        DEFAULT_MAX_SHARED_MD_EVENTS,
        1,
    ),
    "max_event_limit": (
        "OKTO_NEXUS_MAX_EVENT_LIMIT",
        "--max-event-limit",
        DEFAULT_MAX_EVENT_LIMIT,
        1,
    ),
    "poll_token_ttl_seconds": (
        "OKTO_NEXUS_POLL_TOKEN_TTL_SECONDS",
        "--poll-token-ttl-seconds",
        DEFAULT_POLL_TOKEN_TTL_SECONDS,
        60,
    ),
    "metrics_retention_days": (
        "OKTO_NEXUS_METRICS_RETENTION_DAYS",
        "--metrics-retention-days",
        DEFAULT_METRICS_RETENTION_DAYS,
        0,
    ),
    "metrics_publish_interval_seconds": (
        "OKTO_NEXUS_METRICS_PUBLISH_INTERVAL_SECONDS",
        "--metrics-publish-interval-seconds",
        DEFAULT_METRICS_PUBLISH_INTERVAL_SECONDS,
        60,
    ),
    # Retention windows accept 0 ("keep nothing older than right now"); only a
    # negative value is rejected.
    "retention_events_keep_days": (
        "OKTO_NEXUS_RETENTION_EVENTS_KEEP_DAYS",
        "--retention-events-keep-days",
        DEFAULT_RETENTION_EVENTS_KEEP_DAYS,
        0,
    ),
    "retention_read_deliveries_keep_days": (
        "OKTO_NEXUS_RETENTION_READ_DELIVERIES_KEEP_DAYS",
        "--retention-read-deliveries-keep-days",
        DEFAULT_RETENTION_READ_DELIVERIES_KEEP_DAYS,
        0,
    ),
    "retention_closed_sessions_keep_days": (
        "OKTO_NEXUS_RETENTION_CLOSED_SESSIONS_KEEP_DAYS",
        "--retention-closed-sessions-keep-days",
        DEFAULT_RETENTION_CLOSED_SESSIONS_KEEP_DAYS,
        0,
    ),
    # Messages retention is the one window with a HARD floor: by owner directive
    # the keep-days knob may never drop below 7, so a value < 7 fails closed at
    # startup (CONFIG_ERROR) instead of silently purging the bus aggressively.
    "retention_messages_keep_days": (
        "OKTO_NEXUS_RETENTION_MESSAGES_KEEP_DAYS",
        "--retention-messages-keep-days",
        DEFAULT_RETENTION_MESSAGES_KEEP_DAYS,
        MIN_RETENTION_MESSAGES_KEEP_DAYS,
    ),
}

# field: (env var, CLI flag, default, allowed values) - closed-vocabulary
# string knobs, parsed FAIL-CLOSED like the integer fields above.
_ENUM_FIELDS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "metrics_mode": (
        "OKTO_NEXUS_METRICS_MODE",
        "--metrics-mode",
        METRICS_MODE_DISABLED,
        METRICS_MODES,
    ),
    "trust_mode": (
        "OKTO_NEXUS_TRUST_MODE",
        "--trust-mode",
        TRUST_MODE_OPEN,
        TRUST_MODES,
    ),
    "embedding_mode": (
        "OKTO_NEXUS_EMBEDDING_MODE",
        "--embedding-mode",
        EMBEDDING_MODE_OFF,
        EMBEDDING_MODES,
    ),
}

# field: (env var, CLI flag, default) - free string knobs, parsed with the same
# CLI > env > default precedence. Keep this set tiny; sensitive values do not
# belong here.
_STRING_FIELDS: dict[str, tuple[str, str, str]] = {
    "metrics_beacon_url": (
        "OKTO_NEXUS_METRICS_BEACON_URL",
        "--metrics-beacon-url",
        DEFAULT_METRICS_BEACON_URL,
    ),
}

# field: (env var, CLI flag, default) - boolean knobs, parsed FAIL-CLOSED.
# The CLI grammar is value-carrying (``--flag value`` / ``--flag=value``), so
# boolean flags take an explicit true/false value rather than being bare.
_BOOL_FIELDS: dict[str, tuple[str, str, bool]] = {
    "auto_prune_on_start": (
        "OKTO_NEXUS_AUTO_PRUNE_ON_START",
        "--auto-prune-on-start",
        False,
    ),
    "inbox_read_receipts": (
        "OKTO_NEXUS_INBOX_READ_RECEIPTS",
        "--inbox-read-receipts",
        True,
    ),
    "expose_workspace_path": (
        "OKTO_NEXUS_EXPOSE_WORKSPACE_PATH",
        "--expose-workspace-path",
        False,
    ),
    # Meta-harness feature flags (R-I0): all default False (opt-in).
    "feature_trace": (
        "OKTO_NEXUS_FEATURE_TRACE",
        "--feature-trace",
        False,
    ),
    "feature_hitl": (
        "OKTO_NEXUS_FEATURE_HITL",
        "--feature-hitl",
        False,
    ),
    "feature_verification": (
        "OKTO_NEXUS_FEATURE_VERIFICATION",
        "--feature-verification",
        False,
    ),
    "feature_dag": (
        "OKTO_NEXUS_FEATURE_DAG",
        "--feature-dag",
        False,
    ),
    "feature_memory": (
        "OKTO_NEXUS_FEATURE_MEMORY",
        "--feature-memory",
        False,
    ),
    "feature_health": (
        "OKTO_NEXUS_FEATURE_HEALTH",
        "--feature-health",
        False,
    ),
    "feature_replay": (
        "OKTO_NEXUS_FEATURE_REPLAY",
        "--feature-replay",
        False,
    ),
}

#: The meta-harness feature flags (R-I0), derived from ``_BOOL_FIELDS`` so the
#: ``nexus_info.features`` block and the flag fields can never drift apart.
FEATURE_FLAG_FIELDS: tuple[str, ...] = tuple(
    name for name in _BOOL_FIELDS if name.startswith("feature_")
)

_BOOL_TRUE = frozenset({"true", "1", "yes", "on"})
_BOOL_FALSE = frozenset({"false", "0", "no", "off"})


def _parse_cli(argv: list[str]) -> dict[str, str]:
    """Parse a flat ``--flag value`` / ``--flag=value`` argv into a flag->value map.

    Unknown flags raise ``CONFIG_ERROR`` so typos fail closed rather than being
    silently ignored.
    """
    known_flags = {flag for _, flag in _PATH_FIELDS.values()}
    known_flags |= {flag for _, flag, _, _ in _INT_FIELDS.values()}
    known_flags |= {flag for _, flag, _, _ in _ENUM_FIELDS.values()}
    known_flags |= {flag for _, flag, _ in _STRING_FIELDS.values()}
    known_flags |= {flag for _, flag, _ in _BOOL_FIELDS.values()}

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


def _resolve_enum(
    field_name: str,
    flag: str,
    env_var: str,
    default: str,
    allowed: tuple[str, ...],
    env: Mapping[str, str],
    cli: Mapping[str, str],
) -> str:
    """Resolve a closed-vocabulary string field with CLI > env > default precedence.

    The value is trimmed and lowercased; anything outside ``allowed`` raises
    ``CONFIG_ERROR`` so the fail-closed bootstrap aborts cleanly (never a
    silent fallback to the default).
    """
    raw = _resolve_str(flag, env_var, env=env, cli=cli)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value not in allowed:
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            f"Invalid value for {field_name}: {raw!r}. Allowed values: "
            f"{', '.join(allowed)}.",
            {"field": field_name, "value": raw, "allowed": list(allowed)},
        )
    return value


def _resolve_bool(
    field_name: str,
    flag: str,
    env_var: str,
    default: bool,
    env: Mapping[str, str],
    cli: Mapping[str, str],
) -> bool:
    """Resolve a boolean field with CLI > env > default precedence, FAIL-CLOSED.

    Accepted spellings (trimmed, case-insensitive): ``true/1/yes/on`` and
    ``false/0/no/off``. Anything else raises ``CONFIG_ERROR`` rather than being
    silently coerced (``"enabled"`` must not quietly read as ``False``).
    """
    raw = _resolve_str(flag, env_var, env=env, cli=cli)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in _BOOL_TRUE:
        return True
    if value in _BOOL_FALSE:
        return False
    raise OktoNexusError(
        ErrorCode.CONFIG_ERROR,
        f"Invalid boolean for {field_name}: {raw!r}. Use one of: "
        f"{', '.join(sorted(_BOOL_TRUE))} (true) or "
        f"{', '.join(sorted(_BOOL_FALSE))} (false).",
        {"field": field_name, "value": raw},
    )


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
    metrics_dir_env, metrics_dir_flag = _PATH_FIELDS["metrics_dir"]
    metrics_dir_override = _resolve_str(
        metrics_dir_flag, metrics_dir_env, env=env, cli=cli
    )
    if metrics_dir_override is not None:
        kwargs["metrics_dir"] = Path(metrics_dir_override)

    for field_name, (env_var, flag, default, minimum) in _INT_FIELDS.items():
        kwargs[field_name] = _resolve_int(
            field_name, flag, env_var, default, minimum, env, cli
        )

    for field_name, (env_var, flag, default, allowed) in _ENUM_FIELDS.items():
        kwargs[field_name] = _resolve_enum(
            field_name, flag, env_var, default, allowed, env, cli
        )

    for field_name, (env_var, flag, default) in _STRING_FIELDS.items():
        kwargs[field_name] = _resolve_str(flag, env_var, env=env, cli=cli) or default

    for field_name, (env_var, flag, default) in _BOOL_FIELDS.items():
        kwargs[field_name] = _resolve_bool(field_name, flag, env_var, default, env, cli)

    return NexusConfig(**kwargs)
