"""In-process, in-memory push registry for harness events (D1; ADR 0004).

The concrete implementation of
:class:`~okto_nexus.application.ports.HarnessSubscriberRegistry`: ONE instance
lives for the whole life of the ``serve`` process and is shared by the
supervisor across every live session (application/harness_supervisor.py).

Pure in-memory pub/sub - :meth:`subscribe` never touches storage,
:meth:`publish` calls every registered callback SYNCHRONOUSLY, on the calling
(pump) thread. There is no queue and no poll loop anywhere in this class, so
there is nothing here for ``SleepPollWaiter`` (adapters/outbound/waiter.py)
to ever replace - D1's "push, never poll" holds structurally, not just by
convention.
"""

from __future__ import annotations

import itertools
import threading
from typing import Any, Callable

from ....domain.harness import HarnessEvent

Callback = Callable[[HarnessEvent], None]


class InMemoryHarnessSubscriberRegistry:
    """Session-scoped fan-out: each ``session_id`` has its own subscriber set.

    A subscriber callback that raises is caught and dropped for THIS publish
    only - one broken consumer (a wedged SSE writer, a closed MCP stream)
    must never stop the pump thread from reaching every OTHER subscriber of
    the session, or from returning to drain the connector's next event. This
    mirrors the failure-isolation standard the rest of the harness path
    holds itself to (D8): a subscriber is as untrustworthy as a connector.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_session: dict[str, dict[int, Callback]] = {}
        self._next_handle = itertools.count(1)

    def subscribe(self, session_id: str, callback: Callback) -> Any:
        """Register ``callback`` for ``session_id``; returns an opaque handle."""
        token = next(self._next_handle)
        with self._lock:
            self._by_session.setdefault(session_id, {})[token] = callback
        return (session_id, token)

    def unsubscribe(self, handle: Any) -> None:
        """Remove a subscription. Silently ignores an unknown/malformed handle
        (idempotent - a caller unsubscribing twice, or after the session's
        last event already cleaned it up, is not an error)."""
        try:
            session_id, token = handle
        except (TypeError, ValueError):
            return
        with self._lock:
            callbacks = self._by_session.get(session_id)
            if callbacks is None:
                return
            callbacks.pop(token, None)
            if not callbacks:
                self._by_session.pop(session_id, None)

    def publish(self, event: HarnessEvent) -> None:
        """Push ``event`` to every subscriber of ``event.session_id``, now,
        synchronously, on the calling thread. A snapshot of the callback list
        is taken under the lock and then called OUTSIDE it, so a subscriber
        that calls back into :meth:`subscribe`/:meth:`unsubscribe` from
        within its own callback cannot deadlock this registry."""
        with self._lock:
            callbacks = list(self._by_session.get(event.session_id, {}).values())
        for callback in callbacks:
            try:
                callback(event)
            except Exception:  # noqa: BLE001 - one broken subscriber must not break the rest
                continue
