"""Serve-owned local inventory with the existing exclusive store owner."""
from __future__ import annotations

import asyncio
import time
import threading

from ..adapters.outbound.execution.core_inventory import (
    discover_local_candidates, local_inventory_snapshot,
)
from ..adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from ..application.executor_inventory import publish_executor_inventory
from ..domain.execution.keys import ExecutorKey


class EmbeddedInventoryOwner:
    """Retain full local candidates; publish path-free facts without runtime readiness."""

    def __init__(self, deps, fresh_publications, *, refresh_seconds=30):
        self.deps = deps
        self.fresh = fresh_publications
        self.dispatcher = deps.runtime_dispatcher
        self.identity = ensure_execution_installation(deps.connection_factory)
        self.key = ExecutorKey(self.identity.server_id, self.identity.embedded_executor_id)
        self.candidates = ()
        self.publication = None
        self.failure = None
        self.refresh_seconds = refresh_seconds
        self.generation = None
        self._stop = asyncio.Event()
        self._discovery_stopped = threading.Event()
        self._task = None
        self._startup_task = None
        self._refresh_task = None
        self._close_task = None

    def _claim(self):
        dispatcher = self.dispatcher
        with self.deps.connection_factory.unit_of_work() as uow:
            if not dispatcher.repo.owns(uow, owner_id=dispatcher.owner_id,
                    epoch=dispatcher.epoch, now=self.deps.clock.now_iso()):
                raise RuntimeError("The embedded inventory requires the current store owner.")
            row = uow.connection.execute(
                "SELECT * FROM execution_executors WHERE server_id=? AND executor_id=? "
                "AND kind='embedded' AND revoked_at IS NULL",
                (self.key.server_id, self.key.executor_id)).fetchone()
            if row is None:
                raise RuntimeError("The embedded executor is unavailable.")
            generation = row["generation"] + (row["owner_instance_id"] != dispatcher.owner_id)
            uow.connection.execute(
                "UPDATE execution_executors SET owner_instance_id=?,generation=?,control_state='RECOVERING' "
                "WHERE server_id=? AND executor_id=?",
                (dispatcher.owner_id, generation, self.key.server_id, self.key.executor_id))
            return generation

    async def start(self):
        if self._startup_task is None:
            self._startup_task = asyncio.create_task(self._start(), name="embedded-inventory-start")
        return await asyncio.shield(self._startup_task)

    async def _start(self):
        self.generation = await asyncio.to_thread(self._claim)
        await self.refresh()
        if not self._stop.is_set():
            self._task = asyncio.create_task(self._run(), name="embedded-inventory")

    async def refresh(self):
        if self._stop.is_set():
            return
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_owned(), name="embedded-inventory-refresh")
            self._refresh_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        return await asyncio.shield(self._refresh_task)

    async def _refresh_owned(self):
        from nexus_connector_core import DiscoveryCancelled
        try:
            return await self._refresh()
        except DiscoveryCancelled as error:
            self.fresh.pop((self.key.server_id, self.key.executor_id), None)
            if not self._stop.is_set():
                self.failure = error
                raise
            return
        except Exception as error:
            self.failure = error
            self.fresh.pop((self.key.server_id, self.key.executor_id), None)
            raise

    async def _refresh(self):
        observed_at = time.monotonic()
        configuration = getattr(self.deps, 'local_discovery', None)
        discovery = await asyncio.to_thread(discover_local_candidates,
            cancel_requested=self._discovery_stopped.is_set,
            **(configuration.arguments() if configuration is not None else {}))
        if self._stop.is_set():
            return
        candidates = tuple(discovery.candidates)
        age_ms = max(0, int((time.monotonic() - observed_at) * 1000))
        publication = await asyncio.to_thread(self._publish, candidates, age_ms)
        self.candidates = candidates
        self.publication = publication
        self.failure = None
        self.fresh[(self.key.server_id, self.key.executor_id)] = (
            publication.publication_sequence, time.monotonic(), age_ms)

    def _publish(self, candidates, age_ms):
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            previous = uow.connection.execute(
                "SELECT publication_sequence FROM execution_inventory_current "
                "WHERE server_id=? AND executor_id=?",
                (self.key.server_id, self.key.executor_id)).fetchone()
        snapshot = local_inventory_snapshot(candidates,
            server_id=self.key.server_id, executor_id=self.key.executor_id,
            producer_instance_id=self.dispatcher.owner_id,
            publication_sequence=previous[0] + 1 if previous else 1,
            observation_age_ms=age_ms)
        return publish_executor_inventory(self.deps.connection_factory,
            principal=self.key, producer_instance_id=self.dispatcher.owner_id,
            snapshot=snapshot, embedded_owner=(self.dispatcher.owner_id, self.dispatcher.epoch, self.generation))

    async def _run(self):
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), self.refresh_seconds)
                return
            except TimeoutError:
                pass
            try:
                await self.refresh()
            except Exception as error:
                self.failure = error
                self.fresh.pop((self.key.server_id, self.key.executor_id), None)

    def _release(self):
        with self.deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute(
                "UPDATE execution_executors SET control_state='DISCONNECTED' "
                "WHERE server_id=? AND executor_id=? AND owner_instance_id=? AND generation=?",
                (self.key.server_id, self.key.executor_id,
                 self.dispatcher.owner_id, self.generation))

    async def close(self):
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close(), name="embedded-inventory-close")
        return await asyncio.shield(self._close_task)

    async def _close(self):
        self._discovery_stopped.set()
        self._stop.set()
        if self._startup_task is not None:
            await asyncio.gather(self._startup_task, return_exceptions=True)
        if self._task is not None:
            await self._task
        if self._refresh_task is not None:
            await asyncio.gather(self._refresh_task, return_exceptions=True)
        self.fresh.pop((self.key.server_id, self.key.executor_id), None)
        await asyncio.to_thread(self._release)
