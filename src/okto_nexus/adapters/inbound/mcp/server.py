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
from ...outbound.file.store import WorkspaceFileStore
from ...outbound.sqlite.artifacts_repo import SqliteArtifactRepo
from ...outbound.sqlite.connection import ConnectionFactory
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

#: Server-level guidance surfaced to connecting agents (FastMCP ``instructions``).
#: Covers how to choose a communication channel, replying directly by default,
#: starting a monitor when awaiting a reply, and the blocking-vs-follower
#: monitoring mechanics.
SERVER_INSTRUCTIONS = """\
Okto Nexus - local agent coordination bus (workspace-scoped; pass \
project_root). Agents are global identities - discover them with agent_list, \
and the capabilities they advertise with capability_list.

YOUR IDENTITY & CONNECTION. You are connected over MCP streamable HTTP and \
authenticated by the API key in your connection URL (/mcp?api_key=nxs_...): \
that key IS your agent identity, created by the operator on the dashboard. \
Use that agent_id consistently as from_agent_id / agent_id in every call. \
EVERYTHING you need is exposed as MCP tools on THIS connection - never shell \
out to the okto-nexus CLI, never spawn helper processes, never try to attach \
a stdio server: the hub is already running and this session is your only \
required channel. (The legacy stdio mode exists solely for hosts that launch \
the server themselves; if you are reading this over HTTP it does not concern \
you.)

PRE-FLIGHT - run this EXACT sequence on your FIRST turn, in this order, \
BEFORE starting whatever the user asked. It is cheap and idempotent; every \
agent bootstrapping the same way is what makes the swarm predictable:
  1. IDENTITY - agent_whoami(): your agent_id, operator-assigned role, \
capabilities and the permissions in effect. Use that agent_id everywhere. \
Only if you must advertise NEW capabilities for routing, follow with \
agent_register on your OWN id (self-only: minting/modifying other identities \
returns PERMISSION_DENIED - identities are created on the dashboard).
  2. PRESENCE - workspace_resolve(project_root=<cwd>) then \
session_open(agent_id=<you>, workspace_id=<resolved>). Without an open, \
heartbeat-fresh session you are NOT in the broadcast audience (messages to \
"everyone" silently skip you) and the dashboard shows you offline. Keep \
session_heartbeat fresh between turns; store the returned session_secret.
  3. BACKLOG - inbox_count(agent_id=<you>); if anything is pending, \
inbox_pull and triage what accumulated while you were offline (redeliveries \
included), then inbox_ack what you handled. Never skip this: senders are \
already tracking these deliveries.
  4. MONITOR - anchor first: event_cursor(stream="workspace") returns the \
log's current end, so you only ever see events from NOW on. Then, if your \
harness supports background/parallel calls, run an \
event_wait(timeout_seconds=N, cursor=<anchor>) long-poll loop; otherwise \
poll inbox_count + event_get(cursor=<anchor>) between turns, advancing the \
cursor.
THEN follow the user's instructions - communicate per the rules below. When \
your work is finished for good, session_close (presence must reflect \
reality).

HOW TO COMMUNICATE - prefer the most targeted, least noisy channel:

1) DIRECT MESSAGE (default, preferred). message_create with \
target={"strategy":"direct","agent_id":"<recipient>"}. Most efficient, least \
noise, no spurious work. ALWAYS reply DIRECTLY to whoever messaged you (target \
their from_agent_id) unless you explicitly mean to broadcast or hand off. \
Examples: answering a question; acknowledging; a 1:1 follow-up; returning a \
result to the requester.

2) HANDOFF (when exactly ONE free agent should take the work). handoff_create \
with a capability/role/broadcast target: every eligible agent SEES it but only \
the first to handoff_claim gets it (others get HANDOFF_ALREADY_CLAIMED); an \
unfinished claim's lease expires and the work returns to the pool. Use for a \
dispatchable task to a pool of capable agents. Example: "OCR this scan" -> \
handoff target {"strategy":"capability","capability":"ocr"} (find the \
capability via capability_list first); one free OCR worker claims and finishes.

3) BROADCAST (last resort). message_create with NO target. Two valid uses: (a) \
DISSEMINATE instructive/contextual information to everyone - announcements, \
conventions, status, shared decisions; (b) open-ended DISCOVERY when you do NOT \
yet know who to ask - poll the group to locate the right agent. Examples: "Who \
is responsible for application X?" or "Who is impacted by change Y in application \
XYZ?" - only the relevant agents answer, and they reply DIRECTLY to you. Do NOT \
broadcast actionable WORK requests: an undirected "do X" can trigger UNWANTED \
PARALLEL WORK (every eligible agent may act on it). Once discovery identifies the \
owner, switch to a direct message (or a handoff if it is dispatchable work).

CHANNELS are lightweight ORGANIZATIONAL LABELS, not access boundaries and not a \
delivery mechanism. No membership or ACL: any agent in the workspace can read and \
post to ANY channel. They only TAG a message by topic/workstream; they do NOT \
decide who receives it - that is the message TARGET (above). Only "general" \
exists by default; create the channels you need with channel_create (idempotent \
by name) and discover them with channel_list.

YOUR INBOX (how you receive messages). Messages addressed to you are delivered \
to your GLOBAL inbox and stay there until you read them - no cursor, no index, \
regardless of which workspace they were sent in. The flow:
  * inbox_count(agent_id=<you>) - cheap between-turns check; if unread > 0, pull.
  * inbox_pull(agent_id=<you>) - returns your unread messages WITH their body and
    marks them in-flight (leased).
  * inbox_ack(agent_id=<you>, message_ids=[...]) - once handled, move them to
    history. Unacked messages are REDELIVERED (at-least-once), so nothing is lost
    if you stop mid-handling. inbox_peek is a non-destructive look; inbox_history
    is the read archive.
RECOMMENDED RECEPTION LOOP: inbox_count between turns (cheap) -> inbox_pull when \
unread > 0 -> inbox_ack after you finish processing. \
After sending a message that expects a reply, just check your inbox on a later \
turn - the reply lands there (no fire-and-forget, no polling a cursor).

DELIVERY & READ RECEIPTS (how you KNOW a message arrived / was read). \
message_create's response is ITSELF the delivery confirmation: ``recipients`` \
names exactly who got it in their inbox (the fan-out commits atomically with \
the send) and ``delivered_count`` totals it. From then on, two complementary \
trackers:
  * PULL - message_status(message_id=...) returns the per-recipient lane: \
unread (queued), delivered (recipient pulled it, in-flight), read \
(acknowledged, with read_at), parked (dead-letter). Check it INSTEAD of \
re-sending when a recipient seems silent.
  * PUSH - the inbox emits receipt events visible ONLY to you, the sender: \
``message.delivered`` when a recipient pulls your message and ``message.read`` \
when they acknowledge it (atomic with the lane transition). Await one with \
event_wait, e.g. filters={"type": "message.read"} and match \
payload.message_id - no need to poll message_status. Delivery is \
at-least-once: a redelivery after a lease expiry emits message.delivered \
again (payload.recipient_agent_id tells you who).
  * INBOX receipt (default ON; the operator can opt out via the \
inbox_read_receipts setting) - when a recipient acknowledges your message \
you ALSO receive a compact notification in YOUR OWN inbox: body kind \
"message.read_receipt" with read_by, read_at and the message_ids (grouped \
per sender). It is informational - inbox_ack it and move on; do NOT reply. \
Receipts never generate receipts, so acknowledging one is always terminal.

LISTENING FOR EVENTS (observability vs delivery). event_get/event_wait OBSERVE \
the bus (audit/monitoring of message.created, handoff.*, session.* events); \
they are NOT how you receive messages addressed to you - that is the inbox \
above. To register a listener, use the MCP tools on THIS connection - do NOT \
run `okto-nexus tail` or any other CLI command (that is an operator console \
tool, not an agent surface; the dashboard already streams events live for \
humans). Anchor with event_cursor first (pre-flight step 4), then:
  * Snapshot polling (default): event_get between turns, advancing cursor -> \
next_cursor. Non-blocking, fits single-threaded loops.
  * Long-poll listener: event_wait(timeout_seconds=N>0, cursor=...) parks the \
call until a matching event arrives or N elapses (clamped to the server \
ceiling), then returns the page; loop on next_cursor. This is an ordinary \
streamable-HTTP call - safe to use as a wait primitive when you EXPECT an \
event.
  * Targeted wait: event_wait with filters (e.g. {"type": \
"handoff.completed", "handoff_id": ...}) and a short timeout to await one \
specific outcome.

PERMISSIONS. The operator may restrict what your identity can do (direct \
sends, broadcasts, channel posts, handoff create/work/cancel, rate limits, \
peer allowlists). A blocked call returns ok:false with code \
PERMISSION_DENIED and details.required_permission naming the exact flag. Do \
NOT retry or work around it - adapt (e.g. reply directly instead of \
broadcasting) or report that the operator must grant the flag on the \
dashboard (Agents -> Permissions).

ERRORS & RETRIES. Every tool answers with {ok:true,data} or \
{ok:false,error:{code,message,...}}. A DB_ERROR with retryable=true is transient \
(e.g. the SQLite store was briefly busy): retrying the SAME call after a short \
backoff (~0.5-2s) is safe. A MIGRATED error means the tool was replaced - the \
message names the exact replacement tool and parameters; switch to it, do NOT \
retry the old call. PERMISSION_DENIED is a policy decision, not an error to \
retry.
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
SURFACE_REVISION = 10


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
    return Deps(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=repos,
        event_emitter=emitter,
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
        """Report the server's versions: package_version, schema_version, surface_revision.

        Call this when behaviour seems to disagree with your cached tool
        schemas. ``surface_revision`` increments on every change to the tool
        surface (names/parameters/defaults/semantics); ``schema_version`` is
        the highest applied DB migration; ``package_version`` is the installed
        distribution version ("dev" for a source checkout).
        """
        return {
            "package_version": _package_version(),
            "schema_version": _schema_version(deps.connection_factory),
            "surface_revision": SURFACE_REVISION,
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
