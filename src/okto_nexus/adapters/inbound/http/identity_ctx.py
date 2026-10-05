"""Per-request authenticated identity (Nexus v2, C4).

The auth middleware resolves the inbound API key to an :class:`Agent` and
parks it here; anything downstream (REST handlers, MCP tools that want the
caller's identity) reads it without threading parameters through every layer.
``ContextVar`` is async-safe: concurrent requests never observe each other.
"""

from __future__ import annotations

from contextvars import ContextVar

from ....domain.models import Agent

#: The agent authenticated for the CURRENT request (None outside a request
#: or before authentication).
current_agent: ContextVar[Agent | None] = ContextVar("okto_nexus_current_agent", default=None)
trusted_local_operator: ContextVar[bool] = ContextVar("okto_nexus_local_operator", default=False)
# Human identity is independent of the synthetic operator agent used by runtime management.
current_operator: ContextVar[str | None] = ContextVar("okto_nexus_operator", default=None)


def get_authenticated_agent() -> Agent | None:
    """Return the agent bound to the current request, if any."""
    return current_agent.get()


def runtime_request_context():
    """Carry middleware authentication without inventing an agent credential."""
    from ....domain.runtime_context import RuntimeRequestContext
    actor = get_authenticated_agent()
    local = trusted_local_operator.get()
    return RuntimeRequestContext(
        actor.agent_id if actor else None,
        "operator_session" if current_operator.get() is not None else
        "http_loopback" if local else "agent_key" if actor else "unauthenticated",
        trusted_local_operator=local,
        credential_binding=actor.api_key_hash if actor and not local else None,
    )
