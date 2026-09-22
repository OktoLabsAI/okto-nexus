"""Bounded transient replay and fanout; durable replay belongs to the journal.

Overflow is latched, never a silent queue drop. Readers drain the retained
prefix then receive an explicit gap, allowing the supervisor to record UNKNOWN.
Budgets measure serialized event bytes, not a claim about exact Python RSS.
"""
from collections import deque
from dataclasses import fields
import json
import queue
import threading


class NativeEventOverflow(RuntimeError):
    def __init__(self):
        super().__init__("native event buffer overflow; outcome unknown")


class NativeReplayExpired(RuntimeError):
    def __init__(self):
        super().__init__("native event replay expired; use canonical durable replay")


class NativeSubscriptionLimit(RuntimeError):
    pass


def event_bytes(event):
    return len(json.dumps({field.name: getattr(event, field.name) for field in fields(event)},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


class NativeEventHistory:
    def __init__(self, *, max_events=2048, max_bytes=4 * 1024 * 1024):
        self.max_events, self.max_bytes = max_events, max_bytes
        self._items, self._bytes = deque(), 0
        self._expired_sessions = set()
        self._all_expired = False
        self._lock = threading.RLock()

    def _expired(self, session_id):
        if len(self._expired_sessions) < 64:
            self._expired_sessions.add(session_id)
        else:
            self._all_expired = True

    def append(self, event):
        size = event_bytes(event)
        with self._lock:
            if size > self.max_bytes:
                self._expired(event.session_id)
                return False
            while self._items and (len(self._items) >= self.max_events or self._bytes + size > self.max_bytes):
                old, old_size = self._items.popleft()
                self._bytes -= old_size
                self._expired(old.session_id)
            self._items.append((event, size))
            self._bytes += size
            return True

    def snapshot(self, session_id=None):
        with self._lock:
            if self._all_expired or (bool(self._expired_sessions) if session_id is None
                                     else session_id in self._expired_sessions):
                raise NativeReplayExpired()
            return [event for event, _ in self._items if session_id is None or event.session_id == session_id]

    def __iter__(self):
        return iter(self.snapshot())

    def __len__(self):
        with self._lock:
            return len(self._items)


class NativeEventQueue:
    def __init__(self, *, max_events=128, max_bytes=2 * 1024 * 1024):
        self.max_events, self.max_bytes = max_events, max_bytes
        self._items, self._bytes = deque(), 0
        self._overflow = False
        self._changed = threading.Condition()

    def put(self, event):
        size = event_bytes(event)
        with self._changed:
            if self._overflow or len(self._items) >= self.max_events or self._bytes + size > self.max_bytes:
                self._overflow = True
                self._changed.notify_all()
                return False
            self._items.append((event, size))
            self._bytes += size
            self._changed.notify()
            return True

    def get(self, timeout=None):
        with self._changed:
            if not self._changed.wait_for(lambda: self._items or self._overflow, timeout):
                raise queue.Empty
            if self._items:
                event, size = self._items.popleft()
                self._bytes -= size
                return event
            raise NativeEventOverflow()

    def qsize(self):
        with self._changed:
            return len(self._items)


def subscribe(history, subscribers, *, session_id=None):
    """Caller holds its append/snapshot registration lock."""
    if len(subscribers) >= 16:
        raise NativeSubscriptionLimit("native event subscription capacity exhausted")
    backlog = history.snapshot(session_id)
    subscriber = NativeEventQueue()
    subscribers.append(subscriber)
    return subscriber, backlog


def stop_overflowed_process(process):
    # Never used by attach; only an actual owned Popen object is accepted here.
    if process is not None:
        try:
            if process.poll() is None:
                process.kill()
        except OSError:
            pass  # Queue gap and lifecycle observation still report uncertainty.
