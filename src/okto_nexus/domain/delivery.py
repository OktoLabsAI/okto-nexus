"""Canonical transport operation contracts v1. Inbox and handoff retain ownership."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from ..errors import ErrorCode, OktoNexusError

INTENTS = frozenset({"information", "conversation", "handoff_offer", "handoff_execute",
                     "runtime_control", "receipt", "result_notification"})
OPERATION_TRANSITIONS = {
    "PENDING": {"CLAIMED", "CANCELLED", "REJECTED"},
    "CLAIMED": {"SENDING", "PENDING", "CANCELLED", "REJECTED"},
    "SENDING": {"ACCEPTED", "RETRY_WAIT", "OUTCOME_UNKNOWN", "SENT_UNCONFIRMED", "REJECTED", "FAILED_FINAL"},
    "RETRY_WAIT": {"CLAIMED", "CANCELLED", "REJECTED"},
    "ACCEPTED": {"OUTCOME_UNKNOWN"}, "SENT_UNCONFIRMED": {"ACCEPTED", "OUTCOME_UNKNOWN"}, "OUTCOME_UNKNOWN": set(),
    "REJECTED": set(), "CANCELLED": set(), "FAILED_FINAL": set(),
}


def validate_operation_transition(before: str, after: str) -> None:
    if after not in OPERATION_TRANSITIONS.get(before, set()):
        raise OktoNexusError(ErrorCode.CONFLICT, "Unsafe transport state transition.",
                            {"before": before, "after": after})


@dataclass(frozen=True, slots=True)
class DeliveryEnvelope:
    operation_id: str
    sender_agent_id: str
    recipient_agent_id: str
    workspace_id: str
    intent: str
    content: tuple[dict[str, Any], ...]
    root_operation_id: str
    message_id: str | None = None
    delivery_id: str | None = None
    context_id: str | None = None
    subject: str | None = None
    causation_id: str | None = None
    hop_count: int = 0
    response_requested: bool = False
    artifact_refs: tuple[str, ...] = ()
    handoff_id: str | None = None
    claim_epoch: int | None = None
    schema_version: int = 1
    trust: str = "untrusted_content"

    def __post_init__(self):
        if self.schema_version != 1 or self.intent not in INTENTS or self.hop_count < 0:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid delivery envelope version/intent.", {})
        if not all((self.operation_id, self.sender_agent_id, self.recipient_agent_id,
                    self.workspace_id, self.root_operation_id)) or self.trust != "untrusted_content":
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid delivery identity/trust.", {})
        if self.intent == "handoff_execute" and (not self.handoff_id or self.claim_epoch is None):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Managed work requires a canonical claim.", {})
        if any(item.get("type") != "text" or not isinstance(item.get("text"), str) for item in self.content):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Use authorized artifact references for non-text content.", {})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def request_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DispatchResult:
    outcome: str
    ack_level: str = "NONE"
    safe_to_retry: bool = False
    retry_basis: str | None = None
    native_request_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    session_id: str | None = None
    error_code: str | None = None
    redacted_details: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.outcome not in {"NOT_SENT", "REJECTED", "ACCEPTED", "SENT_UNCONFIRMED", "UNKNOWN"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid transport outcome.", {})
        if self.ack_level not in {"NONE", "TRANSPORT_WRITE", "HARNESS_ACCEPTED", "AGENT_ACK"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid acknowledgement level.", {})
        if self.outcome == "ACCEPTED" and self.ack_level not in {"HARNESS_ACCEPTED", "AGENT_ACK"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Write alone does not establish acceptance.", {})
        if self.safe_to_retry and not (
            self.outcome in {"NOT_SENT", "REJECTED"} and self.retry_basis in {"BEFORE_WRITE", "PEER_REJECTED"}
            or self.retry_basis == "PROVEN_NATIVE_DEDUPLICATION"
        ):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Retry requires protocol evidence.", {})
