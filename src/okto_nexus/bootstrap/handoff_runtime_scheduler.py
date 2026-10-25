"""Explicit scheduler composition; production activation has separate gates."""
from ..adapters.outbound.sqlite.handoff_runtime_schedule import SqliteHandoffScheduleRepository
from ..application.handoff_runtime_processor import HandoffRuntimeProcessor
from ..application.handoff_runtime_scheduler import HandoffRuntimeScheduler
from .handoff_runtime_attempts import build_handoff_runtime_attempts
from .capacity_admission import build_capacity_admission


def build_handoff_runtime_candidates(deps, *, acquisition_enabled=True):
    from ..adapters.inbound.mcp.tools.handoff import build_service
    from ..adapters.outbound.sqlite.handoff_runtime_candidates import SqliteHandoffCandidateRepository
    from ..adapters.outbound.sqlite.handoff_runtime_attempts import SqliteHandoffRuntimeAttemptRepository
    from ..application.handoff_runtime_candidates import HandoffCandidateDiscovery
    from .resource_pool import one_shot_pool

    attempts = SqliteHandoffRuntimeAttemptRepository()
    repository = SqliteHandoffCandidateRepository(attempts=attempts,
        availability=deps.runtime_availability, pool_factory=one_shot_pool)
    return HandoffCandidateDiscovery(factory=deps.connection_factory, repository=repository,
        attempts=attempts, handoffs=build_service(deps, register_approval_executor=False),
        acquisition_enabled=acquisition_enabled)


def build_handoff_notice_retirement():
    from ..adapters.outbound.sqlite.execution_pending_cancellation import SqlitePendingExecutionCancellation
    from ..adapters.outbound.sqlite.handoff_notice_retirement import SqliteHandoffNoticeRetirement
    from ..adapters.outbound.sqlite.messages_repo import SqliteMessageDeliveryRepo
    from .resource_pool import one_shot_pool
    return SqliteHandoffNoticeRetirement(cancellations=SqlitePendingExecutionCancellation(),
        inbox=SqliteMessageDeliveryRepo(), schedule=SqliteHandoffScheduleRepository(), pool_factory=one_shot_pool)


def build_handoff_notice_maintenance(deps, **limits):
    from ..application.handoff_notice_maintenance import HandoffNoticeMaintenance
    return HandoffNoticeMaintenance(factory=deps.connection_factory,
        notices=build_handoff_notice_retirement(), **limits)


def build_handoff_runtime_scheduler(deps, *, candidates=None, capacity=None, acquisition_enabled=True, **limits):
    if candidates is None:
        candidates = build_handoff_runtime_candidates(deps, acquisition_enabled=acquisition_enabled)
    processor = HandoffRuntimeProcessor(candidates=candidates,
        attempts=build_handoff_runtime_attempts(deps, capacity=capacity),
        admission=build_capacity_admission(deps, capacity=capacity))
    schedule = SqliteHandoffScheduleRepository()
    notices = build_handoff_notice_retirement()
    idle_ms = getattr(getattr(deps, 'config', None), 'runtime_idle_interval_ms', None)
    if idle_ms is not None:
        limits.setdefault('idle_seconds', idle_ms / 1000)
    from ..adapters.inbound.mcp.tools.handoff import build_service
    lease_watch = build_service(deps, register_approval_executor=False).watch_leases
    scheduler = HandoffRuntimeScheduler(factory=deps.connection_factory,
        repository=schedule, notices=notices, lease_watch=lease_watch, processor=processor, **limits)
    # The serve-level scheduler owns this coalesced runtime signal. Rebuilding
    # it replaces the previous callback instead of accumulating listeners.
    deps.runtime_availability.wake = scheduler.wake
    return scheduler
