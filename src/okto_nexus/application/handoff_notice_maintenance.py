"""Serve-owned bounded notice maintenance; a cancelled observer owns no release."""
import asyncio
import logging
import math
import time

from .handoff_notice_retirement import HandoffNoticeRetirement


class HandoffNoticeMaintenance:
    def __init__(self, *, factory, notices: HandoffNoticeRetirement, page_size=64, interval=1, now=time.time):
        if (type(page_size) is not int or not 1 <= page_size <= 256
                or type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0):
            raise ValueError('Invalid notice maintenance limits.')
        self.factory, self.notices, self.now = factory, notices, now
        self.page_size, self.interval = page_size, interval
        self._stopping = asyncio.Event()
        self._task = None
        self.last_error = None

    def start(self):
        if self._task is not None:
            raise RuntimeError('Notice maintenance already started.')
        self._task = asyncio.create_task(self._run(), name='handoff-notice-maintenance')

    def begin_shutdown(self):
        self._stopping.set()

    @property
    def drained(self):
        return self._task is None or self._task.done() and not self._task.cancelled() and self._task.exception() is None

    def _page(self):
        with self.factory.unit_of_work() as uow:
            return self.notices.retire_page(uow, now=self.now(), limit=self.page_size)

    async def _run(self):
        while not self._stopping.is_set():
            # This retained task owns the writer even if shutdown's HTTP wait
            # expires. No second page can overtake an unfinished producer.
            try:
                await asyncio.to_thread(self._page)
                self.last_error = None
            except Exception:
                if self.last_error is None:
                    logging.getLogger(__name__).exception('Handoff notice conversion remains pending.')
                self.last_error = 'HANDOFF_NOTICE_MAINTENANCE_PENDING'
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    async def aclose(self):
        self.begin_shutdown()
        if self._task is not None:
            await asyncio.shield(self._task)
