"""Bounded retained scheduling; application work is supplied through a port.

One shared tick services durable pages and leases. There is no poller per agent
or handoff, and a timed-out close never replaces a still-running producer.
Canonical handoff claims and attempt journals remain the authority for effects.
"""
import asyncio
from dataclasses import dataclass
import math
import threading
import time
from typing import Protocol

from nexus_connector_core.capacity import CAPACITY_REASONS


SCHEDULE_REASONS = CAPACITY_REASONS | {'NO_CANDIDATES', 'MORE_CANDIDATES', 'CLAIM_COMMITTED', 'SETTLED'}


@dataclass(frozen=True)
class HandoffScheduleLease:
    handoff_id: str
    workspace_id: str
    claim_generation: int
    token: str
    wake_revision: int
    wake_generation: int
    candidate_cursor: str


@dataclass(frozen=True)
class HandoffScheduleOutcome:
    reason: str
    candidate_cursor: str = ''
    done: bool = False

    def __post_init__(self):
        if (self.reason not in SCHEDULE_REASONS or type(self.done) is not bool
                or type(self.candidate_cursor) is not str or len(self.candidate_cursor) > 4096
                or self.candidate_cursor and not self.candidate_cursor.isprintable()):
            raise ValueError('Invalid handoff schedule outcome.')


def schedule_backoff(reason, count):
    if reason == 'MORE_CANDIDATES':
        return 0.05
    base = {'BUSY_AFFINITY': 1, 'POOL_FULL': 1, 'HOST_FULL': 1, 'EARLIER_WORK_PENDING': 1,
            'RECOVERING': 2, 'STALE_OBSERVATION': 2, 'NO_CANDIDATES': 5,
            'NOT_AUTHORIZED': 30, 'CAPACITY_PROTOCOL_UNSUPPORTED': 60}.get(reason, 5)
    return min(300 if base >= 30 else 30, base * 2 ** min(max(count - 1, 0), 6))


class HandoffScheduleRepository(Protocol):
    def wake(self, uow): ...
    def notify(self, uow, *, handoff_id, now): ...
    def sweep(self, uow, *, now, limit): ...
    def lease_due(self, uow, *, now, limit, lease_seconds) -> tuple[HandoffScheduleLease, ...]: ...
    def renew(self, uow, lease, *, now, lease_seconds) -> bool: ...
    def finish(self, uow, lease, outcome, *, now) -> bool: ...


class HandoffScheduleProcessor(Protocol):
    async def process(self, lease: HandoffScheduleLease) -> HandoffScheduleOutcome: ...


class HandoffRuntimeScheduler:
    def __init__(self, *, factory, repository: HandoffScheduleRepository,
                 processor: HandoffScheduleProcessor, max_running=8, scan_limit=64,
                 lease_seconds=30, sweep_seconds=5, now=time.time, monotonic=time.monotonic):
        if (any(type(n) is not int or not 1 <= n <= 256 for n in (max_running, scan_limit))
                or any(type(n) not in (int, float) or not math.isfinite(n) or n <= 0
                       for n in (lease_seconds, sweep_seconds))):
            raise ValueError('Invalid handoff scheduler limits.')
        self.factory, self.repository, self.processor = factory, repository, processor
        self.max_running, self.scan_limit = max_running, scan_limit
        self.lease_seconds, self.sweep_seconds = lease_seconds, sweep_seconds
        self.now, self.monotonic = now, monotonic
        self._signal_lock, self._notified = threading.Lock(), False
        self._running, self._pump = {}, None
        self._next_sweep = 0
        self._closed = False

    @property
    def pending_count(self):
        return len(self._running) + int(self._pump is not None and not self._pump.done())

    def wake(self):
        # Safe from inbound writer threads. No storage or task per notification.
        with self._signal_lock:
            self._notified = True

    def tick(self):
        """Nonblocking maintenance hook; retain one planner even if storage stalls."""
        if self._closed or self._pump is not None and not self._pump.done():
            return
        self._pump = asyncio.create_task(self._plan(), name='handoff-runtime-schedule')
        self._pump.add_done_callback(self._retrieve)

    @staticmethod
    def _retrieve(task):
        if not task.cancelled():
            task.exception()

    def _take_notification(self):
        with self._signal_lock:
            notified, self._notified = self._notified, False
            return notified

    async def _plan(self):
        notified = self._take_notification()
        scan = self.monotonic() >= self._next_sweep
        running = tuple(self._running.values())
        room = self.max_running - len(running)
        try:
            leases = await asyncio.to_thread(self._reserve_page, notified, scan, running, room)
        except BaseException:
            if notified:
                self.wake()  # A failed writer must not swallow the wakeup.
            raise
        if scan:
            self._next_sweep = self.monotonic() + self.sweep_seconds
        # Closing may have started while the planner's writer was still busy.
        # Persisted scan leases simply expire; no productive work was launched.
        if self._closed:
            return
        for lease in leases:
            task = asyncio.create_task(self._execute(lease), name='handoff-runtime-work')
            self._running[task] = lease
            def done(completed):
                self._running.pop(completed, None)
                self._retrieve(completed)
            task.add_done_callback(done)

    def _reserve_page(self, notified, scan, running, room):
        now = self.now()
        with self.factory.unit_of_work() as uow:
            if notified:
                self.repository.wake(uow)
            for lease in running:
                self.repository.renew(uow, lease, now=now, lease_seconds=self.lease_seconds)
            if scan:
                self.repository.sweep(uow, now=now, limit=self.scan_limit)
            return self.repository.lease_due(uow, now=now, limit=room,
                                            lease_seconds=self.lease_seconds) if room else ()

    async def _execute(self, lease):
        try:
            outcome = await self.processor.process(lease)
            if type(outcome) is not HandoffScheduleOutcome:
                raise ValueError('Invalid handoff processor result.')
        except (Exception, asyncio.CancelledError):
            # Scheduling failure says nothing about native effects or ownership.
            outcome = HandoffScheduleOutcome('NEEDS_RECONCILIATION', lease.candidate_cursor)
        await asyncio.to_thread(self._finish, lease, outcome)

    def _finish(self, lease, outcome):
        with self.factory.unit_of_work() as uow:
            self.repository.finish(uow, lease, outcome, now=self.now())

    async def aclose(self, *, timeout=1):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError('Invalid scheduler close timeout.')
        self._closed = True
        tasks = set(self._running)
        if self._pump is not None and not self._pump.done():
            tasks.add(self._pump)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            return len(pending)
        return 0
