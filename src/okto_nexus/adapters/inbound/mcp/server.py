"""MCP stdio server (inbound adapter).

Bootstrap is FAIL-CLOSED and ordered:

1. ``load_config``        - resolve config (CONFIG_ERROR on bad input)
2. ensure home dir        - via ``ConnectionFactory`` construction
3. ``ConnectionFactory``  - configured SQLite connections
4. ``MigrationRunner``    - apply pending migrations (MIGRATION_ERROR on failure)
5. register tools         - ONLY after the store is migrated and healthy

Tools are AUTO-DISCOVERED: every module under
``okto_nexus.adapters.inbound.mcp.tools`` that exposes
``def register(server, deps) -> None`` is invoked with the live MCP server and
a :class:`Deps` container. With zero tool modules present, the server still
starts and registers nothing. Server-level meta tools (``nexus_info``) are
registered separately by :func:`register_meta_tools`.

The MCP SDK (``mcp``) is imported LAZILY (only inside :func:`main` /
:func:`create_server`) so that importing this module - and the domain /
application layers - never requires the SDK to be installed.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import pkgutil
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping

from ....application.ports import Clock, ConnectionFactory as ConnectionFactoryPort
from ....application.ports import EventEmitter, Repos
from ....config import NexusConfig, load_config
from ....envelope import tool_envelope
from ....errors import OktoNexusError
from ...outbound.clock import SystemClock
from ...outbound.embedding import EmbeddingResolution, resolve_embedding_provider
from ...outbound.file.store import WorkspaceFileStore
from ...outbound.sqlite.artifacts_repo import SqliteArtifactRepo
from ...outbound.sqlite.connection import ConnectionFactory
from ...outbound.sqlite.embeddings_repo import SqliteMessageVectorStore
from ...outbound.sqlite.events_repo import SqliteEventEmitter, SqliteEventRepo
from ...outbound.sqlite.handoff_repo import SqliteHandoffRepo, SqliteTaskRepo
from ...outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from ...outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from ...outbound.sqlite.migrations import MigrationRunner
from ...outbound.sqlite.permissions_repo import SqlitePresetRepo
from . import tools as _tools_pkg
from .resources import register_resources, resource_versions

#: Server-level guidance surfaced to connecting agents (FastMCP ``instructions``).
#: Covers how to choose a communication channel, replying directly by default,
#: the canonical pre-flight, the inbox reception loop, and how a
#: monitoring-capable harness (e.g. Claude Code) builds a listener - a
#: backgrounded ``event_wait`` long-poll on THIS connection - plus the
#: anti-patterns it must avoid (curl at the REST API, ``okto-nexus tail``, a
#: standalone monitor process).
SERVER_INSTRUCTIONS = """\nOkto Nexus - local agent coordination bus (workspace-scoped; pass project_root). Agents are global identities - discover them with agent_list and their advertised capabilities with capability_list. DEEP reference docs live in MCP resources (okto-nexus://reference/...); read them on demand. This inline block keeps only what you need to act correctly on the first try.

YOUR IDENTITY. You connect over MCP streamable HTTP; the API key in your URL (/mcp?api_key=nxs_...) IS your agent identity, created by the operator on the dashboard. Use that agent_id consistently as from_agent_id / agent_id in every call. EVERYTHING you need is exposed as MCP tools on THIS connection - never shell out to the okto-nexus CLI, spawn helper processes, or attach a stdio server.

PRE-FLIGHT - run on your FIRST turn, in order, BEFORE the user's task (cheap, idempotent):
  1. agent_whoami() - your agent_id, role, capabilities, permissions. Use that agent_id everywhere.
  2. workspace_resolve(project_root=<cwd>) then session_open(agent_id=<you>, workspace_id=<resolved>). Pass your session_id + session_secret on every authenticated verb - each advances your heartbeat, so working keeps you present (only heartbeat-fresh sessions receive broadcasts and show online); reserve an explicit session_heartbeat for IDLE turns. Store the returned session_secret.
  3. inbox_count(agent_id=<you>); if unread > 0, inbox_pull and triage the backlog, then inbox_ack what you handled.
  4. event_cursor(stream="workspace") to anchor at NOW, then monitor via event_wait (background long-poll) or event_get polling, advancing the cursor.
Full detail: resource okto-nexus://reference/preflight. When finished for good, session_close.

COMMUNICATE - prefer the most targeted, least noisy channel:
  - DIRECT (default, preferred): message_create with target={"strategy":"direct","agent_id":"<recipient>"}. ALWAYS reply directly to whoever messaged you (target their from_agent_id).
  - HANDOFF: handoff_create with a capability/role/broadcast target when exactly ONE free agent should claim dispatchable work (first to handoff_claim wins).
  - BROADCAST (last resort): message_create with NO target - announcements or open-ended discovery only, NEVER actionable work (it triggers unwanted parallel work).
HOW YOU RECEIVE: messages addressed to you land in your GLOBAL inbox - inbox_count -> inbox_pull -> inbox_ack. event_get/event_wait are OBSERVABILITY, not message delivery. Channels are organizational labels, not ACLs and not delivery - the message TARGET decides who receives it. Full detail (channels, delivery/read receipts, reception loop): okto-nexus://reference/communication. Monitoring/listener patterns + anti-patterns (no curl, no CLI tail, no separate monitor process): okto-nexus://reference/monitoring.

PERMISSIONS. The operator may restrict your identity (direct sends, broadcasts, channel posts, handoff create/work/cancel, rate limits, peer allowlists). A blocked call returns ok:false with code PERMISSION_DENIED and details.required_permission. Do NOT retry or work around it - adapt (e.g. reply directly instead of broadcasting) or report that the operator must grant the flag (dashboard Agents -> Permissions).

ERRORS & RETRIES. Every tool answers {ok:true,data} or {ok:false,error:{code,message,...}}. A DB_ERROR with retryable=true is transient - retry the SAME call after a short backoff (~0.5-2s). A MIGRATED error means the tool was replaced; the message names the exact replacement - switch to it, do NOT retry the old call. PERMISSION_DENIED is a policy decision, not a retryable error.
"""

#: Monotonic revision of the MCP tool SURFACE (tool names, parameters,
#: defaults, semantics). Bump by 1 on EVERY surface change so agents can
#: detect stale cached schemas via ``nexus_info``. Started at 2 with the
#: post-S3 safe-by-default surface. 3 = M9 unified target grammar (mixed
#: requires non-empty rules, no null/broadcast sub-rules - everywhere) +
#: shared pagination grammar (integer-string cursor/limit now accepted).
#: 4 = M6 presence (session_open returns session_secret; broadcast audience is
#: heartbeat-fresh sessions with explicit excluded_stale) + M10 trust
#: (session_id/session_secret parameters on message_create,
#: handoff_claim/complete/reject, inbox_pull/ack/extend; trust_mode knob).
#: 5 = event_get/event_wait ``stream`` description no longer advertises the
#: removed ``task`` stream (doc-only fix; ``VALID_STREAMS`` semantics
#: unchanged - a cached schema saying "task" was prescribing INVALID_STREAM).
#: 6 = v2 documentation overhaul: SERVER_INSTRUCTIONS now describe the
#: streamable-HTTP connection (key = identity), the bootstrap sequence, the
#: listener patterns (event_wait long-poll / event_get polling - explicitly
#: NOT `okto-nexus tail`, which older docs prescribed and agents were trying
#: to spawn), and the PERMISSION_DENIED policy envelope (migration 011).
#: 7 = identity lockdown: NEW agent_whoami tool (profile derived from the
#: API key); agent_register is now SELF-ONLY on authenticated connections
#: (minting new identities / rewriting another agent's profile returns
#: PERMISSION_DENIED; identities are created on the dashboard).
#: 8 = delivery/read receipts: inbox_pull emits ``message.delivered`` and
#: inbox_ack emits ``message.read`` (sender-visible, atomic with the lane
#: transition); inbox_ack's response gains ``read_message_ids``.
#: 9 = canonical PRE-FLIGHT: the instructions now prescribe one exact
#: bootstrap (identity -> presence -> backlog -> monitor) so every agent
#: initialises uniformly; NEW event_cursor tool (O(1) end-of-stream anchor
#: so a monitor starts from NOW instead of paging history).
#: 10 = inbox read receipts (opt-out): inbox_ack additionally lands a
#: "message.read_receipt" notification in each sender's inbox (grouped per
#: sender; receipts never generate receipts; disable with the
#: inbox_read_receipts setting).
#: 11 = monitoring guidance for capable harnesses: SERVER_INSTRUCTIONS now
#: spell out that a listener is just a BACKGROUNDED event_wait long-poll on
#: THIS MCP connection (Claude Code & friends) and enumerate the anti-patterns
#: to avoid - curl/raw HTTP at /api/v1, /mcp or the dashboard SSE; `okto-nexus
#: tail` or any CLI; a standalone Python/Node monitor process; spawning any
#: helper process. Doc-only (no tool/parameter/semantics change).
#: 12 = token-reduction Frente 1 (residente): the long prose moved OUT of
#: SERVER_INSTRUCTIONS into MCP resources (okto-nexus://reference/preflight,
#: /communication, /monitoring), read on demand; the inline block keeps only
#: the actionable minimum (identity, 4-step pre-flight, the 3 comm modes,
#: permissions, errors) + pointers. nexus_info now also reports
#: resource_versions for stale-cache detection. Descriptions/instructions only
#: - no tool/parameter/semantics change.
SURFACE_REVISION = 12


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


def build_repos(clock: Clock) -> tuple[Repos, EventEmitter]:
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
        files=WorkspaceFileStore(),
        presets=SqlitePresetRepo(clock),
        message_vectors=SqliteMessageVectorStore(clock),
    )
    emitter = SqliteEventEmitter(events_repo)
    return repos, emitter


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
    factory = ConnectionFactory(config)  # ensures home_dir exists
    MigrationRunner(factory).apply()  # idempotent; MIGRATION_ERROR on failure
    clock = SystemClock()
    repos, emitter = build_repos(clock)
    # Resolve the embedding capability ONCE from the configured mode (off /
    # stub / local). The model singleton is lazy, so this stays cheap even for
    # ``local``; an absent extra degrades to the stub with search disabled.
    embedding = resolve_embedding_provider(config.embedding_mode)
    return Deps(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=repos,
        event_emitter=emitter,
        embedding=embedding,
    )


def register_tools(server: Any, deps: Deps) -> list[str]:
    """Discover and register every tool module; return the module names registered.

    A tool module participates by exposing ``register(server, deps) -> None``.
    """
    registered: list[str] = []
    prefix = _tools_pkg.__name__ + "."
    for module_info in pkgutil.iter_modules(_tools_pkg.__path__, prefix):
        module = importlib.import_module(module_info.name)
        register = getattr(module, "register", None)
        if callable(register):
            register(server, deps)
            registered.append(module_info.name)
    return registered


def _package_version() -> str:
    """Installed distribution version; ``"dev"`` for a plain source checkout."""
    try:
        return importlib.metadata.version("okto-nexus")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def _schema_version(connection_factory: ConnectionFactoryPort) -> int:
    """Highest applied migration version per the ``schema_migrations`` ledger.

    ``0`` means no migration has been applied (bootstrap guarantees this never
    happens on a healthy server, as migrations run before tools register).
    """
    conn = connection_factory.get_connection()
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0]) if row is not None and row[0] is not None else 0
    finally:
        conn.close()


def register_meta_tools(server: Any, deps: Deps) -> None:
    """Register server-level meta tools (currently ``nexus_info``).

    These live in the composition root rather than a ``tools/`` module because
    they describe the WHOLE server (surface revision, schema ledger), not any
    one slice.
    """

    @server.tool()
    @tool_envelope
    def nexus_info() -> dict[str, Any]:
        """Report server versions: package_version, schema_version, surface_revision, resource_versions (uri->version map, for stale-cache detection). Call when behaviour disagrees with cached schemas."""
        return {
            "package_version": _package_version(),
            "schema_version": _schema_version(deps.connection_factory),
            "surface_revision": SURFACE_REVISION,
            "resource_versions": resource_versions(),
        }


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
    from ....application.retention import AUTO_PRUNE_MAX_BATCHES, RetentionService

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


def create_server(deps: Deps) -> Any:
    """Create the MCP server, register tools, and return the server instance.

    Imports the MCP SDK lazily; raises ``ImportError`` if it is missing.
    """
    from mcp.server.fastmcp import FastMCP  # lazy import: SDK only needed here

    server = FastMCP("okto-nexus", instructions=SERVER_INSTRUCTIONS)
    register_tools(server, deps)
    register_meta_tools(server, deps)
    register_resources(server)  # MCP resources: on-demand reference docs (Frente 1)
    return server


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point. Returns a process exit code.

    The first token selects the mode: ``tail`` dispatches to the line-delimited
    event-log follower and ``admin`` to the maintenance commands (CLI
    subcommands); anything else runs the MCP stdio server. The dispatch happens
    BEFORE ``load_config`` because the config parser is flags-only and rejects
    positionals by design.
    """
    args = list(sys.argv[1:]) if argv is None else list(argv)

    if args and args[0] == "tail":
        from ..cli.tail import run_tail  # lazy: avoids an import cycle with this module

        return run_tail(args[1:])

    if args and args[0] == "admin":
        from ..cli.admin import run_admin  # lazy: avoids an import cycle too

        return run_admin(args[1:])

    if args and args[0] == "serve":
        from ..cli.serve import run_serve  # lazy: FastAPI/uvicorn optional

        return run_serve(args[1:])

    if args and args[0] in ("-h", "--help", "help"):
        print(
            "okto-nexus - local agent coordination bus\n\n"
            "Usage:\n"
            "  okto-nexus serve [options]   Start the HTTP hub "
            "(MCP + REST + dashboard); see `okto-nexus serve --help`\n"
            "  okto-nexus tail [options]    Stream the event log as NDJSON "
            "(operator console)\n"
            "  okto-nexus admin <cmd>       Maintenance (prune, issue-keys)\n"
            "  okto-nexus [options]         Run the legacy stdio MCP server "
            "(prefer `serve`)\n"
        )
        return 0

    try:
        deps = bootstrap(os.environ, args)
    except OktoNexusError as exc:
        print(
            f"[okto-nexus] bootstrap failed: {exc.code}: {exc.message}",
            file=sys.stderr,
        )
        return 1

    # Optional stdio identity-by-key (FR8): when OKTO_NEXUS_API_KEY is set,
    # the session's identity derives from the key exactly as on HTTP, and an
    # invalid key FAILS CLOSED (no silent fallback to the open V1 mode). The
    # env absent keeps the V1 contract byte-for-byte (rule br_b89c1d77).
    stdio_key = os.environ.get("OKTO_NEXUS_API_KEY")
    if stdio_key:
        from ....application.auth import AgentKeyAuthService
        from ..http.identity_ctx import current_agent

        auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
        with deps.connection_factory.unit_of_work() as uow:
            agent = auth.resolve(uow, stdio_key)
        if agent is None:
            print(
                "[okto-nexus] OKTO_NEXUS_API_KEY is set but does not resolve "
                "to an active agent. Fix or unset the variable (fail-closed; "
                "the open V1 mode is NOT used as a fallback).",
                file=sys.stderr,
            )
            return 1
        current_agent.set(agent)
        print(
            f"[okto-nexus] stdio session authenticated as agent "
            f"'{agent.agent_id}' via OKTO_NEXUS_API_KEY.",
            file=sys.stderr,
        )

    maybe_auto_prune(deps)  # no-op unless auto_prune_on_start=true; best-effort

    try:
        server = create_server(deps)
    except ImportError:
        print(
            "[okto-nexus] The 'mcp' SDK is not installed. "
            "Install it with: pip install 'mcp>=1.0' (or 'pip install okto-nexus').",
            file=sys.stderr,
        )
        return 1

    server.run()  # stdio transport by default
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
