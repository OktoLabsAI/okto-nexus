"""Journal-first event capture and retryable, atomic result projection."""
import logging
import threading
from typing import Protocol

from ..domain.harness import HarnessEvent


class RuntimeEventJournal(Protocol):
    store_id: str | None
    watermark: int

    def start(self, *, initial_sequences=None): ...
    def check_admission(self): ...
    def append(self, event: HarnessEvent, *, connection_id=None) -> dict: ...
    def read_after(self, ordinal: int, *, limit=16) -> list[dict]: ...
    def compact(self, projected_ordinal: int) -> dict: ...
    def diagnostics(self) -> dict: ...
    def close(self): ...


class RuntimeEventIngress:
    def __init__(self, *, journal: RuntimeEventJournal, connection_factory, repo, events, clock, publish):
        self.journal, self.cf, self.repo = journal, connection_factory, repo
        self.events, self.clock, self.publish = events, clock, publish
        self._project_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._capture_lock = threading.RLock()
        self.projection_pending = False
        self.wake_dispatch = None
        self.consume_terminal = None
        self.capture_health_changed = None

    def check_admission(self):
        with self._capture_lock:
            try:
                self.journal.check_admission()
            except OSError:
                self._report_capture_health(False)
                raise

    def enable_admission(self):
        # Serialize validation and the owner health update with capture faults.
        # Otherwise a stale successful quota check could clear a newer fault.
        with self._capture_lock:
            self.check_admission()
            self._report_capture_health(True)

    def _report_capture_health(self, available):
        if not available:
            logging.getLogger(__name__).error("Runtime journal capture unavailable; new executions paused.")
        if self.capture_health_changed:
            self.capture_health_changed(available)

    def start(self, *, recover=True):
        with self.cf.unit_of_work(write=False) as uow:
            sequences = self.repo.initial_sequences(uow)
        self.journal.start(initial_sequences=sequences)
        if recover:
            self.recover()

    def capture(self, event, *, connection_id=None, defer_projection=False):
        with self._capture_lock:
            try:
                record = self.journal.append(event, connection_id=connection_id)
            except OSError:
                # append has released its file lock. Record a store-wide admission
                # fence outside journal IO and outside any existing writer UoW.
                self._report_capture_health(False)
                raise
        if defer_projection and self.wake_dispatch:
            # Capture must not wait on SQLite projection. The existing bounded
            # owner coordinator drains the durable journal, not a second queue.
            with self._pending_lock:
                self.projection_pending = True
            self.wake_dispatch()
            return HarnessEvent(**record["event"])
        try:
            self.recover()
        except Exception:
            # The journal already fsynced the record. It remains available for
            # recovery; no canonical message or handoff success is fabricated.
            self.projection_pending = True
            logging.getLogger(__name__).warning("Runtime event is journaled; database projection pending.")
        return HarnessEvent(**record["event"])

    def recover(self):
        with self._project_lock:
            with self.cf.unit_of_work(write=False) as uow:
                checkpoint = self.repo.checkpoint(uow, store_id=self.journal.store_id)
            if checkpoint > self.journal.watermark:
                raise OSError("Journal data behind a committed checkpoint is missing")
            records = self.journal.read_after(checkpoint)
            published = []
            if records:
                # One bounded batch commits atomically; journal I/O and public
                # callbacks remain outside the SQLite writer transaction.
                with self.cf.unit_of_work() as uow:
                    for record in records:
                        event = HarnessEvent(**record["event"])
                        inserted = self.repo.project(uow, record=record, event=event,
                                                    events=self.events, now=self.clock.now_iso())
                        if inserted:
                            if self.consume_terminal:
                                self.consume_terminal(uow, event)
                            published.append(event)
            for event in published:
                if event.delivery_phase == "terminal" and self.wake_dispatch:
                    self.wake_dispatch()
                try:
                    self.publish(event)
                except Exception:
                    logging.getLogger(__name__).warning("Runtime event publication failed; durable replay remains available.")
            with self._pending_lock:
                projected = records[-1]["ordinal"] if records else checkpoint
                self.projection_pending = self.journal.watermark > projected
            return len(records)

    def close(self):
        self.journal.close()

    def compact(self):
        with self._project_lock:
            with self.cf.unit_of_work(write=False) as uow:
                checkpoint = self.repo.checkpoint(uow, store_id=self.journal.store_id)
            # The DB transaction has ended before touching journal files.
            with self._capture_lock:
                result = self.journal.compact(checkpoint)
                self.enable_admission()
                return result
