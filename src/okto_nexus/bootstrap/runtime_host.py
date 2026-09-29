"""Owner-scoped composition of the embedded Core runtime.

The HTTP server may acquire a runtime only after an installation and workspace
root have been selected and authorized. Passive catalog and inventory reads do
not construct a runtime or open a journal.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from nexus_connector_core import (
    InstallationCandidate, RuntimeCore, SQLiteOwnedSlotLedger,
    ShutdownPolicy, create_runtime,
)
from nexus_connector_core.journal import SQLiteJournal, open_journal
from nexus_connector_core.models import PreparedLaunch


class EmbeddedRuntimeHost:
    """Own one journal/runtime per executor and one slot ledger per Server.

    Concurrent callers for an executor share one initialization task. A
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
        self._runtime_tasks: dict[str, asyncio.Task[tuple[RuntimeCore, SQLiteJournal]]] = {}
        self._selections: dict[str, tuple[dict, dict]] = {}
        self._closing = False

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
        self, *, executor_id: str,
        candidates: Mapping[str, InstallationCandidate],
        workspace_roots: Mapping[str, str],
        environment: Callable[[PreparedLaunch], Awaitable[Mapping[str, str]]],
        native_factory=None,
    ) -> RuntimeCore:
        if not isinstance(executor_id, str) or not executor_id or not all(
            char.isascii() and (char.isalnum() or char in "_-") for char in executor_id
        ) or len(executor_id) > 128:
            raise ValueError("Invalid executor ID.")
        # Core validates the typed values as well. The host must reject empty
        # maps before opening durable stores, especially on passive startup.
        if not candidates or not workspace_roots or not callable(environment):
            raise ValueError("A selected installation, root and environment are required.")
        selection = (dict(candidates), dict(workspace_roots))
        async with self._lock:
            if self._closing:
                raise RuntimeError("The embedded Core host is shutting down.")
            if executor_id in self._selections and self._selections[executor_id] != selection:
                raise RuntimeError("The selected installation or root changed.")
            task = self._runtime_tasks.get(executor_id)
            if task is None:
                self._selections[executor_id] = selection
                task = asyncio.create_task(self._compose(
                    executor_id, selection, environment, native_factory))
                self._runtime_tasks[executor_id] = task
        runtime, _journal = await asyncio.shield(task)
        return runtime

    async def _compose(self, executor_id, selection, environment, native_factory):
        ledger = await self._ledger()
        journal: SQLiteJournal | None = None
        try:
            await asyncio.to_thread(self.store_dir.mkdir, parents=True, exist_ok=True)
            journal = await open_journal(self.store_dir / f"{executor_id}.db")
            runtime = create_runtime(
                journal=journal, environment=environment,
                candidates=selection[0], workspace_roots=selection[1],
                owned_slot_ledger=ledger, native_factory=native_factory,
                max_owned_sessions=self.max_owned_slots,
            )
            return runtime, journal
        except BaseException:
            if journal is not None:
                await journal.aclose()
            raise

    async def shutdown(self, policy: ShutdownPolicy | None = None) -> dict[str, object]:
        """Drain Core before closing its stores; retain uncertain ownership."""
        async with self._lock:
            self._closing = True
            tasks = dict(self._runtime_tasks)
            ledger_task = self._ledger_task
        reports: dict[str, object] = {}
        uncertain = False
        for executor_id, task in tasks.items():
            try:
                runtime, journal = await asyncio.shield(task)
            except Exception:
                continue  # _compose already closed its journal on failure.
            report = await runtime.shutdown(policy or ShutdownPolicy())
            reports[executor_id] = report
            if "unknown" in report.session_outcomes.values():
                uncertain = True
                continue
            # Core does not own host-supplied journals. Close only after its
            # public shutdown reports no uncertain session ownership.
            await journal.aclose()
        if ledger_task is not None and not uncertain:
            try:
                ledger = await asyncio.shield(ledger_task)
            except Exception:
                pass
            else:
                await ledger.aclose()
        return reports
