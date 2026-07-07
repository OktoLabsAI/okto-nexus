"""Shared MCP composition helper for communication guardrails."""

from __future__ import annotations

from typing import Any

from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.guardrails_repo import (
    SqliteGuardrailAssignmentRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.adapters.outbound.tokenizer import resolve_tokenizer
from okto_nexus.application.guardrails import GuardrailService


def build_guardrail_service(deps: Any) -> GuardrailService:
    """Wire and cache the process-local GuardrailService.

    Tool modules build their application services independently, so this helper
    keeps guardrail wiring consistent across message, artifact and handoff
    write paths while reusing the shared repositories/event emitter.
    """

    existing = getattr(deps, "guardrails", None)
    if existing is not None:
        return existing

    repos = deps.repos
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(repos, "guardrail_assignments", None) is None:
        repos.guardrail_assignments = SqliteGuardrailAssignmentRepo(deps.clock)
    if getattr(deps, "event_emitter", None) is None:
        if getattr(repos, "events", None) is None:
            repos.events = SqliteEventRepo(deps.clock)
        deps.event_emitter = SqliteEventEmitter(repos.events)

    tokenizer_resolution = getattr(deps, "guardrail_tokenizer", None)
    if tokenizer_resolution is None:
        tokenizer_resolution = resolve_tokenizer()
        deps.guardrail_tokenizer = tokenizer_resolution

    service = GuardrailService(
        connection_factory=deps.connection_factory,
        assignments=repos.guardrail_assignments,
        agents=repos.agents,
        clock=deps.clock,
        tokenizer=tokenizer_resolution.tokenizer,
        event_emitter=deps.event_emitter,
    )
    deps.guardrails = service
    return service
