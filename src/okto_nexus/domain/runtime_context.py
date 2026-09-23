"""Authenticated runtime authority, contract v1 (never built from payload)."""
from dataclasses import dataclass, field

from .base import new_id


@dataclass(frozen=True, slots=True)
class RuntimeRequestContext:
    actor_agent_id: str | None
    authentication_source: str
    trusted_local_operator: bool = False
    request_id: str = field(default_factory=lambda: new_id("req"))
    represented_agent_id: str | None = None
    workspace_id: str | None = None
    endpoint_id: str | None = None
    runtime_session_id: str | None = None
    execution_grant_id: str | None = None
    credential_binding: str | None = None
    authentication_time: str | None = None
    request_deadline: str | None = None
    runtime_owner_id: str | None = None
    runtime_owner_epoch: int | None = None


@dataclass(frozen=True, slots=True)
class ExecutionGrant:
    grant_id: str
    issuer_agent_id: str
    actor_agent_id: str
    represented_agent_id: str
    workspace_id: str
    endpoint_id: str
    actions: frozenset[str]
    expires_at: str
    revision: int = 1
    revoked_at: str | None = None
    runtime_profile_id: str | None = None
    handoff_id: str | None = None
    claim_epoch: int | None = None
    max_executions: int = 1
