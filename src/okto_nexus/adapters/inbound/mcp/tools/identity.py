"""MCP inbound tools for the identity slice.

Registers six tools on the FastMCP server, each returning the canonical
envelope (success ``{ok:true,data}`` / failure ``{ok:false,error}``) via
:func:`tool_envelope`, so no exception ever crosses the adapter boundary:

* ``workspace_resolve`` - resolve ``project_root`` to a ``workspace_id``.
* ``workspace_list``    - GLOBAL-ADMIN: enumerate ALL workspaces (the single
  deliberately cross-workspace surface; every other tool stays scoped).
* ``agent_register``    - upsert a logical agent identity.
* ``session_open``      - open a workspace-scoped session.
* ``session_heartbeat`` - advance a session heartbeat / report status.
* ``session_close``     - idempotently close a session.

This module is the slice's composition root: it wires the concrete SQLite
repositories into ``deps.repos`` (only if not already provided) and constructs
the :class:`IdentityService`. It does NOT import the MCP SDK; the live server is
passed into :func:`register`, matching the ``register(server, deps)`` contract.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

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
        project_root: str, display_name: str | None = None
    ) -> dict[str, Any]:
        """Resolve a project_root to its deterministic workspace_id and upsert it."""
        return service.workspace_resolve(
            project_root=project_root, display_name=display_name
        )

    @server.tool()
    @tool_envelope
    def agent_register(
        agent_id: str,
        role: str | None = None,
        capabilities: Any = None,
        metadata: Any = None,
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
        agent_id: str,
        workspace_id: str | None = None,
        metadata: Any = None,
    ) -> dict[str, Any]:
        """Open a session bound to (agent_id, workspace_id); server assigns the id."""
        return service.session_open(
            agent_id=agent_id, workspace_id=workspace_id, metadata=metadata
        )

    @server.tool()
    @tool_envelope
    def session_heartbeat(
        session_id: str, workspace_id: str | None = None
    ) -> dict[str, Any]:
        """Advance a session heartbeat and report the derived status."""
        return service.session_heartbeat(
            session_id=session_id, workspace_id=workspace_id
        )

    @server.tool()
    @tool_envelope
    def session_close(
        session_id: str, workspace_id: str | None = None
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
