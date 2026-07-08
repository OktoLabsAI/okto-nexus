"""MCP inbound tool for the shared.md slice.

Registers the single owned tool ``shared_md_render`` on the FastMCP server,
returning the canonical envelope (success ``{ok:true,data}`` / failure
``{ok:false,error}``) via :func:`tool_envelope`, so no exception ever crosses
the adapter boundary.

This module is the slice's composition root: it wires the concrete renderer and
resolves the repository ports from the shared ``deps.repos`` registry, filling
in the foundational workspace / agent / session SQLite repos if a sibling has
not already provided them. It does NOT import the MCP SDK; the live server is
passed into :func:`register`, matching the ``register(server, deps)`` contract.

Sibling repos (tasks / handoffs / events) are read straight from ``deps.repos``
and may be ``None`` until their slices land; the service renders the matching
section empty in that case. Service construction is LAZY (on first call) so it
observes every slice's repos regardless of tool registration order.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from okto_nexus.adapters.outbound.sharedmd.renderer import FileSystemSharedMdRenderer
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.application.shared_md import (
    DEFAULT_LIMIT_EVENTS,
    SharedMdService,
)
from okto_nexus.envelope import tool_envelope

from ...http.identity_ctx import get_authenticated_agent

#: Parameter descriptions. Module-level so the (stringised) annotations resolve
#: against module globals when FastMCP evaluates them. House style mirrors
#: okto-pulse (enums "one of: ...", optionals "(default: ...)").
_P_WS = (
    "The target workspace_id (from workspace_resolve) whose shared.md is rendered. "
    "REQUIRED - NB: this tool takes the workspace_id directly, not project_root."
)
_P_LIMIT_EVENTS = (
    "How many of the most recent events to include in the rendered timeline "
    f"(optional; default: {DEFAULT_LIMIT_EVENTS}, clamped to the configured maximum)."
)
_P_AGENT = (
    "Your agent_id for permission evaluation in open stdio mode (optional; "
    "authenticated HTTP MCP uses the API-key identity)."
)


def build_service(deps: Any) -> SharedMdService:
    """Wire the renderer + repos from ``deps`` and build the service.

    Idempotent for the foundational repos: workspace / agent / session repos
    already present on ``deps.repos`` are reused so this slice and its peers
    share a single concrete instance. Sibling repos (tasks/handoffs/events) are
    passed through as-is (possibly ``None``). The ``limit_events`` ceiling
    comes from ``deps.config.max_shared_md_events`` (env
    ``OKTO_NEXUS_MAX_SHARED_MD_EVENTS`` / ``--max-shared-md-events``, parsed
    FAIL-CLOSED by ``load_config`` - an invalid value aborts startup with
    CONFIG_ERROR instead of silently falling back).
    """
    repos = deps.repos
    if getattr(repos, "workspaces", None) is None:
        repos.workspaces = SqliteWorkspaceRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(repos, "sessions", None) is None:
        repos.sessions = SqliteSessionRepo(deps.clock)

    renderer = FileSystemSharedMdRenderer(home_dir=deps.config.home_dir)

    return SharedMdService(
        connection_factory=deps.connection_factory,
        workspaces=repos.workspaces,
        renderer=renderer,
        clock=deps.clock,
        agents=getattr(repos, "agents", None),
        sessions=getattr(repos, "sessions", None),
        tasks=getattr(repos, "tasks", None),
        handoffs=getattr(repos, "handoffs", None),
        events=getattr(repos, "events", None),
        max_limit_events=deps.config.max_shared_md_events,
    )


def register(server: Any, deps: Any) -> None:
    """Register the ``shared_md_render`` tool on ``server``.

    The service is built lazily on first invocation so it captures the repos
    wired by every sibling slice, independent of registration order.
    """
    state: dict[str, Any] = {"service": None}

    def _service() -> SharedMdService:
        if state["service"] is None:
            state["service"] = build_service(deps)
        return state["service"]

    @server.tool()
    @tool_envelope
    def shared_md_render(
        workspace_id: Annotated[str, Field(description=_P_WS)],
        limit_events: Annotated[int, Field(description=_P_LIMIT_EVENTS)] = DEFAULT_LIMIT_EVENTS,
        agent_id: Annotated[str | None, Field(description=_P_AGENT)] = None,
    ) -> dict[str, Any]:
        """Render the per-workspace human-readable shared.md (atomic overwrite)."""
        caller = get_authenticated_agent()
        actor = caller.agent_id if caller is not None else agent_id
        return _service().shared_md_render(
            workspace_id=workspace_id, limit_events=limit_events, agent_id=actor
        )
