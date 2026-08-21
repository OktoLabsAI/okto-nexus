"""MCP inbound tools for the handoff lifecycle slice.

Registers eight tools on the FastMCP server, each returning the canonical
envelope (success ``{ok:true,data}`` / failure ``{ok:false,error}``) via
:func:`tool_envelope`, so no exception ever crosses the adapter boundary:

* ``handoff_create``         - create an OPEN handoff (direct targets must
  name a registered agent and land an inbox notification for it); optional
  ``acceptance_criteria``/``verify_by`` make it verification-first (I4);
  optional ``depends_on`` makes it a blocked DAG dependent (I5).
* ``handoff_list_available`` - expire leases then list claimable handoffs.
* ``handoff_claim``          - atomically claim an OPEN handoff.
* ``handoff_complete``       - owner completes a CLAIMED handoff (or parks it
  in VERIFYING when acceptance_criteria were set).
* ``handoff_verify``         - verifier-only pass/fail verdict on a VERIFYING
  handoff (pass -> COMPLETED, fail -> CLAIMED for rework).
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

from okto_nexus.adapters.outbound.sqlite.approvals_repo import (
    SqliteApprovalRepo,
)
from okto_nexus.adapters.outbound.sqlite.governance_repo import (
    SqliteGovernanceRepo,
)
from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo
from okto_nexus.adapters.outbound.sqlite.policy_repo import (
    SqliteAgentPolicyBindingRepo,
    SqlitePolicyRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.adapters.outbound.sqlite.capability_catalog_repo import (
    SqliteCapabilityCatalogRepo,
)
from okto_nexus.adapters.outbound.sqlite.tag_catalog_repo import (
    SqliteTagCatalogRepo,
)
from okto_nexus.application.approvals import ApprovalService
from okto_nexus.application.governance import GovernanceService
from okto_nexus.application.handoff import HandoffService
from okto_nexus.application.identity import SessionTrustGuard
from okto_nexus.domain.governance import ACTION_HANDOFF_CREATE
from okto_nexus.envelope import (
    async_tool_envelope,
    require_json_object_param,
    tool_envelope,
)

from ._guardrails import build_guardrail_service

#: Reused parameter descriptions (kept DRY across the handoff tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = "Absolute path to the project (defines the workspace scope)."
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
    '{"strategy":"role","role":"<role>"}; tag {"strategy":"tag","selector":'
    '{"<key>":["<value>",...]}} (flat: AND across keys, OR within values) or '
    'rich [{"key":"<k>","operator":"In|NotIn|Exists|DoesNotExist","values":'
    '["<v>",...]}] (ANDed; CAUTION: NotIn/DoesNotExist also match agents '
    'MISSING the key); broadcast {"strategy":"broadcast"}; mixed '
    '{"strategy":"mixed","rules":[<sub-target>,...]}; direct_with_fallback '
    '{"strategy":"direct_with_fallback","agent_id":"<id>","fallback_after_seconds":<n>}. '
    "Competing-consumers: the first to handoff_claim wins. Hierarchy/catalog "
    "rules, examples, edge-cases: okto-nexus://reference/target-grammar."
)
_P_VISIBILITY = "Who may SEE the handoff (separate from who may CLAIM it = target). one of: public, eligible, private. REQUIRED (case-insensitive)."
_P_PAYLOAD = "Inline work content (optional; raw JSON object/array, string, or null - NOT JSON-encoded). Returned only to the claimant by handoff_claim / claimant handoff_get. For large content pass an artifact_id."
_P_TRACE = (
    "Trajectory trace_id to stamp on this handoff (optional; non-empty string, "
    "max 128 chars). Needs the feature_trace flag ON, else accepted and ignored; "
    "omitted = generate one."
)
_P_SESSION_OPT = "Session_id attributing this operation to a specific open session of yours (optional)."
#: INVARIANT: the sensitive handoff verbs (claim/complete/reject) share the
#: trust wording with message_create/inbox_* - one credential story bus-wide.
_P_SESSION_TRUST = (
    "Your session_id from session_open (optional in trust_mode=open; REQUIRED "
    "together with session_secret in trust_mode=strict)."
)
_P_SESSION_SECRET = "session_secret from session_open for session_id (optional in open mode but VALIDATED if supplied; REQUIRED in strict mode)."
_P_HANDOFF_AGENT = (
    "Your agent_id (the worker); scopes visibility/eligibility and ownership. REQUIRED."
)
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
#: I4 verification-first params (spec c692da7e). The CONTRACT is fail-closed:
#: while feature_verification is OFF these params are REJECTED (never
#: accepted-and-ignored - the deliberate exception to the flag-gating norm).
_P_CRITERIA = (
    "Verification contract (optional; raw JSON list of 1..20 unique non-empty "
    "strings, max 500 chars each; IMMUTABLE). handoff_complete then parks the "
    "handoff in VERIFYING until the handoff_verify verdict. Needs "
    "feature_verification ON (rejected while OFF, never ignored)."
)
_P_VERIFY_BY = (
    "Who verifies (optional; only WITH acceptance_criteria; raw JSON object). "
    'one of: {"kind":"creator"} (default); {"kind":"agent","agent_id":"<id>"} '
    '(must be registered); {"kind":"capability","capability":"<name>"} (in '
    "the catalog; resolved at verify time). The claimant never verifies "
    "their own delivery."
)
_P_VERDICT = (
    "The verdict. one of: pass (VERIFYING -> COMPLETED; handoff.completed "
    "carries verified_by), fail (VERIFYING -> CLAIMED for rework, lease "
    "renewed). REQUIRED (lowercase)."
)
_P_FEEDBACK = (
    "Rework guidance (optional; max 2000 chars; only with verdict 'fail'). "
    "Persisted (each fail overwrites the previous) and delivered to the "
    "claimant's inbox."
)
_P_VERIFY_AGENT = (
    "Your agent_id (the verifier); must satisfy the handoff's verify_by "
    "resolved AT VERIFY TIME. The claimant (claimed_by) is always refused. "
    "REQUIRED."
)
#: I5 DAG param (spec 6522ad1f). Fail-closed like the verification contract:
#: while feature_dag is OFF the param is REJECTED, never accepted-and-ignored.
_P_DEPENDS_ON = (
    "Handoff ids this one depends on (optional; raw JSON list of 1..20 unique "
    "existing ids; IMMUTABLE). Blocked - unlisted/unclaimable - until ALL "
    "are COMPLETED. Needs feature_dag ON (rejected while OFF)."
)


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
    if getattr(repos, "tag_catalog", None) is None:
        repos.tag_catalog = SqliteTagCatalogRepo(deps.clock)
    if getattr(repos, "capability_catalog", None) is None:
        repos.capability_catalog = SqliteCapabilityCatalogRepo(deps.clock)
    if getattr(repos, "governance", None) is None:
        repos.governance = SqliteGovernanceRepo(deps.clock)
    if getattr(repos, "policies", None) is None:
        repos.policies = SqlitePolicyRepo(deps.clock)
    if getattr(repos, "policy_bindings", None) is None:
        repos.policy_bindings = SqliteAgentPolicyBindingRepo(deps.clock)
    guardrails = build_guardrail_service(deps)
    # Policy enforcement (spec 80624c1a): per-slice service composing the actor's
    # attached policies; always-on and binding-driven - an actor with no bindings
    # passes untouched (BR2 zero-regression). The handoff slice also uses it to
    # gate a declared direct target's audience at creation (FR6/BR13).
    governance = GovernanceService(
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
    # HITL approvals (spec 2948b2a2): the PROCESS-WIDE service built in
    # bootstrap; constructed here defensively for hand-rolled test Deps. It
    # must stay a single instance - the executor registered below is what the
    # operator decision path re-executes through.
    approvals = getattr(deps, "approvals", None)
    if approvals is None:
        if getattr(repos, "approvals", None) is None:
            repos.approvals = SqliteApprovalRepo()
        approvals = ApprovalService(
            connection_factory=deps.connection_factory,
            approvals=repos.approvals,
            clock=deps.clock,
            config=deps.config,
            event_emitter=getattr(deps, "event_emitter", None),
        )
        deps.approvals = approvals
    service = HandoffService(
        connection_factory=deps.connection_factory,
        handoffs=repos.handoffs,
        clock=deps.clock,
        config=deps.config,
        event_emitter=getattr(deps, "event_emitter", None),
        agents=repos.agents,
        messages=repos.messages,
        deliveries=repos.deliveries,
        tag_catalog=repos.tag_catalog,
        capability_catalog=repos.capability_catalog,
        governance=governance,
        approvals=approvals,
        guardrails=guardrails,
    )

    # Approved re-execution (BR2): the persisted kwargs re-enter the REAL use
    # case with the one-shot interception bypass; every other gate stays live.
    def _execute_handoff(kwargs: dict[str, Any]) -> dict[str, Any]:
        return service.handoff_create(**kwargs, _approved_execution=True)

    approvals.register_executor(ACTION_HANDOFF_CREATE, _execute_handoff)

    return service


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
        trace_id: Annotated[str | None, Field(description=_P_TRACE)] = None,
        acceptance_criteria: Annotated[Any, Field(description=_P_CRITERIA)] = None,
        verify_by: Annotated[Any, Field(description=_P_VERIFY_BY)] = None,
        depends_on: Annotated[Any, Field(description=_P_DEPENDS_ON)] = None,
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
            trace_id=trace_id,
            acceptance_criteria=acceptance_criteria,
            verify_by=verify_by,
            depends_on=depends_on,
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
        """Expire leases, then list OPEN handoffs visible+eligible to the caller (paginated); entries are metadata-only until claimed."""
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
        """Owner-only delivery of a CLAIMED handoff: -> COMPLETED, or -> VERIFYING when acceptance_criteria were set (verifier decides via handoff_verify). In strict mode pass session creds."""
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
    def handoff_verify(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        handoff_id: Annotated[str, Field(description=_P_HANDOFF_ID)],
        agent_id: Annotated[str, Field(description=_P_VERIFY_AGENT)],
        verdict: Annotated[str, Field(description=_P_VERDICT)],
        feedback: Annotated[str | None, Field(description=_P_FEEDBACK)] = None,
        session_id: Annotated[str | None, Field(description=_P_SESSION_TRUST)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Verifier-only verdict on a VERIFYING handoff: 'pass' -> COMPLETED (verified_by), 'fail' -> CLAIMED for rework (feedback + renewed lease). In strict mode pass session creds."""
        trust.require(
            tool="handoff_verify",
            agent_id=agent_id,
            session_id=session_id,
            session_secret=session_secret,
        )
        return service.handoff_verify(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
            verdict=verdict,
            feedback=feedback,
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
            str,
            Field(
                description="Your agent_id; must be the handoff's creator. REQUIRED."
            ),
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
        """Read a handoff by id: status, claimant, payload, result/rejected_reason + verification/dependency fields if set. The creator's path to the outcome. Full docs: okto-nexus://reference/tool-docs/handoff."""
        return service.handoff_get(
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id=agent_id,
        )
