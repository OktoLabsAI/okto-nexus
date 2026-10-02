"""FIFO writer admission within one connection factory, with one wait budget."""
from collections import deque
import threading
import time


class WriteGate:
    def __init__(self):
        self._condition = threading.Condition()
        self._waiting = deque()
        self._active = False

    def acquire(self, timeout_seconds):
        deadline = time.monotonic() + timeout_seconds
        ticket = object()
        with self._condition:
            self._waiting.append(ticket)
            try:
                while self._active or self._waiting[0] is not ticket:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("SQLite writer admission timed out.")
                    self._condition.wait(remaining)
                self._active = True
                return max(0, deadline - time.monotonic())
            finally:
                self._waiting.remove(ticket)
                self._condition.notify_all()

    def release(self):
        with self._condition:
            self._active = False
            self._condition.notify_all()
