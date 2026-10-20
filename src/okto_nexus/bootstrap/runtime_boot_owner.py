"""Retain automatic endpoint boot without delaying HTTP or losing its producer."""
import asyncio
import logging


class RuntimeBootOwner:
    def __init__(self, deps, inventory, boot, *, retry_seconds=30):
        self.deps, self.inventory, self.boot = deps, inventory, boot
        self.retry_seconds = retry_seconds
        self.failure = None
        self._stop = asyncio.Event()
        self._task = None

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name='runtime-approved-boot')

    @property
    def drained(self):
        return self._task is None or self._task.done()

    def begin_shutdown(self):
        self._stop.set()

    async def aclose(self):
        self.begin_shutdown()
        if self._task is not None:
            await asyncio.shield(self._task)

    async def wait(self):
        if self._task is not None:
            await asyncio.shield(self._task)

    async def _ready(self):
        ready = asyncio.create_task(self.inventory.wait_usable_observation())
        stopping = asyncio.create_task(self._stop.wait())
        try:
            await asyncio.wait((ready, stopping), return_when=asyncio.FIRST_COMPLETED)
            return not self._stop.is_set() and ready.result()
        finally:
            # These are observation-only coroutines, not producer threads.
            for observer in (ready, stopping):
                observer.cancel()
            await asyncio.gather(ready, stopping, return_exceptions=True)

    async def _run(self):
        completed = set()
        while not self._stop.is_set():
            try:
                if not await self._ready():
                    return
                # The worker is never cancelled at shutdown: its admission
                # still passes the current owner/fence and storage stays
                # owned until it returns. Retries use the same boot intent
                # keys; canonical admission never replays a possible effect.
                sequence = self.inventory.publication.publication_sequence
                results = await asyncio.to_thread(self.boot, self.deps, exclude_endpoint_ids=frozenset(completed))
                self.failure = None
                retry = False
                for row in results or ():
                    if row['state'] == 'deferred' or row.get('retryable'):
                        retry = True
                    else:
                        completed.add(row['endpoint_id'])
                if not retry and self.inventory.initial_observations_complete():
                    return
                # A sibling's completion wakes a new pass immediately. Accepted
                # intents are excluded; deferred work retains its original key.
                changed = asyncio.create_task(self.inventory.wait_publication_change(sequence))
                stopping = asyncio.create_task(self._stop.wait())
                try:
                    await asyncio.wait((changed, stopping), timeout=self.retry_seconds,
                                       return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for observer in (changed, stopping):
                        observer.cancel()
                    await asyncio.gather(changed, stopping, return_exceptions=True)
                continue
            except Exception as error:
                self.failure = error
                logging.getLogger(__name__).warning('Approved runtime boot deferred: %s', type(error).__name__)
            try:
                await asyncio.wait_for(self._stop.wait(), self.retry_seconds)
            except TimeoutError:
                pass
