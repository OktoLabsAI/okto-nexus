"""Single leased owner, bounded workers and durable send-intent fencing."""
import queue
import logging
import threading
import time

from ..domain.base import iso_plus, new_id
from ..errors import OktoNexusError


class RuntimeDispatcher:
    def __init__(self, *, connection_factory, repo, clock, validate, dispatch,
                 workers=2, recovery_seconds=30, send_timeout_seconds=45):
        self.cf, self.repo, self.clock = connection_factory, repo, clock
        self.validate, self.dispatch = validate, dispatch
        self.workers = min(max(int(workers), 1), 8)
        self.recovery_seconds, self.send_timeout_seconds = recovery_seconds, send_timeout_seconds
        self.owner_id, self.epoch = new_id("owner"), None
        self._wake, self._stop = threading.Event(), threading.Event()
        self._queue = queue.Queue(maxsize=self.workers)
        self._lock = threading.Lock()
        self._inflight = {}
        self._threads = []
        self.wake_channel = None

    def start(self):
        if self.epoch is not None:
            return True
        now = self.clock.now_iso()
        with self.cf.unit_of_work() as uow:
            self.epoch = self.repo.acquire_owner(uow, owner_id=self.owner_id, now=now, lease_expires_at=iso_plus(now, 40))
        if self.epoch is None:
            return False
        if self.wake_channel:
            self.wake_channel.start(self.wake, self.owner_id)
        for index in range(self.workers):
            worker = threading.Thread(target=self._worker, daemon=True, name=f"nexus-dispatch-{index}")
            self._threads.append(worker)
            worker.start()
        self._coordinator = threading.Thread(target=self._run, daemon=True, name="nexus-dispatch-owner")
        self._coordinator.start()
        self.wake()
        return True

    def wake(self):
        self._wake.set()

    def _run(self):
        recovered = 0.0
        while not self._stop.is_set():
            signaled = self._wake.wait(10)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                now = self.clock.now_iso()
                with self.cf.unit_of_work() as uow:
                    if not self.repo.heartbeat_owner(uow, owner_id=self.owner_id, epoch=self.epoch, lease_expires_at=iso_plus(now, 40), now=now):
                        self._stop.set()
                        break
                self._expire_sends()
                if signaled or time.monotonic() - recovered >= self.recovery_seconds:
                    self.scan_once()
                    recovered = time.monotonic()
            except Exception:
                # No speculative replay on transient storage failure. Indexed
                # recovery will revisit only PENDING; SENDING remains fenced.
                logging.getLogger(__name__).warning("Runtime dispatcher storage/recovery failed; intents remain durable.")

    def scan_once(self):
        with self._lock:
            capacity = self.workers - len(self._inflight)
        if capacity <= 0 or self._stop.is_set():
            return
        now = self.clock.now_iso()
        with self.cf.unit_of_work() as uow:
            if not self.repo.owns(uow, owner_id=self.owner_id, epoch=self.epoch, now=now):
                return
            pending = self.repo.pending(uow, limit=capacity)
            accepted = []
            selected_endpoints = set()
            for operation in pending:
                if operation["endpoint_id"] in selected_endpoints:
                    continue
                attempt = new_id("attempt")
                if self.repo.claim(uow, operation_id=operation["operation_id"], epoch=self.epoch,
                                   attempt_id=attempt, lease_expires_at=iso_plus(now, 40), now=now):
                    accepted.append((operation, attempt))
                    selected_endpoints.add(operation["endpoint_id"])
        for operation, attempt in accepted:
            with self._lock:
                self._inflight[operation["operation_id"]] = (attempt, None)
            self._queue.put_nowait((operation, attempt))

    def _worker(self):
        while not self._stop.is_set():
            try:
                operation, attempt = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._execute(operation, attempt)
            finally:
                with self._lock:
                    self._inflight.pop(operation["operation_id"], None)
                self._queue.task_done()
                self.wake()

    def _execute(self, operation, attempt):
        key = dict(operation_id=operation["operation_id"], epoch=self.epoch, attempt_id=attempt)
        try:
            with self.cf.unit_of_work() as uow:
                now = self.clock.now_iso()
                if not self.repo.owns(uow, owner_id=self.owner_id, epoch=self.epoch, now=now):
                    return
                try:
                    self.validate(uow, operation)
                except OktoNexusError:
                    self.repo.observe(uow, **key, expected="CLAIMED", status="REJECTED", now=now, reason="authorization_changed")
                    return
                if not self.repo.observe(uow, **key, expected="CLAIMED", status="SENDING", now=now):
                    return
            with self._lock:
                self._inflight[operation["operation_id"]] = (attempt, time.monotonic())
            # Secret resolution, process startup and transport are ALL outside
            # the write transaction. Crash from here is ambiguous, not retryable.
            self.dispatch(operation | {"owner_id": self.owner_id, "owner_epoch": self.epoch, "attempt_id": attempt})
            with self.cf.unit_of_work() as uow:
                if self.repo.owns(uow, owner_id=self.owner_id, epoch=self.epoch, now=self.clock.now_iso()):
                    self.repo.observe(uow, **key, expected="SENDING", status="SENT_UNCONFIRMED",
                                      ack_level="TRANSPORT_WRITE", now=self.clock.now_iso())
        except Exception:
            try:
                with self.cf.unit_of_work() as uow:
                    self.repo.observe(uow, **key, expected="SENDING", status="OUTCOME_UNKNOWN",
                                      now=self.clock.now_iso(), reason="dispatch_failed_after_send_intent")
            except Exception:
                logging.getLogger(__name__).error("Runtime outcome persistence failed; send-intent requires reconciliation.")

    def _expire_sends(self):
        with self._lock:
            overdue = [(operation, attempt) for operation, (attempt, started) in self._inflight.items()
                       if started is not None and time.monotonic() - started >= self.send_timeout_seconds]
        for operation, attempt in overdue:
            with self.cf.unit_of_work() as uow:
                self.repo.observe(uow, operation_id=operation, epoch=self.epoch, attempt_id=attempt,
                    expected="SENDING", status="OUTCOME_UNKNOWN", now=self.clock.now_iso(), reason="timeout_does_not_prove_non_delivery")

    def close(self):
        self._stop.set()
        self.wake()
        if self.epoch is None:
            return
        if self.wake_channel:
            self.wake_channel.close()
        self._coordinator.join(5)
        # Workers remain capacity-bound even if a native call has not returned.
        with self.cf.unit_of_work() as uow:
            self.repo.release_owner(uow, owner_id=self.owner_id, epoch=self.epoch, now=self.clock.now_iso())
