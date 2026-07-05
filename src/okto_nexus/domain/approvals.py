"""Pure domain rules for the HITL approvals queue (spec 2948b2a2).

An action intercepted by a ``require_approval`` governance policy (see
:mod:`okto_nexus.domain.governance`) is serialised INTO the ``approvals`` table
(migration 017) in the SAME unit of work that returns the ``pending_approval``
envelope - an intercepted action can never be lost (BR1). The human decision
over REST is the only trigger: ``approve`` re-invokes the real use case with a
one-shot interception bypass and every other gate active (BR2), ``reject``
closes the row and notifies the requester via a direct message from the
``operator`` agent. ``approved`` only ever describes a CONSUMED execution: a
gate failure during re-execution reverts the row to ``pending`` (BR3).

This module owns the IO-free half: the closed status/decision vocabularies,
the immutable row record, decision validation (fail-closed) and the queue-item
summary, which never exposes the intercepted action's subject/body (BR5 - the
full payload is only readable through the operator-only detail endpoint). It
never imports ``sqlite3`` nor ``mcp`` (enforced by the import-boundary test).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "STATUS_PENDING",
    "STATUS_APPROVED",
    "STATUS_REJECTED",
    "STATUSES",
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "DECISIONS",
    "DEFAULT_REJECT_JUSTIFICATION",
    "OPERATOR_AGENT_ID",
    "Approval",
    "is_reserved_agent_id",
    "validate_decision",
    "validate_status_filter",
    "payload_meta",
]


STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUSES: frozenset[str] = frozenset({STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED})

DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"
DECISIONS: frozenset[str] = frozenset({DECISION_APPROVE, DECISION_REJECT})

#: Body fallback for a rejection without a justification (FR5): the requester
#: is ALWAYS told why-or-that-there-is-no-why, never silently dropped.
DEFAULT_REJECT_JUSTIFICATION = "No justification provided"

#: The first-class human identity (FR6/BR4): seeded idempotently at bootstrap,
#: RESERVED on every public registration path - an agent can never impersonate
#: the human operator. Reservation is unconditional (no flag).
OPERATOR_AGENT_ID = "operator"

#: Keys of the serialised use-case kwargs that carry the action's content and
#: therefore never leave the approvals table through list/event surfaces (BR5).
_CONTENT_KEYS = frozenset({"subject", "body", "payload", "artifacts"})


@dataclass(frozen=True)
class Approval:
    """One stored approvals row, as repos and services see it.

    ``request_payload`` / ``executed_result`` are the JSON TEXT exactly as
    stored - deserialising is the caller's concern (the repo stays dumb).
    """

    approval_id: str
    workspace_id: str
    agent_id: str
    action: str
    policy_id: str
    request_payload: str
    status: str
    decided_by: str | None
    justification: str | None
    executed_result: str | None
    trace_id: str | None
    created_at: str
    decided_at: str | None


def is_reserved_agent_id(raw: Any) -> bool:
    """Whether ``raw`` normalises to the reserved operator identity (BR4).

    Case-insensitive, whitespace-trimmed: ``"operator"``, ``"Operator"`` and
    ``" OPERATOR "`` are all the same reserved name.
    """
    if raw is None:
        return False
    return str(raw).strip().lower() == OPERATOR_AGENT_ID


def validate_decision(raw: Any) -> str:
    """Normalise + validate one decision token; fail-closed outside the set."""
    decision = str(raw).strip().lower() if raw is not None else ""
    if decision not in DECISIONS:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown decision: {raw!r}.",
            {"decision": raw, "supported": sorted(DECISIONS)},
        )
    return decision


def validate_status_filter(raw: Any) -> str | None:
    """Normalise the queue's ``status`` filter; ``all`` -> ``None`` (no filter).

    Missing/empty defaults to ``pending`` (the operator's queue); anything
    outside the vocabulary is fail-closed.
    """
    token = str(raw).strip().lower() if raw is not None else ""
    if not token:
        return STATUS_PENDING
    if token == "all":
        return None
    if token not in STATUSES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown approval status filter: {raw!r}.",
            {"status": raw, "supported": sorted(STATUSES) + ["all"]},
        )
    return token


def payload_meta(kind: str, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Summarise a serialised action for queue items (BR5: no content).

    Returns ``{kind, byte_size, ...routing hints}`` where the hints name WHO
    the action addresses (target / channel), never WHAT it says - subject,
    body, payload and artifacts stay behind the operator-only detail endpoint.
    """
    meta: dict[str, Any] = {"kind": kind}
    size = 0
    for key in ("body", "payload"):
        value = kwargs.get(key)
        if isinstance(value, str):
            size += len(value.encode("utf-8"))
    meta["byte_size"] = size
    for key in ("target", "channel_id", "visibility"):
        value = kwargs.get(key)
        if value is not None and key not in _CONTENT_KEYS:
            meta[key] = value
    return meta
