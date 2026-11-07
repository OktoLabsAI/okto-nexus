"""Serve-owned shutdown coordination with a retained administrative lifetime."""
import asyncio
import math
import json
import threading
import time

from nexus_connector_core import ShutdownPolicy

from ..application.runtime_shutdown import shutdown_runtime
from ..errors import ErrorCode, OktoNexusError


class ServerShutdownCoordinator:
    def __init__(self, deps, *, embedded, inventory, host, on_drained=None, on_embedded_report=None, connection_tests=None, handoff_notices=None, handoff_runtime=None, runtime_boot=None, persist_stop=None):
        self.deps = deps
        self.embedded, self.inventory, self.host = embedded, inventory, host
        self.on_drained = on_drained
        self.on_embedded_report = on_embedded_report
        self.connection_tests = connection_tests
        self.handoff_notices = handoff_notices
        self.handoff_runtime = handoff_runtime
        self.runtime_boot = runtime_boot
        self.supervisor = None
        self.deadline = None
        self._task = None
        self._embedded_done = threading.Event()
        self._legacy_resources = []
        self._legacy_done = False
        self._errors = {}
        self.persist_stop = persist_stop
        self._force_requested = False
        self._safety_shutdown = False
        self._closing = False
        self._decision = asyncio.Event()
        self._drain_resources = []
        self._latch_service = True
        self._drain_observer = None

    def status(self):
        resources = list(self._drain_resources) if not self._closing else []
        if self._drain_observer is not None and not self._drain_observer.done():
            resources.append({'owner': 'drain-observer', 'resource_id': 'retained-read',
                              'outcome': 'pending', 'store_retained': True})
        if self._task is not None and self.supervisor is not None and not self.supervisor.drained:
            resources.append({'owner': 'embedded-supervisor', 'resource_id': 'replacement',
                              'outcome': 'pending', 'store_retained': True})
        if self._task is not None and self.runtime_boot is not None and not self.runtime_boot.drained:
            resources.append({'owner': 'runtime-boot', 'resource_id': 'approved-endpoints',
                              'outcome': 'pending', 'store_retained': True})
        if self._task is not None and self.handoff_runtime is not None and not self.handoff_runtime.drained:
            resources.append({'owner': 'handoff-runtime', 'resource_id': 'scheduler',
                              'outcome': 'pending', 'store_retained': True})
        if self._task is not None and self.handoff_notices is not None and not self.handoff_notices.drained:
            resources.append({'owner': 'handoff-notices', 'resource_id': 'notice-writer',
                              'outcome': 'pending', 'store_retained': True})
        if self.embedded is not None:
            resources.extend(dict(resource, owner="embedded",
                server_id=self.embedded.channel.server_id)
                for resource in self.embedded.shutdown_status()["resources"])
        elif not self._embedded_done.is_set():
            resources.extend({"owner": "embedded", "executor_id": key[0],
                "session_id": key[1], "outcome": "unknown", "store_retained": True}
                for key in self.host._runtime_tasks)
        if self._task is not None and not self._legacy_done:
            resources.extend(self._legacy_resources or [
                {"owner": "legacy", "resource_id": "runtime-owner",
                 "outcome": "unknown", "store_retained": True}])
        done = self._task is not None and self._task.done() and not self._task.cancelled()
        error = self._task.exception() if done else None
        state = "RUNNING" if self._task is None else (
            "DRAINED" if done and error is None else "DRAINING_PENDING")
        return {"state": state, "deadline_monotonic": self.deadline,
                "phase": "closing" if self._closing else "waiting" if self._task is not None else "running",
                "force_requested": self._force_requested,
                "safety_shutdown": self._safety_shutdown,
                "force_available": bool(self._task is not None and not done and
                    self.deadline is not None and time.monotonic() >= self.deadline),
                "resources": resources,
                "error_codes": sorted(set(self._errors.values()) |
                    ({"SHUTDOWN_RECOVERY_REQUIRED"} if error else set()))}

    async def request(self, *, timeout_seconds=50.0, force=False):
        if (isinstance(timeout_seconds, bool) or
                not isinstance(timeout_seconds, (int, float)) or
                not math.isfinite(timeout_seconds) or not 0 <= timeout_seconds <= 300):
            raise ValueError("The shutdown timeout must be between 0 and 300 seconds.")
        if type(force) is not bool:
            raise ValueError("The force decision must be a boolean.")
        if force:
            if self._task is None or asyncio.get_running_loop().time() < self.deadline:
                raise OktoNexusError(ErrorCode.CONFLICT,
                    "Observe the existing drain after its deadline before deciding to force shutdown.",
                    {"reason": "DRAIN_DECISION_NOT_AVAILABLE"})
            if self._task.done():
                return self.status()
            self._force_requested = True
            self._decision.set()
        if self._task is None:
            self.deadline = asyncio.get_running_loop().time() + timeout_seconds
            self.deps.runtime_admission_fence.close()
            if self.supervisor is not None:
                self.supervisor.begin_shutdown()
            if self.runtime_boot is not None:
                self.runtime_boot.begin_shutdown()
            if self.handoff_runtime is not None:
                self.handoff_runtime.begin_shutdown()
            if self.connection_tests is not None:
                self.connection_tests.closed = True
            self.host.begin_drain()
            self._task = asyncio.create_task(self._drain_then_close(), name="server-shutdown-recovery")
        await asyncio.wait((self._task,), timeout=max(
            0.0, self.deadline - asyncio.get_running_loop().time()))
        return self.status()

    async def request_safety_shutdown(self, *, timeout_seconds=50.0, latch_service=True):
        """Internal termination/reset keeps the owned containment contract.

        A reviewed database reset closes runtime resources within the same
        process, so it must not persist a service stop. HTTP cannot select this.
        """
        if type(latch_service) is not bool or (not latch_service and self._task is not None and self._latch_service):
            raise ValueError('An existing service stop cannot be changed into a reset.')
        self._latch_service = latch_service
        self._safety_shutdown = True
        self._decision.set()
        return await self.request(timeout_seconds=timeout_seconds)

    def _canonical_pending(self, quiescent_scopes):
        factory = getattr(self.deps, 'connection_factory', None)
        if factory is None:
            return []
        # Remote executors publish on the same channels while the Server waits.
        # A submitted/uncertain operation is not completion or free capacity.
        with factory.unit_of_work(write=False) as uow:
            rows = uow.connection.execute(
                "SELECT p.server_id,p.executor_id,p.operation_id,p.session_id,p.admission_state "
                "FROM execution_operations p LEFT JOIN execution_sessions s "
                "ON s.server_id=p.server_id AND s.executor_id=p.executor_id AND s.session_id=p.session_id "
                "LEFT JOIN execution_executors e ON e.server_id=p.server_id AND e.executor_id=p.executor_id "
                "LEFT JOIN execution_bindings b ON b.server_id=p.server_id AND b.executor_id=p.executor_id "
                "AND b.binding_id=p.binding_id "
                "LEFT JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
                "WHERE p.admission_state<>'RESOLVED_TERMINAL' AND NOT COALESCE((p.admission_state='DISPATCHED' AND ("
                "(s.owner_generation=json_extract(p.expected_revisions_json,'$.session_owner_generation') "
                "AND (s.lifecycle_state='CLOSED' OR (p.action='runtime.open' "
                "AND s.open_operation_id=p.operation_id AND s.lifecycle_state='READY'))) OR "
                "(s.lifecycle_state='READY' AND s.owner_generation=json_extract(p.expected_revisions_json,'$.session_owner_generation') "
                "AND b.binding_revision=json_extract(p.expected_revisions_json,'$.binding_revision') "
                "AND (p.action IN ('approval.decide','input.provide','turn.interrupt') OR "
                "(p.action='turn.steer' AND ep.adapter_id IN ('codex_app_server','pi_rpc'))) "
                "AND NOT EXISTS (SELECT 1 FROM execution_operations t WHERE t.server_id=p.server_id "
                "AND t.executor_id=p.executor_id AND t.session_id=p.session_id "
                "AND t.action IN ('turn.submit','turn.steer') AND t.admission_state<>'RESOLVED_TERMINAL' "
                "AND NOT COALESCE((t.action='turn.steer' AND t.admission_state='DISPATCHED' "
                "AND t.binding_id=b.binding_id AND b.binding_revision=json_extract(t.expected_revisions_json,'$.binding_revision') "
                "AND ep.adapter_id IN ('codex_app_server','pi_rpc')),0)) "
                "AND NOT EXISTS (SELECT 1 FROM execution_native_requests n WHERE n.server_id=p.server_id "
                "AND n.executor_id=p.executor_id AND n.session_id=p.session_id AND n.stream_epoch=s.stream_epoch "
                "AND n.state='PENDING')) OR "
                "(e.kind='embedded' AND EXISTS (SELECT 1 FROM json_each(?) q "
                "WHERE json_extract(q.value,'$[0]')=p.server_id AND json_extract(q.value,'$[1]')=p.executor_id "
                "AND json_extract(q.value,'$[2]')=p.session_id)))),0) "
                "ORDER BY p.server_id,p.executor_id,p.operation_id LIMIT 129",
                (json.dumps(quiescent_scopes),)).fetchall()
        resources = [dict(row, owner='canonical-operation', outcome='pending', store_retained=True)
                for row in rows]
        if len(rows) == 129:
            resources.append({'owner': 'canonical-operation', 'reason': 'DRAIN_INVENTORY_TRUNCATED',
                              'outcome': 'unknown', 'store_retained': True})
        return resources

    async def _observe_drain(self):
        resources = []
        for name, owner in (('embedded-supervisor', self.supervisor), ('runtime-boot', self.runtime_boot),
                            ('handoff-runtime', self.handoff_runtime)):
            if owner is not None and not owner.drained:
                resources.append({'owner': name, 'outcome': 'pending', 'store_retained': True})
        if self.connection_tests is not None:
            resources.extend({'owner': 'connection-test', 'resource_id': key,
                              'outcome': 'pending', 'store_retained': True}
                             for key, entry in self.connection_tests.tests.items() if not entry['task'].done())
        legacy = getattr(self.deps, 'harness_supervisor', None)
        if legacy is not None:
            resources.extend(legacy.drain_status()['resources'])
        if self.embedded is not None:
            resources.extend({'owner': 'embedded-producer', 'outcome': 'pending', 'store_retained': True}
                             for task in tuple(self.embedded.workers) if not task.done())
        report = await self.host.drain_status()
        resources.extend(report['resources'])
        resources.extend(await asyncio.to_thread(self._canonical_pending, report.get('quiescent_scopes', [])))
        revision = getattr(self.host, 'drain_revision', None)
        if callable(revision) and revision() != report.get('activity_revision'):
            resources.append({'owner': 'embedded-core', 'reason': 'DRAIN_OBSERVATION_CHANGED',
                              'outcome': 'unknown', 'store_retained': True})
        # A permitted decision may have arrived during Core/SQLite observation.
        # Recheck owned producers after the last await, before closing controls.
        if self.embedded is not None and any(not task.done() for task in tuple(self.embedded.workers)):
            resources.append({'owner': 'embedded-producer', 'outcome': 'pending', 'store_retained': True})
        self._drain_resources = resources
        return report['quiescent'] is True and not resources

    async def _drain_then_close(self):
        latched = self.persist_stop is None or not self._latch_service
        while True:
            try:
                if not latched:
                    await self.persist_stop()
                    latched = True
                if self._safety_shutdown or self._force_requested:
                    break
                if self._drain_observer is None:
                    self._drain_observer = asyncio.create_task(self._observe_drain(), name='server-drain-observation')
                # One retained observation may wait on SQLite/Core. The owner
                # remains responsive to a force decision without abandoning it.
                await asyncio.wait((self._drain_observer,), timeout=.05)
                if self._drain_observer.done():
                    observer, self._drain_observer = self._drain_observer, None
                    if observer.result():
                        break
                self._errors.pop('drain', None)
            except Exception:
                self._errors['drain'] = 'DRAIN_OBSERVATION_UNAVAILABLE'
                if self._safety_shutdown:
                    break  # An external ending cannot wait for supervisor storage.
            try:
                await asyncio.wait_for(self._decision.wait(), .1)
            except TimeoutError:
                pass
            self._decision.clear()
        self._closing = True
        self._drain_resources = []
        if self.handoff_notices is not None:
            self.handoff_notices.begin_shutdown()
        if self.inventory is not None:
            self.inventory.begin_shutdown()
        await self._run()
        if self._drain_observer is not None:
            try:
                await asyncio.shield(self._drain_observer)
            except Exception:
                self._errors['drain'] = 'DRAIN_OBSERVATION_UNAVAILABLE'
        if self.on_drained is not None:
            self.on_drained()

    async def wait(self):
        if self._task is None:
            raise RuntimeError("Shutdown has not been requested.")
        await asyncio.shield(self._task)

    async def _embedded(self):
        while True:
            try:
                if self.embedded is not None:
                    report = await self.embedded.request_shutdown(timeout_seconds=max(
                        0.0, self.deadline - asyncio.get_running_loop().time()))
                    if self.on_embedded_report is not None:
                        self.on_embedded_report(report)
                    await self.embedded.wait_shutdown()
                    if self.on_embedded_report is not None:
                        self.on_embedded_report(self.embedded.shutdown_status())
                else:
                    await self.host.shutdown(ShutdownPolicy(0, 0), close_stores=False)
                    await self.host.shutdown(ShutdownPolicy(0, 0))
                    if self.host._runtime_tasks:
                        await asyncio.sleep(.1)
                        continue
                if self.inventory is not None:
                    await self.inventory.close()
                self._errors.pop("embedded", None)
                self._embedded_done.set()
                dispatcher = getattr(self.deps, "runtime_dispatcher", None)
                if dispatcher is not None:
                    dispatcher.wake()
                return
            except Exception:
                self._errors["embedded"] = "EMBEDDED_SHUTDOWN_RECOVERY_REQUIRED"
                await asyncio.sleep(.1)

    async def _legacy(self):
        dispatcher = getattr(self.deps, "runtime_dispatcher", None)
        supervisor = getattr(self.deps, "harness_supervisor", None)
        if dispatcher is None or dispatcher.epoch is None or supervisor is None:
            self._legacy_done = True
            return
        def attempt(timeout):
            if not self._legacy_resources:
                self._legacy_resources = [
                    {"owner": "legacy", "session_id": session.session_id,
                     "outcome": "unknown", "store_retained": True}
                    for session in supervisor.list_live()]
            return shutdown_runtime(dispatcher, supervisor, timeout=timeout,
                extra_drained=lambda: self._embedded_done.is_set() and
                    (self._drain_observer is None or self._drain_observer.done()) and
                    (self.handoff_notices is None or self.handoff_notices.drained) and
                    (self.handoff_runtime is None or self.handoff_runtime.drained) and
                    (self.runtime_boot is None or self.runtime_boot.drained))
        while not dispatcher._shutdown_finished.is_set():
            try:
                await asyncio.to_thread(attempt, max(
                    0.0, self.deadline - asyncio.get_running_loop().time()))
                self._errors.pop("legacy", None)
            except Exception:
                self._errors["legacy"] = "LEGACY_SHUTDOWN_RECOVERY_REQUIRED"
            if not dispatcher._shutdown_finished.is_set():
                await asyncio.sleep(.1)
        self._errors.pop("legacy", None)
        self._legacy_done = True

    async def _run(self):
        # A replacement can already be joining the previous native producers.
        # Fence replacement synchronously in request(), then join it before
        # reading the current bundle or releasing the exclusive store owner.
        if self.supervisor is not None:
            await self.supervisor.aclose()
        # Legacy release is gated by embedded completion, but neither native
        # containment path waits for the other owner's storage/native calls.
        if self.connection_tests is not None:
            await self.connection_tests.shutdown()
        async def notices():
            if self.handoff_notices is not None:
                await self.handoff_notices.aclose()
                dispatcher = getattr(self.deps, 'runtime_dispatcher', None)
                if dispatcher is not None:
                    dispatcher.wake()
        async def handoffs():
            if self.handoff_runtime is not None:
                await self.handoff_runtime.aclose()
                dispatcher = getattr(self.deps, 'runtime_dispatcher', None)
                if dispatcher is not None:
                    dispatcher.wake()
        async def boot():
            if self.runtime_boot is not None:
                await self.runtime_boot.aclose()
                dispatcher = getattr(self.deps, 'runtime_dispatcher', None)
                if dispatcher is not None:
                    dispatcher.wake()
        await asyncio.gather(self._embedded(), self._legacy(), notices(), handoffs(), boot())
