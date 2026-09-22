"""Authenticated runtime authority, contract v1 (never built from payload)."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeRequestContext:
    actor_agent_id: str | None
    authentication_source: str
    trusted_local_operator: bool = False
