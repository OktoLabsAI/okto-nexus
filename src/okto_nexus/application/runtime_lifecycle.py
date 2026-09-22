"""Bounded startup cancellation, contract v1; resources are owned explicitly.

Cancellation stops owned resources; it does not claim that a native turn ended.
Adapters register callbacks immediately after creating an owned resource. Attach
adapters must never register the external operator's process.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import uuid


current_lifecycle = ContextVar("runtime_lifecycle", default=None)


class RuntimeConnectionLifecycle:
    """Starting and live sessions lease a connection's owned resources.

    The last lease closes admission before teardown, so another session cannot
    race a decision to terminate the shared process. Cancelled leases cannot
    kill resources still used by other authorized sessions.
    """
    def __init__(self, *, context=None):
        self.context = context
        self.connection_id = "conn_" + uuid.uuid4().hex
        self._lock = threading.Lock()
        self._active = set()
        self._stops = []
        self._closing = False

    @property
    def closed(self):
        with self._lock:
            return self._closing and not self._active

    def new_scope(self, *, multiplexing):
        with self._lock:
            if self._closing or (self._active and not multiplexing):
                raise RuntimeError("Connection is closing or does not support shared sessions")
            scope = RuntimeLifecycle(connection=self)
            self._active.add(scope)
            return scope

    def register(self, scope, stop):
        with self._lock:
            cancelled = scope not in self._active or self._closing
            if not cancelled:
                self._stops.append(stop)
        if cancelled:
            stop()
            raise RuntimeError("Connection startup was cancelled")

    def claim_exclusive_teardown(self, scope):
        with self._lock:
            if self._active - {scope}:
                return False
            self._closing = True
            return True

    def cancel(self, scope):
        with self._lock:
            self._active.discard(scope)
            if self._active:
                return []
            self._closing = True
            stops, self._stops = self._stops, []
        return _stop_all(stops)


def _stop_all(stops):
    failures = []
    for stop in stops:
        try:
            stop()
        except Exception as exc:
            failures.append(type(exc).__name__)
    return failures


class RuntimeLifecycle:
    def __init__(self, *, connection=None):
        self._lock = threading.Lock()
        self._cancelled = False
        self._stops = []
        self.connection = connection
        self.connection_id = connection.connection_id if connection else "conn_" + uuid.uuid4().hex

    def check(self):
        with self._lock:
            if self._cancelled:
                raise RuntimeError("Runtime startup was cancelled")

    def register(self, stop):
        with self._lock:
            cancelled = self._cancelled
            if not cancelled and self.connection is None:
                self._stops.append(stop)
        if cancelled:
            stop()
            raise RuntimeError("Runtime startup was cancelled")
        if self.connection is not None:
            self.connection.register(self, stop)

    def cancel(self):
        with self._lock:
            self._cancelled = True
            stops, self._stops = self._stops, []
        if self.connection is not None:
            return self.connection.cancel(self)
        return _stop_all(stops)

    def claim_exclusive_teardown(self):
        return self.connection is None or self.connection.claim_exclusive_teardown(self)

    @contextmanager
    def activate(self):
        self.check()
        token = current_lifecycle.set(self)
        try:
            yield
        finally:
            current_lifecycle.reset(token)
