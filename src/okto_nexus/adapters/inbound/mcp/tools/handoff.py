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

from typing import Annotated, Any

from pydantic import Field

from okto_nexus.adapters.outbound.sqlite.handoff_repo import (
    SqliteHandoffRepo,
    SqliteTaskRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.application.handoff import HandoffService
from okto_nexus.envelope import tool_envelope

#: Reused parameter descriptions (kept DRY across the handoff tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
_P_FROM_AGENT = (
    "Your agent_id (the creator); recorded as the handoff's originator - the owner "
    "is whichever agent later claims it (handoff_claim), not necessarily you."
)
#: For a handoff the target controls ELIGIBILITY TO CLAIM (competing consumers:
#: all eligible see it, the first to handoff_claim wins). Spell out the enum.
_P_TARGET_HANDOFF = (
    "Routing rule selecting which agents may CLAIM this handoff. REQUIRED. "
    "Competing-consumers: every eligible agent sees it but only the first to "
    "handoff_claim wins (others get HANDOFF_ALREADY_CLAIMED); an unfinished "
    "claim's lease expires and it returns to the pool. strategy is one of: direct, "
    "capability, role, broadcast, mixed, direct_with_fallback. Shapes: "
    'direct {"strategy":"direct","agent_id":"<id>"} (one named worker); '
    'capability {"strategy":"capability","capability":"<cap>"} (string or list = '
    "any-of) - discover capabilities via capability_list; "
    'role {"strategy":"role","role":"<role>"} (exact, case-sensitive); '
    'broadcast {"strategy":"broadcast"} (any agent in the workspace); '
    'mixed {"strategy":"mixed","rules":[<sub-target>, ...]} (OR of sub-targets); '
    'direct_with_fallback {"strategy":"direct_with_fallback","agent_id":"<id>",'
    '"fallback_after_seconds":<n>,"fallback":<sub-target, default broadcast>} '
    "(named worker first; opens to the fallback pool after the delay)."
)
_P_VISIBILITY = (
    "Who may SEE the handoff - separate from who may CLAIM it (that is the "
    "target). one of: public, eligible, private. REQUIRED (case-insensitive). "
    "public = any agent in the workspace sees it; eligible = only agents the "
    "target makes eligible; private = eligible-only (never broader than the "
    "eligible set)."
)
_P_PAYLOAD = (
    "Inline request body / work content, returned by handoff_list_available and "
    "handoff_claim so the worker need not correlate the event (optional). A string "
    "is returned byte-for-byte; a non-string is stored/returned as opaque JSON "
    "TEXT. For large content, pass an artifact_id reference instead."
)
_P_SESSION_OPT = "Session_id attributing this operation to a specific open session of yours (optional)."
_P_HANDOFF_AGENT = "Your agent_id (the worker); scopes visibility/eligibility and ownership. REQUIRED."
_P_HANDOFF_ID = "The handoff_id to act on. REQUIRED."
_P_CURSOR = (
    "Opaque pagination cursor: pass back the next_cursor from the previous page to "
    "continue (optional; omit or '0' to start from the beginning)."
)
_P_LIMIT = "Max handoffs per page (optional; default applied by the server, clamped to the maximum)."
_P_TIMEOUT = (
    "Long-poll bound in SECONDS for an empty page (optional). >0 blocks until a "
    "claimable handoff appears or the timeout elapses; 0 OR OMITTED is a single "
    "non-blocking scan (no sleep) - unlike event_wait/message_wait, omitting it "
    "does NOT block. Clamped to the server max wait. BLOCKING (only when >0): "
    "parks your turn - see the server instructions."
)
_P_RESULT = "Completion result (string or JSON) recorded with handoff.completed (optional)."
_P_REASON = "Human-readable reason recorded with the rejection (optional)."


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
        project_root: Annotated[str, Field(description=_P_ROOT)],
        from_agent_id: Annotated[str, Field(description=_P_FROM_AGENT)],
        target: Annotated[Any, Field(description=_P_TARGET_HANDOFF)],
        visibility: Annotated[str, Field(description=_P_VISIBILITY)],
        payload: Annotated[str | None, Field(description=_P_PAYLOAD)] = None,
        session_id: Annotated[str | None, Field(description=_P_SESSION_OPT)] = None,
    ) -> dict[str, Any]:
        """Create an OPEN handoff after validating target/visibility; emit handoff.created.

        The optional ``payload`` (the inline request body / work content) is
        persisted with the row and returned by ``handoff_list_available`` and
        ``handoff_claim`` - the worker never has to correlate the
        ``handoff.created`` event to read it. A string is returned byte-for-byte;
        a non-string value is stored/returned as opaque JSON TEXT (not re-parsed).
        For large content, pass an ``artifact_id`` reference instead.
        """
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
        project_root: Annotated[str, Field(description=_P_ROOT)],
        agent_id: Annotated[str, Field(description=_P_HANDOFF_AGENT)],
        cursor: Annotated[str | None, Field(description=_P_CURSOR)] = None,
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
        timeout_seconds: Annotated[int | None, Field(description=_P_TIMEOUT)] = None,
    ) -> dict[str, Any]:
        """Expire leases, then list OPEN handoffs visible+eligible to the caller (paginated).

        Each entry includes the handoff ``payload`` so a worker can triage the
        work BEFORE claiming it.
        """
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
        project_root: Annotated[str, Field(description=_P_ROOT)],
        handoff_id: Annotated[str, Field(description=_P_HANDOFF_ID)],
        agent_id: Annotated[str, Field(description=_P_HANDOFF_AGENT)],
        session_id: Annotated[str | None, Field(description=_P_SESSION_OPT)] = None,
    ) -> dict[str, Any]:
        """Atomically claim an OPEN handoff; single winner, others get a structured error.

        The claim response returns the handoff ``payload`` (the work content)
        alongside ``claimed_by`` / ``lease_expires_at``.
        """
        return service.handoff_claim(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
            session_id=session_id,
        )

    @server.tool()
    @tool_envelope
    def handoff_complete(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        handoff_id: Annotated[str, Field(description=_P_HANDOFF_ID)],
        agent_id: Annotated[str, Field(description=_P_HANDOFF_AGENT)],
        result: Annotated[Any, Field(description=_P_RESULT)] = None,
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
        project_root: Annotated[str, Field(description=_P_ROOT)],
        handoff_id: Annotated[str, Field(description=_P_HANDOFF_ID)],
        agent_id: Annotated[str, Field(description=_P_HANDOFF_AGENT)],
        reason: Annotated[str | None, Field(description=_P_REASON)] = None,
    ) -> dict[str, Any]:
        """Reject a handoff (owner CLAIMED->REJECTED or direct-target OPEN->REJECTED)."""
        return service.handoff_reject(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
            reason=reason,
        )
