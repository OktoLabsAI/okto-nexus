"""Handoff lifecycle application service.

Implements the use cases of Okto Nexus V1 spec #8:

* ``handoff_create``         - validate target/visibility + content limit, persist
  an ``OPEN`` handoff, emit ``handoff.created``. Applies the SAME D1b policy
  as ``message_create``: a ``direct`` target naming an unregistered agent is a
  hard ``NOT_FOUND`` (full rollback), while a pool target (capability/role/
  mixed/broadcast/``direct_with_fallback``) matching ZERO currently-registered
  agents succeeds WITH an explicit ``eligible_count``/``warning`` - lazy
  re-evaluation is a feature (an agent registered later can still claim), so
  zero-match is a warning, never a silent success and never an error. A
  DIRECTED handoff (``direct``/``direct_with_fallback`` naming a registered
  agent) additionally lands ONE synthetic notification in the named agent's
  inbox (same uow) so the recipient is woken without polling.
* ``handoff_list_available`` - run opportunistic lease expiry, then return the
  ``OPEN`` handoffs that are BOTH visible AND eligible to the caller, paginated
  (``next_cursor``/``has_more``/``timed_out``), with optional long-poll. The
  long-poll blocks via the :class:`Waiter` port and re-scans ONLY when the
  waiter reports a store change OR a time-driven boundary is reached (a lease
  expiring, a ``direct_with_fallback`` target opening to its fallback pool) -
  never once per poll interval.
* ``handoff_claim``          - opportunistic expiry + atomic conditional claim
  (single winner) gated by ``is_agent_eligible``.
* ``handoff_complete``       - owner-only ``CLAIMED -> COMPLETED``; persists
  ``result`` on the row and notifies the creator's inbox. When the row has
  ``acceptance_criteria`` (I4) the destination is ``VERIFYING`` instead: the
  metadata-only ``handoff.verification_requested`` event fires and the
  statically resolvable verifier is notified.
* ``handoff_verify``         - verifier-only decision on a VERIFYING handoff:
  ``pass`` -> COMPLETED (canonical ``handoff.completed`` + ``verified_by``),
  ``fail`` -> CLAIMED (feedback overwritten + lease renewed in the SAME
  conditional UPDATE). The executor (``claimed_by``) is always refused.
* ``handoff_reject``         - owner ``CLAIMED -> REJECTED`` or direct-target
  ``OPEN -> REJECTED``; persists ``rejected_reason`` and notifies the creator.
* ``handoff_cancel``         - creator-only ``OPEN -> CANCELLED`` (the
  retraction path for a handoff nobody should take anymore); a CLAIMED
  handoff is resolved by its claimant (complete/reject) or by lease expiry.
* ``handoff_get``            - read ONE handoff by id (status/result/reason):
  the creator's path to the outcome of a finished handoff - terminal handoffs
  leave ``handoff_list_available`` and their events are observability, not
  delivery.

``handoff_complete``/``handoff_reject`` mutate via CONDITIONAL updates that
mirror the claim (the WHERE clause re-asserts the expected status and
claimant); a 0-row outcome is re-read and mapped to the precise catalogue
error (already terminal? lease expired and reopened? different claimant?).

Dependency edges (I5, ``feature_dag``): ``handoff_create`` may name 1..20
pre-existing same-workspace handoffs in ``depends_on`` (immutable, acyclic by
construction; the flag gates CREATION fail-closed only). A handoff whose
dependencies are not all COMPLETED is simply OPEN-but-blocked, derived
ON-READ: it is excluded from ``handoff_list_available`` and refused at claim
(``DEPENDENCY_NOT_MET`` with aggregate counts, never ids). Both producers of
COMPLETED run the synchronous exactly-once unblock scan
(``handoff.unblocked``); REJECTED/CANCELLED producers signal
``handoff.dependency_failed`` to each non-terminal dependent's creator - no
cascade, the dependent is retained for an explicit decision.

This module lives in the application layer: it depends only on the ports in
:mod:`okto_nexus.application.ports`, the pure :mod:`okto_nexus.domain` helpers
(state machine + imported routing/eligibility), the error catalogue and
:class:`NexusConfig`. It NEVER imports ``sqlite3`` nor ``mcp`` (enforced by the
import-boundary test). Every state mutation and its lifecycle event commit
atomically inside a single unit of work.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from typing import Any, Iterator, Mapping, Optional, Sequence

from ..config import NexusConfig
from ..domain.base import (
    check_inline_size,
    clamp_limit,
    iso_plus,
    iso_to_epoch,
    new_id,
    normalize_cursor,
)
from ..domain.handoff import (
    DEPENDENCY_FAILED_STATUSES,
    EVENT_CANCELLED,
    EVENT_CLAIMED,
    EVENT_COMPLETED,
    EVENT_CREATED,
    EVENT_DEPENDENCY_FAILED,
    EVENT_EXPIRED,
    EVENT_REJECTED,
    EVENT_UNBLOCKED,
    EVENT_VERIFICATION_FAILED,
    EVENT_VERIFICATION_REQUESTED,
    HANDOFF_STREAM,
    STATUS_CANCELLED,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_OPEN,
    STATUS_REJECTED,
    STATUS_VERIFYING,
    TERMINAL_STATUSES,
    VERDICT_PASS,
    dependencies_satisfied,
    is_degenerate_self_claim,
    is_direct_target,
    is_eligible_verifier,
    normalize_visibility,
    static_verifier_for,
    summarize_dependencies,
    validate_acceptance_criteria,
    validate_depends_on,
    validate_target,
    validate_verdict,
    validate_verify_by,
)
from ..domain.ids import resolve_workspace_id
from ..domain.inbox import DELIVERY_UNREAD, new_delivery_id
from ..domain.routing import RoutingAgent, can_agent_see_event, is_agent_eligible
from ..domain.tag_selector import reachable, scope_selector, selector_matches
from ..domain.targets import (
    iter_target_capabilities,
    iter_target_selectors,
    normalize_strategy,
)
from ..domain.governance import ACTION_HANDOFF_CREATE
from ..domain.trace import resolve_trace
from ..errors import ErrorCode, OktoNexusError
from .approvals import ApprovalService
from .capabilities import CapabilityCatalogService
from .governance import GovernanceService
from .guardrails import GuardrailService
from .permissions import permission_set_for
from .ports import (
    AgentRepo,
    CapabilityCatalogRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    HandoffRepo,
    MessageDeliveryRepo,
    MessageRepo,
    TagCatalogRepo,
    UnitOfWork,
    Waiter,
)
from .tags import TagCatalogService

#: Default page size for ``handoff_list_available`` when no ``limit`` is given.
DEFAULT_PAGE_LIMIT = 100
#: Hard upper bound on a single page (defensive; keeps responses bounded).
MAX_PAGE_LIMIT = 500

#: Strategies that NAME one specific agent (the D1b directed set): ``direct``
#: requires the agent to be registered NOW; ``direct_with_fallback`` is the
#: sanctioned escape hatch for an agent that will register later (so it warns
#: instead of failing) but still notifies the named agent when it IS known.
_DIRECTED_STRATEGIES: frozenset[str] = frozenset({"direct", "direct_with_fallback"})

#: Explicit zero-match warning for a pool target (S2: never a silent zero).
_ZERO_ELIGIBLE_WARNING = (
    "no registered agent currently matches this target; the handoff will stay "
    "OPEN until a matching agent registers - use handoff_cancel if this was a "
    "mistake."
)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class HandoffService:
    """Use-case orchestration for the handoff lifecycle."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        handoffs: HandoffRepo,
        clock: Clock,
        config: NexusConfig,
        event_emitter: Optional[EventEmitter] = None,
        agents: Optional[AgentRepo] = None,
        waiter: Optional[Waiter] = None,
        messages: Optional[MessageRepo] = None,
        deliveries: Optional[MessageDeliveryRepo] = None,
        tasks: Any = None,
        tag_catalog: Optional[TagCatalogRepo] = None,
        capability_catalog: Optional[CapabilityCatalogRepo] = None,
        governance: Optional[GovernanceService] = None,
        approvals: Optional[ApprovalService] = None,
        guardrails: Optional[GuardrailService] = None,
    ) -> None:
        self._cf = connection_factory
        self._handoffs = handoffs
        self._clock = clock
        self._config = config
        self._emitter = event_emitter
        self._agents = agents
        # Inbox lanes for the directed-handoff / outcome notifications; when
        # either is unwired the notifications are skipped (the lifecycle
        # itself never depends on them).
        self._messages = messages
        self._deliveries = deliveries
        # ``tasks`` is DEPRECATED and ignored: the V1 Task subsystem had no
        # producer (no MCP tool ever created a task) and was removed. The
        # parameter is tolerated so legacy call sites keep constructing.
        del tasks
        # Central tag catalog (F1): when wired, every 'tag' target selector is
        # existence-checked fail-closed before the handoff persists.
        self._tag_catalog = tag_catalog
        # Central capability catalog (migration 014): when wired, every
        # 'capability' target name is existence-checked fail-closed too.
        self._capability_catalog = capability_catalog
        # Policy enforcement (spec 80624c1a): when wired, handoff_create is
        # enforced pre-persistence against the creator's attached policies
        # (governance + the declared-target audience gate); None = no gate.
        self._governance = governance
        # HITL approvals (spec 2948b2a2, feature_hitl): when wired, a
        # require_approval verdict intercepts the create into the approvals
        # queue instead of persisting; None = verdicts are ignored.
        self._approvals = approvals
        # Communication guardrails: when wired, payload/criteria are evaluated
        # before governance/HITL and before any handoff row/event/notification.
        self._guardrails = guardrails
        # Blocking seam for the list_available long-poll: an injected Waiter
        # (deterministic in tests), or the store's own change waiter.
        self._waiter = (
            waiter if waiter is not None else connection_factory.change_waiter()
        )

    @contextmanager
    def _create_uow(
        self,
        *,
        workspace_id: str,
        agent_id: Any,
    ):
        """The write UoW for handoff_create: guardrail/governance audited.

        Guardrails and governance share the same main transaction. Denied
        writes roll that transaction back; scrubbed audit events are emitted by
        the owning service after rollback, preserving the original error.
        """
        try:
            with self._cf.unit_of_work() as uow:
                yield uow
        except OktoNexusError as exc:
            if self._guardrails is not None:
                self._guardrails.emit_denied(
                    workspace_id=workspace_id,
                    actor_agent_id=agent_id,
                    exc=exc,
                )
            if self._governance is not None:
                self._governance.emit_denied(
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                    exc=exc,
                )
            raise

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #
    def handoff_create(
        self,
        *,
        project_root: Any,
        from_agent_id: Any,
        target: Any,
        visibility: Any,
        payload: Any = None,
        trace_id: Any = None,
        acceptance_criteria: Any = None,
        verify_by: Any = None,
        depends_on: Any = None,
        session_id: Any = None,
        _approved_execution: bool = False,
    ) -> dict[str, Any]:
        """Create an ``OPEN`` handoff and emit ``handoff.created`` atomically.

        ``_approved_execution`` is the INTERNAL one-shot bypass of the HITL
        interception (spec 2948b2a2 BR2): only the approval decision path sets
        it, so an approved re-execution cannot be re-intercepted. Every other
        gate (permissions, catalogs, D1b, governance deny/quotas) stays active.

        D1b (mirrors ``message_create``): a ``direct`` target naming an agent
        that is not registered raises ``NOT_FOUND`` and rolls the WHOLE unit
        of work back (no row, no event). Every other strategy resolves its
        currently-eligible agents at creation time: the response carries
        ``eligible_count`` and, when it is 0, an explicit ``warning`` - the
        handoff still persists because eligibility is lazily re-evaluated at
        claim time (an agent registered later can claim it).

        A DIRECTED target (``direct``/``direct_with_fallback``) naming a
        REGISTERED agent also lands one synthetic notification message in that
        agent's inbox inside the same unit of work (the response lists it in
        ``notified``); the notification wakes the recipient - claiming still
        happens via ``handoff_claim``.

        Raises ``WORKSPACE_REQUIRED``/``WORKSPACE_UNRESOLVED`` for workspace
        resolution, ``VALIDATION_ERROR`` for a missing ``from_agent_id`` or an
        invalid target/visibility, and ``CONTENT_TOO_LARGE`` for an oversized
        inline payload.
        """
        workspace_id = self._resolve_workspace(project_root)
        if not _is_nonempty_str(from_agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "from_agent_id is required.",
                {"from_agent_id": from_agent_id},
            )
        normalized_target = validate_target(target)
        normalized_visibility = normalize_visibility(visibility)
        self._check_inline_size("payload", payload)
        payload_text = self._serialize_payload(payload)
        # Trace resolution (D3/D4/D6): the flag is read LIVE at the start of
        # the use case; OFF accepts-and-ignores the parameter (always None),
        # ON validates the explicit id or generates one - handoffs never
        # inherit (no parent). Pure phase: a bad trace persists nothing.
        resolved_trace = resolve_trace(
            explicit=trace_id,
            inherited=None,
            feature_on=bool(getattr(self._config, "feature_trace", False)),
        )
        # Verification contract (I4, feature_verification): fail-closed BOTH
        # ways. OFF rejects the new params outright - a verification contract
        # is never accepted-and-ignored (BR2; deliberate exception to the
        # trace flag's accept-and-ignore) because silently dropping it would
        # hand the creator a false quality guarantee. ON validates the full
        # grammar here (pure phase); existence and degeneracy gate below.
        criteria_list: list[str] | None = None
        verify_by_descriptor: dict[str, Any] | None = None
        if acceptance_criteria is not None or verify_by is not None:
            if not bool(getattr(self._config, "feature_verification", False)):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "acceptance_criteria/verify_by require feature_verification, "
                    "which is OFF - a verification contract is never accepted-"
                    "and-ignored. Enable the flag or drop the parameters.",
                    {"feature_verification": False},
                )
            if acceptance_criteria is None:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "verify_by requires acceptance_criteria - the verifier "
                    "judges the delivery against explicit criteria.",
                    {"verify_by": verify_by},
                )
            criteria_list = validate_acceptance_criteria(acceptance_criteria)
            # BR8: the creator default is MATERIALISED at write time - a
            # verifiable row always carries an explicit descriptor, never an
            # inferred-on-read default.
            verify_by_descriptor = (
                validate_verify_by(verify_by)
                if verify_by is not None
                else {"kind": "creator"}
            )
            if is_degenerate_self_claim(
                normalized_target,
                creator=str(from_agent_id),
                verify_by=verify_by_descriptor,
            ):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "This verification contract is statically unsatisfiable: "
                    "the direct target is the only possible claimant AND the "
                    "resolved verifier, and the executor can never verify "
                    "their own delivery. Change the target or the verify_by.",
                    {
                        "target": normalized_target,
                        "verify_by": verify_by_descriptor,
                    },
                )
        criteria_text = (
            json.dumps(criteria_list, ensure_ascii=False)
            if criteria_list is not None
            else None
        )
        verify_by_text = (
            json.dumps(verify_by_descriptor, ensure_ascii=False)
            if verify_by_descriptor is not None
            else None
        )
        # Dependency edges (I5, feature_dag): fail-closed BOTH ways, the
        # verification precedent (BR2) - OFF rejects the parameter outright
        # (a dependency silently dropped would run work out of order), ON
        # validates the pure grammar here (1..20 unique ids). Existence and
        # state gate below, inside the UoW. Acyclicity holds by construction:
        # every dependency must ALREADY exist, and edges are immutable.
        depends_list: list[str] | None = None
        if depends_on is not None:
            if not bool(getattr(self._config, "feature_dag", False)):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "depends_on requires feature_dag, which is OFF - a "
                    "dependency edge is never accepted-and-ignored. Enable "
                    "the flag or drop the parameter.",
                    {"feature_dag": False},
                )
            depends_list = validate_depends_on(depends_on)

        strategy = normalized_target["strategy"]
        target_text = json.dumps(normalized_target, ensure_ascii=False)
        now = self._clock.now_iso()
        handoff_id = new_id("hof")
        extras: dict[str, Any] = {}

        guardrail_fields: dict[str, Any] = {
            "payload": payload_text,
            "acceptance_criteria": criteria_list,
        }

        with self._create_uow(workspace_id=workspace_id, agent_id=from_agent_id) as uow:
            permission_set_for(self._agents, uow, from_agent_id).require(
                "handoffs", "create"
            )
            # Catalog EXISTENCE gate (F1, fail-closed): every 'tag' selector
            # in the target (incl. nested mixed rules / fallback) must
            # reference registered tags, or the create rolls back untouched.
            self._ensure_target_selectors_registered(uow, normalized_target)
            self._ensure_target_capabilities_registered(uow, normalized_target)
            if verify_by_descriptor is not None:
                self._ensure_verifier_resolvable(uow, verify_by_descriptor)
            dep_statuses: list[str] = []
            if depends_list is not None:
                dep_statuses = self._ensure_dependencies_satisfiable(
                    uow, workspace_id=workspace_id, depends_on=depends_list
                )
            if self._agents is not None:
                if strategy == "direct":
                    # D1b hard gate: a typo'd direct handoff must not sit OPEN
                    # forever, silently. Raising here rolls everything back.
                    named = str(normalized_target.get("agent_id"))
                    target_agent = self._agents.get(uow, named)
                    if target_agent is None:
                        raise OktoNexusError(
                            ErrorCode.NOT_FOUND,
                            f"agent_id '{named}' is not a registered agent; "
                            "check agent_list or register it first. For an "
                            "agent that will register later, use "
                            "direct_with_fallback.",
                            {"agent_id": named, "strategy": strategy},
                        )
                    # Audience gate at CREATION (FR6/BR13): the DECLARED direct
                    # target is evaluated against the creator's EFFECTIVE
                    # audience (combined bindings) here, additively and
                    # fail-safe - the claim-time reachability check stays as the
                    # dynamic gate; this only fails EARLIER, never widens reach.
                    # Opaque by design: the denial never reveals the target's
                    # tags or the creator's selectors (only that the creator's
                    # own scope excludes the target). No bindings on either side
                    # => unrestricted (zero-regression).
                    if self._governance is not None:
                        creator_agent = self._agents.get(uow, str(from_agent_id))
                        if not self._governance.audience_reachable(
                            uow,
                            sender_id=from_agent_id,
                            sender_tags=getattr(creator_agent, "tags", None),
                            recipient_id=named,
                            recipient_tags=getattr(target_agent, "tags", None),
                        ):
                            raise OktoNexusError(
                                ErrorCode.PERMISSION_DENIED,
                                "Direct handoffs from this agent are restricted "
                                "by its communication scope; the target is "
                                "outside it.",
                                {"required_permission": "comm_scope.outbound"},
                            )
                else:
                    eligible = self._eligible_agent_ids(
                        uow, workspace_id, normalized_target, now
                    )
                    extras["eligible_count"] = len(eligible)
                    if not eligible:
                        # Success-with-warning (S2): never silent, never fatal
                        # (lazy re-evaluation lets a later registrant claim).
                        extras["warning"] = _ZERO_ELIGIBLE_WARNING
            if (
                self._guardrails is not None
                and self._guardrails.has_enabled_assignments(uow)
            ):
                self._guardrails.enforce(
                    uow,
                    workspace_id=workspace_id,
                    actor_agent_id=from_agent_id,
                    surface="handoff_create",
                    fields=guardrail_fields,
                )
            # Governance gate (spec 80624c1a): deny + max_count + max_bytes +
            # max_open_handoffs from the actor's attached policies, composed and
            # evaluated PRE-persistence in this same UoW (no bindings = no
            # governance inside enforce() - BR2).
            if self._governance is not None:
                verdict = self._governance.enforce(
                    uow,
                    agent_id=from_agent_id,
                    action=ACTION_HANDOFF_CREATE,
                    size_bytes=len(payload_text.encode("utf-8")) if payload_text else 0,
                )
                if (
                    verdict is not None
                    and self._approvals is not None
                    and not _approved_execution
                ):
                    # HITL interception (spec 2948b2a2 FR2): the create WOULD
                    # have passed but a require_approval policy matched. The
                    # approvals row + approval.requested commit in THIS UoW
                    # (BR1) and the pending envelope early-returns - no
                    # handoff row, no notification, no handoff.created. The
                    # ORIGINAL project_root is persisted (resolution is
                    # deterministic); session_id is deliberately NOT (BR2 -
                    # sessions are ephemeral, secrets never land in the table).
                    approval_kwargs: dict[str, Any] = {
                        "project_root": project_root,
                        "from_agent_id": from_agent_id,
                        "target": normalized_target,
                        "visibility": normalized_visibility,
                        "payload": payload,
                        "trace_id": resolved_trace,
                    }
                    if criteria_list is not None:
                        # An intercepted verifiable create re-executes with
                        # its verification contract intact (normalised values;
                        # revalidation is idempotent). Plain creates keep the
                        # pre-I4 kwargs shape byte-identical (BR1).
                        approval_kwargs["acceptance_criteria"] = criteria_list
                        approval_kwargs["verify_by"] = verify_by_descriptor
                    if depends_list is not None:
                        # An intercepted dependent create re-executes with its
                        # normalised depends_on, and the replay REVALIDATES
                        # existence/state (BR10): a dependency that terminally
                        # failed while the approval sat pending refuses the
                        # re-execution instead of persisting a dead edge.
                        approval_kwargs["depends_on"] = depends_list
                    return self._approvals.intercept(
                        uow,
                        workspace_id=workspace_id,
                        agent_id=from_agent_id,
                        action=ACTION_HANDOFF_CREATE,
                        policy_id=verdict.policy.policy_id,
                        kwargs=approval_kwargs,
                        trace_id=resolved_trace,
                    )
            handoff = self._handoffs.create(
                uow,
                handoff_id=handoff_id,
                workspace_id=workspace_id,
                status=STATUS_OPEN,
                from_agent_id=from_agent_id,
                target=target_text,
                visibility=normalized_visibility,
                payload=payload_text,
                trace_id=resolved_trace,
                acceptance_criteria=criteria_text,
                verify_by=verify_by_text,
                created_at=now,
            )
            born_blocked = False
            if depends_list is not None:
                # Immutable edge set (I5): the rows land in the SAME UoW as
                # the handoff - a rollback leaves neither. Blocked-ness is
                # derived on-read from live dependency statuses (the gates
                # read the TABLE, never the flag), so nothing materialises.
                self._handoffs.create_dependencies(
                    uow,
                    handoff_id=handoff.handoff_id,
                    workspace_id=workspace_id,
                    depends_on=depends_list,
                    created_at=now,
                )
                born_blocked = not dependencies_satisfied(dep_statuses)
            self._touch_agent(uow, from_agent_id, now)
            event_payload: dict[str, Any] = {
                "handoff_id": handoff.handoff_id,
                "workspace_id": handoff.workspace_id,
                "status": handoff.status,
                "from_agent_id": handoff.from_agent_id,
                "target": normalized_target,
                "visibility": handoff.visibility,
                "created_at": handoff.created_at,
            }
            # Metadata-only: the work payload is returned only to the claimant
            # by handoff_claim / claimant handoff_get. Event streams and
            # directed inbox notifications must not become side channels.
            if depends_list is not None:
                event_payload["depends_on"] = depends_list
            if _is_nonempty_str(session_id):
                event_payload["session_id"] = session_id
            self._emit(
                uow,
                handoff=handoff,
                event_type=EVENT_CREATED,
                actor_agent_id=from_agent_id,
                payload=event_payload,
            )
            if strategy in _DIRECTED_STRATEGIES:
                named = str(normalized_target.get("agent_id"))
                body = {
                    "kind": "handoff.directed",
                    "handoff_id": handoff.handoff_id,
                    "from_agent_id": from_agent_id,
                    "next_step": "handoff_claim with this handoff_id",
                }
                # A dependent born blocked says so in the SUBJECT (I5): the
                # named agent learns not to rush a claim that would only be
                # refused - handoff.unblocked wakes it when the edges clear.
                subject = f"handoff {handoff.handoff_id} directed to you" + (
                    " (blocked)" if born_blocked else ""
                )
                if self._notify_inbox(
                    uow,
                    workspace_id=workspace_id,
                    recipient_agent_id=named,
                    from_agent_id=from_agent_id,
                    subject=subject,
                    body=body,
                    now=now,
                    trace_id=handoff.trace_id,
                ):
                    extras["notified"] = [named]
        response = {
            "handoff_id": handoff.handoff_id,
            "workspace_id": handoff.workspace_id,
            "status": STATUS_OPEN,
            "created_at": handoff.created_at,
        }
        if handoff.trace_id is not None:
            # Echoed only when resolved (flag ON): the creator carries the
            # trace forward; flag-OFF responses keep the pre-feature shape.
            response["trace_id"] = handoff.trace_id
        if criteria_list is not None:
            # Echoed only for a verifiable handoff; a plain handoff keeps the
            # pre-I4 response shape (BR1).
            response["acceptance_criteria"] = criteria_list
            response["verify_by"] = verify_by_descriptor
        if depends_list is not None:
            # Echoed only for a dependent handoff (the non-NULL pattern): the
            # normalised edge list plus the aggregate snapshot at creation -
            # an already-COMPLETED dependency is born satisfied.
            response["depends_on"] = depends_list
            response["dependencies"] = summarize_dependencies(dep_statuses)
        response.update(extras)
        return response

    # ------------------------------------------------------------------ #
    # list_available
    # ------------------------------------------------------------------ #
    def handoff_list_available(
        self,
        *,
        project_root: Any,
        agent_id: Any,
        cursor: Any = None,
        limit: Any = None,
        timeout_seconds: Any = None,
    ) -> dict[str, Any]:
        """List the OPEN, visible AND eligible handoffs for ``agent_id``.

        Runs ``expire_old_leases`` first (opportunistic), then filters by
        :func:`can_agent_see_event` AND :func:`is_agent_eligible`. The result is
        paginated with ``next_cursor``/``has_more``/``timed_out``. When
        ``timeout_seconds`` is positive and the page is empty, the call blocks
        (bounded by ``config.max_wait_timeout_seconds``) until a handoff
        appears or the deadline is reached (``timed_out=True``). Blocking goes
        through the :class:`Waiter` port and the scan is re-run ONLY when

        * the waiter reports a store change (a commit by any process), or
        * the next TIME-DRIVEN boundary arrives - the earliest pending lease
          expiry (a reopen needs no write until this scan performs it) or
          ``direct_with_fallback`` opening (eligibility widens with no write);
          see :meth:`_next_wake_epoch`.
        """
        workspace_id = self._resolve_workspace(project_root)
        if not _is_nonempty_str(agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "agent_id is required.",
                {"agent_id": agent_id},
            )
        offset = self._parse_cursor(cursor)
        page_limit = self._parse_limit(limit)
        timeout = self._clamp_timeout(timeout_seconds)
        waiter = self._waiter
        # Floor for boundary waits: a boundary sitting exactly on ``now``
        # (e.g. a lease at the strict-expiry edge) re-scans at poll cadence
        # instead of busy-looping.
        poll_floor_s = max(self._config.poll_interval_ms, 1) / 1000.0
        # Snapshot precedes the first scan (Waiter contract): a write landing
        # between the scan and the wait wakes the first wait_for_change.
        token = waiter.snapshot() if timeout > 0 else None
        deadline = waiter.monotonic() + timeout if timeout > 0 else None

        while True:
            now = self._clock.now_iso()
            with self._cf.unit_of_work() as uow:
                agent = self._routing_agent(uow, agent_id, workspace_id)
                available = self._available_handoffs(uow, workspace_id, agent, now)
            page = available[offset : offset + page_limit]
            has_more = (offset + len(page)) < len(available)
            if page or timeout <= 0:
                return self._list_response(page, offset, has_more, timed_out=False)
            remaining = deadline - waiter.monotonic()
            if remaining <= 0:
                return self._list_response(page, offset, has_more, timed_out=True)
            wait_s = remaining
            next_wake = self._next_wake_epoch(workspace_id, now)
            if next_wake is not None:
                until_boundary = max(next_wake - iso_to_epoch(now), poll_floor_s)
                wait_s = min(remaining, until_boundary)
            changed = waiter.wait_for_change(token, wait_s)
            if not changed and wait_s >= remaining:
                # Full remaining window, no commit anywhere and no boundary
                # pending: a re-scan provably finds the same empty page.
                return self._list_response(page, offset, has_more, timed_out=True)
            # Otherwise re-scan: a write happened, or a time boundary was
            # reached (lease expiry / fallback opening processed by the scan).
            token = waiter.snapshot()

    def _available_handoffs(
        self, uow: UnitOfWork, workspace_id: str, agent: RoutingAgent, now: str
    ) -> list[Any]:
        """Expire stale leases, then return the OPEN visible+eligible handoffs.

        Besides visibility and target eligibility, the caller must be able to
        REACH the handoff's creator (F2 symmetry: the creator's outbound AND
        the caller's own inbound) - what this list offers is exactly what
        ``handoff_claim`` would accept, and an unreachable creator's handoff
        is silently omitted (the policy never leaks).
        """
        self._expire_old_leases(uow, workspace_id=workspace_id, now_iso=now)
        rows = self._handoffs.list(uow, workspace_id=workspace_id, status=STATUS_OPEN)
        visible = [
            h
            for h in rows
            if can_agent_see_event(agent, h, now)
            and is_agent_eligible(agent, h.target, h.created_at, now)
            and self._claimant_in_creator_audience(uow, h, agent.agent_id)
        ]
        if visible:
            # Dependency exclusion (I5/FR3): a blocked handoff is not offered
            # - this list returns exactly what handoff_claim would accept.
            # ONE aggregate query per scan; a handoff with no dependency rows
            # is absent from the map and passes through untouched.
            aggregates = self._handoffs.dependency_aggregates(
                uow,
                workspace_id=workspace_id,
                handoff_ids=[h.handoff_id for h in visible],
            )
            if aggregates:
                visible = [
                    h
                    for h in visible
                    if h.handoff_id not in aggregates
                    or aggregates[h.handoff_id]["satisfied"]
                    == aggregates[h.handoff_id]["total"]
                ]
        visible.sort(key=lambda h: (h.created_at or "", h.handoff_id))
        return visible

    def _next_wake_epoch(self, workspace_id: str, now_iso: str) -> float | None:
        """Earliest FUTURE instant the available set can change WITHOUT a write.

        Two boundaries are time-driven (so ``data_version`` alone would sleep
        through them):

        * a CLAIMED lease expiring - the next scan reopens it (strict
          ``lease_expires_at < now``, so the boundary is the lease instant
          itself, re-checked at poll cadence until strictly past);
        * a ``direct_with_fallback`` target (possibly nested under ``mixed``
          rules or a ``fallback`` sub-target) reaching
          ``created_at + fallback_after_seconds`` - eligibility widens to the
          fallback pool with no write.

        Returns ``None`` when no boundary is pending. Read-only (own deferred
        snapshot; never competes for the WAL writer lock) and defensive: a row
        with a malformed timestamp/target can never break the wait - it is
        skipped (the write path already validates, so this is row-level
        hardening, not policy).
        """
        now_epoch = iso_to_epoch(now_iso)
        candidates: list[float] = []
        with self._cf.unit_of_work(write=False) as uow:
            for handoff in self._handoffs.list(
                uow, workspace_id=workspace_id, status=STATUS_CLAIMED
            ):
                if not handoff.lease_expires_at:
                    continue
                try:
                    lease_epoch = iso_to_epoch(handoff.lease_expires_at)
                except (TypeError, ValueError):
                    continue
                if lease_epoch >= now_epoch:
                    candidates.append(lease_epoch)
            for handoff in self._handoffs.list(
                uow, workspace_id=workspace_id, status=STATUS_OPEN
            ):
                if not handoff.created_at:
                    continue
                try:
                    created_epoch = iso_to_epoch(handoff.created_at)
                    target = _loads_target(handoff.target)
                    for boundary in _fallback_boundaries(target, created_epoch):
                        if boundary > now_epoch:
                            candidates.append(boundary)
                except (TypeError, ValueError, OktoNexusError):
                    continue
        return min(candidates) if candidates else None

    def _list_response(
        self, page: list[Any], offset: int, has_more: bool, *, timed_out: bool
    ) -> dict[str, Any]:
        return {
            "handoffs": [self._serialize_available(h) for h in page],
            "next_cursor": str(offset + len(page)) if has_more else None,
            "has_more": has_more,
            "timed_out": timed_out,
        }

    @staticmethod
    def _serialize_available(handoff: Any) -> dict[str, Any]:
        return {
            "handoff_id": handoff.handoff_id,
            "status": handoff.status,
            "target": _loads_target(handoff.target),
            "visibility": handoff.visibility,
            "from_agent_id": handoff.from_agent_id,
            "created_at": handoff.created_at,
        }

    # ------------------------------------------------------------------ #
    # claim
    # ------------------------------------------------------------------ #
    def handoff_claim(
        self,
        *,
        project_root: Any,
        handoff_id: Any,
        agent_id: Any,
        session_id: Any = None,
    ) -> dict[str, Any]:
        """Atomically claim an OPEN handoff (single winner).

        Expires stale leases first, gates on :func:`is_agent_eligible`
        (``NOT_ELIGIBLE_TO_CLAIM``), then runs the atomic conditional UPDATE.
        Zero affected rows map to ``HANDOFF_ALREADY_CLAIMED`` /
        ``WORKSPACE_MISMATCH`` / ``NOT_FOUND`` with no event emitted.
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        now = self._clock.now_iso()
        lease_ttl = int(self._config.handoff_lease_ttl_seconds)
        # iso_plus is the lease-WRITE boundary: it rejects a non-canonical
        # (non-lexicographically-comparable) clock value and always emits the
        # fixed-width form.
        lease_expires_at = iso_plus(now, lease_ttl)

        with self._cf.unit_of_work() as uow:
            permission_set_for(self._agents, uow, agent_id).require("handoffs", "work")
            self._expire_old_leases(uow, workspace_id=workspace_id, now_iso=now)
            handoff = self._load_in_workspace(uow, workspace_id, handoff_id)

            agent = self._routing_agent(uow, agent_id, workspace_id)
            # Eligibility is target-match AND creator-audience, evaluated
            # DYNAMICALLY at claim time (current tags, not creation-time
            # state). One shared, OPAQUE refusal for both legs: the claimant
            # never learns whether the target or the creator's comm_scope
            # excluded it (the policy never leaks).
            if not is_agent_eligible(
                agent, handoff.target, handoff.created_at, now
            ) or not self._claimant_in_creator_audience(uow, handoff, agent_id):
                raise OktoNexusError(
                    ErrorCode.NOT_ELIGIBLE_TO_CLAIM,
                    "Agent is not eligible to claim this handoff.",
                    {"handoff_id": handoff_id, "agent_id": agent_id},
                )
            # Dependency gate (I5/BR7): read from the TABLE, never the flag -
            # a blocked handoff stays refusable even after feature_dag is
            # switched off. Details carry AGGREGATE counts only (BR8): the
            # dependency ids never leak to a claimant who may not be allowed
            # to see the sibling handoffs.
            dep_rows = self._handoffs.read_dependencies(
                uow, workspace_id=workspace_id, handoff_id=handoff_id
            )
            if dep_rows:
                dep_statuses = [row["status"] or "" for row in dep_rows]
                if not dependencies_satisfied(dep_statuses):
                    summary = summarize_dependencies(dep_statuses)
                    raise OktoNexusError(
                        ErrorCode.DEPENDENCY_NOT_MET,
                        "This handoff is blocked: not every dependency is "
                        "COMPLETED yet. Wait for its handoff.unblocked event "
                        "(or the unblocked inbox notice on a directed "
                        "handoff), then claim again.",
                        {
                            "handoff_id": handoff_id,
                            "pending": summary["pending"],
                            "failed": summary["failed"],
                        },
                    )

            claimed = self._handoffs.claim(
                uow,
                workspace_id=workspace_id,
                handoff_id=handoff_id,
                claimed_by=agent_id,
                lease_expires_at=lease_expires_at,
                updated_at=now,
            )
            self._touch_agent(uow, agent_id, now)
            payload = {
                "handoff_id": claimed.handoff_id,
                "workspace_id": claimed.workspace_id,
                "status": claimed.status,
                "claimed_by": claimed.claimed_by,
                "lease_expires_at": claimed.lease_expires_at,
            }
            if _is_nonempty_str(session_id):
                payload["claimed_session_id"] = session_id
            self._emit(
                uow,
                handoff=claimed,
                event_type=EVENT_CLAIMED,
                actor_agent_id=agent_id,
                payload=payload,
            )
        return {
            "handoff_id": claimed.handoff_id,
            "workspace_id": claimed.workspace_id,
            "status": STATUS_CLAIMED,
            "claimed_by": claimed.claimed_by,
            "lease_expires_at": claimed.lease_expires_at,
            "payload": claimed.payload,
        }

    # ------------------------------------------------------------------ #
    # complete
    # ------------------------------------------------------------------ #
    def handoff_complete(
        self,
        *,
        project_root: Any,
        handoff_id: Any,
        agent_id: Any,
        result: Any = None,
    ) -> dict[str, Any]:
        """Owner-only delivery: ``CLAIMED -> COMPLETED`` or ``-> VERIFYING``.

        ``NOT_OWNER`` when ``agent_id != claimed_by``; ``INVALID_TRANSITION``
        when the source state is not ``CLAIMED``. The mutation is a single
        conditional UPDATE (mirrors the claim); a 0-row outcome is re-read and
        mapped to the precise error. ``result`` (string verbatim, non-string
        serialised - the ``payload`` contract) is persisted on the row in the
        SAME UPDATE so the creator can read it later via ``handoff_get``.

        A handoff WITHOUT ``acceptance_criteria`` completes exactly as before
        I4 (byte-identical flow - BR1): ``handoff.completed`` event + creator
        inbox notification. A VERIFIABLE handoff instead parks in
        ``VERIFYING``: it emits the metadata-only
        ``handoff.verification_requested`` event and notifies the STATICALLY
        resolvable verifier's inbox (creator/agent kinds; a ``capability``
        verifier is dynamic, so observers rely on the event) - completion is
        then decided by ``handoff_verify``.
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        self._check_inline_size("result", result)
        result_text = self._serialize_payload(result)
        now = self._clock.now_iso()

        with self._cf.unit_of_work() as uow:
            permission_set_for(self._agents, uow, agent_id).require("handoffs", "work")
            # Verification routing (I4): the ROW's contract picks the
            # destination. The feature flag gates contract CREATION only - a
            # verifiable handoff must never silently skip its verification,
            # even when the flag was turned off after it was created (it
            # stays decidable). A handoff without criteria keeps the pre-I4
            # flow byte-identical (BR1).
            verification = self._handoffs.read_verification(
                uow, workspace_id=workspace_id, handoff_id=handoff_id
            )
            verifiable = bool(verification and verification.get("acceptance_criteria"))
            destination = STATUS_VERIFYING if verifiable else STATUS_COMPLETED
            updated = self._handoffs.transition_claimed(
                uow,
                workspace_id=workspace_id,
                handoff_id=handoff_id,
                claimed_by=agent_id,
                status=destination,
                updated_at=now,
                result=result_text,
            )
            if updated is None:
                self._raise_claimed_transition_error(
                    uow, workspace_id, handoff_id, agent_id, verb="complete"
                )
            self._touch_agent(uow, agent_id, now)
            if not verifiable:
                payload = {
                    "handoff_id": updated.handoff_id,
                    "workspace_id": updated.workspace_id,
                    "status": updated.status,
                }
                if result is not None:
                    payload["result"] = result
                self._emit(
                    uow,
                    handoff=updated,
                    event_type=EVENT_COMPLETED,
                    actor_agent_id=agent_id,
                    payload=payload,
                )
                notified = self._notify_creator_outcome(
                    uow,
                    handoff=updated,
                    actor_agent_id=agent_id,
                    kind=EVENT_COMPLETED,
                    outcome_key="result",
                    outcome_text=result_text,
                    now=now,
                )
                self._unblock_dependents(
                    uow, completed=updated, actor_agent_id=agent_id, now=now
                )
            else:
                # Metadata-only event: the verification CONTRACT rides along
                # (it is what a dynamic capability verifier needs to act), the
                # delivered RESULT does not - the verifier inspects it via
                # handoff_get. Feedback does not exist yet by construction.
                verify_by_descriptor = _loads_target(verification.get("verify_by"))
                self._emit(
                    uow,
                    handoff=updated,
                    event_type=EVENT_VERIFICATION_REQUESTED,
                    actor_agent_id=agent_id,
                    payload={
                        "handoff_id": updated.handoff_id,
                        "workspace_id": updated.workspace_id,
                        "status": updated.status,
                        "claimed_by": updated.claimed_by,
                        "verify_by": verify_by_descriptor,
                        "acceptance_criteria": _loads_target(
                            verification.get("acceptance_criteria")
                        ),
                    },
                )
                notified = self._notify_static_verifier(
                    uow,
                    handoff=updated,
                    verify_by=verify_by_descriptor,
                    actor_agent_id=agent_id,
                    now=now,
                )
        response: dict[str, Any] = {
            "handoff_id": updated.handoff_id,
            "status": updated.status,
        }
        if notified:
            response["notified"] = notified
        return response

    # ------------------------------------------------------------------ #
    # verify
    # ------------------------------------------------------------------ #
    def handoff_verify(
        self,
        *,
        project_root: Any,
        handoff_id: Any,
        agent_id: Any,
        verdict: Any,
        feedback: Any = None,
    ) -> dict[str, Any]:
        """Verifier-only decision on a VERIFYING handoff.

        ``pass`` -> COMPLETED via the same conditional-UPDATE pattern, emitting
        the CANONICAL ``handoff.completed`` enriched with ``verified_by``
        (never a separate passed event - BR5) and notifying the creator's
        inbox. ``fail`` -> CLAIMED with ``verification_feedback`` (over)written
        and the executor's lease renewed ``now + ttl`` in the SAME UPDATE
        (BR4), emitting ``handoff.verification_failed`` (carrying the
        feedback) and notifying the claimant for rework.

        Authorisation is layered and fail-closed: the caller must be able to
        READ the handoff (the ``handoff_get`` predicate, refused as
        ``PERMISSION_DENIED`` so an outsider learns nothing); the source state
        must be ``VERIFYING`` (``INVALID_TRANSITION`` otherwise - a handoff
        without criteria never enters it); the claimant (executor) is refused
        ALWAYS - anti-self-verification wins over any eligibility (BR3); and
        the caller must match the row's ``verify_by`` descriptor resolved
        DYNAMICALLY at verify time (``capability`` checks the caller's CURRENT
        capabilities, mirroring claim eligibility - D5). ``feedback`` is only
        accepted with ``fail`` (``VALIDATION_ERROR`` on ``pass`` - it exists
        to direct rework, not to be accepted-and-discarded).
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        verdict_value, feedback_value = validate_verdict(verdict, feedback)
        now = self._clock.now_iso()

        with self._cf.unit_of_work() as uow:
            permission_set_for(self._agents, uow, agent_id).require("handoffs", "work")
            handoff = self._load_in_workspace(uow, workspace_id, handoff_id)
            if agent_id not in (handoff.from_agent_id, handoff.claimed_by):
                viewer = self._routing_agent(uow, agent_id, workspace_id)
                if not can_agent_see_event(viewer, handoff, now):
                    raise OktoNexusError(
                        ErrorCode.PERMISSION_DENIED,
                        "You may not read this handoff, so you may not verify "
                        "it either.",
                        {"handoff_id": handoff_id, "agent_id": agent_id},
                    )
            if handoff.status != STATUS_VERIFYING:
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    self._verify_wrong_state_message(handoff.status),
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            # Anti-self-verification (BR3): decided BEFORE eligibility, so
            # the executor is refused even when verify_by would admit them
            # (e.g. the only current holder of the capability).
            if agent_id == handoff.claimed_by:
                raise OktoNexusError(
                    ErrorCode.PERMISSION_DENIED,
                    "The executor (claimed_by) can never verify their own "
                    "delivery - executor and verifier are separate by design.",
                    {"handoff_id": handoff_id, "agent_id": agent_id},
                )
            verification = (
                self._handoffs.read_verification(
                    uow, workspace_id=workspace_id, handoff_id=handoff_id
                )
                or {}
            )
            verify_by_descriptor = _loads_target(verification.get("verify_by")) or {}
            caller_profile = (
                self._agents.get(uow, agent_id) if self._agents is not None else None
            )
            if not is_eligible_verifier(
                str(agent_id),
                creator=str(handoff.from_agent_id),
                verify_by=verify_by_descriptor,
                caller_capabilities=getattr(caller_profile, "capabilities", None) or (),
            ):
                raise OktoNexusError(
                    ErrorCode.PERMISSION_DENIED,
                    "You are not this handoff's verifier under its verify_by "
                    "descriptor (resolved dynamically at verify time).",
                    {
                        "handoff_id": handoff_id,
                        "agent_id": agent_id,
                        "verify_by": verify_by_descriptor,
                    },
                )
            # result/rejected_reason predate the verdict and are immutable
            # here; read once for the event/response.
            outcome = self._handoffs.read_outcome(
                uow, workspace_id=workspace_id, handoff_id=handoff_id
            ) or {"result": None, "rejected_reason": None}
            if verdict_value == VERDICT_PASS:
                updated = self._handoffs.transition_verifying(
                    uow,
                    workspace_id=workspace_id,
                    handoff_id=handoff_id,
                    status=STATUS_COMPLETED,
                    updated_at=now,
                )
                if updated is None:  # pragma: no cover - unreachable: the read
                    # and the UPDATE share one BEGIN IMMEDIATE transaction, so
                    # the row cannot change in between; defence in depth.
                    self._raise_verifying_transition_error(
                        uow, workspace_id, handoff_id
                    )
                event_payload: dict[str, Any] = {
                    "handoff_id": updated.handoff_id,
                    "workspace_id": updated.workspace_id,
                    "status": updated.status,
                    "verified_by": agent_id,
                }
                if outcome.get("result") is not None:
                    event_payload["result"] = outcome["result"]
                self._emit(
                    uow,
                    handoff=updated,
                    event_type=EVENT_COMPLETED,
                    actor_agent_id=agent_id,
                    payload=event_payload,
                )
                notified = self._notify_creator_outcome(
                    uow,
                    handoff=updated,
                    actor_agent_id=agent_id,
                    kind=EVENT_COMPLETED,
                    outcome_key="result",
                    outcome_text=outcome.get("result"),
                    now=now,
                )
                self._unblock_dependents(
                    uow, completed=updated, actor_agent_id=agent_id, now=now
                )
            else:
                lease_ttl = int(self._config.handoff_lease_ttl_seconds)
                lease_expires_at = iso_plus(now, lease_ttl)
                updated = self._handoffs.transition_verifying(
                    uow,
                    workspace_id=workspace_id,
                    handoff_id=handoff_id,
                    status=STATUS_CLAIMED,
                    updated_at=now,
                    verification_feedback=feedback_value,
                    lease_expires_at=lease_expires_at,
                )
                if updated is None:  # pragma: no cover - unreachable, see the
                    # pass branch; defence in depth.
                    self._raise_verifying_transition_error(
                        uow, workspace_id, handoff_id
                    )
                event_payload = {
                    "handoff_id": updated.handoff_id,
                    "workspace_id": updated.workspace_id,
                    "status": updated.status,
                    "claimed_by": updated.claimed_by,
                    "lease_expires_at": updated.lease_expires_at,
                }
                if feedback_value is not None:
                    event_payload["feedback"] = feedback_value
                self._emit(
                    uow,
                    handoff=updated,
                    event_type=EVENT_VERIFICATION_FAILED,
                    actor_agent_id=agent_id,
                    payload=event_payload,
                )
                notified = self._notify_verification_failed(
                    uow,
                    handoff=updated,
                    actor_agent_id=agent_id,
                    feedback=feedback_value,
                    now=now,
                )
            self._touch_agent(uow, agent_id, now)
        response: dict[str, Any] = {
            "handoff_id": updated.handoff_id,
            "workspace_id": updated.workspace_id,
            "status": updated.status,
            "from_agent_id": updated.from_agent_id,
            "target": _loads_target(updated.target),
            "visibility": updated.visibility,
            "claimed_by": updated.claimed_by,
            "lease_expires_at": updated.lease_expires_at,
            "result": outcome.get("result"),
            "rejected_reason": outcome.get("rejected_reason"),
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
            "notified": bool(notified),
        }
        if agent_id == updated.claimed_by:
            response["payload"] = updated.payload
        if verdict_value == VERDICT_PASS:
            response["verified_by"] = agent_id
        elif feedback_value is not None:
            response["verification_feedback"] = feedback_value
        return response

    @staticmethod
    def _verify_wrong_state_message(status: str) -> str:
        """Directed INVALID_TRANSITION message for a verify on a wrong state."""
        if status == STATUS_CLAIMED:
            return (
                "handoff_verify requires the handoff to be VERIFYING, but it "
                "is CLAIMED - the executor submits the delivery first via "
                "handoff_complete (which parks a verifiable handoff in "
                "VERIFYING)."
            )
        if status == STATUS_OPEN:
            return (
                "handoff_verify requires the handoff to be VERIFYING, but it "
                "is OPEN - nothing has been delivered yet. A handoff without "
                "acceptance_criteria never enters VERIFYING."
            )
        return (
            "handoff_verify requires the handoff to be VERIFYING, but it is "
            f"already {status}."
        )

    def _raise_verifying_transition_error(
        self, uow: UnitOfWork, workspace_id: str, handoff_id: str
    ) -> None:
        """Map a failed conditional VERIFYING transition to the precise error.

        Mirrors :meth:`_raise_claimed_transition_error` for the verify verb:
        re-reads the row (absence maps via :meth:`_load_in_workspace`) and
        reports the state that raced the UPDATE. Always raises.
        """
        handoff = self._load_in_workspace(uow, workspace_id, handoff_id)
        raise OktoNexusError(
            ErrorCode.INVALID_TRANSITION,
            "handoff_verify failed; the handoff is no longer VERIFYING "
            f"(current status: {handoff.status}).",
            {"handoff_id": handoff_id, "status": handoff.status},
        )

    # ------------------------------------------------------------------ #
    # reject
    # ------------------------------------------------------------------ #
    def handoff_reject(
        self,
        *,
        project_root: Any,
        handoff_id: Any,
        agent_id: Any,
        reason: Any = None,
    ) -> dict[str, Any]:
        """Reject a handoff.

        The claim owner transitions ``CLAIMED -> REJECTED``; a ``direct`` target
        may transition an unclaimed ``OPEN -> REJECTED``. A caller that is
        neither owner nor direct target gets ``NOT_OWNER``; a terminal/invalid
        source state gets ``INVALID_TRANSITION``. Both branches mutate via a
        conditional UPDATE that re-asserts the state read above (the read and
        the update share one IMMEDIATE transaction, and a 0-row outcome still
        maps to a precise error rather than clobbering the row). ``reason`` is
        persisted on the row (``rejected_reason``) in the same UPDATE so the
        creator can read it later via ``handoff_get``; the creator (when
        registered and not the rejecting agent) also gets an inbox
        notification (``notified`` in the response).
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        self._check_inline_size("reason", reason)
        reason_text = self._serialize_payload(reason)
        now = self._clock.now_iso()

        with self._cf.unit_of_work() as uow:
            permission_set_for(self._agents, uow, agent_id).require("handoffs", "work")
            handoff = self._load_in_workspace(uow, workspace_id, handoff_id)
            if handoff.status in TERMINAL_STATUSES:
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    "Terminal handoff cannot be rejected.",
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            if handoff.status == STATUS_CLAIMED:
                if handoff.claimed_by != agent_id:
                    raise OktoNexusError(
                        ErrorCode.NOT_OWNER,
                        "Only the claim owner may reject a CLAIMED handoff.",
                        {
                            "handoff_id": handoff_id,
                            "agent_id": agent_id,
                            "claimed_by": handoff.claimed_by,
                        },
                    )
                updated = self._handoffs.transition_claimed(
                    uow,
                    workspace_id=workspace_id,
                    handoff_id=handoff_id,
                    claimed_by=agent_id,
                    status=STATUS_REJECTED,
                    updated_at=now,
                    rejected_reason=reason_text,
                )
            elif handoff.status == STATUS_OPEN:
                if not is_direct_target(handoff.target, agent_id):
                    raise OktoNexusError(
                        ErrorCode.NOT_OWNER,
                        "Only the direct target may reject an OPEN handoff.",
                        {"handoff_id": handoff_id, "agent_id": agent_id},
                    )
                updated = self._handoffs.reject_open(
                    uow,
                    workspace_id=workspace_id,
                    handoff_id=handoff_id,
                    updated_at=now,
                    rejected_reason=reason_text,
                )
            elif handoff.status == STATUS_VERIFYING:
                # BR6: the work was already delivered - reject can no longer
                # withdraw it. Only the verify verb leaves VERIFYING.
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    "The delivery is under verification; only handoff_verify "
                    "decides a VERIFYING handoff - a 'fail' verdict returns "
                    "it to CLAIMED for rework.",
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            else:
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    "handoff cannot be rejected from its current state.",
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            if updated is None:  # pragma: no cover - unreachable: the read and
                # the UPDATE share one BEGIN IMMEDIATE transaction, so the row
                # cannot change in between; kept as defence in depth.
                self._raise_claimed_transition_error(
                    uow, workspace_id, handoff_id, agent_id, verb="reject"
                )
            self._touch_agent(uow, agent_id, now)
            payload = {
                "handoff_id": updated.handoff_id,
                "workspace_id": updated.workspace_id,
                "status": updated.status,
            }
            if _is_nonempty_str(reason):
                payload["reason"] = reason
            self._emit(
                uow,
                handoff=updated,
                event_type=EVENT_REJECTED,
                actor_agent_id=agent_id,
                payload=payload,
            )
            notified = self._notify_creator_outcome(
                uow,
                handoff=updated,
                actor_agent_id=agent_id,
                kind=EVENT_REJECTED,
                outcome_key="reason",
                outcome_text=reason_text,
                now=now,
            )
            self._fail_dependents(uow, failed=updated, actor_agent_id=agent_id, now=now)
        response: dict[str, Any] = {
            "handoff_id": updated.handoff_id,
            "status": STATUS_REJECTED,
        }
        if notified:
            response["notified"] = notified
        return response

    # ------------------------------------------------------------------ #
    # cancel
    # ------------------------------------------------------------------ #
    def handoff_cancel(
        self,
        *,
        project_root: Any,
        handoff_id: Any,
        agent_id: Any,
        reason: Any = None,
    ) -> dict[str, Any]:
        """Creator-only ``OPEN -> CANCELLED`` - retract a handoff nobody took.

        The retraction path for a mistaken/stale handoff (e.g. a pool target
        created with zero eligible agents): only the CREATOR
        (``from_agent_id``) may cancel, and only while the handoff is OPEN. A
        CLAIMED handoff raises ``INVALID_TRANSITION`` - it is resolved by its
        claimant (``handoff_complete``/``handoff_reject``) or returns to OPEN
        when the claim lease expires (cancel it then). A terminal handoff
        (COMPLETED/REJECTED/CANCELLED) also raises ``INVALID_TRANSITION``.
        Emits ``handoff.cancelled`` in the same transaction; the optional
        ``reason`` rides the event payload.
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        self._check_inline_size("reason", reason)
        now = self._clock.now_iso()

        with self._cf.unit_of_work() as uow:
            permission_set_for(self._agents, uow, agent_id).require(
                "handoffs", "cancel"
            )
            # Opportunistic expiry first: a CLAIMED handoff whose lease already
            # elapsed is logically OPEN again, so its creator may cancel it.
            self._expire_old_leases(uow, workspace_id=workspace_id, now_iso=now)
            handoff = self._load_in_workspace(uow, workspace_id, handoff_id)
            if handoff.from_agent_id != agent_id:
                raise OktoNexusError(
                    ErrorCode.NOT_OWNER,
                    "Only the creator (from_agent_id) may cancel a handoff.",
                    {
                        "handoff_id": handoff_id,
                        "agent_id": agent_id,
                        "from_agent_id": handoff.from_agent_id,
                    },
                )
            if handoff.status == STATUS_CLAIMED:
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    "handoff_cancel applies only to OPEN handoffs; this one is "
                    "CLAIMED - it is resolved by its claimant via "
                    "handoff_complete/handoff_reject, or returns to OPEN when "
                    "the claim lease expires (cancel it then).",
                    {
                        "handoff_id": handoff_id,
                        "status": handoff.status,
                        "claimed_by": handoff.claimed_by,
                    },
                )
            if handoff.status == STATUS_VERIFYING:
                # BR6: the creator cannot retract a delivered handoff - the
                # judgement (handoff_verify) is the only exit from VERIFYING.
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    "handoff_cancel applies only to OPEN handoffs; this one "
                    "is VERIFYING - the delivery was already submitted and "
                    "only handoff_verify (pass/fail) decides it.",
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            if handoff.status != STATUS_OPEN:
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    f"handoff_cancel requires the handoff to be OPEN, but it "
                    f"is already {handoff.status}.",
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            # The load above and this write share one BEGIN IMMEDIATE
            # transaction, so the OPEN precondition cannot be raced away.
            updated = self._handoffs.update_status(
                uow,
                workspace_id=workspace_id,
                handoff_id=handoff_id,
                status=STATUS_CANCELLED,
                updated_at=now,
            )
            self._touch_agent(uow, agent_id, now)
            payload = {
                "handoff_id": updated.handoff_id,
                "workspace_id": updated.workspace_id,
                "status": updated.status,
            }
            if _is_nonempty_str(reason):
                payload["reason"] = reason
            self._emit(
                uow,
                handoff=updated,
                event_type=EVENT_CANCELLED,
                actor_agent_id=agent_id,
                payload=payload,
            )
            self._fail_dependents(uow, failed=updated, actor_agent_id=agent_id, now=now)
        return {"handoff_id": updated.handoff_id, "status": STATUS_CANCELLED}

    # ------------------------------------------------------------------ #
    # get
    # ------------------------------------------------------------------ #
    def handoff_get(
        self,
        *,
        project_root: Any,
        handoff_id: Any,
        agent_id: Any,
    ) -> dict[str, Any]:
        """Read ONE handoff by id - the creator's path to the outcome.

        Terminal handoffs leave ``handoff_list_available`` and their lifecycle
        events are observability (visibility-gated), not delivery - this read
        is how the creator (or anyone allowed) checks status/result by id.
        Runs opportunistic lease expiry first so the returned status reflects
        an already-elapsed lease. Access: the creator (``from_agent_id``) and
        the claimant (``claimed_by``) always may; any other agent is gated by
        the same visibility predicate as ``handoff_list_available``
        (``can_agent_see_event``) and gets ``NOT_OWNER`` otherwise.
        ``NOT_FOUND``/``WORKSPACE_MISMATCH`` map absence precisely.
        Verification-first handoffs (I4) additionally expose
        ``acceptance_criteria``/``verify_by`` (decoded) and
        ``verification_feedback`` - each omitted when NULL.
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        now = self._clock.now_iso()

        with self._cf.unit_of_work() as uow:
            self._expire_old_leases(uow, workspace_id=workspace_id, now_iso=now)
            handoff = self._load_in_workspace(uow, workspace_id, handoff_id)
            if agent_id not in (handoff.from_agent_id, handoff.claimed_by):
                viewer = self._routing_agent(uow, agent_id, workspace_id)
                if not can_agent_see_event(viewer, handoff, now):
                    raise OktoNexusError(
                        ErrorCode.NOT_OWNER,
                        "You may not read this handoff: only the creator, the "
                        "claimant, or an agent admitted by its visibility/"
                        "eligibility may call handoff_get.",
                        {"handoff_id": handoff_id, "agent_id": agent_id},
                    )
            outcome = self._handoffs.read_outcome(
                uow, workspace_id=workspace_id, handoff_id=handoff_id
            ) or {"result": None, "rejected_reason": None}
            verification = self._handoffs.read_verification(
                uow, workspace_id=workspace_id, handoff_id=handoff_id
            )
            dep_rows = self._handoffs.read_dependencies(
                uow, workspace_id=workspace_id, handoff_id=handoff_id
            )
            self._touch_agent(uow, agent_id, now)
        response = {
            "handoff_id": handoff.handoff_id,
            "workspace_id": handoff.workspace_id,
            "status": handoff.status,
            "from_agent_id": handoff.from_agent_id,
            "target": _loads_target(handoff.target),
            "visibility": handoff.visibility,
            "claimed_by": handoff.claimed_by,
            "lease_expires_at": handoff.lease_expires_at,
            "result": outcome["result"],
            "rejected_reason": outcome["rejected_reason"],
            "created_at": handoff.created_at,
            "updated_at": handoff.updated_at,
        }
        if agent_id == handoff.claimed_by:
            response["payload"] = handoff.payload
        # Verification contract exposure (I4/FR6): the three columns surface
        # top-level ONLY when non-NULL (the trace_id pattern) - a
        # non-verifiable handoff keeps its pre-I4 shape byte-identical.
        if verification and verification.get("acceptance_criteria"):
            response["acceptance_criteria"] = _loads_target(
                verification["acceptance_criteria"]
            )
            response["verify_by"] = _loads_target(verification["verify_by"])
        if outcome.get("verification_feedback") is not None:
            response["verification_feedback"] = outcome["verification_feedback"]
        # Dependency exposure (I5/FR7): the same non-NULL pattern - only a
        # dependent handoff carries the edge list and the LIVE aggregate
        # (derived on-read; a vanished dependency row counts pending); a
        # dependency-free handoff keeps its pre-I5 shape byte-identical.
        if dep_rows:
            response["depends_on"] = [row["depends_on_id"] for row in dep_rows]
            response["dependencies"] = summarize_dependencies(
                [row["status"] or "" for row in dep_rows]
            )
        return response

    # ------------------------------------------------------------------ #
    # Opportunistic lease expiry
    # ------------------------------------------------------------------ #
    def expire_old_leases(self, *, project_root: Any) -> dict[str, Any]:
        """Public entry point to expire stale leases for a workspace.

        Primarily an internal routine invoked before list/claim, exposed here
        for completeness/testing. Returns the list of reopened handoff ids.
        """
        workspace_id = self._resolve_workspace(project_root)
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            expired = self._expire_old_leases(
                uow, workspace_id=workspace_id, now_iso=now
            )
        return {"workspace_id": workspace_id, "expired": expired}

    def _expire_old_leases(
        self, uow: UnitOfWork, *, workspace_id: str, now_iso: str
    ) -> list[str]:
        """Reopen every CLAIMED handoff whose lease strictly expired before now.

        Strict threshold: ``lease_expires_at < now`` expires; ``== now`` does
        not. Each successful reopen emits ``handoff.expired`` in the same
        transaction. Returns the reopened handoff ids.
        """
        now_epoch = iso_to_epoch(now_iso)
        expired: list[str] = []
        for handoff in self._handoffs.list(
            uow, workspace_id=workspace_id, status=STATUS_CLAIMED
        ):
            if not handoff.lease_expires_at:
                continue
            try:
                lease_epoch = iso_to_epoch(handoff.lease_expires_at)
            except (ValueError, TypeError):
                continue
            if lease_epoch >= now_epoch:  # strict: == now does NOT expire
                continue
            reopened = self._handoffs.reopen_expired(
                uow,
                workspace_id=workspace_id,
                handoff_id=handoff.handoff_id,
                updated_at=now_iso,
            )
            if reopened is None:
                continue
            self._emit(
                uow,
                handoff=reopened,
                event_type=EVENT_EXPIRED,
                actor_agent_id=None,
                payload={
                    "handoff_id": reopened.handoff_id,
                    "workspace_id": reopened.workspace_id,
                    "status": reopened.status,
                    "previous_claimed_by": handoff.claimed_by,
                },
            )
            expired.append(reopened.handoff_id)
        return expired

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _resolve_workspace(self, project_root: Any) -> str:
        if not _is_nonempty_str(project_root):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "project_root (workspace_id) is required for handoff operations.",
                {},
            )
        # resolve_workspace_id raises WORKSPACE_UNRESOLVED for irresolvable paths.
        return resolve_workspace_id(project_root)

    def _touch_agent(self, uow: UnitOfWork, agent_id: Any, now: str) -> None:
        """Best-effort stamp of the actor's ``last_seen_at`` within ``uow``."""
        if self._agents is not None and _is_nonempty_str(agent_id):
            self._agents.touch(uow, agent_id=agent_id, at=now)

    def _eligible_agent_ids(
        self,
        uow: UnitOfWork,
        workspace_id: str,
        target: Mapping[str, Any],
        now: str,
    ) -> list[str]:
        """Agents from the GLOBAL registry eligible for ``target`` right now.

        The same lazily-re-evaluated predicate claiming uses
        (:func:`is_agent_eligible` with ``created_at == now``), resolved at
        creation time ONLY to inform the creator (``eligible_count`` /
        zero-match warning) - it is never an ACL: a later registrant can still
        claim. The creator is not excluded (it may claim its own handoff).
        """
        assert self._agents is not None  # caller guards
        eligible: list[str] = []
        for agent in self._agents.list(uow):
            view = RoutingAgent(
                agent_id=agent.agent_id,
                workspace_id=workspace_id,
                role=agent.role,
                capabilities=agent.capabilities,
                tags=getattr(agent, "tags", None),
            )
            if is_agent_eligible(view, target, now, now):
                eligible.append(agent.agent_id)
        return eligible

    def _notify_inbox(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        recipient_agent_id: str,
        from_agent_id: str,
        subject: str,
        body: Mapping[str, Any],
        now: str,
        trace_id: str | None = None,
    ) -> bool:
        """Land ONE synthetic notification in ``recipient_agent_id``'s inbox.

        Reuses the messages + message_deliveries lanes (no new transport, no
        new event type) inside the CALLER's unit of work. Skipped (``False``)
        when the message/delivery repos are unwired, the recipient is not a
        registered agent (``message_deliveries.recipient_agent_id`` is an FK
        to ``agents``), or the recipient's own ``comm_scope.inbound`` excludes
        the notifier (F2 - recipient policy, silently honoured); the handoff
        lifecycle never depends on it.
        """
        if self._messages is None or self._deliveries is None:
            return False
        if self._agents is None or not _is_nonempty_str(recipient_agent_id):
            return False
        recipient = self._agents.get(uow, recipient_agent_id)
        if recipient is None:
            return False
        if str(recipient_agent_id) != str(from_agent_id):
            # Only the recipient's INBOUND leg gates a notification (F2): a
            # lifecycle notice must never be lost to the NOTIFIER's outbound
            # selector - the communication it reports already happened.
            inbound = scope_selector(getattr(recipient, "comm_scope", None), "inbound")
            if inbound is not None:
                sender = (
                    self._agents.get(uow, str(from_agent_id))
                    if _is_nonempty_str(from_agent_id)
                    else None
                )
                if not selector_matches(inbound, getattr(sender, "tags", None)):
                    return False
        message = self._messages.create(
            uow,
            message_id=new_id("msg"),
            workspace_id=workspace_id,
            from_agent_id=from_agent_id,
            target=json.dumps(
                {"strategy": "direct", "agent_id": recipient_agent_id},
                ensure_ascii=False,
            ),
            subject=subject,
            body=json.dumps(dict(body), ensure_ascii=False),
            # The synthetic notification carries the handoff's trace so the
            # recipient sees it on the inbox item and can propagate it (I1).
            trace_id=trace_id,
            created_at=now,
        )
        self._deliveries.create(
            uow,
            delivery_id=new_delivery_id(),
            message_id=message.message_id,
            recipient_agent_id=recipient_agent_id,
            status=DELIVERY_UNREAD,
            created_at=now,
        )
        return True

    def _notify_creator_outcome(
        self,
        uow: UnitOfWork,
        *,
        handoff: Any,
        actor_agent_id: str,
        kind: str,
        outcome_key: str,
        outcome_text: str | None,
        now: str,
    ) -> list[str]:
        """Deliver a terminal outcome to the CREATOR's inbox (cross-workspace).

        The ``handoff.completed``/``handoff.rejected`` event may be invisible
        to the creator (visibility ``eligible``/``private`` with a target the
        creator does not match), and a terminal handoff leaves every listing
        surface - so the outcome is pushed to the creator's GLOBAL inbox.
        Skipped when the creator IS the actor (no self-notification) or is
        not a registered agent. Returns the notified agent ids (0 or 1).
        """
        creator = handoff.from_agent_id
        if not _is_nonempty_str(creator) or creator == actor_agent_id:
            return []
        verb = kind.rsplit(".", 1)[-1]  # "completed" / "rejected"
        body: dict[str, Any] = {
            "kind": kind,
            "handoff_id": handoff.handoff_id,
            "status": handoff.status,
            "by_agent_id": actor_agent_id,
            "next_step": "handoff_get with this handoff_id for the full outcome",
        }
        if outcome_text is not None:
            body[outcome_key] = outcome_text
        if self._notify_inbox(
            uow,
            workspace_id=handoff.workspace_id,
            recipient_agent_id=creator,
            from_agent_id=actor_agent_id,
            subject=f"handoff {handoff.handoff_id} {verb} by {actor_agent_id}",
            body=body,
            now=now,
            trace_id=getattr(handoff, "trace_id", None),
        ):
            return [creator]
        return []

    def _notify_static_verifier(
        self,
        uow: UnitOfWork,
        *,
        handoff: Any,
        verify_by: Any,
        actor_agent_id: str,
        now: str,
    ) -> list[str]:
        """Wake the STATICALLY resolvable verifier after a delivery.

        ``creator``/``agent`` descriptors name exactly one agent; a
        ``capability`` verifier is dynamic (any current holder may verify), so
        there is no single inbox to notify - observers act on the
        ``handoff.verification_requested`` event instead. Skipped when the
        verifier IS the executor (they cannot verify anyway) or the inbox
        lanes are unwired. Returns the notified agent ids (0 or 1).
        """
        verify_by_map = verify_by if isinstance(verify_by, Mapping) else {}
        verifier = static_verifier_for(verify_by_map, str(handoff.from_agent_id))
        if not _is_nonempty_str(verifier) or verifier == actor_agent_id:
            return []
        body = {
            "kind": EVENT_VERIFICATION_REQUESTED,
            "handoff_id": handoff.handoff_id,
            "status": handoff.status,
            "claimed_by": handoff.claimed_by,
            "next_step": "handoff_get to inspect the delivery, then "
            "handoff_verify with verdict 'pass' or 'fail'",
        }
        if self._notify_inbox(
            uow,
            workspace_id=handoff.workspace_id,
            recipient_agent_id=verifier,
            from_agent_id=actor_agent_id,
            subject=f"handoff {handoff.handoff_id} awaits your verification",
            body=body,
            now=now,
            trace_id=getattr(handoff, "trace_id", None),
        ):
            return [verifier]
        return []

    def _notify_verification_failed(
        self,
        uow: UnitOfWork,
        *,
        handoff: Any,
        actor_agent_id: str,
        feedback: str | None,
        now: str,
    ) -> list[str]:
        """Wake the claimant for rework after a ``fail`` verdict (best-effort).

        The handoff is CLAIMED again with a renewed lease, so the executor
        can re-complete; the notification carries the (latest) feedback when
        given. Returns the notified agent ids (0 or 1).
        """
        claimant = handoff.claimed_by
        if not _is_nonempty_str(claimant) or claimant == actor_agent_id:
            return []
        body: dict[str, Any] = {
            "kind": EVENT_VERIFICATION_FAILED,
            "handoff_id": handoff.handoff_id,
            "status": handoff.status,
            "by_agent_id": actor_agent_id,
            "lease_expires_at": handoff.lease_expires_at,
            "next_step": "address the feedback and call handoff_complete again",
        }
        if feedback is not None:
            body["feedback"] = feedback
        if self._notify_inbox(
            uow,
            workspace_id=handoff.workspace_id,
            recipient_agent_id=claimant,
            from_agent_id=actor_agent_id,
            subject=f"handoff {handoff.handoff_id} verification failed",
            body=body,
            now=now,
            trace_id=getattr(handoff, "trace_id", None),
        ):
            return [claimant]
        return []

    @staticmethod
    def _require_id(field: str, value: Any) -> None:
        if not _is_nonempty_str(value):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} is required.",
                {field: value},
            )

    def _load_in_workspace(
        self, uow: UnitOfWork, workspace_id: str, handoff_id: str
    ) -> Any:
        """Load a handoff scoped to the workspace, mapping absence precisely.

        ``NOT_FOUND`` when the id exists nowhere; ``WORKSPACE_MISMATCH`` when it
        exists only in another workspace (no cross-workspace read).
        """
        handoff = self._handoffs.get(
            uow, workspace_id=workspace_id, handoff_id=handoff_id
        )
        if handoff is not None:
            return handoff
        if self._handoffs.exists_any_workspace(uow, handoff_id=handoff_id):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_MISMATCH,
                "handoff belongs to a different workspace.",
                {"handoff_id": handoff_id, "workspace_id": workspace_id},
            )
        raise OktoNexusError(
            ErrorCode.NOT_FOUND,
            "handoff_id does not exist.",
            {"handoff_id": handoff_id},
        )

    def _raise_claimed_transition_error(
        self,
        uow: UnitOfWork,
        workspace_id: str,
        handoff_id: str,
        agent_id: str,
        *,
        verb: str,
    ) -> None:
        """Map a failed conditional CLAIMED transition to the precise error.

        Called when the conditional UPDATE affected 0 rows. Re-reads the row in
        the same transaction: absence maps via :meth:`_load_in_workspace`
        (``NOT_FOUND``/``WORKSPACE_MISMATCH``); an OPEN row means the claim
        lease expired and reopened it; a terminal row was already finished; a
        CLAIMED row held by someone else is ``NOT_OWNER``. Always raises.
        """
        handoff = self._load_in_workspace(uow, workspace_id, handoff_id)
        if handoff.status == STATUS_OPEN:
            raise OktoNexusError(
                ErrorCode.INVALID_TRANSITION,
                f"handoff_{verb} requires the handoff to be CLAIMED, but it is "
                "OPEN - the claim lease may have expired and reopened it. Call "
                "handoff_claim again before retrying.",
                {"handoff_id": handoff_id, "status": handoff.status},
            )
        if handoff.status in TERMINAL_STATUSES:
            raise OktoNexusError(
                ErrorCode.INVALID_TRANSITION,
                f"handoff_{verb} requires the handoff to be CLAIMED, but it is "
                f"already {handoff.status}.",
                {"handoff_id": handoff_id, "status": handoff.status},
            )
        if handoff.claimed_by != agent_id:
            raise OktoNexusError(
                ErrorCode.NOT_OWNER,
                f"Only the claim owner may {verb} this handoff.",
                {
                    "handoff_id": handoff_id,
                    "agent_id": agent_id,
                    "claimed_by": handoff.claimed_by,
                },
            )
        raise OktoNexusError(  # pragma: no cover - defensive: the predicate
            # held on re-read, so the UPDATE could not have affected 0 rows.
            ErrorCode.INVALID_TRANSITION,
            f"handoff_{verb} failed; the current state does not allow it.",
            {"handoff_id": handoff_id, "status": handoff.status},
        )

    def _routing_agent(
        self, uow: UnitOfWork, agent_id: str, workspace_id: str
    ) -> RoutingAgent:
        """Build the routing view of the caller from the agent profile (if any)."""
        role: str | None = None
        capabilities: Any = None
        tags: Any = None
        if self._agents is not None:
            profile = self._agents.get(uow, agent_id)
            if profile is not None:
                role = profile.role
                capabilities = profile.capabilities
                tags = getattr(profile, "tags", None)
        return RoutingAgent(
            agent_id=agent_id,
            workspace_id=workspace_id,
            role=role,
            capabilities=capabilities,
            tags=tags,
        )

    def _claimant_in_creator_audience(
        self, uow: UnitOfWork, handoff: Any, agent_id: Any
    ) -> bool:
        """Whether creator and claimant can REACH each other (F1 + F2).

        The dynamic leg of claim eligibility: a handoff is a communication
        from its creator, so a claimant must sit inside the creator's
        ``comm_scope.outbound`` audience (F1) AND the creator must sit inside
        the claimant's own ``comm_scope.inbound`` (F2) - the shared
        :func:`~okto_nexus.domain.tag_selector.reachable` double intersection,
        including its self carve-out (a creator may always claim its own
        handoff). Evaluated against CURRENT tags at claim/list time - never
        creation-time state. Unknown creator or an unwired agent repo means
        that side is unrestricted.
        """
        if self._agents is None:
            return True
        creator_id = getattr(handoff, "from_agent_id", None)
        creator = (
            self._agents.get(uow, str(creator_id))
            if _is_nonempty_str(creator_id)
            else None
        )
        if creator is None:
            creator = {
                "agent_id": str(creator_id) if _is_nonempty_str(creator_id) else None
            }
        claimant = self._agents.get(uow, str(agent_id))
        if claimant is None:
            claimant = {"agent_id": str(agent_id)}
        return reachable(creator, claimant)

    def _ensure_target_selectors_registered(
        self, uow: UnitOfWork, normalized_target: Any
    ) -> None:
        """Catalog EXISTENCE gate over every 'tag' selector in the target.

        FORM was already validated; unregistered pairs raise
        ``VALIDATION_ERROR`` fail-closed before anything persists. A no-op
        when no catalog repo is wired.
        """
        if self._tag_catalog is None:
            return
        service = TagCatalogService(catalog=self._tag_catalog)
        for selector in iter_target_selectors(normalized_target):
            service.ensure_registered(uow, selector, field="target.selector")

    def _ensure_target_capabilities_registered(
        self, uow: UnitOfWork, normalized_target: Any
    ) -> None:
        """Catalog EXISTENCE gate over every capability name in the target
        (migration 014), including sub-rules nested in ``mixed``/``fallback``.

        FORM was already validated; unregistered names raise
        ``VALIDATION_ERROR`` fail-closed before anything persists. A no-op
        when no catalog repo is wired.
        """
        if self._capability_catalog is None:
            return
        names = list(iter_target_capabilities(normalized_target))
        if names:
            CapabilityCatalogService(
                catalog=self._capability_catalog
            ).ensure_registered(uow, names, field="target.capability")

    def _ensure_verifier_resolvable(
        self, uow: UnitOfWork, verify_by_descriptor: Mapping[str, Any]
    ) -> None:
        """Existence gate over a validated ``verify_by`` descriptor (BR8).

        FORM was already validated (pure phase); this is the I/O leg: an
        ``agent`` kind must name a REGISTERED agent and a ``capability`` kind
        must reference the central catalog - both fail-closed with
        ``VALIDATION_ERROR`` before anything persists (mirroring the target's
        own catalog gates). ``creator`` needs no lookup (the creator is the
        caller). A no-op when the corresponding repo is unwired.
        """
        kind = verify_by_descriptor.get("kind")
        if kind == "agent" and self._agents is not None:
            named = str(verify_by_descriptor.get("agent_id"))
            if self._agents.get(uow, named) is None:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"verify_by.agent_id '{named}' is not a registered agent; "
                    "check agent_list or register it first.",
                    {"verify_by": dict(verify_by_descriptor)},
                )
        elif kind == "capability" and self._capability_catalog is not None:
            CapabilityCatalogService(
                catalog=self._capability_catalog
            ).ensure_registered(
                uow,
                [str(verify_by_descriptor.get("capability"))],
                field="verify_by.capability",
            )

    def _ensure_dependencies_satisfiable(
        self, uow: UnitOfWork, *, workspace_id: str, depends_on: Sequence[str]
    ) -> list[str]:
        """Existence + state gate over a validated ``depends_on`` list (I5).

        FORM was already validated (pure phase); this is the I/O leg,
        fail-closed before anything persists. Every id must name a handoff in
        THIS workspace - ``DEPENDENCY_NOT_FOUND`` lists EVERY missing id at
        once, and a cross-workspace id is INDISTINGUISHABLE from a
        nonexistent one (BR8: no probing another workspace's ids). None may
        already be terminally failed: a REJECTED/CANCELLED dependency can
        never become COMPLETED, so the dependent would be born permanently
        blocked - that create is statically unsatisfiable
        (``VALIDATION_ERROR``, mirroring the degenerate verify_by gate). An
        already-COMPLETED dependency is fine: it is born satisfied. Returns
        the dependencies' CURRENT statuses, index-aligned with ``depends_on``
        (the aggregate snapshot the create response echoes).
        """
        statuses: list[str] = []
        missing: list[str] = []
        failed: list[str] = []
        for dep_id in depends_on:
            row = self._handoffs.get(uow, workspace_id=workspace_id, handoff_id=dep_id)
            if row is None:
                missing.append(dep_id)
                continue
            statuses.append(row.status)
            if row.status in DEPENDENCY_FAILED_STATUSES:
                failed.append(dep_id)
        if missing:
            raise OktoNexusError(
                ErrorCode.DEPENDENCY_NOT_FOUND,
                "depends_on names handoffs that do not exist in this "
                "workspace. Dependencies must already exist when the "
                "dependent is created (acyclicity by construction).",
                {"missing": missing},
            )
        if failed:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "This dependency set is statically unsatisfiable: a "
                "REJECTED/CANCELLED dependency can never become COMPLETED, "
                "so the new handoff would stay blocked forever. Drop the "
                "failed ids or re-create that work first.",
                {"failed": failed},
            )
        return statuses

    def _unblock_dependents(
        self, uow: UnitOfWork, *, completed: Any, actor_agent_id: str, now: str
    ) -> None:
        """Synchronous exactly-once unblock scan after a COMPLETED (I5/BR6).

        Called by BOTH producers of COMPLETED - the non-verifiable complete
        and the 'pass' verdict - inside the SAME UoW as the transition, so
        exactly-once holds by construction: only the transaction completing
        the LAST edge observes every dependency satisfied (SQLite's single
        writer serialises concurrent completes), and earlier completions see
        a pending edge and skip. For each still-OPEN dependent whose edges
        are now all COMPLETED it emits ``handoff.unblocked`` with the
        DEPENDENT's row - trace/visibility/target inherit from the dependent,
        never from the completed dependency - and the completer as actor. A
        DIRECTED dependent additionally wakes its named agent's inbox; pool
        dependents rely on the event (the handoff.created split).
        """
        dependents = self._handoffs.dependents_of(
            uow,
            workspace_id=completed.workspace_id,
            depends_on_id=completed.handoff_id,
        )
        for dependent_id in dependents:
            dependent = self._handoffs.get(
                uow, workspace_id=completed.workspace_id, handoff_id=dependent_id
            )
            if dependent is None or dependent.status != STATUS_OPEN:
                continue
            rows = self._handoffs.read_dependencies(
                uow, workspace_id=completed.workspace_id, handoff_id=dependent_id
            )
            if not dependencies_satisfied([row["status"] or "" for row in rows]):
                continue
            self._emit(
                uow,
                handoff=dependent,
                event_type=EVENT_UNBLOCKED,
                actor_agent_id=actor_agent_id,
                payload={
                    "handoff_id": dependent.handoff_id,
                    "workspace_id": dependent.workspace_id,
                    "status": dependent.status,
                    "unblocked_by": completed.handoff_id,
                },
            )
            target = _loads_target(dependent.target)
            strategy = target.get("strategy") if isinstance(target, Mapping) else None
            if strategy in _DIRECTED_STRATEGIES:
                self._notify_inbox(
                    uow,
                    workspace_id=dependent.workspace_id,
                    recipient_agent_id=str(target.get("agent_id")),
                    from_agent_id=actor_agent_id,
                    subject=f"handoff {dependent.handoff_id} unblocked",
                    body={
                        "kind": EVENT_UNBLOCKED,
                        "handoff_id": dependent.handoff_id,
                        "unblocked_by": completed.handoff_id,
                        "next_step": "handoff_claim with this handoff_id",
                    },
                    now=now,
                    trace_id=getattr(dependent, "trace_id", None),
                )

    def _fail_dependents(
        self, uow: UnitOfWork, *, failed: Any, actor_agent_id: str, now: str
    ) -> None:
        """Signal dependents that an edge terminally failed (I5/BR5).

        Called by the application producers of REJECTED/CANCELLED in the SAME
        UoW as the transition. NO cascade: the dependent's status never
        changes here - each non-terminal dependent gets
        ``handoff.dependency_failed`` (the DEPENDENT's row, so its own trace/
        visibility govern the event) plus one inbox notice to its CREATOR,
        who decides: cancel the dependent, or re-create the failed work AND a
        new dependent (edges are immutable, so a re-created dependency never
        reattaches). The raw ADMIN status override on the REST surface does
        not pass through here - documented caveat S2.
        """
        dependents = self._handoffs.dependents_of(
            uow, workspace_id=failed.workspace_id, depends_on_id=failed.handoff_id
        )
        for dependent_id in dependents:
            dependent = self._handoffs.get(
                uow, workspace_id=failed.workspace_id, handoff_id=dependent_id
            )
            if dependent is None or dependent.status in TERMINAL_STATUSES:
                continue
            self._emit(
                uow,
                handoff=dependent,
                event_type=EVENT_DEPENDENCY_FAILED,
                actor_agent_id=actor_agent_id,
                payload={
                    "handoff_id": dependent.handoff_id,
                    "workspace_id": dependent.workspace_id,
                    "status": dependent.status,
                    "failed_dependency": failed.handoff_id,
                    "dependency_status": failed.status,
                },
            )
            creator = getattr(dependent, "from_agent_id", None)
            if _is_nonempty_str(creator):
                self._notify_inbox(
                    uow,
                    workspace_id=dependent.workspace_id,
                    recipient_agent_id=str(creator),
                    from_agent_id=actor_agent_id,
                    subject=(f"handoff {dependent.handoff_id} has a failed dependency"),
                    body={
                        "kind": EVENT_DEPENDENCY_FAILED,
                        "handoff_id": dependent.handoff_id,
                        "failed_dependency": failed.handoff_id,
                        "dependency_status": failed.status,
                        "next_step": "handoff_cancel the blocked dependent, "
                        "or re-create the failed work and a new dependent",
                    },
                    now=now,
                    trace_id=getattr(dependent, "trace_id", None),
                )

    def _parse_cursor(self, cursor: Any) -> int:
        # Shared pagination grammar (domain.base): one cursor parser bus-wide.
        return normalize_cursor(cursor)

    def _parse_limit(self, limit: Any) -> int:
        # Shared pagination grammar (domain.base): one limit parser bus-wide.
        return clamp_limit(limit, default=DEFAULT_PAGE_LIMIT, maximum=MAX_PAGE_LIMIT)

    def _clamp_timeout(self, timeout_seconds: Any) -> float:
        if timeout_seconds is None:
            return 0.0
        if isinstance(timeout_seconds, bool):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "timeout_seconds must be a non-negative number.",
                {"timeout_seconds": timeout_seconds},
            )
        try:
            value = float(timeout_seconds)
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "timeout_seconds must be a non-negative number.",
                {"timeout_seconds": timeout_seconds},
            ) from None
        if value < 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "timeout_seconds must be a non-negative number.",
                {"timeout_seconds": timeout_seconds},
            )
        # Clamp to the configured maximum wait (seconds, not ms).
        return min(value, float(self._config.max_wait_timeout_seconds))

    def _check_inline_size(self, field: str, value: Any) -> None:
        """Enforce the inclusive 64KB UTF-8 inline content limit (shared helper)."""
        check_inline_size(field, value, self._config.max_inline_bytes)

    @staticmethod
    def _serialize_payload(payload: Any) -> str | None:
        """Serialise the inline payload to TEXT for storage (``None`` stays ``None``).

        A string is stored verbatim so it round-trips byte-for-byte back to the
        worker via ``handoff_list_available`` / ``handoff_claim``; any other
        JSON-serialisable value is encoded. The payload is treated as OPAQUE on
        read-back (returned as the stored TEXT, never re-parsed) - unlike
        ``target``, which is always a routing object and is echoed decoded.
        """
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False)

    def _emit(
        self,
        uow: UnitOfWork,
        *,
        handoff: Any,
        event_type: str,
        actor_agent_id: str | None,
        payload: Mapping[str, Any] | None,
    ) -> None:
        """Emit a handoff lifecycle event inside ``uow`` (skipped if unwired).

        ``event_id`` is owned/assigned by the Event Log slice (imported via the
        ``EventEmitter`` port), not redefined here.
        """
        if self._emitter is None:
            return
        event_payload = dict(payload) if payload else None
        trace_id = getattr(handoff, "trace_id", None)
        if trace_id is not None:
            # BR5: every handoff.* lifecycle event carries the row's trace in
            # its payload when set - created/claimed/completed/rejected/
            # cancelled/expired all flow through this single seam (D1).
            event_payload = dict(event_payload or {})
            event_payload["trace_id"] = trace_id
        self._emitter.emit(
            uow,
            workspace_id=handoff.workspace_id,
            stream=HANDOFF_STREAM,
            type=event_type,
            payload=event_payload,
            actor_agent_id=actor_agent_id,
            visibility=handoff.visibility,
            target=handoff.target,
        )


def _loads_target(text: Any) -> Any:
    """Deserialise a stored target descriptor back into an object for responses."""
    if text is None:
        return None
    if isinstance(text, Mapping):
        return text
    if isinstance(text, str):
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return text
    return text


def _fallback_boundaries(target: Any, created_epoch: float) -> Iterator[float]:
    """Yield every instant ``target``'s eligible set can WIDEN with no write.

    Walks an already-stored (write-path-validated) target descriptor: each
    ``direct_with_fallback`` contributes ``created_epoch +
    fallback_after_seconds`` (the inclusive instant the fallback pool opens),
    recursing into ``mixed`` sub-rules and nested ``fallback`` sub-targets.
    Mirrors the time dependence of :func:`is_agent_eligible` - any strategy
    this yields nothing for is time-invariant. Raises ``VALIDATION_ERROR``
    only for an out-of-grammar strategy token (the caller skips that row).
    """
    if not isinstance(target, Mapping):
        return
    strategy = normalize_strategy(target.get("strategy", target.get("kind")))
    if strategy == "direct_with_fallback":
        after = target.get("fallback_after_seconds")
        if isinstance(after, (int, float)) and not isinstance(after, bool):
            yield created_epoch + float(after)
        fallback = target.get("fallback")
        if isinstance(fallback, Mapping):
            yield from _fallback_boundaries(fallback, created_epoch)
    elif strategy == "mixed":
        rules = target.get("rules", target.get("targets"))
        if isinstance(rules, Sequence) and not isinstance(rules, (str, bytes)):
            for rule in rules:
                yield from _fallback_boundaries(rule, created_epoch)
