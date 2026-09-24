"""Single leased owner, bounded workers and durable send-intent fencing."""
import queue
import logging
import threading
import time

from ..domain.base import iso_plus, new_id
from ..errors import OktoNexusError
from ..domain.runtime_commands import RuntimeCommandNotSent


class RuntimeDispatcher:
    def __init__(self, *, connection_factory, repo, clock, validate, dispatch,
                 workers=2, recovery_seconds=30, send_timeout_seconds=45):
        self.cf, self.repo, self.clock = connection_factory, repo, clock
        self.validate, self.dispatch = validate, dispatch
        self.workers = min(max(int(workers), 1), 8)
        self.recovery_seconds, self.send_timeout_seconds = recovery_seconds, send_timeout_seconds
        self.owner_id, self.epoch = new_id("owner"), None
        self._wake_condition = threading.Condition()
        self._wake_generation = 0
        self._stop = threading.Event()
        self._quiescing = threading.Event()
        self._shutdown_finished = threading.Event()
        self._shutdown_ready = None
        self._queue = queue.Queue(maxsize=self.workers)
        self._lock = threading.Lock()
        self._inflight = {}
        self._threads = []
        self.wake_channel = None
        self.event_ingress = None
        self.command_dispatcher = None
        self.publish_results = None
        self._publication_queue = queue.Queue(maxsize=1)
        self._publication_active = False
        self._publication_rescan = False
        self._publication_thread = None

    def start(self):
        if self.epoch is not None:
            return True
        now = self.clock.now_iso()
        with self.cf.unit_of_work() as uow:
            self.epoch = self.repo.acquire_owner(uow, owner_id=self.owner_id, now=now, lease_expires_at=iso_plus(now, 40))
        if self.epoch is None:
            return False
        self.cf.configure_runtime_owner(self.owner_id, self.epoch, clock=self.clock)
        if self.event_ingress:
            try:
                self.event_ingress.start(recover=False)
                journal = self.event_ingress.journal
                # Snapshot captured bytes before any new native admission. This
                # boundary never extends to late events of the previous owner.
                with self.cf.unit_of_work() as uow:
                    if not self.repo.set_recovery_boundary(uow, owner_id=self.owner_id,
                            epoch=self.epoch, store_id=journal.store_id, watermark=journal.watermark,
                            now=self.clock.now_iso()):
                        raise RuntimeError("Runtime journal recovery lost ownership")
                deadline = time.monotonic() + 30
                while self.event_ingress.recover():
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Runtime recovery startup budget exceeded; checkpoint retained")
                    with self.cf.unit_of_work() as uow:
                        now = self.clock.now_iso()
                        if not self.repo.heartbeat_owner(uow, owner_id=self.owner_id, epoch=self.epoch,
                                lease_expires_at=iso_plus(now, 40), now=now):
                            raise RuntimeError("Runtime journal recovery lost ownership")
                with self.cf.unit_of_work() as uow:
                    self.repo.finish_recovery(uow, epoch=self.epoch, now=self.clock.now_iso())
            except BaseException:
                self.event_ingress.close()
                with self.cf.unit_of_work() as uow:
                    self.repo.release_owner(uow, owner_id=self.owner_id, epoch=self.epoch, now=self.clock.now_iso())
                self.epoch = None
                self.cf.configure_runtime_owner(None, None)
                raise
        if self.wake_channel:
            self.wake_channel.start(self.wake, self.owner_id)
        if self.command_dispatcher:
            self.command_dispatcher.service.owner_identity = (self.owner_id, self.epoch)
            self.command_dispatcher.start()
        if self.publish_results:
            self._publication_thread = threading.Thread(target=self._publish_worker, daemon=True, name="nexus-result-publication")
            self._publication_thread.start()
        for index in range(self.workers):
            worker = threading.Thread(target=self._worker, daemon=True, name=f"nexus-dispatch-{index}")
            self._threads.append(worker)
            worker.start()
        self._coordinator = threading.Thread(target=self._run, daemon=True, name="nexus-dispatch-owner")
        self._coordinator.start()
        self.wake()
        return True

    def wake(self):
        with self._wake_condition:
            self._wake_generation += 1
            self._wake_condition.notify()

    def _schedule_publication(self):
        with self._lock:
            if not self.publish_results or self._quiescing.is_set():
                return
            if self._publication_active:
                self._publication_rescan = True
                return
            self._publication_active = True
            self._publication_queue.put_nowait(True)

    def _publish_worker(self):
        while not self._stop.is_set():
            try:
                self._publication_queue.get(timeout=1)
            except queue.Empty:
                continue
            processed = 0
            try:
                if self.publish_results and not self._quiescing.is_set():
                    processed = self.publish_results()
            except Exception:
                logging.getLogger(__name__).warning("Captured result publication remains pending after storage failure.")
            finally:
                with self._lock:
                    self._publication_active = False
                    rescan, self._publication_rescan = self._publication_rescan, False
                self._publication_queue.task_done()
                if processed or rescan or self._quiescing.is_set():
                    self.wake()

    def _wait_for_wake(self, observed, timeout=10):
        # Read and acknowledge a generation under the same lock as producers.
        # A wake during scanning stays outstanding for the next iteration;
        # there is no separate clear that can erase a concurrent commit's wake.
        with self._wake_condition:
            self._wake_condition.wait_for(
                lambda: self._wake_generation != observed or self._stop.is_set(),
                timeout=timeout,
            )
            return self._wake_generation

    def _run(self):
        recovered = 0.0
        observed = 0
        while not self._stop.is_set():
            generation = self._wait_for_wake(observed)
            signaled = generation != observed
            observed = generation
            if self._stop.is_set():
                break
            try:
                now = self.clock.now_iso()
                with self.cf.unit_of_work() as uow:
                    if not self.repo.heartbeat_owner(uow, owner_id=self.owner_id, epoch=self.epoch, lease_expires_at=iso_plus(now, 40), now=now):
                        self._stop.set()
                        break
                self._expire_sends()
                if self.command_dispatcher:
                    self.command_dispatcher.expire()
                if self.event_ingress:
                    self.event_ingress.recover()
                    if self.event_ingress.projection_pending:
                        self.wake()
                self._schedule_publication()
                if self._shutdown_ready and self._shutdown_ready():
                    with self._lock:
                        idle = not self._inflight and not self._publication_active
                    if idle and (not self.command_dispatcher or self.command_dispatcher.idle()):
                        if self.event_ingress and self.event_ingress.projection_pending:
                            self.wake()
                            continue
                        if self.event_ingress:
                            self.event_ingress.close()
                        self.close()
                        self._shutdown_finished.set()
                        break
                if signaled or time.monotonic() - recovered >= self.recovery_seconds:
                    if self.command_dispatcher:
                        self.command_dispatcher.scan_once()
                    self.scan_once()
                    recovered = time.monotonic()
            except Exception:
                # No speculative replay on transient storage failure. Indexed
                # recovery will revisit only PENDING; SENDING remains fenced.
                logging.getLogger(__name__).warning("Runtime dispatcher storage/recovery failed; intents remain durable.")

    def operation_inflight(self, operation_id):
        with self._lock:
            active = operation_id in self._inflight
        return active or bool(self.command_dispatcher and self.command_dispatcher.operation_inflight(operation_id))

    def scan_once(self):
        with self._lock:
            capacity = self.workers - len(self._inflight)
        if capacity <= 0 or self._stop.is_set() or self._quiescing.is_set():
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
                if self._quiescing.is_set():
                    return
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
            if self.event_ingress:
                self.event_ingress.journal.check_admission()
            # Secret resolution, process startup and transport are ALL outside
            # the write transaction. Crash from here is ambiguous, not retryable.
            self.dispatch(operation | {"owner_id": self.owner_id, "owner_epoch": self.epoch, "attempt_id": attempt})
            with self.cf.unit_of_work() as uow:
                if self.repo.owns(uow, owner_id=self.owner_id, epoch=self.epoch, now=self.clock.now_iso()):
                    self.repo.observe(uow, **key, expected="SENDING", status="SENT_UNCONFIRMED",
                                      ack_level="TRANSPORT_WRITE", now=self.clock.now_iso())
        except RuntimeCommandNotSent:
            with self.cf.unit_of_work() as uow:
                now = self.clock.now_iso()
                if self.repo.owns(uow, owner_id=self.owner_id, epoch=self.epoch, now=now):
                    self.repo.observe(uow, **key, expected="SENDING", status="REJECTED", now=now,
                        reason="native_write_not_started", ack_level="NONE")
        except Exception:
            try:
                with self.cf.unit_of_work() as uow:
                    now = self.clock.now_iso()
                    if self.repo.owns(uow, owner_id=self.owner_id, epoch=self.epoch, now=now):
                        self.repo.observe(uow, **key, expected="SENDING", status="OUTCOME_UNKNOWN",
                                          now=now, reason="dispatch_failed_after_send_intent")
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

    def quiesce(self):
        """Stop claims and external calls that have not reached send-intent.

        Heartbeats and capture/projection continue until all owned activity has
        drained. A timed-out shutdown must not donate its lease to a new owner.
        """
        self._quiescing.set()
        self.wake()

    def finish_shutdown_when(self, ready, *, timeout):
        self._shutdown_ready = ready
        self.wake()
        return self._shutdown_finished.wait(timeout)

    def close(self):
        self._stop.set()
        self.wake()
        if self.epoch is None:
            return
        if self.wake_channel:
            self.wake_channel.close()
        if self._coordinator is not threading.current_thread():
            self._coordinator.join(5)
        if self.command_dispatcher:
            self.command_dispatcher.join_idle_workers()
        if self._publication_thread and not self._publication_active and self._publication_thread is not threading.current_thread():
            self._publication_thread.join(1.5)
        # Workers remain capacity-bound even if a native call has not returned.
        with self.cf.unit_of_work() as uow:
            self.repo.release_owner(uow, owner_id=self.owner_id, epoch=self.epoch, now=self.clock.now_iso())
        self.cf.configure_runtime_owner(None, None)
