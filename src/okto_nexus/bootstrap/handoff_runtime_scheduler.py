"""Explicit scheduler composition; production activation has separate gates."""
from ..adapters.outbound.sqlite.handoff_runtime_schedule import SqliteHandoffScheduleRepository
from ..application.handoff_runtime_processor import HandoffRuntimeProcessor
from ..application.handoff_runtime_scheduler import HandoffRuntimeScheduler
from .handoff_runtime_attempts import build_handoff_runtime_attempts
from .capacity_admission import build_capacity_admission


def build_handoff_runtime_candidates(deps):
    from ..adapters.inbound.mcp.tools.handoff import build_service
    from ..adapters.outbound.sqlite.handoff_runtime_candidates import SqliteHandoffCandidateRepository
    from ..adapters.outbound.sqlite.handoff_runtime_attempts import SqliteHandoffRuntimeAttemptRepository
    from ..application.handoff_runtime_candidates import HandoffCandidateDiscovery
    from .resource_pool import one_shot_pool

    attempts = SqliteHandoffRuntimeAttemptRepository()
    repository = SqliteHandoffCandidateRepository(attempts=attempts,
        availability=deps.runtime_availability, pool_factory=one_shot_pool)
    return HandoffCandidateDiscovery(factory=deps.connection_factory, repository=repository,
        attempts=attempts, handoffs=build_service(deps, register_approval_executor=False))


def build_handoff_runtime_scheduler(deps, *, candidates=None, capacity=None, **limits):
    if candidates is None:
        candidates = build_handoff_runtime_candidates(deps)
    processor = HandoffRuntimeProcessor(candidates=candidates,
        attempts=build_handoff_runtime_attempts(deps, capacity=capacity),
        admission=build_capacity_admission(deps, capacity=capacity))
    scheduler = HandoffRuntimeScheduler(factory=deps.connection_factory,
        repository=SqliteHandoffScheduleRepository(), processor=processor, **limits)
    # The serve-level scheduler owns this coalesced runtime signal. Rebuilding
    # it replaces the previous callback instead of accumulating listeners.
    deps.runtime_availability.wake = scheduler.wake
    return scheduler
