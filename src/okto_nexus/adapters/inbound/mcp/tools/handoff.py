"""MCP inbound tools for the handoff lifecycle slice.

Registers five tools on the FastMCP server, each returning the canonical
envelope (success ``{ok:true,data}`` / failure ``{ok:false,error}``) via
:func:`tool_envelope`, so no exception ever crosses the adapter boundary:

* ``handoff_create``         - create an OPEN handoff.
* ``handoff_list_available`` - expire leases then list claimable handoffs.
* ``handoff_claim``          - atomically claim an OPEN handoff.
* ``handoff_complete``       - owner completes a CLAIMED handoff.
* ``handoff_reject``         - owner / direct-target rejects a handoff.

This module is the slice's composition root: it wires the concrete SQLite
repositories into ``deps.repos`` (only if not already provided) and constructs
the :class:`HandoffService`. It does NOT import the MCP SDK; the live server is
passed into :func:`register`, matching the ``register(server, deps)`` contract.
"""

from __future__ import annotations

from typing import Any

from okto_nexus.adapters.outbound.sqlite.handoff_repo import (
    SqliteHandoffRepo,
    SqliteTaskRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.application.handoff import HandoffService
from okto_nexus.envelope import tool_envelope


def build_service(deps: Any) -> HandoffService:
    """Wire the SQLite repos into ``deps.repos`` and build the service.

    Idempotent: repositories already present on ``deps.repos`` are reused so the
    handoff slice and any peers (e.g. identity providing ``agents``) share a
    single concrete instance.
    """
    repos = deps.repos
    if getattr(repos, "handoffs", None) is None:
        repos.handoffs = SqliteHandoffRepo(deps.clock)
    if getattr(repos, "tasks", None) is None:
        repos.tasks = SqliteTaskRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    return HandoffService(
        connection_factory=deps.connection_factory,
        handoffs=repos.handoffs,
        tasks=repos.tasks,
        clock=deps.clock,
        config=deps.config,
        event_emitter=getattr(deps, "event_emitter", None),
        agents=repos.agents,
    )


def register(server: Any, deps: Any) -> None:
    """Register the handoff tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def handoff_create(
        project_root: str,
        from_agent_id: str,
        target: Any,
        visibility: str,
        payload: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an OPEN handoff after validating target/visibility; emit handoff.created."""
        return service.handoff_create(
            project_root=project_root,
            from_agent_id=from_agent_id,
            target=target,
            visibility=visibility,
            payload=payload,
            session_id=session_id,
        )

    @server.tool()
    @tool_envelope
    def handoff_list_available(
        project_root: str,
        agent_id: str,
        cursor: str | None = None,
        limit: int | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Expire leases, then list OPEN handoffs visible+eligible to the caller (paginated)."""
        return service.handoff_list_available(
            project_root=project_root,
            agent_id=agent_id,
            cursor=cursor,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )

    @server.tool()
    @tool_envelope
    def handoff_claim(
        project_root: str,
        handoff_id: str,
        agent_id: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Atomically claim an OPEN handoff; single winner, others get a structured error."""
        return service.handoff_claim(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
            session_id=session_id,
        )

    @server.tool()
    @tool_envelope
    def handoff_complete(
        project_root: str,
        handoff_id: str,
        agent_id: str,
        result: Any = None,
    ) -> dict[str, Any]:
        """Owner-only transition CLAIMED -> COMPLETED; emit handoff.completed."""
        return service.handoff_complete(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
            result=result,
        )

    @server.tool()
    @tool_envelope
    def handoff_reject(
        project_root: str,
        handoff_id: str,
        agent_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Reject a handoff (owner CLAIMED->REJECTED or direct-target OPEN->REJECTED)."""
        return service.handoff_reject(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
            reason=reason,
        )
