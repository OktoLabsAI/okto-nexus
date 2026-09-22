"""Bounded startup cancellation, contract v1; resources are owned explicitly.

Cancellation stops owned resources; it does not claim that a native turn ended.
Adapters register callbacks immediately after creating an owned resource. Attach
adapters must never register the external operator's process.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import threading


current_lifecycle = ContextVar("runtime_lifecycle", default=None)


class RuntimeLifecycle:
    def __init__(self):
        self._lock = threading.Lock()
        self._cancelled = False
        self._stops = []

    def check(self):
        with self._lock:
            if self._cancelled:
                raise RuntimeError("Runtime startup was cancelled")

    def register(self, stop):
        with self._lock:
            cancelled = self._cancelled
            if not cancelled:
                self._stops.append(stop)
        if cancelled:
            stop()
            raise RuntimeError("Runtime startup was cancelled")

    def cancel(self):
        with self._lock:
            self._cancelled = True
            stops, self._stops = self._stops, []
        failures = []
        for stop in stops:
            try:
                stop()
            except Exception as exc:
                failures.append(type(exc).__name__)
        return failures

    @contextmanager
    def activate(self):
        self.check()
        token = current_lifecycle.set(self)
        try:
            yield
        finally:
            current_lifecycle.reset(token)
