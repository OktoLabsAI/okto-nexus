"""MCP inbound tool for the central tag catalog (F1).

Registers the single READ-ONLY tool ``tag_list``: the full operator-managed
catalog every ``tags`` / ``comm_scope`` / ``{"strategy": "tag"}`` reference is
validated against (fail-closed - unregistered tags are rejected at write
time, so this catalog is the complete vocabulary an agent can target).

Registry WRITES are operator-only and live on the REST surface
(``/api/v1/tags`` + the dashboard Tag Registry screen) - agents can read the
vocabulary but never grow it. Auto-discovered via the ``register(server,
deps)`` contract; does NOT import the MCP SDK.
"""

from __future__ import annotations

from typing import Any

from okto_nexus.adapters.outbound.sqlite.tag_catalog_repo import (
    SqliteTagCatalogRepo,
)
from okto_nexus.application.tags import TagCatalogService
from okto_nexus.envelope import tool_envelope


def build_service(deps: Any) -> TagCatalogService:
    """Wire the SQLite catalog repo into ``deps.repos`` and build the service.

    Idempotent: a ``tag_catalog`` repo already present is reused so this slice
    and its peers (message/handoff existence gates, the REST registry) share a
    single concrete instance.
    """
    repos = deps.repos
    if getattr(repos, "tag_catalog", None) is None:
        repos.tag_catalog = SqliteTagCatalogRepo(deps.clock)
    return TagCatalogService(catalog=repos.tag_catalog)


def register(server: Any, deps: Any) -> None:
    """Register the ``tag_list`` tool on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def tag_list() -> dict[str, Any]:
        """List the global operator-managed tag catalog (keys + values) that agent tags, comm_scope and tag targets are validated against fail-closed."""
        with deps.connection_factory.unit_of_work(write=False) as uow:
            tags = service.snapshot(uow)
        return {"tags": tags, "total": len(tags)}
