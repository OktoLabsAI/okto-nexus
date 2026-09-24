"""Bounded priority workers under the existing serve owner and wake generation."""
import logging
import queue
import threading
import time

from ..domain.base import new_id
from ..domain.runtime_commands import RuntimeCommandNotSent
from ..errors import OktoNexusError


class RuntimeCommandDispatcher:
    def __init__(self, *, owner, repo, service):
        self.owner, self.repo, self.service = owner, repo, service
        self._lock = threading.Lock()
        self._inflight = {}
        self._capacities = {"close": 1, "control": 2, "turn": 2}
        self._queues = {lane: queue.Queue(size) for lane, size in self._capacities.items()}
        self._threads = []

    def start(self):
        for control, size in self._capacities.items():
            for index in range(size):
                thread = threading.Thread(target=self._worker, args=(control,), daemon=True,
                    name=f"nexus-command-{control}-{index}")
                self._threads.append(thread)
                thread.start()

    def operation_inflight(self, operation_id):
        with self._lock:
            return operation_id in self._inflight

    def normal_operations_inflight(self):
        with self._lock:
            return tuple(operation for operation, (_, _, lane) in self._inflight.items() if lane == "turn")

    def idle(self):
        with self._lock:
            return not self._inflight

    def join_idle_workers(self):
        if self.idle():
            deadline = time.monotonic() + 1.5
            for thread in self._threads:
                if thread is not threading.current_thread():
                    thread.join(max(0, deadline - time.monotonic()))

    def scan_once(self):
        if self.owner._stop.is_set() or self.owner._quiescing.is_set():
            return
        for control, size in self._capacities.items():
            with self._lock:
                capacity = size - sum(lane == control for _, _, lane in self._inflight.values())
            if capacity <= 0:
                continue
            now = self.owner.clock.now_iso()
            selected = []
            with self.owner.cf.unit_of_work() as uow:
                if not self.owner.repo.owns(uow, owner_id=self.owner.owner_id, epoch=self.owner.epoch, now=now):
                    return
                endpoints = set()
                blocked = self.owner.normal_inflight_agents(uow) if control == "turn" else ()
                for command in self.repo.pending(uow, control=control != "turn", close_only=control == "close",
                        limit=capacity, blocked_agents=blocked):
                    if command["endpoint_id"] in endpoints:
                        continue
                    attempt = new_id("attempt")
                    if self.repo.claim(uow, operation_id=command["operation_id"], epoch=self.owner.epoch, attempt_id=attempt, now=now):
                        selected.append(command | {"owner_epoch": self.owner.epoch, "attempt_id": attempt})
                        endpoints.add(command["endpoint_id"])
            for command in selected:
                with self._lock:
                    self._inflight[command["operation_id"]] = (command["attempt_id"], None, control)
                self._queues[control].put_nowait(command)

    def _worker(self, control):
        while not self.owner._stop.is_set():
            try:
                command = self._queues[control].get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._execute(command, control)
            finally:
                with self._lock:
                    self._inflight.pop(command["operation_id"], None)
                self._queues[control].task_done()
                self.owner.wake()

    def _execute(self, command, control):
        key = dict(operation_id=command["operation_id"], epoch=command["owner_epoch"], attempt_id=command["attempt_id"])
        try:
            with self.owner.cf.unit_of_work() as uow:
                now = self.owner.clock.now_iso()
                if self.owner._quiescing.is_set() or not self.owner.repo.owns(uow, owner_id=self.owner.owner_id, epoch=self.owner.epoch, now=now):
                    return
                try:
                    self.service.validate(uow, command)
                except OktoNexusError:
                    self.repo.observe(uow, **key, expected="CLAIMED", status="REJECTED", reason="authorization_or_binding_changed", now=now)
                    return
                if not self.repo.observe(uow, **key, expected="CLAIMED", status="SENDING", now=now):
                    return
            with self._lock:
                self._inflight[command["operation_id"]] = (command["attempt_id"], time.monotonic(), control)
            result = self.service.execute(command)
            status = "SENT_UNCONFIRMED"
            if command["verb"] == "close":
                status = "OUTCOME_UNKNOWN" if result["lifecycle_state"] == "outcome_unknown" else "DONE"
            self._observe_owned(key, status=status, result=result)
        except RuntimeCommandNotSent:
            self._observe_owned(key, status="REJECTED", reason="stale_control_or_occupied_lane")
        except Exception:
            self._observe_owned(key, status="OUTCOME_UNKNOWN", reason="command_failed_after_send_intent")

    def _observe_owned(self, key, *, status, reason=None, result=None):
        try:
            with self.owner.cf.unit_of_work() as uow:
                now = self.owner.clock.now_iso()
                if self.owner.repo.owns(uow, owner_id=self.owner.owner_id, epoch=self.owner.epoch, now=now):
                    self.repo.observe(uow, **key, expected="SENDING", status=status, reason=reason, result=result, now=now)
        except Exception:
            logging.getLogger(__name__).error("Runtime command outcome could not persist; send intent remains uncertain.")

    def expire(self):
        with self._lock:
            overdue = [(op, attempt) for op, (attempt, start, _) in self._inflight.items()
                if start is not None and time.monotonic() - start >= self.owner.send_timeout_seconds]
        for operation_id, attempt in overdue:
            self._observe_owned(dict(operation_id=operation_id, epoch=self.owner.epoch, attempt_id=attempt),
                status="OUTCOME_UNKNOWN", reason="timeout_does_not_cancel_native_call")
