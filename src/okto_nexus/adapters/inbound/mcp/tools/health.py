"""MCP inbound tool for the coordination-health slice (spec 7df9b1e0, I7).

Registers the ONE tool this slice owns, returning the canonical envelope via
:func:`tool_envelope` so no exception ever crosses the adapter boundary:

* ``coordination_health`` - windowed health report for a workspace (volumes,
  unclaimed handoffs, claim->complete average, rejection rate, inbox backlog,
  presence buckets), thresholds ALWAYS echoed in the payload.

Gated LIVE by ``feature_health`` (flag OFF -> VALIDATION_ERROR
``{feature_health: false}``; the tool stays registered in both states). The
tool takes NO agent identity / session on purpose (dec_ed36e779): it is a
passive read - like ``event_get`` - and must never stamp a heartbeat into the
very presence metric it reports. The operator's REST read is NOT gated and
lives in the HTTP adapter.

This module is the slice's composition root: it reuses the peer-owned
workspace repo from ``deps.repos`` and wires the stateless observability
queries adapter + presence classifier into the shared
:class:`HealthService` - the SAME service class the REST route uses, so
tool/REST parity holds by construction. It does NOT import the MCP SDK; the
live FastMCP server is passed into :func:`register`, matching the
``register(server, deps)`` contract.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteWorkspaceRepo
from okto_nexus.adapters.outbound.sqlite.observability_repo import (
    SqliteObservabilityQueries,
)
from okto_nexus.application.health import HealthService
from okto_nexus.application.observability import ObservabilityService
from okto_nexus.envelope import tool_envelope

#: Reused parameter descriptions (house style, mirrors the sibling tools).
_P_ROOT = (
    "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
)
_P_WINDOW = "Report window - one of: 1h, 24h, 7d (default: 24h)."


def build_service(deps: Any) -> HealthService:
    """Wire the concrete adapters into the shared read-only service.

    Idempotent on ``deps.repos``: the workspace repo is reused if a peer
    already provided it. The observability queries adapter is STATELESS
    (SELECT-only), so a local instance is equivalent to a shared one - the
    same wiring the HTTP app uses for analytics/overview.
    """
    repos = deps.repos
    if getattr(repos, "workspaces", None) is None:
        repos.workspaces = SqliteWorkspaceRepo(deps.clock)
    queries = SqliteObservabilityQueries()
    observability = ObservabilityService(queries, deps.clock, deps.config)
    return HealthService(
        connection_factory=deps.connection_factory,
        queries=queries,
        workspaces=repos.workspaces,
        observability=observability,
        clock=deps.clock,
        config=deps.config,
    )


def register(server: Any, deps: Any) -> None:
    """Register the health tool on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def coordination_health(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        window: Annotated[str, Field(description=_P_WINDOW)] = "24h",
    ) -> dict[str, Any]:
        """Windowed coordination-health report for the workspace: aggregated ok|warn status, 7 metric blocks and the thresholds used. Requires the feature_health flag ON."""
        service.require_feature_health()
        return service.health(project_root=project_root, window=window)
