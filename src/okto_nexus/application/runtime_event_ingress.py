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
    def close(self): ...


class RuntimeEventIngress:
    def __init__(self, *, journal: RuntimeEventJournal, connection_factory, repo, events, clock, publish):
        self.journal, self.cf, self.repo = journal, connection_factory, repo
        self.events, self.clock, self.publish = events, clock, publish
        self._project_lock = threading.Lock()
        self.projection_pending = False

    def start(self):
        with self.cf.unit_of_work(write=False) as uow:
            sequences = self.repo.initial_sequences(uow)
        self.journal.start(initial_sequences=sequences)
        self.recover()

    def capture(self, event, *, connection_id=None):
        record = self.journal.append(event, connection_id=connection_id)
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
            for record in records:
                event = HarnessEvent(**record["event"])
                with self.cf.unit_of_work() as uow:
                    inserted = self.repo.project(uow, record=record, event=event,
                                                events=self.events, now=self.clock.now_iso())
                if inserted:
                    try:
                        self.publish(event)
                    except Exception:
                        logging.getLogger(__name__).warning("Runtime event publication failed; durable replay remains available.")
            self.projection_pending = bool(records and len(records) == 16)
            return len(records)

    def close(self):
        self.journal.close()
