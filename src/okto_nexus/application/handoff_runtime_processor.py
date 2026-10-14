"""Process one bounded candidate page through the durable attempt use cases."""
import asyncio
from dataclasses import dataclass
from typing import Protocol

from .handoff_runtime_scheduler import HandoffScheduleOutcome, SCHEDULE_REASONS


@dataclass(frozen=True)
class HandoffCandidatePage:
    attempt_ids: tuple[str, ...]
    cursor: str = ''
    more: bool = False
    settled: bool = False
    reason: str = 'NO_CANDIDATES'

    def __post_init__(self):
        if (type(self.attempt_ids) is not tuple or len(set(self.attempt_ids)) != len(self.attempt_ids)
                or any(type(x) is not str or not x for x in self.attempt_ids)
                or type(self.more) is not bool or type(self.settled) is not bool
                or self.settled and (self.attempt_ids or self.more) or self.reason not in SCHEDULE_REASONS):
            raise ValueError('Invalid handoff candidate page.')


class HandoffRuntimeCandidates(Protocol):
    def prepare_page(self, lease, *, limit: int) -> HandoffCandidatePage:
        """Recover original attempts first; prepare at most one candidate per agent.

        Persist each new request before returning its ID. Share canonical
        eligibility/binding resolution and creator affinity; no host I/O or
        native work in this call. Rotate the page cursor between rounds.
        """
        ...


class HandoffRuntimeProcessor:
    def __init__(self, *, candidates: HandoffRuntimeCandidates, attempts, admission, page_size=4):
        if type(page_size) is not int or not 1 <= page_size <= 32:
            raise ValueError('Invalid candidate concurrency limit.')
        self.candidates, self.attempts, self.admission = candidates, attempts, admission
        self.page_size = page_size

    async def process(self, lease):
        page = await asyncio.to_thread(self.candidates.prepare_page, lease, limit=self.page_size)
        if type(page) is not HandoffCandidatePage or len(page.attempt_ids) > self.page_size:
            raise ValueError('Candidate source exceeded its bounded page.')
        if page.settled:
            return HandoffScheduleOutcome('SETTLED', page.cursor, done=True)
        results = await asyncio.gather(*(self._candidate(identity) for identity in page.attempt_ids))
        reason = ('MORE_CANDIDATES' if page.more else 'NEEDS_RECONCILIATION'
                  if 'NEEDS_RECONCILIATION' in results else 'CLAIM_COMMITTED'
                  if 'CLAIM_COMMITTED' in results else page.reason)
        # Discovery confirms canonical settlement on a subsequent page. A
        # successful consumption does not imply handoff_complete or clear
        # unresolved losing attempts from earlier pages.
        return HandoffScheduleOutcome(reason, page.cursor)

    async def _candidate(self, identity):
        try:
            attempt = await self.attempts.reserve(identity)
            if attempt.state == 'RESERVED' and attempt.disposition == 'ACQUIRE':
                attempt = await asyncio.to_thread(self.attempts.claim, identity)
            if attempt.operation_id:
                await self.admission.consume(attempt.operation_id)
                return 'CLAIM_COMMITTED'
            if attempt.active:
                attempt = await self.attempts.release(identity)
            return 'NEEDS_RECONCILIATION' if attempt.active else attempt.reason or 'NO_CANDIDATES'
        except Exception:
            # The claim response could be lost AFTER commit. Release re-reads
            # durable ownership and is a no-op for a committed winner. Never
            # infer no-effect from this catch or create another operation ID.
            try:
                attempt = await self.attempts.release(identity)
                if attempt.operation_id:
                    return 'NEEDS_RECONCILIATION'
                return 'NEEDS_RECONCILIATION' if attempt.active else 'NO_CANDIDATES'
            except Exception:
                return 'NEEDS_RECONCILIATION'
