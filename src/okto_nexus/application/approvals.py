"""HITL approvals application service (spec 2948b2a2, feature_hitl).

The interception half of the human-in-the-loop slice: when a write path's
governance verdict is :class:`~okto_nexus.domain.governance.ApprovalRequired`
(a ``require_approval`` policy matched an action that would otherwise pass -
BR8), the write path calls :meth:`ApprovalService.intercept` INSIDE its own
unit of work. The full re-executable action is serialised into ``approvals``
and ``approval.requested`` is emitted in that SAME UoW (BR1 - the client never
receives an ``approval_id`` for a row that does not exist), then the write
path early-returns the ``pending_approval`` envelope instead of executing.

The decision half (approve re-executes with a one-shot bypass, reject notifies
the requester) and the operator-only queue reads live here too; both work with
``feature_hitl`` OFF - the flag gates ONLY the interception (BR6), read live
inside :meth:`okto_nexus.application.governance.GovernanceService.enforce`.

Application layer: ports + domain + errors only; never imports ``sqlite3`` nor
``mcp`` (enforced by the import-boundary test). Executors for approved
re-execution are REGISTERED by the wiring layer (tools / REST), so this module
never imports the messages/handoff services (no cycle).
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Optional

from ..domain.approvals import (
    DECISION_APPROVE,
    DEFAULT_REJECT_JUSTIFICATION,
    OPERATOR_AGENT_ID,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Approval,
    payload_meta,
    validate_decision,
)
from ..domain.base import new_id
from ..domain.governance import (
    ACTION_MESSAGE_CREATE,
    EVENT_APPROVAL_DENIED,
    EVENT_APPROVAL_GRANTED,
    EVENT_APPROVAL_REQUESTED,
)
from ..errors import ErrorCode, OktoNexusError
from .ports import ApprovalRepo, Clock, ConnectionFactory, EventEmitter, UnitOfWork

#: Stream + visibility of every approval.* event: workspace-wide and public,
#: like governance.denied - payloads carry metadata only, never content (BR5).
APPROVAL_STREAM = "workspace"
APPROVAL_VISIBILITY = "public"

#: The envelope's status marker (FR2). Additive: the ok:true wrapper is the
#: transport's, this is the data-level discriminator agents branch on.
PENDING_STATUS = "pending_approval"

#: An executor re-invokes the REAL use case from the persisted kwargs with the
#: one-shot interception bypass; registered by the wiring layer per action.
Executor = Callable[[dict[str, Any]], dict[str, Any]]


def seed_operator_agent(uow: UnitOfWork, *, agents: Any) -> bool:
    """Guarantee the first-class ``operator`` identity exists (FR6/BR4).

    Runs at bootstrap, BEFORE any tool registers (the seed_capability_catalog
    pattern) and unconditionally - no flag. Create-if-missing only: an existing
    operator row (role, permissions, key hash) is NEVER touched, so re-runs and
    upgrades are safe. Returns whether the row was created.
    """
    if agents.get(uow, OPERATOR_AGENT_ID) is not None:
        return False
    agents.upsert(uow, agent_id=OPERATOR_AGENT_ID, role="operator")
    return True


def approval_to_summary(approval: Approval) -> dict[str, Any]:
    """Queue item (FR8): routing metadata only, never subject/body (BR5)."""
    try:
        payload = json.loads(approval.request_payload)
    except (TypeError, ValueError):  # pragma: no cover - we always store JSON
        payload = {}
    kwargs = payload.get("kwargs") or {}
    item: dict[str, Any] = {
        "approval_id": approval.approval_id,
        "action": approval.action,
        "agent_id": approval.agent_id,
        "policy_id": approval.policy_id,
        "status": approval.status,
        "created_at": approval.created_at,
        "decided_at": approval.decided_at,
        "decided_by": approval.decided_by,
        "payload_meta": payload_meta(approval.action, kwargs),
    }
    if approval.trace_id is not None:
        item["trace_id"] = approval.trace_id
    if approval.justification is not None:
        item["justification"] = approval.justification
    return item


def approval_to_detail(approval: Approval) -> dict[str, Any]:
    """Operator-only detail (FR8): the ONE surface with the full payload."""
    item = approval_to_summary(approval)
    item["workspace_id"] = approval.workspace_id
    try:
        item["request_payload"] = json.loads(approval.request_payload)
    except (TypeError, ValueError):  # pragma: no cover - we always store JSON
        item["request_payload"] = None
    if approval.executed_result is not None:
        try:
            item["executed_result"] = json.loads(approval.executed_result)
        except (TypeError, ValueError):  # pragma: no cover
            item["executed_result"] = None
    return item


class ApprovalService:
    """Interception, operator queue and decisions for HITL approvals."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        approvals: ApprovalRepo,
        clock: Clock,
        config: Any = None,
        event_emitter: Optional[EventEmitter] = None,
    ) -> None:
        self._cf = connection_factory
        self._approvals = approvals
        self._clock = clock
        self._config = config
        self._emitter = event_emitter
        self._executors: dict[str, Executor] = {}

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #
    def register_executor(self, action: str, executor: Executor) -> None:
        """Register the re-execution callable for one action (wiring layer).

        The executor receives the persisted use-case kwargs and MUST run the
        real use case with the one-shot interception bypass and every other
        gate active (BR2) - the wiring closes over the concrete service so
        this module never imports it.
        """
        self._executors[str(action)] = executor

    # ------------------------------------------------------------------ #
    # Interception (called INSIDE the write path's UoW - BR1)
    # ------------------------------------------------------------------ #
    def intercept(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        agent_id: Any,
        action: str,
        policy_id: str,
        kwargs: Mapping[str, Any],
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist the intercepted action + emit ``approval.requested``.

        Runs inside the WRITE PATH's unit of work: the approvals row, the
        event and the returned envelope commit (or roll back) together (BR1).
        ``kwargs`` must be the COMPLETE re-executable use-case arguments with
        ``project_root`` already realpath-resolved; session credentials are
        deliberately NOT persisted - the submitter's authenticity was verified
        at interception time and secrets never land in the table.
        """
        approval_id = new_id("apr")
        now = self._clock.now_iso()
        caller = str(agent_id) if agent_id is not None else ""
        request_payload = json.dumps(
            {"kind": action, "kwargs": dict(kwargs)}, ensure_ascii=False
        )
        self._approvals.add(
            uow,
            approval_id=approval_id,
            workspace_id=workspace_id,
            agent_id=caller,
            action=action,
            policy_id=policy_id,
            request_payload=request_payload,
            trace_id=trace_id,
            created_at=now,
        )
        if self._emitter is not None:
            event_payload: dict[str, Any] = {
                "approval_id": approval_id,
                "action": action,
                "agent_id": caller,
                "policy_id": policy_id,
            }
            if trace_id is not None:
                event_payload["trace_id"] = trace_id
            self._emitter.emit(
                uow,
                workspace_id=workspace_id,
                stream=APPROVAL_STREAM,
                type=EVENT_APPROVAL_REQUESTED,
                payload=event_payload,
                actor_agent_id=caller or None,
                visibility=APPROVAL_VISIBILITY,
                target=None,
            )
        envelope: dict[str, Any] = {
            "status": PENDING_STATUS,
            "approval_id": approval_id,
            "action": action,
            "policy_id": policy_id,
            "watch": {
                "stream": APPROVAL_STREAM,
                "types": [EVENT_APPROVAL_GRANTED, EVENT_APPROVAL_DENIED],
                "approval_id": approval_id,
            },
        }
        if trace_id is not None:
            envelope["trace_id"] = trace_id
        return envelope

    # ------------------------------------------------------------------ #
    # Decision (FR4/FR5; works with the flag OFF - BR6)
    # ------------------------------------------------------------------ #
    def decide(
        self,
        *,
        approval_id: str,
        decision: Any,
        decided_by: str,
        justification: Any = None,
    ) -> dict[str, Any]:
        """Decide one pending approval: approve re-executes, reject notifies.

        APPROVE runs in THREE units of work (D-design; the crash window
        between them is a VISIBLE anomaly - ``approved`` with a null
        ``executed_result`` - never a lost or duplicated action):

        1. the decision flip - a CONDITIONAL pending-only UPDATE, so the
           second of two racing decisions gets ``CONFLICT``, never an
           overwrite (AC6);
        2. re-execution of the persisted kwargs through the executor the
           wiring registered for the action, with the one-shot interception
           bypass and EVERY other gate active (BR2) - a gate failure reverts
           ``approved`` back to ``pending`` and propagates the gate's REAL
           error (BR3: the operator sees exactly what the agent would);
        3. ``executed_result`` + ``approval.granted`` (metadata only - BR5).

        REJECT is one unit of work (flip + ``approval.denied`` atomically),
        then a BEST-EFFORT direct message from the operator to the requester
        carrying the justification (fallback: the domain's default) - the
        notification failing never unwinds the rejection; the response's
        ``notified`` flag reports it honestly.
        """
        normalized = validate_decision(decision)
        just_raw = "" if justification is None else str(justification).strip()
        just = just_raw or None
        aid = str(approval_id)
        approving = normalized == DECISION_APPROVE
        target_status = STATUS_APPROVED if approving else STATUS_REJECTED
        decider = str(decided_by)
        now = self._clock.now_iso()

        # UoW 1: the conditional flip (+ the denial event, atomically).
        with self._cf.unit_of_work() as uow:
            row = self._approvals.get(uow, aid)
            if row is None:
                raise self._not_found(aid)
            if approving and row.action not in self._executors:
                # Fail BEFORE the flip: nothing written, the row stays
                # pending and decidable once the wiring is complete.
                raise OktoNexusError(
                    ErrorCode.INTERNAL_ERROR,
                    f"No executor registered for action {row.action!r}; "
                    "the approval stays pending.",
                    {"approval_id": aid, "action": row.action},
                )
            flipped = self._approvals.mark_decided(
                uow,
                approval_id=aid,
                status=target_status,
                decided_by=decider,
                justification=just,
                decided_at=now,
            )
            if not flipped:
                raise OktoNexusError(
                    ErrorCode.CONFLICT,
                    f"Approval {aid!r} was already decided "
                    f"({row.status} by {row.decided_by}).",
                    {
                        "approval_id": aid,
                        "status": row.status,
                        "decided_by": row.decided_by,
                        "decided_at": row.decided_at,
                    },
                )
            if not approving:
                self._emit_decision(
                    uow, row, event_type=EVENT_APPROVAL_DENIED, decided_by=decider
                )

        try:
            payload = json.loads(row.request_payload)
        except (TypeError, ValueError):  # pragma: no cover - we always store JSON
            payload = {}
        kwargs = dict(payload.get("kwargs") or {})

        if not approving:
            notified = self._notify_rejection(
                row, decider=decider, kwargs=kwargs, justification=just
            )
            response: dict[str, Any] = {
                "approval_id": aid,
                "status": STATUS_REJECTED,
                "decided_by": decider,
                "decided_at": now,
                "notified": notified,
            }
            if just is not None:
                response["justification"] = just
            return response

        # UoW 2 lives inside the use case: the executor re-invokes it with the
        # one-shot bypass; ANY failure is a gate speaking - revert honestly
        # (approved must only ever describe a consumed execution - BR3).
        executor = self._executors[row.action]
        try:
            result = executor(kwargs)
        except BaseException:
            with self._cf.unit_of_work() as uow:
                self._approvals.revert_to_pending(uow, approval_id=aid)
            raise

        # UoW 3: persist the receipt + announce the grant (metadata only).
        with self._cf.unit_of_work() as uow:
            self._approvals.set_executed_result(
                uow,
                approval_id=aid,
                executed_result=json.dumps(result, ensure_ascii=False, default=str),
            )
            self._emit_decision(
                uow, row, event_type=EVENT_APPROVAL_GRANTED, decided_by=decider
            )
        return {
            "approval_id": aid,
            "status": STATUS_APPROVED,
            "decided_by": decider,
            "decided_at": now,
            "executed_result": result,
        }

    def _emit_decision(
        self, uow: UnitOfWork, row: Approval, *, event_type: str, decided_by: str
    ) -> None:
        """Emit granted/denied with routing metadata only - never content (BR5)."""
        if self._emitter is None:
            return
        payload: dict[str, Any] = {
            "approval_id": row.approval_id,
            "action": row.action,
            "agent_id": row.agent_id,
            "policy_id": row.policy_id,
            "decided_by": decided_by,
        }
        if row.trace_id is not None:
            payload["trace_id"] = row.trace_id
        self._emitter.emit(
            uow,
            workspace_id=row.workspace_id,
            stream=APPROVAL_STREAM,
            type=event_type,
            payload=payload,
            actor_agent_id=decided_by or None,
            visibility=APPROVAL_VISIBILITY,
            target=None,
        )

    def _notify_rejection(
        self,
        row: Approval,
        *,
        decider: str,
        kwargs: Mapping[str, Any],
        justification: str | None,
    ) -> bool:
        """Direct operator->requester message with the justification (FR5).

        Rides the ``message_create`` executor: the one-shot bypass skips the
        session gate (the operator decides over REST, sessionless) and the
        re-interception; permissions and governance stay live. Best-effort by
        design - a failure here never unwinds the committed rejection.
        """
        executor = self._executors.get(ACTION_MESSAGE_CREATE)
        project_root = kwargs.get("project_root")
        if executor is None or project_root is None:
            return False
        justification = justification or DEFAULT_REJECT_JUSTIFICATION
        try:
            executor(
                {
                    "project_root": project_root,
                    "from_agent_id": decider,
                    "subject": f"Approval {row.approval_id}: {row.action} rejected",
                    "body": (
                        f"Your {row.action} request was rejected by {decider}. "
                        f"Justification: {justification}"
                    ),
                    "target": {"strategy": "direct", "agent_id": row.agent_id},
                    "trace_id": row.trace_id,
                }
            )
        except OktoNexusError:
            return False
        return True

    # ------------------------------------------------------------------ #
    # Operator queue reads (FR8; work with the flag OFF - BR6)
    # ------------------------------------------------------------------ #
    def list_approvals(
        self,
        *,
        workspace_id: str,
        status: str | None = STATUS_PENDING,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Oldest-first queue items (summaries - BR5), workspace-scoped."""
        with self._cf.unit_of_work(write=False) as uow:
            rows = self._approvals.list(
                uow, workspace_id=workspace_id, status=status, limit=limit
            )
        return [approval_to_summary(row) for row in rows]

    def get_approval(self, *, approval_id: str) -> dict[str, Any]:
        """Full detail incl. the intact request payload (operator-only)."""
        with self._cf.unit_of_work(write=False) as uow:
            row = self._approvals.get(uow, str(approval_id))
        if row is None:
            raise self._not_found(approval_id)
        return approval_to_detail(row)

    @staticmethod
    def _not_found(approval_id: Any) -> OktoNexusError:
        return OktoNexusError(
            ErrorCode.NOT_FOUND,
            f"Approval {approval_id!r} not found.",
            {"approval_id": approval_id},
        )
