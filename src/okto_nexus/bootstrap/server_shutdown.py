"""Serve-owned shutdown coordination with a retained administrative lifetime."""
import asyncio
import math
import threading

from nexus_connector_core import ShutdownPolicy

from ..application.runtime_shutdown import shutdown_runtime


class ServerShutdownCoordinator:
    def __init__(self, deps, *, embedded, inventory, host, on_drained=None, on_embedded_report=None, connection_tests=None):
        self.deps = deps
        self.embedded, self.inventory, self.host = embedded, inventory, host
        self.on_drained = on_drained
        self.on_embedded_report = on_embedded_report
        self.connection_tests = connection_tests
        self.deadline = None
        self._task = None
        self._embedded_done = threading.Event()
        self._legacy_resources = []
        self._legacy_done = False
        self._errors = {}

    def status(self):
        resources = []
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
                "resources": resources,
                "error_codes": sorted(set(self._errors.values()) |
                    ({"SHUTDOWN_RECOVERY_REQUIRED"} if error else set()))}

    async def request(self, *, timeout_seconds=50.0):
        if (isinstance(timeout_seconds, bool) or
                not isinstance(timeout_seconds, (int, float)) or
                not math.isfinite(timeout_seconds) or not 0 <= timeout_seconds <= 300):
            raise ValueError("The shutdown timeout must be between 0 and 300 seconds.")
        if self._task is None:
            self.deadline = asyncio.get_running_loop().time() + timeout_seconds
            self.deps.runtime_admission_fence.close()
            if self.inventory is not None:
                self.inventory.begin_shutdown()
            self._task = asyncio.create_task(self._run(), name="server-shutdown-recovery")
        await asyncio.wait((self._task,), timeout=max(
            0.0, self.deadline - asyncio.get_running_loop().time()))
        return self.status()

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
                extra_drained=self._embedded_done.is_set)
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
        # Legacy release is gated by embedded completion, but neither native
        # containment path waits for the other owner's storage/native calls.
        if self.connection_tests is not None:
            await self.connection_tests.shutdown()
        await asyncio.gather(self._embedded(), self._legacy())
        if self.on_drained is not None:
            self.on_drained()
