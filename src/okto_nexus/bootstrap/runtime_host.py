"""Owner-scoped composition of the embedded Core runtime.

The HTTP server may acquire a runtime only after an installation and workspace
root have been selected and authorized. Passive catalog and inventory reads do
not construct a runtime or open a journal.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from nexus_connector_core import (
    InstallationCandidate, RuntimeCore, SQLiteOwnedSlotLedger,
    ShutdownPolicy, create_runtime, ExecutionCapacity, CoreError,
)
from nexus_connector_core.journal import SQLiteJournal, open_journal
from nexus_connector_core.models import PreparedLaunch, ProcessBirthRecord, SessionKey


class EmbeddedRuntimeHost:
    """Own one journal/runtime per session and one slot ledger per Server.

    Concurrent callers for a session share one initialization task. A
    cancelled waiter cannot cancel that task and strand an opened SQLite
    worker. A changed candidate/root map requires explicit owner shutdown;
    silently reusing a runtime would execute against the old selection.
    """

    def __init__(self, store_dir: Path, *, max_owned_slots: int = 64, capacity_enabled: bool = False):
        store_dir = Path(store_dir)
        if not store_dir.is_absolute():
            raise ValueError("The embedded Core store directory must be absolute.")
        if type(max_owned_slots) is not int or max_owned_slots <= 0:
            raise ValueError("The embedded Core slot limit must be positive.")
        self.store_dir = store_dir
        self.max_owned_slots = max_owned_slots
        if type(capacity_enabled) is not bool:
            raise ValueError('Capacity support must be a boolean.')
        self.capacity_enabled = capacity_enabled
        self._capacity_services = {}
        self._capacity_gate = asyncio.Lock()
        self._lock = asyncio.Lock()
        self._ledger_task: asyncio.Task[SQLiteOwnedSlotLedger] | None = None
        self._runtime_tasks: dict[tuple[str, str], asyncio.Task[
            tuple[RuntimeCore, SQLiteJournal]]] = {}
        self._selections: dict[tuple[str, str], tuple[dict, dict, object, bool, str]] = {}
        self._closing = False
        self._draining = False
        self._history_closing = False
        self._native_action_owners = {}
        self.local_launch_factory = None
        self._history_tasks = set()
        self._released_compositions = set()
        self._drain_observations = {}

    def begin_drain(self):
        """Fence new composition while controls keep their existing runtime."""
        self._draining = True
        for task in tuple(self._runtime_tasks.values()):
            if task.done() and not task.cancelled() and task.exception() is None:
                begin = getattr(task.result()[0], 'begin_drain', None)
                if callable(begin):
                    begin()

    @property
    def draining(self):
        return self._draining

    def drain_revision(self):
        """Memory-only fence against stale proofs across host/SQLite awaits."""
        values = []
        for key, task in self._runtime_tasks.items():
            value = None
            if task.done() and not task.cancelled() and task.exception() is None:
                revision = getattr(task.result()[0], 'drain_revision', None)
                if callable(revision):
                    value = revision()
            values.append((key, id(task), value))
        return self._draining, self._closing, tuple(sorted(values))

    async def drain_status(self):
        resources = []
        quiescent_scopes = []
        observed = {}
        for key, task in tuple(self._runtime_tasks.items()):
            reason = None
            if not task.done() or task.cancelled():
                reason = 'COMPOSITION_PENDING'
            elif task.exception() is not None:
                if key not in self._released_compositions:
                    reason = 'COMPOSITION_UNKNOWN'
            else:
                runtime = task.result()[0]
                status = getattr(runtime, 'drain_status', None)
                if (not callable(status) or not callable(getattr(runtime, 'begin_drain', None))
                        or not callable(getattr(runtime, 'drain_revision', None))):
                    reason = 'DRAIN_PROTOCOL_UNAVAILABLE'
                else:
                    runtime.begin_drain()
                    observation = self._drain_observations.get(key)
                    if observation is None:
                        observation = asyncio.create_task(status(), name='embedded-drain-observation')
                        self._drain_observations[key] = observation
                        self._history_tasks.add(observation)
                        observation.add_done_callback(self._history_tasks.discard)
                    # Keep one owned observation across caller cancellation and
                    # timeouts. A slow native read cannot create another reader.
                    await asyncio.wait((observation,), timeout=.01)
                    if not observation.done():
                        reason = 'DRAIN_OBSERVATION_PENDING'
                    else:
                        self._drain_observations.pop(key, None)
                        try:
                            report = observation.result()
                            observed[key] = report.get('activity_revision')
                            if (report.get('state') != 'QUIESCENT' or report.get('quiescent') is not True
                                    or report.get('resources')):
                                reason = 'CORE_' + str(report.get('state', 'UNKNOWN'))
                                resources.extend(dict(row, owner='embedded-core', executor_id=key[0],
                                    session_id=key[1], store_retained=True) for row in report.get('resources', ()))
                            elif (report.get('activity_revision') is not None and
                                  report['activity_revision'] == runtime.drain_revision() and key in self._selections):
                                quiescent_scopes.append([self._selections[key][4], key[0], key[1]])
                            else:
                                reason = 'DRAIN_OBSERVATION_CHANGED'
                        except Exception:
                            reason = 'DRAIN_OBSERVATION_UNKNOWN'
            if reason:
                resources.append({'owner': 'embedded-core', 'executor_id': key[0],
                    'session_id': key[1], 'reason': reason, 'outcome': 'pending', 'store_retained': True})
        revision = self.drain_revision()
        if any(value != observed.get(key) for key, _task, value in revision[2]):
            resources.append({'owner': 'embedded-core', 'reason': 'DRAIN_OBSERVATION_CHANGED',
                              'outcome': 'unknown', 'store_retained': True})
        return {'state': 'QUIESCENT' if self._draining and not resources else 'UNKNOWN',
                'quiescent': self._draining and not resources, 'resources': resources,
                'quiescent_scopes': quiescent_scopes, 'activity_revision': revision}

    def _journal_path(self, executor_id, session_id):
        digest = hashlib.sha256((executor_id + "\0" + session_id).encode("ascii")).hexdigest()
        return self.store_dir / f"session-{digest}.db"

    async def historical_receipt(self, *, session_id, key):
        """Read retained Core history without constructing or authorizing a runtime."""
        async def read(journal):
            return await journal.get_receipt(key)
        return await self.with_history(executor_id=key.executor_id,session_id=session_id,read=read)

    async def read_existing_process_birth(
        self, *, server_id: str, executor_id: str, session_id: str,
    ) -> ProcessBirthRecord | None:
        """Read historical birth proof only from an already composed runtime.

        The caller must authenticate and validate the current dispatch/session
        fences separately. This method neither proves liveness nor grants work
        authority. It never waits for composition or opens a missing journal.
        An admitted reader survives caller cancellation; final host shutdown
        joins it before closing its journal.
        """
        for value in (server_id, executor_id, session_id):
            if (type(value) is not str or not 1 <= len(value) <= 160 or
                    not all(char.isascii() and (char.isalnum() or char in "_-") for char in value)):
                raise ValueError("Invalid process birth selection.")
        loop = asyncio.get_running_loop()
        key = (executor_id, session_id)
        # Check the stable task's owning loop before waiting on an asyncio.Lock
        # which may already be contended/bound to that other loop. Repeat under
        # the lock below; this early read never grants access to the runtime.
        existing = self._runtime_tasks.get(key)
        if existing is not None and existing.get_loop() is not loop:
            raise CoreError('SCOPE_MISMATCH', 'embedded_process_birth')
        async with self._lock:
            if self._closing or self._history_closing:
                raise CoreError('RUNTIME_DRAINING', 'embedded_process_birth')
            runtime_task = self._runtime_tasks.get(key)
            if (runtime_task is None or not runtime_task.done() or runtime_task.cancelled()
                    or runtime_task.exception() is not None):
                raise CoreError('SESSION_UNKNOWN', 'embedded_process_birth')
            selection = self._selections.get(key)
            if runtime_task.get_loop() is not loop or selection is None or selection[4] != server_id:
                raise CoreError('SCOPE_MISMATCH', 'embedded_process_birth')
            runtime, _journal = runtime_task.result()
            task = asyncio.create_task(runtime.process_birth(SessionKey(server_id, executor_id, session_id)))
            self._history_tasks.add(task)

            def release(done):
                self._history_tasks.discard(done)
                # A cancelled observer must not leave an unobserved task error.
                # Retrieving it does not change what an awaiting caller receives.
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(release)
        return await asyncio.shield(task)

    async def with_history(self, *, executor_id, session_id, read):
        """Retain a journal reader through observer cancellation and shutdown."""
        async with self._lock:
            if self._history_closing:
                raise RuntimeError("The embedded Core host is shutting down.")
            task = asyncio.create_task(self._read_history(executor_id, session_id, read))
            self._history_tasks.add(task)
            task.add_done_callback(self._history_tasks.discard)
        return await asyncio.shield(task)

    async def _read_history(self, executor_id, session_id, read):
        runtime_task = self._runtime_tasks.get((executor_id,session_id))
        if runtime_task is not None:
            _, journal = await asyncio.shield(runtime_task)
            return await read(journal)
        path = self._journal_path(executor_id, session_id)
        if not await asyncio.to_thread(path.is_file):
            raise FileNotFoundError("The retained Core journal is unavailable.")
        journal = await open_journal(path)
        try:
            return await read(journal)
        finally:
            await journal.aclose()

    async def _ledger(self) -> SQLiteOwnedSlotLedger:
        async with self._lock:
            # A delayed composition must not create a worker after the final
            # shutdown pass captured the stores it is responsible for closing.
            if self._history_closing:
                raise CoreError('RUNTIME_DRAINING', 'embedded_store_owner', retry_safe=True)
            if self._ledger_task is None:
                self._ledger_task = asyncio.create_task(self._open_ledger())
            task = self._ledger_task
        return await asyncio.shield(task)

    async def _open_ledger(self) -> SQLiteOwnedSlotLedger:
        await asyncio.to_thread(self.store_dir.mkdir, parents=True, exist_ok=True)
        return await asyncio.to_thread(
            SQLiteOwnedSlotLedger, self.store_dir / "owned-slots.db",
            max_slots=self.max_owned_slots,
        )

    def _runtime_for_capacity(self, session):
        task = self._runtime_tasks.get((session.executor_id, session.session_id))
        if task is None or not task.done() or task.cancelled() or task.exception() is not None:
            return None
        return task.result()[0]

    async def capacity_service(self, *, server_id, executor_id, boot_id, authority, clock=None):
        """Compose the shared public Core port without creating a harness.

        The dispatch owner supplies its current authority checks. A new owner
        fences the previous observer; outstanding durable reservations remain
        recoverable under their original immutable requests.
        """
        if not self.capacity_enabled:
            raise CoreError('CAPACITY_PROTOCOL_UNSUPPORTED', 'embedded_capacity')
        ledger = await self._ledger()
        key = (server_id, executor_id)
        async with self._capacity_gate:
            if self._closing:
                raise CoreError('RECOVERING', 'embedded_capacity')
            prior = self._capacity_services.get(key)
            if prior and prior[0].boot_id == boot_id:
                if prior[1] is not authority:
                    raise CoreError('RESERVATION_CONFLICT', 'embedded_capacity_owner')
                return prior[0]
            service = ExecutionCapacity(ledger, authority=authority, boot_id=boot_id, clock=clock,
                namespace=key, runtime_lookup=self._runtime_for_capacity)
            self._capacity_services[key] = (service, authority)
        # Retiring a slow observer must not hold the composition gate for
        # unrelated executor namespaces. aclose fences it before its first wait.
        if prior:
            await prior[0].aclose()
        return service

    async def acquire(
        self, *, server_id: str, executor_id: str, session_id: str,
        candidates: Mapping[str, InstallationCandidate],
        workspace_roots: Mapping[str, str],
        environment: Callable[[PreparedLaunch], Awaitable[Mapping[str, str]]],
        native_factory=None, native_action_factory=None, native_approvals_enabled=False,
    ) -> RuntimeCore:
        for value, label in ((server_id, "server"), (executor_id, "executor"), (session_id, "session")):
            if (not isinstance(value, str) or not value or len(value) > 160 or
                    not all(char.isascii() and (char.isalnum() or char in "_-")
                            for char in value)):
                raise ValueError(f"Invalid {label} ID.")
        # Core validates the typed values as well. The host must reject empty
        # maps before opening durable stores, especially on passive startup.
        if not candidates or not workspace_roots or not callable(environment):
            raise ValueError("A selected installation, root and environment are required.")
        if native_action_factory is not None and (
                not callable(native_action_factory) or set(candidates) != {"pi_rpc"}):
            raise ValueError("A native action factory requires one approved Pi installation.")
        if type(native_approvals_enabled) is not bool:
            raise ValueError("Native approval capture must be a boolean.")
        selection = (dict(candidates), dict(workspace_roots), native_action_factory, native_approvals_enabled, server_id)
        key = (executor_id, session_id)
        async with self._lock:
            if self._closing:
                raise RuntimeError("The embedded Core host is shutting down.")
            if key in self._selections and self._selections[key] != selection:
                raise RuntimeError("The selected installation or root changed.")
            task = self._runtime_tasks.get(key)
            if task is None:
                if self._draining:
                    raise CoreError('RUNTIME_DRAINING', 'embedded_composition', retry_safe=True)
                self._selections[key] = selection
                task = asyncio.create_task(self._compose(
                    key, selection, environment, native_factory))
                self._runtime_tasks[key] = task
        runtime, _journal = await asyncio.shield(task)
        return runtime

    async def _compose(self, key, selection, environment, native_factory):
        journal: SQLiteJournal | None = None
        try:
            ledger = await self._ledger()
            from nexus_connector_core import JournalLocation, SessionKey
            await ledger.register_journal_locations((JournalLocation(
                self._journal_path(*key).name, SessionKey(selection[4], *key)),))
            await asyncio.to_thread(self.store_dir.mkdir, parents=True, exist_ok=True)
            journal = await open_journal(self._journal_path(*key))
            native_owner = None
            async def native_launch(prepared, session_id, context):
                if native_owner is None:
                    raise RuntimeError("The native action owner is unavailable.")
                return await native_owner.launch(prepared, session_id, context)
            runtime = create_runtime(
                journal=journal, environment=environment,
                candidates=selection[0], workspace_roots=selection[1],
                owned_slot_ledger=ledger, native_factory=native_factory,
                max_owned_sessions=self.max_owned_slots,
                capacity_enabled=self.capacity_enabled,
                pi_native_action=native_launch if selection[2] is not None else None,
                native_approvals_enabled=selection[3],
            )
            if selection[2] is not None:
                from nexus_connector_core.native_action_socket import PiNativeActionOwner
                native_owner = selection[2](runtime)
                if not isinstance(native_owner, PiNativeActionOwner):
                    raise ValueError("The native action factory must return an owned Pi ingress.")
                self._native_action_owners[key] = native_owner
            if self._draining:
                begin = getattr(runtime, 'begin_drain', None)
                if callable(begin):
                    begin()
            return runtime, journal
        except BaseException:
            if journal is not None:
                await journal.aclose()
            self._released_compositions.add(key)
            raise

    async def close_native_actions(self, *, executor_id, session_id, timeout_seconds=0):
        owner = self._native_action_owners.get((executor_id, session_id))
        return owner is None or await owner.close(timeout_seconds=timeout_seconds)

    async def operation_receipt(self, *, session_id, key):
        """Read the host-owned journal without creating a runtime or replaying work."""
        task = self._runtime_tasks.get((key.executor_id, session_id))
        if task is None:
            return None
        _, journal = await asyncio.shield(task)
        return await journal.get_receipt(key)

    def shutdown_resources(self):
        resources = []
        for (executor_id, session_id), task in sorted(self._runtime_tasks.items()):
            resource = {"executor_id": executor_id, "session_id": session_id,
                        "outcome": "unknown", "store_retained": True,
                        "process_state": "UNKNOWN", "core_release_pending": True}
            if task.done() and not task.cancelled() and task.exception() is None:
                runtime, _ = task.result()
                for key, facts in runtime.shutdown_resources().items():
                    if key.executor_id == executor_id and key.session_id == session_id:
                        resource.update(process_state=facts["process_state"],
                                        core_release_pending=facts["release_pending"])
            resources.append(resource)
        return resources

    async def shutdown(self, policy: ShutdownPolicy | None = None,
                       *, close_stores: bool = True
                       ) -> dict[tuple[str, str], object]:
        """Contain immediately; close stores only after their producers have joined.

        Dispatch owners use close_stores=False while publication/history work
        is still active, then call again after joining those producers.
        """
        if type(close_stores) is not bool:
            raise ValueError("Store closure must be a boolean.")
        async with self._lock:
            self._closing = True
            # Containment leaves journals available for final publication.
            # The store-closing pass fences new readers before joining them.
            self._history_closing |= close_stores
            tasks = dict(self._runtime_tasks)
            ledger_task = self._ledger_task
            history_tasks = tuple(self._history_tasks)
        await asyncio.gather(*(service.aclose() for service, _ in self._capacity_services.values()))
        # Canceled observers cannot abandon an open history journal.
        if close_stores:
            await asyncio.gather(*history_tasks, return_exceptions=True)
        reports: dict[tuple[str, str], object] = {}
        uncertain = False

        async def stop_one(key, task):
            try:
                runtime, journal = await asyncio.shield(task)
            except Exception:
                # Only discard an initialization after its journal cleanup
                # completed. A failed cleanup still retains uncertain ownership.
                released = key in self._released_compositions
                if released:
                    self._runtime_tasks.pop(key, None)
                    self._selections.pop(key, None)
                    self._released_compositions.discard(key)
                return key, None, not released
            owner = self._native_action_owners.get(key)
            if owner is not None:
                await owner.close(timeout_seconds=0)
            report = await runtime.shutdown(policy or ShutdownPolicy())
            if owner is not None and not await owner.close(timeout_seconds=0):
                if owner.session_key is None:
                    raise RuntimeError("Native action ownership is still pending.")
                report = replace(report, session_outcomes={
                    **report.session_outcomes, owner.session_key: "unknown"})
            if "unknown" in report.session_outcomes.values():
                return key, report, True
            if not close_stores:
                return key, report, False
            # Core does not own host-supplied journals. Close only after its
            # public shutdown reports no uncertain session ownership.
            await journal.aclose()
            self._native_action_owners.pop(key, None)
            self._runtime_tasks.pop(key, None)
            self._selections.pop(key, None)
            return key, report, False

        # A Server can own many independent sessions. Drain them concurrently
        # so the shutdown budget does not multiply by the session count.
        stopped = await asyncio.gather(
            *(stop_one(key, task) for key, task in tasks.items()),
            return_exceptions=True,
        )
        failures = []
        for result in stopped:
            if isinstance(result, BaseException):
                uncertain = True
                failures.append(result)
                continue
            key, report, unresolved = result
            uncertain |= unresolved
            if report is not None:
                reports[key] = report
        if close_stores and ledger_task is not None and not uncertain:
            try:
                ledger = await asyncio.shield(ledger_task)
            except Exception:
                pass
            else:
                await ledger.aclose()
        if failures:
            raise failures[0]
        return reports
