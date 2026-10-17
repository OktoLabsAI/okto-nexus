"""Replace a failed embedded owner only after all its producers have drained.

The HTTP/store owner survives this transition. Native effects are never retried
here: the replacement consumes the same durable reconciliation contracts as boot.
"""
import asyncio
import logging


class EmbeddedRuntimeSupervisor:
    def __init__(self, app, coordinator, *, poll_seconds=1.0):
        self.app, self.coordinator = app, coordinator
        self.poll_seconds = poll_seconds
        self._stop = asyncio.Event()
        self._task = None
        self._candidate = None
        self._starting = None
        self.failure = None

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name='embedded-owner-supervisor')

    @property
    def drained(self):
        return self._task is None or (self._task.done() and not self._task.cancelled()
                                     and self._task.exception() is None)

    def begin_shutdown(self):
        self._stop.set()
        if self._candidate is not None:
            self._candidate.begin_shutdown()
        # A replacement startup may be awaiting its initial recovery. Fence it
        # now; the coordinator joins this supervisor before reading current owners.
        if self._starting is not None:
            self._starting._stopping.set()
            self._starting.capacity_waiter.stop()

    async def aclose(self):
        self.begin_shutdown()
        if self._task is not None:
            await asyncio.shield(self._task)

    async def _replace(self, old):
        from .embedded_inventory import EmbeddedInventoryOwner
        from .embedded_dispatch import EmbeddedDispatchOwner
        from .runtime_host import EmbeddedRuntimeHost
        from .runtime_boot_owner import RuntimeBootOwner
        from ..application.execution_local_launch import ApprovedLocalLaunch
        from ..adapters.inbound.mcp.tools.harness import run_runtime_boot

        state, coordinator = self.app.state, self.coordinator
        inventory, boot = old.inventory, coordinator.runtime_boot
        inventory.begin_shutdown()
        if boot is not None:
            boot.begin_shutdown()
        # Request starts a retained cleanup owner; a zero observation budget
        # neither cancels cleanup nor authorizes replacement of uncertain work.
        await old.request_shutdown(timeout_seconds=0)
        await asyncio.gather(old.wait_shutdown(), *([boot.aclose()] if boot else []))
        if old.shutdown_status()['state'] != 'DRAINED':
            raise RuntimeError('Embedded predecessor still owns runtime resources.')
        # Join discovery, probes and publication before changing the generation.
        await inventory.close()
        if self._stop.is_set() or not await asyncio.to_thread(old._recovery_enabled):
            return
        if self._candidate is None:
            self._candidate = EmbeddedInventoryOwner(state.deps, inventory.fresh,
                predecessor_generation=inventory.generation)
        candidate = self._candidate
        # A failed claim has no native producer. Retry only its completed task;
        # the transaction still requires the exact released predecessor.
        task = candidate._startup_task
        if task is not None and task.done() and not task.cancelled() and task.exception() is not None:
            candidate._startup_task = None
        await candidate.start()
        if self._stop.is_set():
            await candidate.close()
            self._candidate = None
            return
        host = EmbeddedRuntimeHost(old.host.store_dir,
                                   max_owned_slots=old.host.max_owned_slots,
                                   capacity_enabled=old.host.capacity_enabled)
        host.local_launch_factory = lambda scope: ApprovedLocalLaunch(candidate, scope)
        dispatch = EmbeddedDispatchOwner(candidate, host)
        dispatch.native_factory = old.native_factory
        replacement_boot = RuntimeBootOwner(state.deps, candidate, run_runtime_boot)
        # No await between publishing references: HTTP, shutdown and reset all
        # see one bundle. The new dispatch still has to reconcile before READY.
        state.embedded_core_host = coordinator.host = host
        state.embedded_inventory_owner = coordinator.inventory = candidate
        state.embedded_dispatch_owner = coordinator.embedded = dispatch
        state.runtime_boot_owner = coordinator.runtime_boot = replacement_boot
        self._candidate = None
        self._starting = dispatch
        await self._start_replacement()

    async def _start_replacement(self):
        owner = self._starting
        if self._stop.is_set():
            return
        await owner.start()
        if not self._stop.is_set():
            self.coordinator.runtime_boot.start()
            self.app.state.deps.runtime_dispatcher.wake()
            logging.getLogger(__name__).info(
                'Embedded owner replaced after retained cleanup: generation=%s',
                owner.channel.connection_generation)
        self._starting = None

    async def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    if self._starting is not None:
                        await self._start_replacement()
                    else:
                        owner = self.coordinator.embedded
                        if (owner.failure is not None and owner._stopping.is_set()
                                and await asyncio.to_thread(owner._recovery_enabled)):
                            await self._replace(owner)
                    self.failure = None
                except Exception as error:
                    # Retain the exact old/candidate owner across storage or
                    # ownership failures; do not reset locks or discard evidence.
                    if self.failure is None or type(self.failure) is not type(error):
                        logging.getLogger(__name__).warning(
                            'Embedded replacement deferred: type=%s code=%s',
                            type(error).__name__, getattr(error, 'code', None))
                    self.failure = error
                try:
                    await asyncio.wait_for(self._stop.wait(), self.poll_seconds)
                except TimeoutError:
                    pass
        finally:
            while self._candidate is not None:
                try:
                    await self._candidate.close()
                except Exception as error:
                    # Shutdown remains pending. A failed release transaction
                    # cannot detach a claimed generation or discovery worker.
                    self.failure = error
                    await asyncio.sleep(.1)
                else:
                    self._candidate = None
                    self.failure = None
