"""Serve-owned local inventory with the existing exclusive store owner."""
from __future__ import annotations

import asyncio
import logging
import time
import threading

from nexus_connector_core import CoreError, HarnessObservationResult, IndependentInventoryObserver, resolve_installation

from ..adapters.outbound.execution.core_inventory import (
    discover_local_candidates, local_inventory_snapshot,
)
from ..adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from ..application.executor_inventory import publish_executor_inventory
from ..application.execution_inventory_refresh import claim_inventory_refresh
from ..domain.execution.keys import ExecutorKey
from ..errors import ErrorCode, OktoNexusError


logger = logging.getLogger(__name__)


class EmbeddedInventoryOwner:
    """Retain full local candidates; publish path-free facts without runtime readiness."""

    def __init__(self, deps, fresh_publications, *, refresh_seconds=30, predecessor_generation=None):
        self.deps = deps
        self.fresh = fresh_publications
        self.dispatcher = deps.runtime_dispatcher
        self.identity = ensure_execution_installation(deps.connection_factory)
        self.key = ExecutorKey(self.identity.server_id, self.identity.embedded_executor_id)
        self.candidates = ()
        self.raw_candidates = ()
        # (adapter_id, candidate_ref) -> why discovery left a candidate untrusted (#67).
        self.trust_details = {}
        self.publication = None
        self.published_batch = None
        self.failure = None
        self._publication_failures = 0
        self.refresh_seconds = refresh_seconds
        self.generation = None
        self.predecessor_generation = predecessor_generation
        self._stop = asyncio.Event()
        self._discovery_stopped = threading.Event()
        self._task = None
        self._startup_task = None
        self._refresh_task = None
        self._refresh_tasks = set()
        self._close_task = None
        self._claim_lock = asyncio.Lock()
        self._delivery = None
        self._delivery_frontier = None
        self._observer = IndependentInventoryObserver(self._observe, refresh_seconds=refresh_seconds)
        self._adapter_locks = {adapter: asyncio.Lock() for adapter in self._observer.adapters}
        self._probe_task = None
        self._observation_changed = asyncio.Event()

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
            if self.predecessor_generation is not None:
                # Same-process replacement is a new authority generation too.
                # Never take over a changed owner or revive a revoked executor.
                if (row['owner_instance_id'] != dispatcher.owner_id
                        or row['generation'] != self.predecessor_generation
                        or row['control_state'] != 'DISCONNECTED'):
                    raise RuntimeError('The predecessor embedded owner has not been released or changed.')
                generation = row['generation'] + 1
            else:
                generation = row["generation"] + (row["owner_instance_id"] != dispatcher.owner_id)
            uow.connection.execute(
                "UPDATE execution_executors SET owner_instance_id=?,generation=?,control_state='RECOVERING',last_seen_at=? "
                "WHERE server_id=? AND executor_id=?",
                (dispatcher.owner_id, generation, self.deps.clock.now_iso(), self.key.server_id, self.key.executor_id))
            return generation

    async def start(self):
        """Claim the generation before dispatch starts; observe asynchronously.

        Serving the dashboard must not wait for a provider tree scan. No
        current-process freshness is advertised until the retained refresh
        worker has published an observation under this generation.
        """
        if self._startup_task is None:
            self._startup_task = asyncio.create_task(self._start(), name="embedded-inventory-start")
        return await asyncio.shield(self._startup_task)

    async def _start(self):
        self.generation = await asyncio.to_thread(self._claim)
        self.fresh.pop((self.key.server_id, self.key.executor_id), None)
        if not self._stop.is_set():
            self._task = asyncio.create_task(self._run(), name="embedded-inventory")

    async def refresh(self, adapter_ids=None):
        if self._stop.is_set():
            return
        task = self._refresh_task if adapter_ids is None else None
        if task is None or task.done():
            task = asyncio.create_task(self._refresh_owned(adapter_ids), name="embedded-inventory-refresh")
            self._refresh_tasks.add(task)
            task.add_done_callback(self._refresh_tasks.discard)
            task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
            if adapter_ids is None:
                self._refresh_task = task
        return await asyncio.shield(task)

    async def _refresh_owned(self, adapter_ids):
        # Waiting for a requested full refresh never holds publication or a
        # sibling worker. Automatic observers continue independently.
        try:
            await self._claim_pending_refresh()
        except Exception as error:
            self.failure = error
            self.fresh.pop((self.key.server_id, self.key.executor_id), None)
            self._observation_changed.set()
            raise
        if self._stop.is_set():
            return
        frontier = self._observer.request_refresh(adapter_ids)
        if adapter_ids is None and self._delivery is not None:
            self._delivery_frontier = frontier
        previous_failures = self._publication_failures
        if not await self._observer.wait_refresh(frontier):
            return
        revision = self._observer.snapshot().revision
        while not self._stop.is_set():
            self._observation_changed.clear()
            if self.failure is not None and self._publication_failures > previous_failures:
                raise self.failure
            if self.published_batch is not None and self.published_batch.revision >= revision:
                return
            await self._observation_changed.wait()

    async def discover_candidates(self, adapter_id=None):
        configuration = getattr(self.deps, 'local_discovery', None)
        discovery = await asyncio.to_thread(discover_local_candidates,
            cancel_requested=self._discovery_stopped.is_set,
            adapter_ids=(adapter_id,) if adapter_id is not None else None,
            **(configuration.arguments() if configuration is not None else {}))
        found = tuple(discovery.candidates)
        from ..application.execution_installation_succession import apply_update_policy
        found = await asyncio.to_thread(apply_update_policy, self.deps, self.key, found,
                                        getattr(self, 'notify_installation_update', None))
        self._note_trust_reasons(found, adapter_id)
        return found

    def _note_trust_reasons(self, candidates, adapter_id=None):
        """Log and keep the Core reason of each untrusted candidate; an older Core has none."""
        from nexus_connector_core.availability import effective_installation_ref
        details = {}
        for item in candidates:
            reason = getattr(item, 'reason', None)
            if item.trust == 'untrusted' and reason:
                details[(item.adapter_id, effective_installation_ref(item))] = reason
        previous = self.trust_details
        for key, reason in details.items():
            if previous.get(key) != reason:
                logger.warning('Untrusted %s candidate: %s', key[0], reason)
        self.trust_details = {**{k: v for k, v in previous.items()
                                 if adapter_id is not None and k[0] != adapter_id}, **details}

    async def _observe(self, adapter_id, cancel_requested):
        from ..application.execution_local_observations import apply_local_observations, refresh_approved_installations
        async with self._adapter_locks[adapter_id]:
            raw = await self.discover_candidates(adapter_id)
            if not cancel_requested():
                await refresh_approved_installations(self, raw)
            candidates = await asyncio.to_thread(apply_local_observations,
                self.deps.connection_factory, self.key, raw)
            return HarnessObservationResult(tuple(candidates), raw)

    async def wait_usable_observation(self, adapter_id=None):
        """Wait for current-process freshness; never treat a saved view as ready."""
        from ..application.executor_inventory_views import INVENTORY_TTL_MS
        while not self._stop.is_set():
            self._observation_changed.clear()
            receipt = self.fresh.get((self.key.server_id, self.key.executor_id))
            if (receipt is not None and self.publication is not None and self.published_batch is not None
                    and receipt[0] == self.publication.publication_sequence
                    and any(row.state in ('PRESENT', 'ABSENT') and
                        row.observation_age_ms + receipt[2] + max(0, (time.monotonic() - receipt[1]) * 1000) < INVENTORY_TTL_MS
                        for row in self.published_batch.observations
                        if adapter_id is None or row.adapter_id == adapter_id)):
                return True
            await self._observation_changed.wait()
        return False

    def initial_observations_complete(self):
        return self.published_batch is not None and all(
            row.state in ('PRESENT', 'ABSENT') for row in self.published_batch.observations)

    async def wait_publication_change(self, after_sequence):
        while not self._stop.is_set():
            self._observation_changed.clear()
            if self.publication is not None and self.publication.publication_sequence > after_sequence:
                return True
            await self._observation_changed.wait()
        return False

    async def check_installation(self, *, access, context, request):
        if self._stop.is_set() or (self._probe_task is not None and not self._probe_task.done()):
            raise OktoNexusError(ErrorCode.CONFLICT, 'A local version check is active or the executor is stopping.', {})
        async def run():
            from ..application.execution_local_observations import observe_local_installation
            async with self._adapter_locks[request['adapter_id']]:
                result = await observe_local_installation(self, access=access, context=context, request=request)
            await self.refresh((request['adapter_id'],))
            try:
                selected = resolve_installation(self.published_batch.candidates,
                    request['adapter_id'], request['candidate_ref'])
                result['publication_pending'] = selected.version != result['version'] or selected.trust != 'selected'
            except (CoreError, AttributeError):
                result['publication_pending'] = True
            return result
        self._probe_task = asyncio.create_task(run(), name='embedded-version-check')
        self._probe_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        return await asyncio.shield(self._probe_task)

    async def _claim_pending_refresh(self):
        async with self._claim_lock:
            delivery = await asyncio.to_thread(self._claim_refresh)
            if self._stop.is_set():
                return
            if delivery is not None and delivery != self._delivery:
                self._delivery = delivery
                self._delivery_frontier = self._observer.request_refresh()

    def _claim_refresh(self):
        # Claim before discovery: requests arriving during a scan must wait for
        # the next observation. Revalidate the exclusive store lease here too.
        with self.deps.connection_factory.unit_of_work() as uow:
            row = uow.connection.execute(
                "SELECT control_state FROM execution_executors WHERE server_id=? AND executor_id=? "
                "AND kind='embedded' AND owner_instance_id=? AND generation=? AND revoked_at IS NULL",
                (self.key.server_id, self.key.executor_id, self.dispatcher.owner_id, self.generation)).fetchone()
            if row is None or not self.dispatcher.repo.owns(uow,
                    owner_id=self.dispatcher.owner_id, epoch=self.dispatcher.epoch,
                    now=self.deps.clock.now_iso()):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                    "The embedded inventory owner is no longer current.", {})
            return claim_inventory_refresh(uow, server_id=self.key.server_id,
                executor_id=self.key.executor_id, producer_instance_id=self.dispatcher.owner_id,
                connection_generation=self.generation)

    def _publish(self, batch, age_ms, delivery_id=None):
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            previous = uow.connection.execute(
                "SELECT publication_sequence FROM execution_inventory_current "
                "WHERE server_id=? AND executor_id=?",
                (self.key.server_id, self.key.executor_id)).fetchone()
        snapshot = local_inventory_snapshot(batch.candidates,
            server_id=self.key.server_id, executor_id=self.key.executor_id,
            producer_instance_id=self.dispatcher.owner_id,
            publication_sequence=previous[0] + 1 if previous else 1,
            observation_age_ms=age_ms, observations=batch.coverage())
        return publish_executor_inventory(self.deps.connection_factory,
            principal=self.key, producer_instance_id=self.dispatcher.owner_id,
            snapshot=snapshot, embedded_owner=(self.dispatcher.owner_id, self.dispatcher.epoch, self.generation),
            refresh_delivery_id=delivery_id)

    async def _run(self):
        if self._stop.is_set():
            return
        self._observer.start()
        last_publication = 0.0
        next_claim = 0.0
        while not self._stop.is_set():
            try:
                if time.monotonic() >= next_claim:
                    await self._claim_pending_refresh()
                    next_claim = time.monotonic() + min(5.0, self.refresh_seconds)
                if self._stop.is_set():
                    break
                batch = self._observer.snapshot()
                delivery = self._delivery if (self._delivery_frontier is not None
                    and self._observer.refresh_complete(self._delivery_frontier)
                    and all(row.state in ('PRESENT', 'ABSENT') and row.observation_age_ms < 120_000
                            for row in batch.observations)) else None
                if batch.revision > 0 and (self.published_batch is None
                        or batch.revision != self.published_batch.revision or delivery is not None
                        or time.monotonic() - last_publication >= self.refresh_seconds):
                    age_ms = max(0, int((time.monotonic() - batch.assembled_at_monotonic) * 1000))
                    publication = await asyncio.to_thread(self._publish, batch, age_ms, delivery)
                    # Only an accepted publication changes selection evidence.
                    self.published_batch = batch
                    self.candidates, self.raw_candidates = batch.candidates, batch.raw_candidates
                    self.publication = publication
                    self.failure = None
                    last_publication = time.monotonic()
                    self.fresh[(self.key.server_id, self.key.executor_id)] = (
                        publication.publication_sequence, batch.assembled_at_monotonic, 0)
                    if delivery is not None:
                        self._delivery = self._delivery_frontier = None
                    self._observation_changed.set()
            except Exception as error:
                self.failure = error
                self._publication_failures += 1
                self.fresh.pop((self.key.server_id, self.key.executor_id), None)
                self._observation_changed.set()
            # Cancelling this observation-only wait does not cancel any worker.
            # Poll durable refresh requests without delaying native discovery.
            try:
                await asyncio.wait_for(self._observer.wait_changed(self._observer.snapshot().revision),
                                       min(1.0, self.refresh_seconds))
            except TimeoutError:
                pass

    def _release(self):
        with self.deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute(
                "UPDATE execution_executors SET control_state='DISCONNECTED' "
                "WHERE server_id=? AND executor_id=? AND owner_instance_id=? AND generation=?",
                (self.key.server_id, self.key.executor_id,
                 self.dispatcher.owner_id, self.generation))

    def begin_shutdown(self):
        self._discovery_stopped.set()
        self._observer.begin_shutdown()
        self._stop.set()
        self._observation_changed.set()

    async def close(self):
        if (self._close_task is not None and self._close_task.done()
                and not self._close_task.cancelled()
                and self._close_task.exception() is not None):
            self._close_task = None
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close(), name="embedded-inventory-close")
        return await asyncio.shield(self._close_task)

    async def _close(self):
        self.begin_shutdown()
        if self._startup_task is not None:
            await asyncio.gather(self._startup_task, return_exceptions=True)
        if self._task is not None:
            await self._task
        await self._observer.aclose()
        if self._refresh_task is not None:
            await asyncio.gather(self._refresh_task, return_exceptions=True)
        await asyncio.gather(*self._refresh_tasks, return_exceptions=True)
        if self._probe_task is not None:
            await asyncio.gather(self._probe_task, return_exceptions=True)
        self.fresh.pop((self.key.server_id, self.key.executor_id), None)
        await asyncio.to_thread(self._release)
