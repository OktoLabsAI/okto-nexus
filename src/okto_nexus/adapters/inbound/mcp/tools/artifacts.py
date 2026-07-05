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

from typing import Annotated, Any

from pydantic import Field

from okto_nexus.adapters.outbound.file.store import WorkspaceFileStore
from okto_nexus.adapters.outbound.sqlite.artifacts_repo import SqliteArtifactRepo
from okto_nexus.adapters.outbound.sqlite.governance_repo import (
    SqliteGovernanceRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteWorkspaceRepo
from okto_nexus.adapters.outbound.sqlite.policy_repo import (
    SqliteAgentPolicyBindingRepo,
    SqlitePolicyRepo,
)
from okto_nexus.application.artifacts import ArtifactService
from okto_nexus.application.governance import GovernanceService
from okto_nexus.envelope import tool_envelope

from ...http.identity_ctx import get_authenticated_agent

#: Reused parameter descriptions (kept DRY across the artifact tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = (
    "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
)
_P_ARTIFACT_TYPE = "Artifact classification - one of: file, text, json, markdown. REQUIRED. json content is validated as well-formed; inline-vs-reference is decided by content-vs-path."
_P_NAME = "Human-friendly name/label for the artifact (optional)."
_P_PATH = "Filesystem path to register by REFERENCE (must stay within the workspace root; only path + metadata stored, never bytes). Provide this OR content - at least one REQUIRED."
_P_CONTENT = "Inline UTF-8 content (bounded by max_inline_bytes; json must be well-formed). Provide this OR path - at least one REQUIRED."
_P_METADATA = "Free-form JSON object stored with the artifact (optional)."
_P_ARTIFACT_ID = "The artifact_id to retrieve. REQUIRED."


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
    if getattr(repos, "governance", None) is None:
        repos.governance = SqliteGovernanceRepo(deps.clock)
    if getattr(repos, "policies", None) is None:
        repos.policies = SqlitePolicyRepo(deps.clock)
    if getattr(repos, "policy_bindings", None) is None:
        repos.policy_bindings = SqliteAgentPolicyBindingRepo(deps.clock)
    # Policy enforcement (spec 80624c1a): per-slice service composing the actor's
    # attached policies; always-on and binding-driven - an actor with no bindings
    # passes untouched (BR2 zero-regression).
    governance = GovernanceService(
        connection_factory=deps.connection_factory,
        governance=repos.governance,
        clock=deps.clock,
        config=deps.config,
        agents=getattr(repos, "agents", None),
        capability_catalog=getattr(repos, "capability_catalog", None),
        event_emitter=getattr(deps, "event_emitter", None),
        policies=repos.policies,
        policy_bindings=repos.policy_bindings,
    )
    return ArtifactService(
        connection_factory=deps.connection_factory,
        artifacts=repos.artifacts,
        workspaces=repos.workspaces,
        files=repos.files,
        clock=deps.clock,
        config=deps.config,
        agents=getattr(repos, "agents", None),
        event_emitter=getattr(deps, "event_emitter", None),
        governance=governance,
    )


def register(server: Any, deps: Any) -> None:
    """Register the artifact tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def artifact_put(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        artifact_type: Annotated[str, Field(description=_P_ARTIFACT_TYPE)],
        name: Annotated[str | None, Field(description=_P_NAME)] = None,
        path: Annotated[str | None, Field(description=_P_PATH)] = None,
        content: Annotated[str | None, Field(description=_P_CONTENT)] = None,
        metadata: Annotated[Any, Field(description=_P_METADATA)] = None,
    ) -> dict[str, Any]:
        """Register a file/text/json/markdown artifact in the resolved workspace."""
        caller = get_authenticated_agent()
        return service.artifact_put(
            project_root=project_root,
            artifact_type=artifact_type,
            name=name,
            path=path,
            content=content,
            metadata=metadata,
            agent_id=caller.agent_id if caller is not None else None,
        )

    @server.tool()
    @tool_envelope
    def artifact_get(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        artifact_id: Annotated[str, Field(description=_P_ARTIFACT_ID)],
    ) -> dict[str, Any]:
        """Retrieve an artifact by id within the workspace resolved from project_root. Reads are audience-scoped: a caller outside the frozen audience gets NOT_FOUND (indistinguishable from a missing id)."""
        caller = get_authenticated_agent()
        return service.artifact_get(
            project_root=project_root,
            artifact_id=artifact_id,
            agent_id=caller.agent_id if caller is not None else None,
        )
