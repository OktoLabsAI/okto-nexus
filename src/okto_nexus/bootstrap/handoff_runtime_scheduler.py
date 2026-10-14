"""Explicit scheduler composition; production activation has separate gates."""
from ..adapters.outbound.sqlite.handoff_runtime_schedule import SqliteHandoffScheduleRepository
from ..application.handoff_runtime_processor import HandoffRuntimeProcessor
from ..application.handoff_runtime_scheduler import HandoffRuntimeScheduler
from .handoff_runtime_attempts import build_handoff_runtime_attempts
from .capacity_admission import build_capacity_admission


def build_handoff_runtime_scheduler(deps, *, candidates, capacity=None, **limits):
    processor = HandoffRuntimeProcessor(candidates=candidates,
        attempts=build_handoff_runtime_attempts(deps, capacity=capacity),
        admission=build_capacity_admission(deps, capacity=capacity))
    return HandoffRuntimeScheduler(factory=deps.connection_factory,
        repository=SqliteHandoffScheduleRepository(), processor=processor, **limits)
