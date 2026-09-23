"""Versioned runtime administrative input models shared by HTTP and MCP."""
from typing import Any

from pydantic import BaseModel, Field


class RuntimeAdminBody(BaseModel):
    model_config = {"extra": "forbid", "strict": True}


class RuntimeProfileBody(RuntimeAdminBody):
    profile_id: str = Field(min_length=1, max_length=128)
    adapter_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)
    inherit_ambient: bool = False
    enabled: bool = False


class RuntimeEndpointBody(RuntimeAdminBody):
    endpoint_id: str = Field(min_length=1, max_length=128)
    agent_id: str
    adapter_id: str
    project_root: str
    profile_id: str | None = None
    enabled: bool = False
    priority: int = 0
    selection_group: str | None = None
    response_policy: str = "explicit"
    consumption: str = "exclusive"
    public_config: dict[str, Any] = Field(default_factory=dict)


class RuntimeBootBody(RuntimeAdminBody):
    enabled: bool
    expected_revision: int = Field(ge=1)


class RuntimeEndpointUpdateBody(RuntimeAdminBody):
    expected_revision: int = Field(ge=1)
    public_config: dict[str, Any]


class RuntimeReconcileBody(RuntimeAdminBody):
    expected_revision: int = Field(ge=1)
    idempotency_key: str
    reason: str
    acknowledge_uncertain_effects: bool = False
