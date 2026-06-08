"""MCP inbound tools for the artifacts slice.

Registers two tools on the FastMCP server, each returning the canonical
envelope (``{ok:true,data}`` / ``{ok:false,error}``) via :func:`tool_envelope`
so no exception ever crosses the adapter boundary:

* ``artifact_put`` - register an artifact and emit ``artifact.created``.
* ``artifact_get`` - retrieve an artifact within the resolved workspace.

This module is the slice's composition root: it wires the concrete SQLite repo,
the workspace repo (shared with the identity slice, reused if already present),
and the workspace file store into ``deps.repos``, then constructs the
:class:`ArtifactService`. It does NOT import the MCP SDK; the live server is
passed into :func:`register`, matching the ``register(server, deps)`` contract.
"""

from __future__ import annotations

from typing import Any

from okto_nexus.adapters.outbound.file.store import WorkspaceFileStore
from okto_nexus.adapters.outbound.sqlite.artifacts_repo import SqliteArtifactRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteWorkspaceRepo
from okto_nexus.application.artifacts import ArtifactService
from okto_nexus.envelope import tool_envelope


def build_service(deps: Any) -> ArtifactService:
    """Wire the concrete adapters into ``deps.repos`` and build the service.

    Idempotent: repositories already present on ``deps.repos`` are reused so the
    artifacts slice and its peers (e.g. identity) share a single concrete
    instance per port.
    """
    repos = deps.repos
    if getattr(repos, "artifacts", None) is None:
        repos.artifacts = SqliteArtifactRepo(deps.clock)
    if getattr(repos, "workspaces", None) is None:
        repos.workspaces = SqliteWorkspaceRepo(deps.clock)
    if getattr(repos, "files", None) is None:
        repos.files = WorkspaceFileStore()
    return ArtifactService(
        connection_factory=deps.connection_factory,
        artifacts=repos.artifacts,
        workspaces=repos.workspaces,
        files=repos.files,
        clock=deps.clock,
        config=deps.config,
        event_emitter=getattr(deps, "event_emitter", None),
    )


def register(server: Any, deps: Any) -> None:
    """Register the artifact tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def artifact_put(
        project_root: str,
        artifact_type: str,
        name: str | None = None,
        path: str | None = None,
        content: str | None = None,
        metadata: Any = None,
    ) -> dict[str, Any]:
        """Register a file/text/json/markdown artifact in the resolved workspace."""
        return service.artifact_put(
            project_root=project_root,
            artifact_type=artifact_type,
            name=name,
            path=path,
            content=content,
            metadata=metadata,
        )

    @server.tool()
    @tool_envelope
    def artifact_get(project_root: str, artifact_id: str) -> dict[str, Any]:
        """Retrieve an artifact by id within the workspace resolved from project_root."""
        return service.artifact_get(project_root=project_root, artifact_id=artifact_id)
