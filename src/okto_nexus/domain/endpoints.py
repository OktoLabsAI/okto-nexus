"""Versioned connection contracts, independent of products and SDKs."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..errors import ErrorCode, OktoNexusError

ADAPTER_CONTRACT_VERSION = 1


def adapter_identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", value):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid adapter identifier.", {})
    return value


@dataclass(frozen=True, slots=True)
class EndpointCapabilities:
    conversation: bool = False
    managed_work: bool = False
    context_without_execution: bool = False
    events: bool = False
    observes_acceptance: bool = False
    correlated_results: bool = False
    native_deduplication: bool = False
    native_replay: bool = False
    multiplexing: bool = False
    steer_timing: str | None = None
    interrupt: bool = False
    interrupt_requires_settle: bool = False
    observes_stop: bool = False
    approvals: bool = False

    def restrict(self, allowed: EndpointCapabilities) -> EndpointCapabilities:
        """Intersection only; declarations/profile can never grant capability."""
        from dataclasses import fields
        return EndpointCapabilities(**{
            f.name: (self.steer_timing if self.steer_timing == allowed.steer_timing else None)
            if f.name == "steer_timing" else
            bool(self.interrupt_requires_settle or allowed.interrupt_requires_settle)
            if f.name == "interrupt_requires_settle" else
            bool(getattr(self, f.name) and getattr(allowed, f.name))
            for f in fields(self)
        })


@dataclass(frozen=True, slots=True)
class AgentEndpoint:
    endpoint_id: str
    agent_id: str
    adapter_id: str
    workspace_id: str
    protocol: str
    runtime_profile_id: str | None = None
    contract_version: int = ADAPTER_CONTRACT_VERSION
    enabled: bool = False
    activation_state: str = "pending_review"
    priority: int = 0
    selection_group: str | None = None
    delivery_consumption: str = "exclusive"
    response_policy: str = "explicit"
    public_config: dict = field(default_factory=dict)
    secret_refs: tuple[str, ...] = ()
    revision: int = 1
    health: str = "unknown"
    last_observed_at: str | None = None

    def __post_init__(self):
        adapter_identifier(self.adapter_id)
        if not all((self.endpoint_id, self.agent_id, self.workspace_id, self.protocol)):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Endpoint requires an exact identity/workspace binding.", {})
        if self.workspace_id == "*" or self.contract_version != ADAPTER_CONTRACT_VERSION or self.revision < 1:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported endpoint scope or version.", {})
        if self.delivery_consumption not in {"exclusive", "mirror_only", "pull"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid consumption policy.", {})
        if self.response_policy not in {"explicit", "none", "conversation"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid response policy.", {})
