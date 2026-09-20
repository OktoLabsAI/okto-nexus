"""In-process, in-memory push registry for ordinary per-recipient inbox
deliveries (ADR 0004 follow-up; closes the SYS-03/UAT-05 target-grammar gap).

The concrete implementation of
:class:`~okto_nexus.application.ports.InboxDeliveryNotifier`: a near-exact
mirror of
:class:`~okto_nexus.adapters.outbound.harness.subscribers.InMemoryHarnessSubscriberRegistry`
(same lock-snapshot-then-call-outside-the-lock shape, same
one-broken-subscriber-never-breaks-another isolation), keyed by RECIPIENT
``agent_id`` instead of harness ``session_id``.

ONE instance lives for the whole ``serve`` process (wired once, cached on
``deps`` by ``tools/messages.py``'s composition root - see its own
docstring) and is shared by every :class:`MessageService` instance AND by
:class:`~okto_nexus.application.harness_supervisor.HarnessSupervisor`, which
subscribes a live session's ``owning_agent_id`` on
:meth:`~HarnessSupervisor.open` and unsubscribes when that session stops
being tracked.

Pure in-memory pub/sub - :meth:`publish` never touches storage and never
blocks on anything beyond calling registered callbacks. There is no queue
and no poll loop anywhere in this class, so D1's push-not-poll contract
extends cleanly to this, the INBOUND half of the harness path (the OUTBOUND
half is ``InMemoryHarnessSubscriberRegistry``, above).
"""

from __future__ import annotations

import itertools
import threading
from typing import Any, Callable, Mapping

Callback = Callable[[Mapping[str, Any]], None]


class InMemoryInboxDeliveryNotifier:
    """Agent-scoped fan-out: each ``agent_id`` has its own subscriber set.

    A subscriber callback that raises is caught and dropped for THIS
    publish only - one broken consumer must never stop
    :meth:`publish` from reaching every OTHER subscriber of the same
    ``agent_id`` (there is normally at most one - a single live harness
    session - but nothing here assumes that), or from returning control to
    its caller (``MessageService.create_message``, already past its own
    write transaction by the time it calls this).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_agent: dict[str, dict[int, Callback]] = {}
        self._next_handle = itertools.count(1)

    def subscribe(self, agent_id: str, callback: Callback) -> Any:
        """Register ``callback`` for ``agent_id``; returns an opaque handle."""
        token = next(self._next_handle)
        with self._lock:
            self._by_agent.setdefault(agent_id, {})[token] = callback
        return (agent_id, token)

    def unsubscribe(self, handle: Any) -> None:
        """Remove a subscription. Silently ignores an unknown/malformed
        handle (idempotent - a caller unsubscribing twice, or after its own
        session was already reaped, is not an error)."""
        try:
            agent_id, token = handle
        except (TypeError, ValueError):
            return
        with self._lock:
            callbacks = self._by_agent.get(agent_id)
            if callbacks is None:
                return
            callbacks.pop(token, None)
            if not callbacks:
                self._by_agent.pop(agent_id, None)

    def publish(self, agent_id: str, message: Mapping[str, Any]) -> None:
        """Push ``message`` to every subscriber of ``agent_id``, now,
        synchronously, on the calling thread. A snapshot of the callback
        list is taken under the lock and then called OUTSIDE it, so a
        subscriber that calls back into :meth:`subscribe`/:meth:`unsubscribe`
        from within its own callback cannot deadlock this registry."""
        with self._lock:
            callbacks = list(self._by_agent.get(agent_id, {}).values())
        for callback in callbacks:
            try:
                callback(message)
            except Exception:  # noqa: BLE001 - one broken subscriber must not break the rest
                continue
