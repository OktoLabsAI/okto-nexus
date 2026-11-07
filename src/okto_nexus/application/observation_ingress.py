"""Bounded OBS admission before HTTP bodies, thread dispatch and writer queues.

This process-local guard bounds even malformed/unauthenticated attempts. Durable
actor/source/report budgets are enforced separately inside the publish UoW.
"""
from contextlib import contextmanager
from math import ceil
from threading import BoundedSemaphore, Lock
from time import monotonic

from ..errors import ErrorCode, OktoNexusError


class ObservationIngress:
    def __init__(self, config, *, capacity=32, timer=monotonic):
        self.config, self.timer = config, timer
        self.slots, self.lock = BoundedSemaphore(capacity), Lock()
        self.updated = timer()
        self.available = float(config.observation_installation_burst)

    @contextmanager
    def enter(self):
        if not self.slots.acquire(blocking=False):
            raise OktoNexusError('OBSERVATION_BUSY', 'Observation ingestion is busy.',
                                 {'retry_after_seconds': 1}, retryable=True)
        try:
            with self.lock:
                now = self.timer()
                rate = self.config.observation_installation_rate_per_minute / 60
                burst = self.config.observation_installation_burst
                self.available = min(burst, self.available + max(0, now - self.updated) * rate)
                self.updated = now
                if self.available < 1:
                    raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED,
                        'The observation ingress budget is exhausted.',
                        {'retry_after_seconds': max(1, ceil((1 - self.available) / rate))},
                        retryable=True)
                self.available -= 1
            yield
        finally:
            self.slots.release()
