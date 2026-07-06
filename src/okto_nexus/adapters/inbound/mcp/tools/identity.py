"""MCP inbound tools for the identity slice.

Registers ten tools on the FastMCP server, each returning the canonical
envelope (success ``{ok:true,data}`` / failure ``{ok:false,error}``) via
:func:`tool_envelope`, so no exception ever crosses the adapter boundary:

* ``workspace_resolve`` - resolve ``project_root`` to a ``workspace_id``.
* ``workspace_list``    - GLOBAL-ADMIN: enumerate ALL workspaces (on-disk
  paths opt-in via ``include_paths``).
* ``agent_register``    - update YOUR OWN identity profile (self-only when
  the connection is authenticated; new identities come from the dashboard).
* ``agent_whoami``      - return the caller's own profile, derived from the
  API key (agent_id, role, capabilities, permissions).
* ``agent_list``        - GLOBAL: enumerate ALL agents (discovery surface).
* ``agent_get``         - read one agent's details incl. ``last_seen_at``.
* ``capability_list``   - GLOBAL: enumerate capabilities advertised by agents.
* ``session_open``      - open a workspace-scoped session.
* ``session_heartbeat`` - advance a session heartbeat / report status.
* ``session_close``     - idempotently close a session.

The deliberately cross-workspace (global) surfaces are ``workspace_list``,
``agent_list`` / ``agent_get`` and ``capability_list`` (agents are global
identities); every other tool stays scoped to a single workspace.

This module is the slice's composition root: it wires the concrete SQLite
repositories into ``deps.repos`` (only if not already provided) and constructs
the :class:`IdentityService`. It does NOT import the MCP SDK; the live server is
passed into :func:`register`, matching the ``register(server, deps)`` contract.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from okto_nexus.adapters.outbound.sqlite.capability_catalog_repo import (
    SqliteCapabilityCatalogRepo,
)
from okto_nexus.adapters.outbound.sqlite.comm_preset_repo import (
    SqliteAgentCommBindingRepo,
    SqliteCommPresetRepo,
)
from okto_nexus.adapters.outbound.sqlite.governance_repo import (
    SqliteGovernanceRepo,
)
from okto_nexus.adapters.outbound.sqlite.policy_repo import (
    SqliteAgentPolicyBindingRepo,
    SqlitePolicyRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.application.comm_preset_catalog import CommPresetCatalogService
from okto_nexus.application.governance import GovernanceService
from okto_nexus.application.identity import IdentityService
from okto_nexus.envelope import tool_envelope

from ...http.identity_ctx import get_authenticated_agent

#: Reused parameter descriptions (kept DRY across the identity tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = (
    "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
)
_P_DISPLAY_NAME = "Human-friendly label to store/refresh for the workspace (optional)."
_P_AGENT_ID = "The logical agent identity (stable, opaque string); agents are GLOBAL, not per-workspace. REQUIRED."
_P_ROLE = "Logical role, e.g. validator, worker (optional); matched exactly/case-sensitively by role-strategy targets."
_P_CAPABILITIES = (
    "What this agent can do - used by capability routing + capability_list "
    'discovery (optional). Accepts a flag-map ({"ocr":true}), a list '
    '(["ocr","pdf"]), or a single name string. Blank names dropped. '
    "FAIL-CLOSED: every name must already exist in the central capability "
    "catalog (see capability_list; operators register names on the dashboard "
    "Registry or POST /api/v1/capabilities)."
)
_P_AGENT_METADATA = (
    "Free-form JSON object of extra attributes stored with the agent (optional)."
)
_P_SESSION_AGENT = "Your agent_id; the session is bound to this identity. REQUIRED."
_P_SESSION_WS = (
    "Workspace_id (from workspace_resolve) the session operates in (optional; omit "
    "for an unbound session)."
)
_P_SESSION_METADATA = "Free-form JSON object stored with the session (optional)."
_P_SESSION_ID = "The session_id returned by session_open. REQUIRED."
_P_SESSION_WS_GUARD = "Workspace_id scope guard (optional); when given it must match the session's workspace."
_P_GET_AGENT_ID = "The agent_id to look up. REQUIRED."
_P_INCLUDE_PATHS = (
    "Also return each workspace on-disk root_realpath (default false; paths "
    "OMITTED by default - opt-in defense-in-depth). For routine discovery use "
    "agent_list / capability_list."
)


def build_service(deps: Any) -> IdentityService:
    """Wire the SQLite repos into ``deps.repos`` and build the service.

    Idempotent: repositories already present on ``deps.repos`` are reused so the
    identity slice and any peers share a single concrete instance. The session
    stale TTL comes from ``deps.config.session_stale_ttl_seconds`` (env
    ``OKTO_NEXUS_SESSION_STALE_TTL_SECONDS`` / ``--session-stale-ttl-seconds``,
    parsed FAIL-CLOSED by ``load_config`` - an invalid value aborts startup
    with CONFIG_ERROR instead of silently falling back).
    """
    repos = deps.repos
    if getattr(repos, "workspaces", None) is None:
        repos.workspaces = SqliteWorkspaceRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(repos, "sessions", None) is None:
        repos.sessions = SqliteSessionRepo(deps.clock)
    if getattr(repos, "capability_catalog", None) is None:
        repos.capability_catalog = SqliteCapabilityCatalogRepo(deps.clock)
    return IdentityService(
        connection_factory=deps.connection_factory,
        workspaces=repos.workspaces,
        agents=repos.agents,
        sessions=repos.sessions,
        clock=deps.clock,
        config=deps.config,
        event_emitter=getattr(deps, "event_emitter", None),
        stale_ttl_seconds=deps.config.session_stale_ttl_seconds,
        capability_catalog=repos.capability_catalog,
    )


def _build_governance(deps: Any) -> "GovernanceService":
    """Governance read-model backing the whoami block (spec ffef15bf, FR6).

    Idempotent on ``deps.repos.governance`` like every other slice wiring;
    call AFTER :func:`build_service` so agents/capability_catalog exist.
    """
    repos = deps.repos
    if getattr(repos, "governance", None) is None:
        repos.governance = SqliteGovernanceRepo(deps.clock)
    if getattr(repos, "policies", None) is None:
        repos.policies = SqlitePolicyRepo(deps.clock)
    if getattr(repos, "policy_bindings", None) is None:
        repos.policy_bindings = SqliteAgentPolicyBindingRepo(deps.clock)
    return GovernanceService(
        connection_factory=deps.connection_factory,
        governance=repos.governance,
        clock=deps.clock,
        config=deps.config,
        agents=repos.agents,
        capability_catalog=repos.capability_catalog,
        event_emitter=getattr(deps, "event_emitter", None),
        policies=repos.policies,
        policy_bindings=repos.policy_bindings,
    )


def _build_comm_presets(deps: Any) -> "CommPresetCatalogService":
    """Communication-preset catalog backing the whoami block (spec 6f961722).

    Idempotent on ``deps.repos.comm_presets`` / ``comm_bindings`` like every
    other slice wiring; call AFTER :func:`build_service` so ``agents`` exists.
    Only ``resolve_communication`` is used on the whoami hot path (self-only);
    the operator CRUD surface is wired separately over HTTP.
    """
    repos = deps.repos
    if getattr(repos, "comm_presets", None) is None:
        repos.comm_presets = SqliteCommPresetRepo(deps.clock)
    if getattr(repos, "comm_bindings", None) is None:
        repos.comm_bindings = SqliteAgentCommBindingRepo(deps.clock)
    return CommPresetCatalogService(
        connection_factory=deps.connection_factory,
        presets=repos.comm_presets,
        comm_bindings=repos.comm_bindings,
        agents=repos.agents,
    )


def register(server: Any, deps: Any) -> None:
    """Register the identity tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)
    governance = _build_governance(deps)
    comm_presets = _build_comm_presets(deps)

    @server.tool()
    @tool_envelope
    def workspace_resolve(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        display_name: Annotated[str | None, Field(description=_P_DISPLAY_NAME)] = None,
    ) -> dict[str, Any]:
        """Resolve a project_root to its deterministic workspace_id and upsert it."""
        return service.workspace_resolve(
            project_root=project_root, display_name=display_name
        )

    @server.tool()
    @tool_envelope
    def agent_register(
        agent_id: Annotated[str, Field(description=_P_AGENT_ID)],
        role: Annotated[str | None, Field(description=_P_ROLE)] = None,
        capabilities: Annotated[Any, Field(description=_P_CAPABILITIES)] = None,
        metadata: Annotated[Any, Field(description=_P_AGENT_METADATA)] = None,
    ) -> dict[str, Any]:
        """Update YOUR OWN profile (role/capabilities/metadata); SELF-ONLY (else PERMISSION_DENIED). Capabilities are fail-closed against the central catalog. Docs: okto-nexus://reference/tool-docs/identity."""
        caller = get_authenticated_agent()
        return service.agent_register(
            agent_id=agent_id,
            role=role,
            capabilities=capabilities,
            metadata=metadata,
            actor_agent_id=caller.agent_id if caller is not None else None,
        )

    @server.tool()
    @tool_envelope
    def agent_whoami() -> dict[str, Any]:
        """Return YOUR OWN profile: agent_id, role, capabilities, metadata, permissions, effective_policies + governance, plus communication style when set. Docs: okto-nexus://reference/tool-docs/identity."""
        caller = get_authenticated_agent()
        data = service.agent_whoami(
            actor_agent_id=caller.agent_id if caller is not None else None,
        )
        # Policy blocks (spec 80624c1a, FR11/AC10): present ONLY when the caller
        # has bindings, so an actor with none stays byte-identical to the
        # pre-policy surface (BR2). effective_policies names WHICH policies apply
        # (<policy_id>@<version> / inline; audience-only sources included);
        # governance carries the resolved rules. NEITHER leaks the audience
        # selector contents (comm_scope stays operator-private) nor other agents'.
        if caller is not None:
            labels = governance.effective_policy_labels_for(caller.agent_id)
            if labels:
                data["effective_policies"] = labels
            policies = governance.policies_for_agent(caller.agent_id)
            if policies:
                data["governance"] = policies
            # Communication block (spec 6f961722, BR11): SELF-ONLY style guidance
            # {"source": <label>, "content": <dict>}, present ONLY when the caller
            # has a resolvable binding - an agent with none stays byte-identical to
            # the pre-feature whoami (D-CP-6). NEVER on _agent_to_data / discovery.
            communication = comm_presets.resolve_communication(caller.agent_id)
            if communication:
                data["communication"] = communication
        return data

    @server.tool()
    @tool_envelope
    def session_open(
        agent_id: Annotated[str, Field(description=_P_SESSION_AGENT)],
        workspace_id: Annotated[str | None, Field(description=_P_SESSION_WS)] = None,
        metadata: Annotated[Any, Field(description=_P_SESSION_METADATA)] = None,
    ) -> dict[str, Any]:
        """Open a session bound to (agent_id, workspace_id); returns a per-session session_secret (ONLY here - keep it; required by sensitive verbs in strict mode). Heartbeat to receive broadcasts."""
        return service.session_open(
            agent_id=agent_id, workspace_id=workspace_id, metadata=metadata
        )

    @server.tool()
    @tool_envelope
    def session_heartbeat(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        workspace_id: Annotated[
            str | None, Field(description=_P_SESSION_WS_GUARD)
        ] = None,
    ) -> dict[str, Any]:
        """Advance a session heartbeat and report the derived status; keeps you PRESENT (in the broadcast audience) and clear of the stale-session reaper."""
        return service.session_heartbeat(
            session_id=session_id, workspace_id=workspace_id
        )

    @server.tool()
    @tool_envelope
    def session_close(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        workspace_id: Annotated[
            str | None, Field(description=_P_SESSION_WS_GUARD)
        ] = None,
    ) -> dict[str, Any]:
        """Close a session (idempotent); repeating returns ok and stays closed."""
        return service.session_close(session_id=session_id, workspace_id=workspace_id)

    @server.tool()
    @tool_envelope
    def workspace_list(
        include_paths: Annotated[bool, Field(description=_P_INCLUDE_PATHS)] = False,
    ) -> dict[str, Any]:
        """GLOBAL-ADMIN: enumerate ALL workspaces. Paths OMITTED by default (include_paths=true is an admin/ops opt-in). For discovery use agent_list / capability_list."""
        return {"workspaces": service.workspace_list(include_paths=include_paths)}

    @server.tool()
    @tool_envelope
    def agent_list() -> dict[str, Any]:
        """List registered agents (global), each with role/capabilities and last_seen_at. Authenticated callers see only agents their comm scope can reach (plus themselves); anonymous callers see all."""
        caller = get_authenticated_agent()
        return {
            "agents": service.agent_list(
                caller_agent_id=caller.agent_id if caller is not None else None,
            )
        }

    @server.tool()
    @tool_envelope
    def agent_get(
        agent_id: Annotated[str, Field(description=_P_GET_AGENT_ID)],
    ) -> dict[str, Any]:
        """Return one agent's details incl. last_seen_at. Scoped by reachability: an agent outside your comm scope reads as NOT_FOUND, indistinguishable from a non-existent agent_id."""
        caller = get_authenticated_agent()
        return service.agent_get(
            agent_id=agent_id,
            caller_agent_id=caller.agent_id if caller is not None else None,
        )

    @server.tool()
    @tool_envelope
    def capability_list() -> dict[str, Any]:
        """List the capability catalog merged with owners: every registered name (with description; agent_count 0 if unowned), agents scoped to your comm reach. Normalised as capability routing matches."""
        caller = get_authenticated_agent()
        return {
            "capabilities": service.capability_list(
                caller_agent_id=caller.agent_id if caller is not None else None,
            )
        }
