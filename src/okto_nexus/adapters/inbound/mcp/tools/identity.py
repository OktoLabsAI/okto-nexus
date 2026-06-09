"""MCP inbound tools for the identity slice.

Registers nine tools on the FastMCP server, each returning the canonical
envelope (success ``{ok:true,data}`` / failure ``{ok:false,error}``) via
:func:`tool_envelope`, so no exception ever crosses the adapter boundary:

* ``workspace_resolve`` - resolve ``project_root`` to a ``workspace_id``.
* ``workspace_list``    - GLOBAL-ADMIN: enumerate ALL workspaces.
* ``agent_register``    - upsert a logical agent identity.
* ``agent_list``        - GLOBAL: enumerate ALL agents (discovery surface).
* ``agent_get``         - read one agent's details incl. ``last_seen_at``.
* ``capability_list``   - GLOBAL: enumerate capabilities advertised by agents.
* ``session_open``      - open a workspace-scoped session.
* ``session_heartbeat`` - advance a session heartbeat / report status.
* ``session_close``     - idempotently close a session.

The deliberately cross-workspace (global) surfaces are ``workspace_list``,
``agent_list`` / ``agent_get`` and ``capability_list`` (agents are global
identities); every other tool stays scoped to a single workspace.

This module is the slice's composition root: it wires the concrete SQLite
repositories into ``deps.repos`` (only if not already provided) and constructs
the :class:`IdentityService`. It does NOT import the MCP SDK; the live server is
passed into :func:`register`, matching the ``register(server, deps)`` contract.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Mapping

from pydantic import Field

from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.application.identity import (
    DEFAULT_SESSION_STALE_TTL_SECONDS,
    IdentityService,
)
from okto_nexus.envelope import tool_envelope

#: Reused parameter descriptions (kept DRY across the identity tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
_P_DISPLAY_NAME = "Human-friendly label to store/refresh for the workspace (optional)."
_P_AGENT_ID = "The logical agent identity (stable, opaque string); agents are GLOBAL, not per-workspace. REQUIRED."
_P_ROLE = (
    "Logical role, e.g. validator, worker (optional); matched exactly and "
    "case-sensitively by role-strategy targets."
)
_P_CAPABILITIES = (
    "What this agent can do - used by capability routing AND capability_list "
    "discovery (advertised set == addressable set) (optional). Accepts a "
    'flag-mapping ({"ocr": true, "pdf": true} - only truthy keys count), a list of '
    'names (["ocr", "pdf"]), or a single name string. Blank/whitespace names are '
    "dropped; omit for no capabilities."
)
_P_AGENT_METADATA = "Free-form JSON object of extra attributes stored with the agent (optional)."
_P_SESSION_AGENT = "Your agent_id; the session is bound to this identity. REQUIRED."
_P_SESSION_WS = (
    "Workspace_id (from workspace_resolve) the session operates in (optional; omit "
    "for an unbound session)."
)
_P_SESSION_METADATA = "Free-form JSON object stored with the session (optional)."
_P_SESSION_ID = "The session_id returned by session_open. REQUIRED."
_P_SESSION_WS_GUARD = "Workspace_id scope guard (optional); when given it must match the session's workspace."
_P_GET_AGENT_ID = "The agent_id to look up. REQUIRED."

#: Environment knob for the session stale TTL (seconds). Not part of
#: ``NexusConfig``, so it is resolved here in the inbound adapter.
STALE_TTL_ENV = "OKTO_NEXUS_SESSION_STALE_TTL_SECONDS"


def _resolve_stale_ttl(env: Mapping[str, str]) -> int:
    """Resolve the session stale TTL from the environment (positive int)."""
    raw = env.get(STALE_TTL_ENV)
    if raw is None or not str(raw).strip():
        return DEFAULT_SESSION_STALE_TTL_SECONDS
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_SESSION_STALE_TTL_SECONDS
    return value if value > 0 else DEFAULT_SESSION_STALE_TTL_SECONDS


def build_service(deps: Any, env: Mapping[str, str] | None = None) -> IdentityService:
    """Wire the SQLite repos into ``deps.repos`` and build the service.

    Idempotent: repositories already present on ``deps.repos`` are reused so the
    identity slice and any peers share a single concrete instance.
    """
    environ = env if env is not None else os.environ
    repos = deps.repos
    if getattr(repos, "workspaces", None) is None:
        repos.workspaces = SqliteWorkspaceRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(repos, "sessions", None) is None:
        repos.sessions = SqliteSessionRepo(deps.clock)
    return IdentityService(
        connection_factory=deps.connection_factory,
        workspaces=repos.workspaces,
        agents=repos.agents,
        sessions=repos.sessions,
        clock=deps.clock,
        config=deps.config,
        event_emitter=getattr(deps, "event_emitter", None),
        stale_ttl_seconds=_resolve_stale_ttl(environ),
    )


def register(server: Any, deps: Any) -> None:
    """Register the identity tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def workspace_resolve(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        display_name: Annotated[str | None, Field(description=_P_DISPLAY_NAME)] = None,
    ) -> dict[str, Any]:
        """Resolve a project_root to its deterministic workspace_id and upsert it."""
        return service.workspace_resolve(
            project_root=project_root, display_name=display_name
        )

    @server.tool()
    @tool_envelope
    def agent_register(
        agent_id: Annotated[str, Field(description=_P_AGENT_ID)],
        role: Annotated[str | None, Field(description=_P_ROLE)] = None,
        capabilities: Annotated[Any, Field(description=_P_CAPABILITIES)] = None,
        metadata: Annotated[Any, Field(description=_P_AGENT_METADATA)] = None,
    ) -> dict[str, Any]:
        """Register (upsert) a logical agent identity; no workspace required."""
        return service.agent_register(
            agent_id=agent_id,
            role=role,
            capabilities=capabilities,
            metadata=metadata,
        )

    @server.tool()
    @tool_envelope
    def session_open(
        agent_id: Annotated[str, Field(description=_P_SESSION_AGENT)],
        workspace_id: Annotated[str | None, Field(description=_P_SESSION_WS)] = None,
        metadata: Annotated[Any, Field(description=_P_SESSION_METADATA)] = None,
    ) -> dict[str, Any]:
        """Open a session bound to (agent_id, workspace_id); server assigns the id."""
        return service.session_open(
            agent_id=agent_id, workspace_id=workspace_id, metadata=metadata
        )

    @server.tool()
    @tool_envelope
    def session_heartbeat(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        workspace_id: Annotated[str | None, Field(description=_P_SESSION_WS_GUARD)] = None,
    ) -> dict[str, Any]:
        """Advance a session heartbeat and report the derived status."""
        return service.session_heartbeat(
            session_id=session_id, workspace_id=workspace_id
        )

    @server.tool()
    @tool_envelope
    def session_close(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        workspace_id: Annotated[str | None, Field(description=_P_SESSION_WS_GUARD)] = None,
    ) -> dict[str, Any]:
        """Close a session (idempotent); repeating returns ok and stays closed."""
        return service.session_close(
            session_id=session_id, workspace_id=workspace_id
        )

    @server.tool()
    @tool_envelope
    def workspace_list() -> dict[str, Any]:
        """GLOBAL-ADMIN: enumerate ALL workspaces across every scope.

        This is the single deliberately cross-workspace tool in the identity
        slice. All other identity tools remain scoped to one workspace.
        """
        return {"workspaces": service.workspace_list()}

    @server.tool()
    @tool_envelope
    def agent_list() -> dict[str, Any]:
        """List ALL registered agents (global), each with role/capabilities and
        last_seen_at - the timestamp of its most recent action on the bus.

        Discovery surface for addressing: use it to find an agent_id before
        sending a direct message or opening a directed handoff.
        """
        return {"agents": service.agent_list()}

    @server.tool()
    @tool_envelope
    def agent_get(
        agent_id: Annotated[str, Field(description=_P_GET_AGENT_ID)],
    ) -> dict[str, Any]:
        """Return one agent's details, including its last interaction (last_seen_at)."""
        return service.agent_get(agent_id=agent_id)

    @server.tool()
    @tool_envelope
    def capability_list() -> dict[str, Any]:
        """List the capabilities advertised by registered agents (global discovery).

        For each capability, the agents that possess it - so a caller can pick a
        `target: {strategy: "capability"}` knowing the capability exists and who
        would match it. Normalised exactly as capability routing matches.
        """
        return {"capabilities": service.capability_list()}
