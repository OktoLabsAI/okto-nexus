"""MCP tools for issuing ephemeral poll tokens (EPT)."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from okto_nexus.adapters.inbound.http.identity_ctx import get_authenticated_agent
from okto_nexus.adapters.outbound.sqlite.events_repo import SqliteEventRepo
from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.adapters.outbound.sqlite.poll_tokens_repo import SqlitePollTokenRepo
from okto_nexus.application.poll_tokens import PollTokenService
from okto_nexus.envelope import tool_envelope

_P_SESSION_ID = "session_id returned by session_open. REQUIRED."
_P_SESSION_SECRET = "session_secret returned by session_open. REQUIRED."


def build_service(deps: Any) -> PollTokenService:
    """Wire repos and build the EPT service."""
    repos = deps.repos
    if getattr(repos, "poll_tokens", None) is None:
        repos.poll_tokens = SqlitePollTokenRepo(deps.clock)
    if getattr(repos, "sessions", None) is None:
        repos.sessions = SqliteSessionRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(repos, "events", None) is None:
        repos.events = SqliteEventRepo(deps.clock)
    if getattr(repos, "deliveries", None) is None:
        repos.deliveries = SqliteMessageDeliveryRepo(deps.clock)
    if getattr(repos, "messages", None) is None:
        repos.messages = SqliteMessageRepo(deps.clock)
    if getattr(repos, "handoffs", None) is None:
        repos.handoffs = SqliteHandoffRepo(deps.clock)
    return PollTokenService(
        connection_factory=deps.connection_factory,
        poll_tokens=repos.poll_tokens,
        sessions=repos.sessions,
        agents=repos.agents,
        events=repos.events,
        deliveries=repos.deliveries,
        messages=repos.messages,
        handoffs=repos.handoffs,
        clock=deps.clock,
        config=deps.config,
    )


def _actor_agent_id() -> str | None:
    agent = get_authenticated_agent()
    return None if agent is None else agent.agent_id


def register(server: Any, deps: Any) -> None:
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def poll_token_issue(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        session_secret: Annotated[str, Field(description=_P_SESSION_SECRET)],
    ) -> dict[str, Any]:
        """Issue an ephemeral read-only monitor bearer (nxsept_...) for this authenticated agent's session workspace. Store only in the background monitor; never persist the raw token."""
        return service.issue(
            actor_agent_id=_actor_agent_id(),
            session_id=session_id,
            session_secret=session_secret,
        )

    @server.tool()
    @tool_envelope
    def poll_token_renew(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        session_secret: Annotated[str, Field(description=_P_SESSION_SECRET)],
    ) -> dict[str, Any]:
        """Rotate and extend the active ephemeral poll token for this session. The previous raw nxsept_ bearer stops working immediately."""
        return service.renew(
            actor_agent_id=_actor_agent_id(),
            session_id=session_id,
            session_secret=session_secret,
        )

    @server.tool()
    @tool_envelope
    def poll_token_revoke(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        session_secret: Annotated[str, Field(description=_P_SESSION_SECRET)],
    ) -> dict[str, Any]:
        """Revoke the active ephemeral poll token for this session."""
        return service.revoke(
            actor_agent_id=_actor_agent_id(),
            session_id=session_id,
            session_secret=session_secret,
        )
