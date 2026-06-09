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
starts and registers nothing.

The MCP SDK (``mcp``) is imported LAZILY (only inside :func:`main` /
:func:`create_server`) so that importing this module - and the domain /
application layers - never requires the SDK to be installed.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping

from ....application.ports import Clock, ConnectionFactory as ConnectionFactoryPort
from ....application.ports import EventEmitter, Repos
from ....config import NexusConfig, load_config
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
from ...outbound.sqlite.messages_repo import SqliteChannelRepo, SqliteMessageRepo
from ...outbound.sqlite.migrations import MigrationRunner
from . import tools as _tools_pkg


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
        tasks=SqliteTaskRepo(clock),
        handoffs=SqliteHandoffRepo(clock),
        artifacts=SqliteArtifactRepo(clock),
        files=WorkspaceFileStore(),
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


def create_server(deps: Deps) -> Any:
    """Create the MCP server, register tools, and return the server instance.

    Imports the MCP SDK lazily; raises ``ImportError`` if it is missing.
    """
    from mcp.server.fastmcp import FastMCP  # lazy import: SDK only needed here

    server = FastMCP(
        "okto-nexus",
        instructions=(
            "Local agent coordination bus (workspace-scoped; pass project_root). "
            "MONITORING: event_wait/message_wait are BLOCKING long-polls - "
            "timeout_seconds > 0 parks the calling turn until an event/message "
            "arrives or the timeout expires. To watch the bus WITHOUT blocking, "
            "run the CLI follower detached and react to each NDJSON line, e.g.:\n"
            "  okto-nexus tail --project-root <path> --agent-id <you> --from latest\n"
            "Or poll in-loop with timeout_seconds=0 (a non-blocking snapshot; "
            "advance cursor -> next_cursor). A future SSE/HTTP transport will "
            "replace polling with server push."
        ),
    )
    register_tools(server, deps)
    return server


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point. Returns a process exit code.

    The first token selects the mode: ``tail`` dispatches to the line-delimited
    event-log follower (a CLI subcommand); anything else runs the MCP stdio
    server. The dispatch happens BEFORE ``load_config`` because the config
    parser is flags-only and rejects positionals by design.
    """
    args = list(sys.argv[1:]) if argv is None else list(argv)

    if args and args[0] == "tail":
        from ..cli.tail import run_tail  # lazy: avoids an import cycle with this module

        return run_tail(args[1:])

    try:
        deps = bootstrap(os.environ, args)
    except OktoNexusError as exc:
        print(
            f"[okto-nexus] bootstrap failed: {exc.code}: {exc.message}",
            file=sys.stderr,
        )
        return 1

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
