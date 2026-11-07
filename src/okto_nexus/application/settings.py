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
import hashlib
from dataclasses import dataclass, replace
from typing import Any, Callable

from ..config import (
    EMBEDDING_MODES,
    META_HARNESS_RECEIPT_DISPLAY_MODES,
    METRICS_MODES,
    MIN_RETENTION_MESSAGES_KEEP_DAYS,
    NexusConfig,
    OBSERVATION_INTEGER_LIMITS,
    TRUST_MODES,
)
from ..errors import ErrorCode, OktoNexusError
from .ports import Clock, UnitOfWork


@dataclass(frozen=True)
class SettingSpec:
    """One editable knob: type, bounds and the operator-facing description."""

    key: str
    type: str  # "int" | "float" | "bool" | "enum"
    description: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] | None = None
    requires_restart: bool = False
    group: str = "general"
    implemented: bool = True


_OBSERVATION_DESCRIPTIONS = {
    "observation_max_valid_for_seconds": (
        "Maximum validity in seconds for new external activity reports; default 3600. "
        "Omitted report TTL is fixed at 90 seconds by the protocol. A lower maximum "
        "requires an explicit smaller TTL on new reports; accepted replays retain their original expiry."
    ),
    "observation_future_tolerance_seconds": (
        "Allowed future clock skew in seconds for a new external report; default 30. "
        "Skew never extends validity beyond the report TTL from Server receipt."
    ),
    "observation_source_stale_seconds": (
        "Seconds without a current source report before external source activity is stale; default 30. "
        "This does not change agent presence, sessions or execution capacity."
    ),
    "observation_source_rate_per_minute": "Maximum admitted external reports per minute for one source; default 60.",
    "observation_source_burst": "Maximum accumulated report burst for one external source; default 20.",
    "observation_agent_rate_per_minute": "Maximum admitted external reports per minute across one agent's sources; default 1920.",
    "observation_agent_burst": "Maximum accumulated report burst across one agent's external sources; default 80.",
    "observation_installation_rate_per_minute": "Maximum admitted external reports per minute across this installation; default 8192.",
    "observation_installation_burst": "Maximum accumulated external report burst across this installation; default 512.",
    "observation_max_sources_per_agent": "Maximum registered external observation sources for one agent; default 32.",
    "observation_max_sources": "Maximum registered external observation sources in this installation; default 4096.",
    "observation_max_instances": "Maximum registered external observed instances in this installation; default 4096.",
    "observation_max_tokens_per_source": "Maximum active publish credentials for one observation source; default 8.",
    "observation_event_retention_days": "External observation event history retention in days; default 7. Replay and generation fences are preserved separately.",
    "observation_max_events": "Maximum retained external observation events; default 20000. This does not cap canonical coordination history.",
}


#: The dashboard-editable subset of NexusConfig. ``home_dir``/``db_path``
#: stay CLI/env-only on purpose: repointing storage mid-flight cannot be
#: applied safely to a running process.
SETTING_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec(
        "feature_observations", "bool",
        "Opt-in external activity telemetry, disabled by default. Sources require explicit authorization. "
        "Enabling this does not enable runtime connections, change agent presence or grant permissions.",
        group="features",
    ),
    *(SettingSpec(name, "int", _OBSERVATION_DESCRIPTIONS[name], minimum=low, maximum=high,
                  group="observations")
      for name, (_, low, high) in OBSERVATION_INTEGER_LIMITS.items()),
    SettingSpec(
        "remote_machine_policy", "enum",
        "When another registered Connector machine requests the same agent: require approval (default), "
        "deny, or accept and revoke the previous machine. Automatic replacement preserves approved "
        "harness settings and the remaining execution budget and expiry; the first machine always needs approval.",
        choices=("manual", "deny", "auto_replace"),
    ),
    SettingSpec(
        "delivery_coalesce", "enum",
        "When a runtime agent is busy and a sender queues a newer message, off (default) delivers every "
        "message as its own turn. same_sender cancels the sender's earlier unsent messages with the same "
        "session affinity and adds their text to the newer turn. A message that reached the runtime is never cancelled.",
        choices=("off", "same_sender"),
    ),
    SettingSpec(
        "transport_security", "enum",
        "Allow HTTP/HTTPS and WS/WSS (default), or require HTTPS/WSS. "
        "Configure TLS before selecting HTTPS only. Applies to new requests and connections; "
        "restart to close existing streams. TLS can terminate at a trusted reverse proxy.",
        choices=("http_https", "https_only"),
    ),
    SettingSpec(
        "runtime_update_policy", "enum",
        "When a runtime installation updates to a newer build: 'review' (default) holds the "
        "new build for operator review. 'follow' adopts one strictly newer build under the "
        "approved installation and keeps live sessions.",
        choices=("review", "follow"),
    ),
    SettingSpec("connection_key_ttl_seconds", "int", "New connection key lifetime in seconds; 86400 = 24 hours, 0 = unlimited. Agents may override this default. Existing keys keep their issued expiry.", minimum=0, maximum=315360000),
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
        "handoff_notify_expiry",
        "bool",
        "Tell the creator and the previous claimant when a handoff lease "
        "expires. Both notices start a turn when the agent has a runtime session.",
    ),
    SettingSpec(
        "handoff_silence_warn_fraction",
        "float",
        "Fraction of the handoff lease after which the creator gets one "
        "warning when the claimant sent no message to the creator. "
        "0 turns the warning off.",
        minimum=0.0,
        maximum=1.0,
    ),
    SettingSpec(
        "max_relay_depth",
        "int",
        "Maximum relay depth of one chain. A relay past this depth is "
        "refused. Applies to new chains only.",
        minimum=0,
        maximum=64,
    ),
    SettingSpec(
        "max_executions_per_root",
        "int",
        "Maximum executions that one root message can start. Applies to "
        "new roots only.",
        minimum=1,
        maximum=1024,
    ),
    SettingSpec(
        "root_deadline_seconds",
        "int",
        "Seconds that a root message chain can run before it closes. "
        "Applies to new roots only.",
        minimum=1,
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
        "poll_token_ttl_seconds",
        "int",
        "TTL (s) for ephemeral poll tokens issued to remote monitor processes. "
        "Shorter limits exposure if a background process leaks its bearer.",
        minimum=60,
        maximum=86400,
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
        "metrics_mode",
        "enum",
        "Anonymous usage metrics: 'disabled' writes nothing, 'local_only' "
        "keeps a local JSONL audit trail, and 'anonymous_beacon' publishes "
        "bounded aggregate deltas to the configured beacon.",
        choices=METRICS_MODES,
        group="metrics",
    ),
    SettingSpec(
        "metrics_retention_days",
        "int",
        "Retention window (days) for local metrics files. A value of 0 keeps "
        "only currently pending local state once pruning is implemented.",
        minimum=0,
        maximum=3650,
        group="metrics",
        implemented=False,
    ),
    SettingSpec(
        "metrics_publish_interval_seconds",
        "int",
        "Background publish cadence (s) for anonymous metrics. Changing this "
        "while serve is running takes effect after restart; the manual publish "
        "endpoint is available immediately.",
        minimum=60,
        maximum=86400,
        requires_restart=True,
        group="metrics",
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
        "meta_harness_receipt_display",
        "enum",
        "How read receipts appear in Meta-harness: 'inline' hides receipt "
        "notification turns and shows an aggregate acknowledgement flag on "
        "the original message; 'timeline' keeps receipts as separate chat turns.",
        choices=META_HARNESS_RECEIPT_DISPLAY_MODES,
        group="interface",
    ),
    SettingSpec(
        "expose_workspace_path",
        "bool",
        "Show each workspace's absolute project path (root_realpath) on the "
        "Workspaces screen and the /api/v1/workspaces API. Off (default) "
        "redacts the path (defense-in-depth); turn on to reveal it.",
    ),
    SettingSpec(
        "feature_attention", "bool",
        "Show the operator attention projection of existing Nexus facts. Disabling it "
        "preserves Approvals, Handoffs and their original actions.",
        group="interface",
    ),
    SettingSpec(
        "attention_unclaimed_seconds", "int",
        "Seconds before an eligible open handoff without a claimant needs attention. "
        "0 disables this time threshold; handoff leases and execution remain unchanged.",
        minimum=0, maximum=86400, group="interface",
    ),
    SettingSpec(
        "attention_disconnected_seconds", "int",
        "Seconds before an executor disconnected with pending work is escalated in attention. "
        "0 disables this escalation; connection recovery and execution remain unchanged.",
        minimum=0, maximum=86400, group="interface",
    ),
    # ------------------------------------------------------------------ #
    # Meta-harness feature flags (R-I0). All opt-in (default off). Most flags
    # unlock behaviour inside consuming use-cases once those features ship.
    # feature_memory is experimental and also controls dashboard/MCP surface
    # exposure at bootstrap. Exposed read-only to agents via nexus_info.features.
    # ------------------------------------------------------------------ #
    SettingSpec(
        "feature_trace",
        "bool",
        "Opt-in: trace-id propagation across messages and handoffs so "
        "multi-agent trajectories can be reconstructed.",
        group="features",
    ),
    SettingSpec(
        "feature_hitl",
        "bool",
        "Opt-in: human-in-the-loop steering - operator pause, inject and "
        "redirect over agent coordination.",
        group="features",
    ),
    SettingSpec(
        "feature_verification",
        "bool",
        "Opt-in: handoff verification - completion evidence is checked "
        "before a handoff closes.",
        group="features",
    ),
    SettingSpec(
        "feature_dag",
        "bool",
        "Opt-in: handoff dependency graphs (depends_on) with "
        "dependency-aware claiming.",
        group="features",
    ),
    SettingSpec(
        "feature_memory",
        "bool",
        "Experimental opt-in: shared memory primitives (memory_*) and the "
        "dashboard Memory tab. MCP tool exposure is decided at server startup.",
        group="features",
        requires_restart=True,
    ),
    SettingSpec(
        "feature_health",
        "bool",
        "Opt-in: coordination health reporting (windowed metrics over "
        "bus activity).",
        group="features",
    ),
    SettingSpec(
        "feature_harness_integrations", "bool",
        "Runtime connections, enabled by default. Admission is checked on every request; MCP publication requires restart.",
        group="features", requires_restart=True,
    ),
    SettingSpec(
        "feature_replay",
        "bool",
        "Opt-in: replay/eval export of coordination history (NDJSON + "
        "manifest).",
        group="features",
    ),
)

_SPEC_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SETTING_SPECS}


def _coerce(spec: SettingSpec, raw: Any) -> Any:
    """Validate ``raw`` against the spec; raise CONFIG_ERROR otherwise."""
    if spec.key in OBSERVATION_INTEGER_LIMITS and type(raw) is not int:
        raise OktoNexusError(ErrorCode.CONFIG_ERROR,
            f"Setting {spec.key!r} expects an integer, without boolean or numeric coercion.", {})
    if spec.key == "feature_observations" and type(raw) is not bool:
        raise OktoNexusError(ErrorCode.CONFIG_ERROR,
            "Setting 'feature_observations' expects a boolean.", {})
    if spec.key in {"attention_unclaimed_seconds", "attention_disconnected_seconds"} and type(raw) is not int:
        # Zero explicitly disables a time rule; never turn false or a fraction
        # into that policy through the legacy integer coercion below.
        raise OktoNexusError(ErrorCode.CONFIG_ERROR,
            "Attention thresholds must be integer seconds; use 0 explicitly to disable a time rule.", {})
    if spec.key == "connection_key_ttl_seconds" and type(raw) is not int:
        # Unlike an ordinary numeric tuning knob, truncating 0.5 or coercing
        # false to zero would silently grant an unlimited credential lifetime.
        raise OktoNexusError(ErrorCode.CONFIG_ERROR,
            "Connection key lifetime must be integer seconds; use 0 explicitly for unlimited.", {})
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
    if spec.type == "float":
        try:
            fvalue = float(raw)
        except (TypeError, ValueError):
            fvalue = float("nan")
        if isinstance(raw, bool) or not (spec.minimum <= fvalue <= spec.maximum):
            raise OktoNexusError(
                ErrorCode.CONFIG_ERROR,
                f"Setting {spec.key!r} must be a number from {spec.minimum} to {spec.maximum}.",
                {"key": spec.key, "value": raw},
            )
        return fvalue
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
    (tracked during CLI/env resolution, with a programmatic fallback): stored
    overrides never shadow them, and the UI shows them as read-only.
    """

    def __init__(
        self,
        config: NexusConfig,
        clock: Clock,
        pinned: frozenset[str] = frozenset(),
        *,
        effective_policy_owner: Callable[[], bool] | None = None,
    ) -> None:
        self._config = config
        self._clock = clock
        self._pinned = pinned
        self._effective_policy_owner = effective_policy_owner
        self._server_policy_active = False

    def _require_policy_owner(self) -> None:
        if self._effective_policy_owner is None or not self._effective_policy_owner():
            raise OktoNexusError(ErrorCode.CONFIG_ERROR,
                "The Server no longer owns this effective policy.", {})

    def start_server_policy(self, uow: UnitOfWork) -> None:
        """Publish resolved policy only from the lock-owning Server lifespan."""
        if self._effective_policy_owner is None:
            return
        self._require_policy_owner()
        from .server_effective_policy import publish_effective_policy
        publish_effective_policy(uow, values={
            key: getattr(self._config, key)
            for key in ('feature_harness_integrations', 'feature_hitl')
        }, now=self._clock.now_iso())
        uow.after_commit(lambda: setattr(self, '_server_policy_active', True))

    def stop_server_policy(self) -> None:
        self._server_policy_active = False

    def _stage_live(self, uow: UnitOfWork, changes: dict[str, Any]) -> None:
        if self._server_policy_active:
            self._require_policy_owner()
            from .server_effective_policy import publish_effective_policy
            policy = {key: value for key, value in changes.items()
                if key in ('feature_harness_integrations', 'feature_hitl')}
            if policy:
                publish_effective_policy(uow, values=policy, now=self._clock.now_iso())
        if 'feature_harness_integrations' in changes:
            self._sync_runtime_writer_mode(uow, changes['feature_harness_integrations'])
        committed = dict(changes)
        def apply_committed():
            for key, value in committed.items():
                setattr(self._config, key, value)
        uow.after_commit(apply_committed)

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
            if not spec.implemented:
                continue
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

    def update(self, uow: UnitOfWork, changes: dict[str, Any], *, apply_live: bool = True) -> dict[str, Any]:
        """Validate and persist changes, applying live values after commit.

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
        if apply_live:
            self._stage_live(uow, validated)
        return validated

    def native_decision_review(self, uow: UnitOfWork) -> dict[str, Any]:
        """The exact global policy a project review may initialize, never reset."""
        key = 'feature_hitl'
        row = uow.connection.execute('SELECT value,updated_at FROM settings WHERE key=?', (key,)).fetchone()
        pinned = key in self._pinned
        legacy = getattr(self._config, '_legacy_settings_provenance', False)
        source = 'cli/env' if pinned else 'stored' if row is not None else 'legacy-context' if legacy else 'default'
        value = self._config.feature_hitl
        if self._server_policy_active:
            from .server_effective_policy import read_effective_policy
            published = read_effective_policy(uow).get(key)
            if published is not None:
                value = published['value']
        state = dict(value=value, source=source, stored=dict(row) if row is not None else None)
        revision = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return dict(value=value, source=source, editable=not pinned, revision=revision,
                    can_initialize=not pinned and not legacy and row is None and value is False)

    def validate_native_decisions(self, uow: UnitOfWork, review: dict[str, Any]) -> None:
        current = self.native_decision_review(uow)
        if (not isinstance(review, dict) or set(review) != {'expected_revision', 'initialize'} or
                type(review['initialize']) is not bool):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid native decision policy review.', {})
        if review['expected_revision'] != current['revision']:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The Server decision policy changed. Review setup again.', {})
        if not (current['can_initialize'] if review['initialize'] else current['value'] is True):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                'Native decisions are disabled by an existing Server policy. Project setup cannot replace that policy.', {})

    def stage_native_decisions(self, uow: UnitOfWork, review: dict[str, Any]) -> None:
        self.validate_native_decisions(uow, review)
        if review['initialize']:
            # Finish owns the transaction. Do not expose a setting that may
            # still roll back to concurrent runtime workers.
            self.update(uow, {'feature_hitl': True}, apply_live=False)

    def refresh_native_decisions(self, factory) -> None:
        # Serialize this cache refresh with ordinary setting writers, and read
        # their latest committed value rather than replaying the setup's value.
        with factory.unit_of_work() as uow:
            if 'feature_hitl' not in self._pinned:
                self._stage_live(uow, {'feature_hitl': self.load_overrides(uow).get(
                    'feature_hitl', NexusConfig().feature_hitl)})

    def reset(self, uow: UnitOfWork, keys: list[str] | None = None) -> list[str]:
        """Drop stored overrides (all, or the given keys) and restore defaults."""
        defaults = NexusConfig()
        targets = keys if keys is not None else [s.key for s in SETTING_SPECS]
        for key in targets:
            if key not in _SPEC_BY_KEY:
                raise OktoNexusError(
                    ErrorCode.CONFIG_ERROR, f"Unknown setting: {key!r}.", {"key": key}
                )
        cleared: list[str] = []
        changes: dict[str, Any] = {}
        for key in targets:
            uow.connection.execute("DELETE FROM settings WHERE key = ?", (key,))
            if key not in self._pinned:
                changes[key] = getattr(defaults, key)
            cleared.append(key)
        self._stage_live(uow, changes)
        return cleared

    def _sync_runtime_writer_mode(self, uow, enabled):
        # Only the current owner can change the live admission mode. A cached
        # client configuration cannot silently downgrade the store contract.
        uow.connection.execute("UPDATE runtime_writer_contract SET admission_enabled=? "
            "WHERE singleton=1 AND owner_id=nexus_runtime_owner_id() "
            "AND owner_epoch=nexus_runtime_owner_epoch() AND EXISTS("
            "SELECT 1 FROM runtime_dispatcher_owner o WHERE o.owner_id=runtime_writer_contract.owner_id "
            "AND o.epoch=runtime_writer_contract.owner_epoch AND o.lease_expires_at>?)",
            (int(enabled), self._clock.now_iso()))


def detect_pinned_fields(resolved: NexusConfig) -> frozenset[str]:
    """Preserve explicit CLI/env choices, including choices equal to defaults.

    Programmatic configurations retain the existing nondefault-value fallback.
    """
    defaults = NexusConfig()
    pinned = {
        spec.key
        for spec in SETTING_SPECS
        if spec.key in getattr(resolved, '_explicit_fields', ()) or
            getattr(resolved, spec.key) != getattr(defaults, spec.key)
    }
    return frozenset(pinned)


def with_defaults(config: NexusConfig) -> NexusConfig:
    """A defensive copy helper (kept for tests)."""
    result = replace(config)
    if hasattr(config, '_explicit_fields'):
        result._explicit_fields = config._explicit_fields
    if hasattr(config, '_legacy_settings_provenance'):
        result._legacy_settings_provenance = config._legacy_settings_provenance
    return result
