"""MCP inbound tools for the handoff lifecycle slice.

Registers seven tools on the FastMCP server, each returning the canonical
envelope (success ``{ok:true,data}`` / failure ``{ok:false,error}``) via
:func:`tool_envelope`, so no exception ever crosses the adapter boundary:

* ``handoff_create``         - create an OPEN handoff (direct targets must
  name a registered agent and land an inbox notification for it).
* ``handoff_list_available`` - expire leases then list claimable handoffs.
* ``handoff_claim``          - atomically claim an OPEN handoff.
* ``handoff_complete``       - owner completes a CLAIMED handoff.
* ``handoff_reject``         - owner / direct-target rejects a handoff.
* ``handoff_cancel``         - creator retracts an OPEN handoff.
* ``handoff_get``            - read one handoff by id (status/result/reason).

This module is the slice's composition root: it wires the concrete SQLite
repositories into ``deps.repos`` (only if not already provided) and constructs
the :class:`HandoffService`. It does NOT import the MCP SDK; the live server is
passed into :func:`register`, matching the ``register(server, deps)`` contract.
"""

from __future__ import annotations

import functools
from typing import Annotated, Any

import anyio.to_thread
from pydantic import Field

from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.handoff import HandoffService
from okto_nexus.application.identity import SessionTrustGuard
from okto_nexus.envelope import (
    async_tool_envelope,
    require_json_object_param,
    tool_envelope,
)

#: Reused parameter descriptions (kept DRY across the handoff tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
_P_FROM_AGENT = (
    "Your agent_id (the creator); recorded as the handoff's originator - the owner "
    "is whichever agent later claims it (handoff_claim), not necessarily you."
)
#: Compact routing-target cheat-sheet: every CLAIM-eligibility strategy SHAPE
#: stays inline (so a harness without resources can target correctly - S7); the
#: rules/examples live in okto-nexus://reference/target-grammar (shared with
#: message_create). For a handoff the target controls ELIGIBILITY TO CLAIM
#: (competing consumers: all eligible see it, the first to handoff_claim wins).
_P_TARGET_HANDOFF = (
    "Routing target as a raw JSON object - which agents may CLAIM this handoff "
    '(REQUIRED). strategy one of: direct {"strategy":"direct","agent_id":"<id>"}; '
    'capability {"strategy":"capability","capability":"<cap>"}; role '
    '{"strategy":"role","role":"<role>"}; broadcast {"strategy":"broadcast"}; '
    'mixed {"strategy":"mixed","rules":[<sub-target>,...]}; direct_with_fallback '
    '{"strategy":"direct_with_fallback","agent_id":"<id>","fallback_after_seconds":<n>}. '
    "Competing-consumers: the first to handoff_claim wins. Rules/examples/"
    "edge-cases: read resource okto-nexus://reference/target-grammar."
)
_P_VISIBILITY = "Who may SEE the handoff (separate from who may CLAIM it = target). one of: public, eligible, private. REQUIRED (case-insensitive)."
_P_PAYLOAD = "Inline work content (optional; raw JSON object/array, string, or null - NOT JSON-encoded). Returned by handoff_list_available/handoff_claim. For large content pass an artifact_id."
_P_SESSION_OPT = "Session_id attributing this operation to a specific open session of yours (optional)."
#: INVARIANT: the sensitive handoff verbs (claim/complete/reject) share the
#: trust wording with message_create/inbox_* - one credential story bus-wide.
_P_SESSION_TRUST = (
    "Your session_id from session_open (optional in trust_mode=open; REQUIRED "
    "together with session_secret in trust_mode=strict)."
)
_P_SESSION_SECRET = (
    "The session_secret returned by session_open for session_id (optional in "
    "trust_mode=open - but if supplied it is VALIDATED, a mismatch fails; "
    "REQUIRED together with session_id in trust_mode=strict)."
)
_P_HANDOFF_AGENT = "Your agent_id (the worker); scopes visibility/eligibility and ownership. REQUIRED."
_P_HANDOFF_ID = "The handoff_id to act on. REQUIRED."
_P_CURSOR = (
    "Opaque pagination cursor: pass back the next_cursor from the previous page to "
    "continue (optional; omit or '0' to start from the beginning)."
)
_P_LIMIT = "Max handoffs per page (optional; default applied by the server, clamped to the maximum)."
_P_TIMEOUT = "Long-poll bound in SECONDS (optional). 0/omitted = non-blocking snapshot; >0 OPTS IN to blocking until a claimable handoff appears or the timeout elapses."
_P_RESULT = "Completion result (optional; string or JSON) persisted on the handoff, recorded with handoff.completed, and delivered to the creator inbox."
_P_REASON = "Human-readable reason (optional) persisted on the handoff, recorded with the rejection, and delivered to the creator inbox."
_P_CANCEL_REASON = (
    "Human-readable reason recorded with the handoff.cancelled event (optional)."
)
_P_GET_AGENT = "Your agent_id (REQUIRED). Creator and claimant always read; others are gated by the handoff visibility."


def build_service(deps: Any) -> HandoffService:
    """Wire the SQLite repos into ``deps.repos`` and build the service.

    Idempotent: repositories already present on ``deps.repos`` are reused so the
    handoff slice and any peers (e.g. identity providing ``agents``) share a
    single concrete instance.
    """
    repos = deps.repos
    if getattr(repos, "handoffs", None) is None:
        repos.handoffs = SqliteHandoffRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(repos, "sessions", None) is None:
        repos.sessions = SqliteSessionRepo(deps.clock)
    if getattr(repos, "messages", None) is None:
        repos.messages = SqliteMessageRepo(deps.clock)
    if getattr(repos, "deliveries", None) is None:
        repos.deliveries = SqliteMessageDeliveryRepo(deps.clock)
    return HandoffService(
        connection_factory=deps.connection_factory,
        handoffs=repos.handoffs,
        clock=deps.clock,
        config=deps.config,
        event_emitter=getattr(deps, "event_emitter", None),
        agents=repos.agents,
        messages=repos.messages,
        deliveries=repos.deliveries,
    )


def register(server: Any, deps: Any) -> None:
    """Register the handoff tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)
    # M10: the sensitive verbs (claim/complete/reject) are credential-gated
    # according to NexusConfig.trust_mode; the guard validates BEFORE the
    # service runs, in its own read-only transaction.
    trust = SessionTrustGuard(
        connection_factory=deps.connection_factory,
        sessions=deps.repos.sessions,
        trust_mode=getattr(deps.config, "trust_mode", "open"),
    )

    @server.tool()
    @tool_envelope
    def handoff_create(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        from_agent_id: Annotated[str, Field(description=_P_FROM_AGENT)],
        target: Annotated[Any, Field(description=_P_TARGET_HANDOFF)],
        visibility: Annotated[str, Field(description=_P_VISIBILITY)],
        payload: Annotated[Any, Field(description=_P_PAYLOAD)] = None,
        session_id: Annotated[str | None, Field(description=_P_SESSION_OPT)] = None,
    ) -> dict[str, Any]:
        """Create an OPEN handoff (validates target/visibility); emit handoff.created. After creating, poll handoff_get for status/result. Full docs: okto-nexus://reference/tool-docs/handoff."""
        require_json_object_param("target", target, required=True)
        return service.handoff_create(
            project_root=project_root,
            from_agent_id=from_agent_id,
            target=target,
            visibility=visibility,
            payload=payload,
            session_id=session_id,
        )

    @server.tool()
    @async_tool_envelope
    async def handoff_list_available(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        agent_id: Annotated[str, Field(description=_P_HANDOFF_AGENT)],
        cursor: Annotated[Any, Field(description=_P_CURSOR)] = None,
        limit: Annotated[Any, Field(description=_P_LIMIT)] = None,
        timeout_seconds: Annotated[Any, Field(description=_P_TIMEOUT)] = None,
    ) -> dict[str, Any]:
        """Expire leases, then list OPEN handoffs visible+eligible to the caller (paginated); each entry includes the payload for triage before claiming."""
        # Long-poll OFF the event loop (mirrors event_wait): the blocking wait
        # runs in a worker thread so a parked listener never freezes the shared
        # serve event loop (dashboard REST + every other MCP tool over HTTP).
        return await anyio.to_thread.run_sync(
            functools.partial(
                service.handoff_list_available,
                project_root=project_root,
                agent_id=agent_id,
                cursor=cursor,
                limit=limit,
                timeout_seconds=timeout_seconds,
            )
        )

    @server.tool()
    @tool_envelope
    def handoff_claim(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        handoff_id: Annotated[str, Field(description=_P_HANDOFF_ID)],
        agent_id: Annotated[str, Field(description=_P_HANDOFF_AGENT)],
        session_id: Annotated[str | None, Field(description=_P_SESSION_TRUST)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Atomically claim an OPEN handoff; single winner, others get a structured error. Returns the payload + claimed_by/lease_expires_at. In strict mode pass session_id + session_secret."""
        trust.require(
            tool="handoff_claim",
            agent_id=agent_id,
            session_id=session_id,
            session_secret=session_secret,
        )
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
        session_id: Annotated[str | None, Field(description=_P_SESSION_TRUST)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Owner-only transition CLAIMED -> COMPLETED; emit handoff.completed. In trust_mode=strict pass session_id + session_secret."""
        trust.require(
            tool="handoff_complete",
            agent_id=agent_id,
            session_id=session_id,
            session_secret=session_secret,
        )
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
        session_id: Annotated[str | None, Field(description=_P_SESSION_TRUST)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Reject a handoff (owner CLAIMED->REJECTED or direct-target OPEN->REJECTED). In trust_mode=strict pass session_id + session_secret."""
        trust.require(
            tool="handoff_reject",
            agent_id=agent_id,
            session_id=session_id,
            session_secret=session_secret,
        )
        return service.handoff_reject(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
            reason=reason,
        )

    @server.tool()
    @tool_envelope
    def handoff_cancel(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        handoff_id: Annotated[str, Field(description=_P_HANDOFF_ID)],
        agent_id: Annotated[
            str, Field(description="Your agent_id; must be the handoff's creator. REQUIRED.")
        ],
        reason: Annotated[str | None, Field(description=_P_CANCEL_REASON)] = None,
        session_id: Annotated[str | None, Field(description=_P_SESSION_TRUST)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Creator-only OPEN -> CANCELLED; retract a handoff nobody should take (e.g. a pool target matching zero agents). Only OPEN handoffs cancel. In strict mode pass session creds."""
        trust.require(
            tool="handoff_cancel",
            agent_id=agent_id,
            session_id=session_id,
            session_secret=session_secret,
        )
        return service.handoff_cancel(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
            reason=reason,
        )

    @server.tool()
    @tool_envelope
    def handoff_get(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        handoff_id: Annotated[str, Field(description=_P_HANDOFF_ID)],
        agent_id: Annotated[str, Field(description=_P_GET_AGENT)],
    ) -> dict[str, Any]:
        """Read one handoff by id: status, claimant, payload, result/rejected_reason. The creator's path to the outcome (do not scan events). Full docs: okto-nexus://reference/tool-docs/handoff."""
        return service.handoff_get(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
        )
