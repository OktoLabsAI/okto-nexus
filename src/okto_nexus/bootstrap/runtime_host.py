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
    ShutdownPolicy, create_runtime,
)
from nexus_connector_core.journal import SQLiteJournal, open_journal
from nexus_connector_core.models import PreparedLaunch


class EmbeddedRuntimeHost:
    """Own one journal/runtime per session and one slot ledger per Server.

    Concurrent callers for a session share one initialization task. A
    cancelled waiter cannot cancel that task and strand an opened SQLite
    worker. A changed candidate/root map requires explicit owner shutdown;
    silently reusing a runtime would execute against the old selection.
    """

    def __init__(self, store_dir: Path, *, max_owned_slots: int = 8):
        store_dir = Path(store_dir)
        if not store_dir.is_absolute():
            raise ValueError("The embedded Core store directory must be absolute.")
        if type(max_owned_slots) is not int or max_owned_slots <= 0:
            raise ValueError("The embedded Core slot limit must be positive.")
        self.store_dir = store_dir
        self.max_owned_slots = max_owned_slots
        self._lock = asyncio.Lock()
        self._ledger_task: asyncio.Task[SQLiteOwnedSlotLedger] | None = None
        self._runtime_tasks: dict[tuple[str, str], asyncio.Task[
            tuple[RuntimeCore, SQLiteJournal]]] = {}
        self._selections: dict[tuple[str, str], tuple[dict, dict, object]] = {}
        self._closing = False
        self._native_action_owners = {}
        self.local_launch_factory = None

    async def _ledger(self) -> SQLiteOwnedSlotLedger:
        async with self._lock:
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

    async def acquire(
        self, *, executor_id: str, session_id: str,
        candidates: Mapping[str, InstallationCandidate],
        workspace_roots: Mapping[str, str],
        environment: Callable[[PreparedLaunch], Awaitable[Mapping[str, str]]],
        native_factory=None, native_action_factory=None,
    ) -> RuntimeCore:
        for value, label in ((executor_id, "executor"), (session_id, "session")):
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
        selection = (dict(candidates), dict(workspace_roots), native_action_factory)
        key = (executor_id, session_id)
        async with self._lock:
            if self._closing:
                raise RuntimeError("The embedded Core host is shutting down.")
            if key in self._selections and self._selections[key] != selection:
                raise RuntimeError("The selected installation or root changed.")
            task = self._runtime_tasks.get(key)
            if task is None:
                self._selections[key] = selection
                task = asyncio.create_task(self._compose(
                    key, selection, environment, native_factory))
                self._runtime_tasks[key] = task
        runtime, _journal = await asyncio.shield(task)
        return runtime

    async def _compose(self, key, selection, environment, native_factory):
        ledger = await self._ledger()
        journal: SQLiteJournal | None = None
        try:
            await asyncio.to_thread(self.store_dir.mkdir, parents=True, exist_ok=True)
            digest = hashlib.sha256(
                (key[0] + "\0" + key[1]).encode("ascii")).hexdigest()
            journal = await open_journal(self.store_dir / f"session-{digest}.db")
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
                pi_native_action=native_launch if selection[2] is not None else None,
            )
            if selection[2] is not None:
                from nexus_connector_core.native_action_socket import PiNativeActionOwner
                native_owner = selection[2](runtime)
                if not isinstance(native_owner, PiNativeActionOwner):
                    raise ValueError("The native action factory must return an owned Pi ingress.")
                self._native_action_owners[key] = native_owner
            return runtime, journal
        except BaseException:
            if journal is not None:
                await journal.aclose()
            raise

    async def close_native_actions(self, *, executor_id, session_id, timeout_seconds=0):
        owner = self._native_action_owners.get((executor_id, session_id))
        return owner is None or await owner.close(timeout_seconds=timeout_seconds)

    async def shutdown(self, policy: ShutdownPolicy | None = None
                       ) -> dict[tuple[str, str], object]:
        """Drain Core before closing its stores; retain uncertain ownership."""
        async with self._lock:
            self._closing = True
            tasks = dict(self._runtime_tasks)
            ledger_task = self._ledger_task
        reports: dict[tuple[str, str], object] = {}
        uncertain = False

        async def stop_one(key, task):
            try:
                runtime, journal = await asyncio.shield(task)
            except Exception:
                return key, None, False  # _compose closed its failed journal.
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
        if ledger_task is not None and not uncertain:
            try:
                ledger = await asyncio.shield(ledger_task)
            except Exception:
                pass
            else:
                await ledger.aclose()
        if failures:
            raise failures[0]
        return reports
