"""Permission resolution at the application layer (migration 011).

The single place services turn an ``agent_id`` into a resolved
:class:`~okto_nexus.domain.permissions.PermissionSet`. Enforcement lives in
the application services themselves (message/handoff/artifact/event), NEVER
in transport adapters - so stdio MCP, HTTP MCP and REST inherit identical
rules by construction.

Default-allow everywhere: an unknown agent_id, a ``None`` repo, or a ``NULL``
permissions column all resolve to the unrestricted set, keeping every
pre-migration agent and every cooperative-trust flow working unchanged.
"""

from __future__ import annotations

from typing import Any, Optional

from ..domain.permissions import PermissionSet
from .ports import AgentRepo, UnitOfWork


def permission_set_for(
    agents: Optional[AgentRepo], uow: UnitOfWork, agent_id: Any
) -> PermissionSet:
    """Resolve the PermissionSet for ``agent_id`` inside the caller's uow."""
    if agents is None or not isinstance(agent_id, str) or not agent_id.strip():
        return PermissionSet(None)
    agent = agents.get(uow, agent_id.strip())
    if agent is None:
        return PermissionSet(None)
    return PermissionSet(agent.permissions)
