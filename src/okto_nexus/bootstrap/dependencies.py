"""Fail-closed Nexus bootstrap shared by HTTP and CLI.

No transport starts on import.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping

from okto_nexus.application.runtime_admission_fence import RuntimeAdmissionFence
from okto_nexus.application.approvals import ApprovalService, seed_operator_agent
from okto_nexus.application.artifacts import externalize_legacy_artifacts
from okto_nexus.application.capabilities import seed_capability_catalog
from okto_nexus.application.comm_preset_catalog import seed_comm_presets
from okto_nexus.application.ports import Clock, EventEmitter, Repos
from okto_nexus.application.ports import ConnectionFactory as ConnectionFactoryPort
from okto_nexus.application.telemetry.ports import TelemetryPort
from okto_nexus.application.telemetry.service import TelemetryService
from okto_nexus.config import NexusConfig, load_config
from okto_nexus.errors import OktoNexusError
from okto_nexus.adapters.outbound.clock import SystemClock
from okto_nexus.adapters.outbound.embedding import EmbeddingResolution, resolve_embedding_provider
from okto_nexus.adapters.outbound.file.artifacts import LocalArtifactStore
from okto_nexus.adapters.outbound.file.store import WorkspaceFileStore
from okto_nexus.adapters.outbound.sqlite.approvals_repo import SqliteApprovalRepo
from okto_nexus.adapters.outbound.sqlite.artifacts_repo import SqliteArtifactRepo
from okto_nexus.adapters.outbound.sqlite.capability_catalog_repo import SqliteCapabilityCatalogRepo
from okto_nexus.adapters.outbound.sqlite.comm_preset_repo import (
    SqliteAgentCommBindingRepo,
    SqliteCommPresetRepo,
)
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.embeddings_repo import SqliteMessageVectorStore
from okto_nexus.adapters.outbound.sqlite.events_repo import SqliteEventEmitter, SqliteEventRepo
from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from okto_nexus.adapters.outbound.sqlite.governance_repo import SqliteGovernanceRepo
from okto_nexus.adapters.outbound.sqlite.guardrails_repo import (
    SqliteAgentGroupRepo,
    SqliteGuardrailAssignmentRepo,
    SqliteGuardrailRepo,
)
from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo, SqliteTaskRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.memory_repo import (
    SqliteMemoryRepo,
    SqliteMemoryVectorStore,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.adapters.outbound.sqlite.permissions_repo import SqlitePresetRepo
from okto_nexus.adapters.outbound.sqlite.policy_repo import (
    SqliteAgentPolicyBindingRepo,
    SqlitePolicyRepo,
)
from okto_nexus.adapters.outbound.sqlite.poll_tokens_repo import SqlitePollTokenRepo
from okto_nexus.adapters.outbound.sqlite.tag_catalog_repo import SqliteTagCatalogRepo
from okto_nexus.adapters.outbound.telemetry import LocalTelemetryEventStore, NexusTelemetryHttpSink
from okto_nexus.adapters.outbound.telemetry.event_emitter import TelemetryEventEmitter
from okto_nexus.adapters.outbound.telemetry.local_store import resolve_metrics_dir

@dataclass
class Deps:
    """Dependency container handed to every tool's ``register`` function.

    Attributes
    ----------
    config:
        The resolved :class:`NexusConfig`.
    connection_factory:
        Factory for configured SQLite connections / units of work.
    clock:
        :class:`Clock` implementation (``SystemClock`` in production).
    repos:
        :class:`Repos` registry; fields are populated as slices land.
    event_emitter:
        :class:`EventEmitter` facade (``None`` until the events slice lands).
    """

    config: NexusConfig
    connection_factory: ConnectionFactoryPort
    clock: Clock
    repos: Repos = field(default_factory=Repos)
    event_emitter: EventEmitter | None = None
    # Resolved embedding capability (provider + search/degraded flags) for the
    # configured ``embedding_mode``. ``None`` until bootstrap wires it.
    embedding: EmbeddingResolution | None = None
    # Shared HITL approval service (spec 2948b2a2): ONE instance per process so
    # the executors each slice registers (messages/handoff) are visible to the
    # decision path regardless of transport. ``None`` until bootstrap wires it.
    approvals: ApprovalService | None = None
    # Optional, best-effort anonymous usage telemetry facade. Disabled by
    # default; when enabled, adapters record bounded metadata only.
    telemetry: TelemetryPort | None = None
    native_decisions: Any = None
    runtime_admission_fence: RuntimeAdmissionFence = field(default_factory=RuntimeAdmissionFence)


def build_repos(clock: Clock, config: NexusConfig) -> tuple[Repos, EventEmitter]:
    """Instantiate every concrete outbound adapter and the event emitter.

    This is the single composition root for the persistence layer. Each slice's
    tool module ALSO knows how to wire its own repos idempotently, but doing it
    here once - BEFORE any tool registers - guarantees that:

    * every service shares ONE concrete instance per port, and
    * the :class:`EventEmitter` is already present when slices that emit audit
      events (artifacts/handoff/identity/messages) build their services,
      regardless of the alphabetical tool-discovery order.

    Returns the populated :class:`Repos` registry and the shared emitter.
    """
    events_repo = SqliteEventRepo(clock)
    repos = Repos(
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        events=events_repo,
        channels=SqliteChannelRepo(clock),
        messages=SqliteMessageRepo(clock),
        deliveries=SqliteMessageDeliveryRepo(clock),
        tasks=SqliteTaskRepo(clock),
        handoffs=SqliteHandoffRepo(clock),
        artifacts=SqliteArtifactRepo(clock),
        artifact_store=LocalArtifactStore(config.home_dir / "artifacts"),
        files=WorkspaceFileStore(),
        presets=SqlitePresetRepo(clock),
        message_vectors=SqliteMessageVectorStore(clock),
        memories=SqliteMemoryRepo(clock),
        memory_vectors=SqliteMemoryVectorStore(clock),
        tag_catalog=SqliteTagCatalogRepo(clock),
        capability_catalog=SqliteCapabilityCatalogRepo(clock),
        governance=SqliteGovernanceRepo(clock),
        policies=SqlitePolicyRepo(clock),
        policy_bindings=SqliteAgentPolicyBindingRepo(clock),
        agent_groups=SqliteAgentGroupRepo(clock),
        guardrails=SqliteGuardrailRepo(clock),
        guardrail_assignments=SqliteGuardrailAssignmentRepo(clock),
        comm_presets=SqliteCommPresetRepo(clock),
        comm_bindings=SqliteAgentCommBindingRepo(clock),
        approvals=SqliteApprovalRepo(),
        poll_tokens=SqlitePollTokenRepo(clock),
    )
    emitter = SqliteEventEmitter(events_repo)
    return repos, emitter


def build_telemetry(config: NexusConfig, clock: Clock) -> TelemetryPort:
    """Build the telemetry facade and its local/HTTP outbound adapters."""
    store = LocalTelemetryEventStore(resolve_metrics_dir(config))
    sink = NexusTelemetryHttpSink(
        config=config,
        clock=clock,
        app_version=_package_version(),
    )
    return TelemetryService(
        config=config,
        store=store,
        sink=sink,
        clock=clock,
        app_version=_package_version(),
    )


def bootstrap(
    env: Mapping[str, str] | None = None,
    argv: list[str] | None = None,
) -> Deps:
    """Run the fail-closed bootstrap and return a ready :class:`Deps`.

    Does NOT import the MCP SDK, so it is safe to call from tests. All concrete
    repositories and the shared event emitter are wired here so that tool
    auto-discovery only ever REUSES these instances (its idempotent guards see
    them already present), giving every slice a single coherent backing store.
    """
    env = env if env is not None else os.environ
    config = load_config(env, argv)
    config._connection_key_ttl_pinned = config.connection_key_ttl_seconds != 86400
    factory = ConnectionFactory(config)  # ensures home_dir exists
    MigrationRunner(factory).apply()  # idempotent; MIGRATION_ERROR on failure
    ensure_execution_installation(factory)
    clock = SystemClock()
    repos, emitter = build_repos(clock, config)
    externalize_legacy_artifacts(
        connection_factory=factory,
        artifacts=repos.artifacts,
        artifact_store=repos.artifact_store,
    )
    telemetry = build_telemetry(config, clock)
    emitter = TelemetryEventEmitter(emitter, telemetry)
    # Transition seed (migration 014): absorb every announced capability into
    # the central catalog, idempotently, BEFORE any fail-closed gate can run -
    # the invariant "owned => registered" is what keeps existing agents
    # (re-)registering without error under the new regime.
    with factory.unit_of_work() as uow:
        seed_capability_catalog(
            uow, catalog=repos.capability_catalog, agents=repos.agents
        )
        # First-class operator identity (spec 2948b2a2 FR6/BR4): seeded
        # unconditionally BEFORE any tool registers; create-if-missing only,
        # so an existing operator (role, permissions, key) is never touched.
        seed_operator_agent(uow, agents=repos.agents)
        # Built-in communication presets (spec 6f961722): a starter style
        # vocabulary, create-if-missing only, so an operator's edits/renames
        # survive a restart and re-running never duplicates or bumps a version.
        seed_comm_presets(uow, presets=repos.comm_presets)
    # Resolve the embedding capability ONCE from the configured mode (off /
    # stub / local). The model singleton is lazy, so this stays cheap even for
    # ``local``; an absent extra degrades to the stub with search disabled.
    embedding = resolve_embedding_provider(config.embedding_mode)
    # ONE approval service per process (spec 2948b2a2): every slice injects
    # this instance, so the executors registered by messages/handoff wiring
    # are the ones the operator decision path re-executes through.
    approvals = ApprovalService(
        connection_factory=factory,
        approvals=repos.approvals,
        clock=clock,
        config=config,
        event_emitter=emitter,
    )
    deps = Deps(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=repos,
        event_emitter=emitter,
        embedding=embedding,
        approvals=approvals,
        telemetry=telemetry,
    )
    from .execution_authority import build_execution_access
    from ..application.execution_binding_approvals import (
        BINDING_APPROVAL_ACTION, ExecutionBindingApprovals,
    )
    approvals.register_transactional_decision(
        BINDING_APPROVAL_ACTION,
        ExecutionBindingApprovals(access=build_execution_access(deps)).decide)
    from importlib.util import find_spec
    if find_spec("nexus_connector_core") is not None:
        from ..application.execution_native_decisions import ExecutionNativeDecisions
        from ..application.execution_native_requests import NATIVE_APPROVAL_ACTION
        deps.native_decisions = ExecutionNativeDecisions(
            factory=factory, access=build_execution_access(deps), approvals=approvals)
        approvals.register_transactional_decision(NATIVE_APPROVAL_ACTION, deps.native_decisions.decide)
    return deps


def _package_version() -> str:
    """Installed distribution version; ``"dev"`` for a plain source checkout."""
    try:
        return importlib.metadata.version("okto-nexus")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def maybe_auto_prune(deps: Deps) -> dict[str, Any] | None:
    """Opportunistic retention reaper, gated by ``auto_prune_on_start``.

    When the knob (default ``False``; env ``OKTO_NEXUS_AUTO_PRUNE_ON_START`` /
    ``--auto-prune-on-start true``) is enabled, server startup runs ONE
    bounded, incremental retention pass (``AUTO_PRUNE_MAX_BATCHES`` batches
    per table) using the configured windows - cheap and predictable, never a
    full drain; backlog converges across restarts or via ``okto-nexus admin
    prune``. BEST-EFFORT by design: a failure is reported to stderr and
    startup proceeds (retention must never keep the bus down). Returns the
    prune report, or ``None`` when disabled/failed.
    """
    if not deps.config.auto_prune_on_start:
        return None
    from okto_nexus.application.retention import AUTO_PRUNE_MAX_BATCHES, RetentionService

    try:
        report = RetentionService.from_deps(deps).prune(
            max_batches=AUTO_PRUNE_MAX_BATCHES
        )
    except OktoNexusError as exc:
        print(
            f"[okto-nexus] auto-prune skipped: {exc.code}: {exc.message}",
            file=sys.stderr,
        )
        return None
    print(
        f"[okto-nexus] auto-prune deleted {report['total_deleted']} row(s)",
        file=sys.stderr,
    )
    return report


