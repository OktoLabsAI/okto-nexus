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


def get_authenticated_agent() -> Agent | None:
    """Return the agent bound to the current request, if any."""
    return current_agent.get()
