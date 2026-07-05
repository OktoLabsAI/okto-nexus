"""Runtime settings: the dashboard-editable view over :class:`NexusConfig`.

Every knob the CLI/env already accepts (TTLs, retention windows, limits,
trust mode) can ALSO be adjusted from the Settings screen and persisted in
the ``settings`` table - non-exclusively: precedence stays strict
``CLI > env > stored override > default``. A value pinned on the command
line wins for that run and the UI reports it as read-only ("cli/env").

Pure application code: stdlib + config only (import boundary enforced).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from ..config import (
    EMBEDDING_MODES,
    MIN_RETENTION_MESSAGES_KEEP_DAYS,
    NexusConfig,
    TRUST_MODES,
)
from ..errors import ErrorCode, OktoNexusError
from .ports import Clock, UnitOfWork


@dataclass(frozen=True)
class SettingSpec:
    """One editable knob: type, bounds and the operator-facing description."""

    key: str
    type: str  # "int" | "bool" | "enum"
    description: str
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] | None = None
    requires_restart: bool = False
    group: str = "general"


#: The dashboard-editable subset of NexusConfig. ``home_dir``/``db_path``
#: stay CLI/env-only on purpose: repointing storage mid-flight cannot be
#: applied safely to a running process.
SETTING_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec(
        "session_stale_ttl_seconds",
        "int",
        "Seconds without a heartbeat before an active session shows as "
        "'stale' (amber on the graph). Too short causes false alarms; too "
        "long hides stuck agents.",
        minimum=5,
        maximum=3600,
    ),
    SettingSpec(
        "presence_ttl_seconds",
        "int",
        "Presence window (s): with a heartbeat older than this the agent "
        "drops out of the broadcast audience and shows offline on the dashboard.",
        minimum=60,
        maximum=86400,
    ),
    SettingSpec(
        "session_reap_seconds",
        "int",
        "Heartbeat age (s) past which abandoned sessions are closed "
        "automatically (opportunistic reaper).",
        minimum=300,
        maximum=604800,
    ),
    SettingSpec(
        "handoff_lease_ttl_seconds",
        "int",
        "Lease (s) of a claimed handoff: without completion within it, the "
        "claim expires and the work returns to the pool for another agent.",
        minimum=30,
        maximum=86400,
    ),
    SettingSpec(
        "inbox_lease_ttl_seconds",
        "int",
        "Lease (s) for messages pulled via inbox_pull: without an ack within "
        "it, the delivery returns to 'unread'.",
        minimum=30,
        maximum=86400,
    ),
    SettingSpec(
        "max_wait_timeout_seconds",
        "int",
        "Ceiling (s) for the timeout parameter of message_wait/event_wait "
        "(agent long polling).",
        minimum=1,
        maximum=300,
    ),
    SettingSpec(
        "poll_interval_ms",
        "int",
        "Internal interval (ms) between checks in long-polling waits. Lower = "
        "more responsive, more SQLite read load.",
        minimum=50,
        maximum=5000,
    ),
    SettingSpec(
        "busy_timeout_ms",
        "int",
        "PRAGMA busy_timeout (ms): how long a connection waits for SQLite "
        "locks before failing. Affects new connections.",
        minimum=100,
        maximum=60000,
        requires_restart=True,
    ),
    SettingSpec(
        "max_event_limit",
        "int",
        "Maximum events returned per page in event_get/event_wait and the "
        "dashboard feed.",
        minimum=10,
        maximum=10000,
    ),
    SettingSpec(
        "max_shared_md_events",
        "int",
        "Ceiling of events rendered by shared_md_render (the workspace "
        "Markdown digest).",
        minimum=10,
        maximum=10000,
    ),
    SettingSpec(
        "max_inline_bytes",
        "int",
        "Maximum size (UTF-8 bytes) of inline content in messages and "
        "artifacts before artifact_put is required.",
        minimum=1024,
        maximum=1048576,
    ),
    SettingSpec(
        "trust_mode",
        "enum",
        "'open': session credentials optional but validated when supplied. "
        "'strict': sensitive verbs (message_create, handoff_*, inbox_*) "
        "require session_id + session_secret.",
        choices=TRUST_MODES,
    ),
    SettingSpec(
        "retention_events_keep_days",
        "int",
        "Window (days) for the event log: prune removes events older than this.",
        minimum=1,
        maximum=3650,
    ),
    SettingSpec(
        "retention_read_deliveries_keep_days",
        "int",
        "Window (days) for READ deliveries. The unread/delivered/parked lanes "
        "are never pruned.",
        minimum=1,
        maximum=3650,
    ),
    SettingSpec(
        "retention_closed_sessions_keep_days",
        "int",
        "Window (days) for CLOSED sessions. Active/stale sessions are never pruned.",
        minimum=1,
        maximum=3650,
    ),
    SettingSpec(
        "retention_messages_keep_days",
        "int",
        "Window (days) for MESSAGES: prune removes messages older than this by "
        "PURE AGE, regardless of delivery status, taking their deliveries and "
        "embeddings with them. Hard minimum 7 (fail-closed).",
        minimum=MIN_RETENTION_MESSAGES_KEEP_DAYS,
        maximum=3650,
    ),
    SettingSpec(
        "embedding_mode",
        "enum",
        "Semantic search over message content: 'off' disables it (no embeddings; "
        "/messages/search answers EMBEDDINGS_UNAVAILABLE); 'stub' uses a "
        "zero-dependency deterministic provider; 'local' uses "
        "sentence-transformers (requires the [embeddings] extra). Takes effect "
        "after a restart.",
        choices=EMBEDDING_MODES,
        requires_restart=True,
    ),
    SettingSpec(
        "auto_prune_on_start",
        "bool",
        "Run the retention prune automatically on every server boot.",
    ),
    SettingSpec(
        "inbox_read_receipts",
        "bool",
        "Deliver a read receipt to the sender's inbox when a recipient "
        "acknowledges its message (receipts never generate receipts). "
        "Turn off to keep inboxes receipt-free.",
    ),
    SettingSpec(
        "expose_workspace_path",
        "bool",
        "Show each workspace's absolute project path (root_realpath) on the "
        "Workspaces screen and the /api/v1/workspaces API. Off (default) "
        "redacts the path (defense-in-depth); turn on to reveal it.",
    ),
    # ------------------------------------------------------------------ #
    # Meta-harness feature flags (R-I0). All opt-in (default off). A flag
    # never adds or removes MCP tools; it only unlocks behaviour inside
    # the consuming use-cases once those features ship. Exposed read-only
    # to agents via nexus_info.features.
    # ------------------------------------------------------------------ #
    SettingSpec(
        "feature_trace",
        "bool",
        "Opt-in: trace-id propagation across messages and handoffs so "
        "multi-agent trajectories can be reconstructed. No effect until "
        "the consuming feature ships.",
        group="features",
    ),
    SettingSpec(
        "feature_hitl",
        "bool",
        "Opt-in: human-in-the-loop steering - operator pause, inject and "
        "redirect over agent coordination. No effect until the consuming "
        "feature ships.",
        group="features",
    ),
    SettingSpec(
        "feature_verification",
        "bool",
        "Opt-in: handoff verification - completion evidence is checked "
        "before a handoff closes. No effect until the consuming feature "
        "ships.",
        group="features",
    ),
    SettingSpec(
        "feature_dag",
        "bool",
        "Opt-in: handoff dependency graphs (depends_on) with "
        "dependency-aware claiming. No effect until the consuming "
        "feature ships.",
        group="features",
    ),
    SettingSpec(
        "feature_memory",
        "bool",
        "Opt-in: shared memory primitives (memory_*) for cross-agent "
        "knowledge. No effect until the consuming feature ships.",
        group="features",
    ),
    SettingSpec(
        "feature_health",
        "bool",
        "Opt-in: coordination health reporting (windowed metrics over "
        "bus activity). No effect until the consuming feature ships.",
        group="features",
    ),
    SettingSpec(
        "feature_replay",
        "bool",
        "Opt-in: replay/eval export of coordination history (NDJSON + "
        "manifest). No effect until the consuming feature ships.",
        group="features",
    ),
)

_SPEC_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SETTING_SPECS}


def _coerce(spec: SettingSpec, raw: Any) -> Any:
    """Validate ``raw`` against the spec; raise CONFIG_ERROR otherwise."""
    if spec.type == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.strip().lower() in ("true", "1", "false", "0"):
            return raw.strip().lower() in ("true", "1")
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            f"Setting {spec.key!r} expects a boolean.",
            {"key": spec.key, "value": raw},
        )
    if spec.type == "enum":
        value = str(raw)
        if spec.choices and value not in spec.choices:
            raise OktoNexusError(
                ErrorCode.CONFIG_ERROR,
                f"Setting {spec.key!r} must be one of {', '.join(spec.choices or ())}.",
                {"key": spec.key, "value": raw},
            )
        return value
    # int
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            f"Setting {spec.key!r} expects an integer.",
            {"key": spec.key, "value": raw},
        ) from None
    if spec.minimum is not None and value < spec.minimum:
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            f"Setting {spec.key!r} must be >= {spec.minimum}.",
            {"key": spec.key, "value": value},
        )
    if spec.maximum is not None and value > spec.maximum:
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            f"Setting {spec.key!r} must be <= {spec.maximum}.",
            {"key": spec.key, "value": value},
        )
    return value


class SettingsService:
    """Load, expose and update the stored runtime overrides.

    ``pinned`` is the set of config fields fixed by CLI/env for this run
    (detected at serve bootstrap by diffing against pure defaults): stored
    overrides never shadow them, and the UI shows them as read-only.
    """

    def __init__(
        self,
        config: NexusConfig,
        clock: Clock,
        pinned: frozenset[str] = frozenset(),
    ) -> None:
        self._config = config
        self._clock = clock
        self._pinned = pinned

    # ------------------------------------------------------------------ #
    def load_overrides(self, uow: UnitOfWork) -> dict[str, Any]:
        rows = uow.connection.execute("SELECT key, value FROM settings").fetchall()
        overrides: dict[str, Any] = {}
        for row in rows:
            spec = _SPEC_BY_KEY.get(row["key"])
            if spec is None:
                continue  # stale key from an older version: ignore, keep row
            try:
                overrides[spec.key] = _coerce(spec, json.loads(row["value"]))
            except (ValueError, OktoNexusError):
                continue  # never let a corrupt row break bootstrap
        return overrides

    def apply_overrides(self, uow: UnitOfWork) -> dict[str, Any]:
        """Mutate the live config with stored overrides (skipping pinned)."""
        applied: dict[str, Any] = {}
        for key, value in self.load_overrides(uow).items():
            if key in self._pinned:
                continue
            setattr(self._config, key, value)
            applied[key] = value
        return applied

    # ------------------------------------------------------------------ #
    def describe(self, uow: UnitOfWork) -> list[dict[str, Any]]:
        """The full settings catalogue for GET /api/v1/settings."""
        overrides = self.load_overrides(uow)
        defaults = NexusConfig()
        items: list[dict[str, Any]] = []
        for spec in SETTING_SPECS:
            current = getattr(self._config, spec.key)
            if spec.key in self._pinned:
                source = "cli/env"
            elif spec.key in overrides:
                source = "stored"
            else:
                source = "default"
            items.append(
                {
                    "key": spec.key,
                    "type": spec.type,
                    "group": spec.group,
                    "description": spec.description,
                    "value": current,
                    "default": getattr(defaults, spec.key),
                    "min": spec.minimum,
                    "max": spec.maximum,
                    "choices": list(spec.choices) if spec.choices else None,
                    "source": source,
                    "editable": spec.key not in self._pinned,
                    "requires_restart": spec.requires_restart,
                }
            )
        return items

    def update(self, uow: UnitOfWork, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate, persist and apply ``changes``; returns what was applied.

        Unknown keys and attempts to change CLI/env-pinned values fail
        loudly (CONFIG_ERROR) - silent partial writes would be worse.
        """
        validated: dict[str, Any] = {}
        for key, raw in changes.items():
            spec = _SPEC_BY_KEY.get(key)
            if spec is None:
                raise OktoNexusError(
                    ErrorCode.CONFIG_ERROR,
                    f"Unknown setting: {key!r}.",
                    {"key": key},
                )
            if key in self._pinned:
                raise OktoNexusError(
                    ErrorCode.CONFIG_ERROR,
                    f"Setting {key!r} is pinned by a CLI flag or environment "
                    "variable for this run; remove the flag to manage it here.",
                    {"key": key},
                )
            validated[key] = _coerce(spec, raw)

        now = self._clock.now_iso()
        for key, value in validated.items():
            uow.connection.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, json.dumps(value), now),
            )
            setattr(self._config, key, value)
        return validated

    def reset(self, uow: UnitOfWork, keys: list[str] | None = None) -> list[str]:
        """Drop stored overrides (all, or the given keys) and restore defaults."""
        defaults = NexusConfig()
        targets = keys if keys is not None else [s.key for s in SETTING_SPECS]
        cleared: list[str] = []
        for key in targets:
            if key not in _SPEC_BY_KEY:
                raise OktoNexusError(
                    ErrorCode.CONFIG_ERROR, f"Unknown setting: {key!r}.", {"key": key}
                )
            uow.connection.execute("DELETE FROM settings WHERE key = ?", (key,))
            if key not in self._pinned:
                setattr(self._config, key, getattr(defaults, key))
            cleared.append(key)
        return cleared


def detect_pinned_fields(resolved: NexusConfig) -> frozenset[str]:
    """Fields whose resolved value differs from the pure default.

    Heuristic for "set via CLI/env": exact-default CLI values are treated
    as unpinned (acceptable: the UI then manages a value the operator
    explicitly typed as the default - same number, no surprise).
    """
    defaults = NexusConfig()
    pinned = {
        spec.key
        for spec in SETTING_SPECS
        if getattr(resolved, spec.key) != getattr(defaults, spec.key)
    }
    return frozenset(pinned)


def with_defaults(config: NexusConfig) -> NexusConfig:
    """A defensive copy helper (kept for tests)."""
    return replace(config)
