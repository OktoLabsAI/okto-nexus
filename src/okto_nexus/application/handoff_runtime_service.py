"""Serve lifetime for the bounded scheduler, independent of native containment."""
import asyncio
import math

from .handoff_runtime_scheduler import HandoffRuntimeScheduler


class HandoffRuntimeService:
    def __init__(self, scheduler: HandoffRuntimeScheduler, *, interval=.25):
        if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
            raise ValueError('Invalid handoff service interval.')
        self.scheduler, self.interval = scheduler, interval
        self._stopping = asyncio.Event()
        self._task = None

    def start(self):
        if self._task is not None or self._stopping.is_set():
            raise RuntimeError('Handoff runtime service already started or closed.')
        self._task = asyncio.create_task(self._run(), name='handoff-runtime-service')

    def begin_shutdown(self):
        self.scheduler.begin_shutdown()
        self._stopping.set()

    @property
    def drained(self):
        return (self.scheduler.pending_count == 0 and (self._task is None or
            self._task.done() and not self._task.cancelled() and self._task.exception() is None))

    async def _run(self):
        try:
            while not self._stopping.is_set():
                self.scheduler.tick()
                try:
                    await asyncio.wait_for(self._stopping.wait(), self.interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.scheduler.begin_shutdown()
            # A timeout does not release a retained DB/host producer. Keep the
            # serve owner alive until those exact tasks actually return.
            while await self.scheduler.aclose(timeout=self.interval):
                pass

    async def aclose(self):
        self.begin_shutdown()
        if self._task is not None:
            await asyncio.shield(self._task)
