"""Request-local managed identity; never a canonical agent key."""

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ExecutionPrincipal:
    capability_id: str
    secret_hash: str = field(repr=False)
    audience: str
    scope: Mapping[str, object]


current_execution_principal: ContextVar[ExecutionPrincipal | None] = ContextVar(
    'nexus_execution_principal', default=None)
current_execution_tool: ContextVar[str | None] = ContextVar('nexus_execution_tool', default=None)
