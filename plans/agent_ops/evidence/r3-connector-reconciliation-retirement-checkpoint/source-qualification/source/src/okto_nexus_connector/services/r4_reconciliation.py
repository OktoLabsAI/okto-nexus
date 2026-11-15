"""Bounded reconciliation from public Core facts and persisted wire bindings."""
import asyncio
import copy
import logging
import secrets

from nexus_connector_core import EventCursor, OperationKey, project_r4_bound_receipt, project_r4_resource_release, decode_r4_frame, encode_r4_frame

from ..errors import ConnectorError
from ..storage.r4_publications import R4PublicationStore
from .r4_session_release import (
    SessionReleaseRecoveryOutbox, retire_resolved_checkpoint, retire_reconciliation_checkpoint,
)


class R4ReconciliationReporter:
    def __init__(self, store, host, server_id, executor_id, *, release_outbox: SessionReleaseRecoveryOutbox | None = None,
                 boot_id='reconciliation', validate_authority=None, publish_receipts=None):
        self.publications = R4PublicationStore.for_state(store)
        self.store = store
        from ..storage.r4_events import R4EventStore
        self.event_store = R4EventStore.for_state(store)
        self.host, self.server_id, self.executor_id = host, server_id, executor_id
        self.cycle = None
        self.cursor = None
        self.after, self.high = 0, None
        self.claims_done = False
        self.blocked = False
        self.requested_sessions, self.seen_sessions = set(), set()
        if release_outbox is None:
            from ..storage.r4_session_releases import R4SessionReleaseStore
            release_outbox = R4SessionReleaseStore.for_state(store)
        self.release_outbox = release_outbox
        self._release_observations = {}
        self._report_complete = False
        self.boot_id = boot_id
        self.validate_authority, self.publish_receipts = validate_authority, publish_receipts
        self._preopen_reports, self._preopen_sent, self._preopen_after = [], {}, 0
        self._unstarted_sessions = set()
        self._checkpoint_task = None
        self._checkpoint_epoch = 0

    def require_authority(self, request):
        if self.validate_authority is None:
            raise ConnectorError('RECONCILIATION_REQUIRED', 'launch_recovery',
                                 'A live replacement owner is required for process recovery.')
        self.validate_authority(request)

    async def accepted(self, ack):
        """Called only after the authenticated transport validates this ACK."""
        ack = decode_r4_frame(encode_r4_frame(ack))
        if (ack['type'] != 'reconcile.accepted' or ack['recovery_remaining']
                or (ack['server_id'], ack['executor_id']) != (self.server_id, self.executor_id)
                or tuple(ack[k] for k in ('connection_id', 'connection_generation', 'reconcile_id')) != self.cycle
                or not self._report_complete or self.cursor is not None or self.blocked):
            raise ConnectorError('RECONCILIATION_REQUIRED', 'session_release',
                                 'The original complete reconciliation was not confirmed.')
        # Capture the exact completed cycle before the first worker await. A
        # later report must not lend its facts to this earlier authenticated ACK.
        accepted_observations = copy.deepcopy(self._release_observations)
        accepted_preopen = tuple(self._preopen_sent.values())
        for frame in accepted_preopen:
            await asyncio.to_thread(self.publications.acknowledge, frame)
        after = 0
        for _ in range(256):
            next_after = await asyncio.to_thread(self.release_outbox.reconcile_page,
                ack, accepted_observations, after=after)
            if next_after is None:
                break
            if next_after <= after:
                raise ConnectorError('JOURNAL_UNAVAILABLE', 'session_release', 'The recovery cursor did not advance.')
            after = next_after
        else:
            raise ConnectorError('RECONCILIATION_REQUIRED', 'session_release', 'Release recovery exceeded its page budget.')
        observations = list(accepted_observations.items())
        for offset in range(0,len(observations),128):
            await asyncio.to_thread(self.release_outbox.record_reconciliation_checkpoints,
                ack,dict(observations[offset:offset+128]))
        # Only the release proof commit gates readiness. Maintenance starts
        # independently and rechecks if another accepted cycle arrives while
        # its previous pass is still running.
        self._checkpoint_epoch += 1
        if self._checkpoint_task is None or self._checkpoint_task.done():
            self._checkpoint_task=asyncio.create_task(self._retire_resolved_checkpoints())

    async def _retire_resolved_checkpoints(self):
        """Keep historical cleanup outside the connection's readiness path."""
        log=logging.getLogger(__name__)
        while True:
            epoch=self._checkpoint_epoch
            for attempt in range(3):
                after,failed=0,False
                try:
                    journal=await self.host.ensure_history_journal()
                    while True:
                        page=await asyncio.to_thread(self.release_outbox.resolved_checkpoint_page,
                            self.server_id,self.executor_id,after=after)
                        if not page: break
                        for after,request,sequence,digest in page:
                            try:
                                await retire_resolved_checkpoint(self.store,request,journal,
                                    sequence=sequence,digest=digest)
                            except Exception as error:
                                failed=True
                                log.warning('Resolved checkpoint deferred: type=%s code=%s stage=%s',
                                    type(error).__name__,getattr(error,'code',None),getattr(error,'stage',None))
                        if len(page)<128: break
                        await asyncio.sleep(0)
                    after = 0
                    while True:
                        page = await asyncio.to_thread(self.release_outbox.reconciliation_checkpoint_page,
                            self.server_id,self.executor_id,after=after)
                        if not page:
                            break
                        for after,proof,digest in page:
                            try:
                                await retire_reconciliation_checkpoint(self.store,proof,digest,journal)
                            except Exception as error:
                                failed = True
                                log.warning('Reconciliation checkpoint deferred: type=%s code=%s stage=%s',
                                    type(error).__name__,getattr(error,'code',None),getattr(error,'stage',None))
                        if len(page)<128:
                            break
                        await asyncio.sleep(0)
                except Exception as error:
                    failed=True
                    log.warning('Resolved checkpoint scan deferred: type=%s code=%s stage=%s',
                        type(error).__name__,getattr(error,'code',None),getattr(error,'stage',None))
                if not failed: break
                if attempt<2: await asyncio.sleep(2**attempt)
            if self._checkpoint_epoch==epoch: return

    async def _fact(self, row, journal):
        if row is None or row['binding'] is None:
            return None
        source = row['binding']['source']
        key = OperationKey(self.server_id, self.executor_id, source['operation_id'])
        fact = await journal.get_receipt(key)
        if fact is None:
            return None
        previous = row['receipt']
        revision = previous['receipt_revision'] if previous else 1
        projected = project_r4_bound_receipt(row['binding'], fact, key=key, receipt_revision=revision)
        if projected != previous:
            if previous:
                projected['receipt_revision'] += 1
            await asyncio.to_thread(self.publications.record, projected)
            self.blocked = True  # HTTP must commit this exact revision first.
        return projected

    async def report(self, request):
        if (request['server_id'], request['executor_id']) != (self.server_id, self.executor_id):
            raise ConnectorError('SCOPE_MISMATCH', 'r4_reconcile', 'The reconciliation scope changed.')
        if request.get('preopen_refusal_supported') is not True and await asyncio.to_thread(
                self.publications.pending, self.server_id, self.executor_id):
            raise ConnectorError('RECONCILIATION_REQUIRED', 'r4_reconcile', 'Receipt publication must finish before reconciliation.')
        if request.get('stream_watermarks'):
            raise ConnectorError('RECONCILIATION_REQUIRED', 'r4_reconcile', 'Event stream recovery is required.')
        cycle = tuple(request[k] for k in ('connection_id', 'connection_generation', 'reconcile_id'))
        if request['cursor'] is None:
            self.cycle, self.cursor = cycle, None
            self.after, self.high, self.claims_done, self.blocked = 0, None, False, False
            self.requested_sessions, self.seen_sessions = set(), set()
            self.seen_sessions.update(await asyncio.to_thread(
                self.publications.recovered_startup_sessions,
                self.server_id, self.executor_id,
                generation=request['connection_generation'],
                session_ids=request['session_ids']))
            self._release_observations = {}
            self._report_complete = False
            self._preopen_reports, self._preopen_sent, self._preopen_after = [], {}, 0
            self._unstarted_sessions = set()
            if request.get('preopen_refusal_supported') is True:
                from .r4_preopen_recovery import recover_preopen_publications
                self._preopen_reports = await recover_preopen_publications(
                    self.publications, self.host, request, boot_id=self.boot_id)
        elif cycle != self.cycle or request['cursor'] != self.cursor:
            raise ConnectorError('STALE_GENERATION', 'r4_reconcile', 'The reconciliation cursor is stale.')
        pending = self.publications.pending_unfenced if request.get('preopen_refusal_supported') is True else self.publications.pending
        if await asyncio.to_thread(pending, self.server_id, self.executor_id):
            raise ConnectorError('RECONCILIATION_REQUIRED', 'r4_reconcile', 'Receipt publication must finish before reconciliation.')
        self.seen_sessions.update(item['refusal']['source']['session_id'] for item in self._preopen_reports)
        self.requested_sessions.update(request['session_ids'])
        if len(self.requested_sessions) > 32768:
            raise ConnectorError('CAPACITY_EXCEEDED', 'r4_reconcile', 'The reconciliation session budget is exhausted.')
        journal = await self.host.ensure_history_journal()
        ledger = await self.host.ensure_ledger()
        if request['cursor'] is None:
            from .r4_launch_recovery import recover_launches
            await recover_launches(self, journal, ledger, request)
            from .r4_denied_capacity import recover_denied_opening_capacity
            await recover_denied_opening_capacity(self, journal, ledger, request)
        # The authenticated recovery channel supplies the replacement
        # generation. Old HELD reservations are cancellable without a native
        # process proof; consumed or uncertain records must still block below.
        for _ in range(32):
            released = await ledger.release_fenced_capacity_holds(self.server_id, self.executor_id,
                connection_generation=request['connection_generation'], limit=128)
            if released < 128:
                break
        else:
            raise ConnectorError('RECONCILIATION_REQUIRED', 'capacity_reconcile',
                                 'The capacity recovery scan requires another pass.')
        # Live/unreleased slots cannot be adopted as stopped resources.
        for source in (journal, ledger):
            after, high = 0, None
            for _ in range(32):
                page = await source.owned_slot_page(after_rowid=after, high_water_rowid=high, limit=128)
                if any((r.key.server_id, r.key.executor_id) == (self.server_id, self.executor_id) for r in page.reservations):
                    raise ConnectorError('RECONCILIATION_REQUIRED', 'r4_reconcile', 'Owned resources require live recovery.')
                high = page.high_water_rowid
                if page.next_after_rowid is None:
                    break
                if page.next_after_rowid <= after:
                    raise ConnectorError('JOURNAL_UNAVAILABLE', 'r4_reconcile', 'The ownership cursor did not advance.')
                after = page.next_after_rowid
            else:
                raise ConnectorError('RECONCILIATION_REQUIRED', 'r4_reconcile', 'The ownership scan requires another recovery pass.')
        rows = await asyncio.to_thread(self.publications.lookup, self.server_id, self.executor_id, request['operation_ids'])
        receipts = []
        for operation_id in request['operation_ids']:
            fact = await self._fact(rows.get(operation_id), journal)
            if fact is None:
                if self._preopen_reports or request.get('launch_recovery_supported') and self._unstarted_sessions:
                    # Only the Server can retire never-dispatched children of
                    # these exact openings. Omit a missing fact; its canonical
                    # checks must reject any other unexplained operation.
                    continue
                raise ConnectorError('RECONCILIATION_REQUIRED', 'r4_reconcile', 'The requested operation has no verified Core receipt.')
            else:
                receipts.append({k: fact[k] for k in ('operation_id', 'intent_hash', 'receipt_revision', 'stage')})
        claims, facts, watermarks = [], [], []
        if not self.claims_done:
            page = await journal.claimed_sessions(self.server_id, self.executor_id,
                after_rowid=self.after, high_water_rowid=self.high, limit=128,
                pending_only=True)
            self.high = page.high_water_rowid
            for claim in page.claims:
                self.seen_sessions.add(claim.key.session_id)
                history = await asyncio.to_thread(self.publications.session_history,
                    self.server_id, self.executor_id, claim.key.session_id)
                generation = claim.opening_owner_generation
                closed = None
                opening = None
                for row in history:
                    metadata = row['metadata']
                    if metadata.get('session_owner_generation') != generation:
                        continue
                    if metadata['operation_id'] == claim.opening_operation_id:
                        opening = row
                    if metadata['action'] == 'runtime.close':
                        observed = await self._fact(row, journal)
                        if observed is not None and observed['stage'] == 'SUCCEEDED':
                            closed = row
                release_fact = None
                if closed is None and opening is not None and opening['binding'] is not None:
                    slot = await ledger.owned_slot_state(claim.key)
                    launch = await journal.get_process_launch(claim.key)
                    never_claimed = launch is not None and launch.stop_proof == 'NEVER_CLAIMED'
                    if never_claimed or slot is not None and slot.released:
                        opening_receipt = await journal.get_receipt(OperationKey(
                            self.server_id, self.executor_id, claim.opening_operation_id))
                        if opening_receipt is not None:
                            if never_claimed:
                                if request.get('launch_recovery_supported') is not True:
                                    raise ConnectorError('VERSION_INCOMPATIBLE', 'launch_recovery',
                                                         'Never-started recovery was not negotiated.')
                                from nexus_connector_core.launch_release_r4 import project_r4_unstarted_release
                                release_fact = project_r4_unstarted_release(
                                    opening['binding'], claim, slot, opening_receipt, launch,
                                    journal_slot=await journal.owned_slot_state(claim.key),
                                    birth=await journal.get_process_birth(claim.key))
                            else:
                                release_fact = project_r4_resource_release(
                                    opening['binding'], claim, slot, opening_receipt)
                released = (closed is not None or release_fact is not None) and opening is not None and opening['metadata'].get('stream_epoch') is not None
                generation = generation if generation is not None else 0
                claims.append(dict(session_id=claim.key.session_id, owner_generation=generation,
                                   state='RELEASED' if released else 'UNKNOWN'))
                facts.append(dict(session_id=claim.key.session_id, owner_generation=generation,
                                  process_state='EXITED' if released else 'UNKNOWN'))
                if release_fact is not None:
                    facts[-1].update(release_fact)
                if released:
                    facts[-1]['proof_digest'] = (release_fact['proof_digest'] if release_fact is not None
                                                   else closed['binding']['digest'])
                    epoch = opening['metadata']['stream_epoch']
                    sequence = await journal.contiguous_watermark(EventCursor(
                        self.server_id, self.executor_id, claim.key.session_id, epoch))
                    watermarks.append(dict(session_id=claim.key.session_id, stream_epoch=epoch, sequence=sequence))
                    remaining = journal.events(EventCursor(self.server_id,self.executor_id,claim.key.session_id,epoch,sequence))
                    try:
                        async for _ in remaining:
                            self.blocked = True
                            break
                    finally:
                        close = getattr(remaining,'aclose',None)
                        if close is not None:
                            await close()
                    if sequence > 0:
                        progress = await asyncio.to_thread(self.event_store.read,
                            {**opening['metadata'],'stream_epoch':epoch})
                        self.blocked |= progress['remote_acked'] != sequence or progress['core_applied'] != sequence
                    if len(self._release_observations) >= 32768:
                        raise ConnectorError('CAPACITY_EXCEEDED', 'session_release', 'The recovery fact budget is exhausted.')
                    self._release_observations[(claim.key.session_id, generation)] = dict(
                        opening=dict(opening['metadata']), claim=dict(claims[-1]),
                        fact=dict(facts[-1]), watermark=dict(watermarks[-1]))
                else:
                    self.blocked = True
            if page.next_after_rowid is None:
                self.claims_done = True
            elif page.next_after_rowid <= self.after:
                raise ConnectorError('JOURNAL_UNAVAILABLE', 'r4_reconcile', 'The claim cursor did not advance.')
            else:
                self.after = page.next_after_rowid
        if self.claims_done and self.requested_sessions - self.seen_sessions:
            raise ConnectorError('RECONCILIATION_REQUIRED', 'r4_reconcile', 'The requested session has no durable Core claim.')
        # Leave wire budget for the ordinary receipt/claim page. Capacity and
        # prior-binding evidence can make count-only pages exceed 1 MiB.
        from nexus_connector_core.protocol import canonical_json
        preopen_page, preopen_bytes = [], 0
        for item in self._preopen_reports[self._preopen_after:self._preopen_after + 128]:
            size = len(canonical_json(item)) + 1
            if preopen_bytes + size > 384 * 1024:
                if not preopen_page:
                    raise ConnectorError('CAPACITY_EXCEEDED', 'r4_preopen', 'The recovery proof exceeds its page budget.')
                break
            preopen_page.append(item)
            preopen_bytes += size
        self._preopen_after += len(preopen_page)
        for item in preopen_page:
            self._preopen_sent[item['receipt']['operation_id']] = item['receipt']
        complete = (self.claims_done and self._preopen_after == len(self._preopen_reports)
                    and len(request['operation_ids']) < 256 and len(request['session_ids']) < 256)
        self._report_complete = complete
        self.cursor = None if complete else 'page_' + secrets.token_hex(16)
        return {k: request[k] for k in ('protocol_major', 'contract_revision', 'server_id', 'executor_id',
            'connection_id', 'connection_generation', 'reconcile_id', 'cursor')} | dict(
                type='reconcile.report', next_cursor=self.cursor, complete=complete,
                receipts=receipts, claims=claims, ownership_facts=facts, stream_watermarks=watermarks) | (
                    {'preopen_refusals': preopen_page} if preopen_page else {}) | (
                    {'launch_recovery_supported': True} if request.get('launch_recovery_supported') is True else {})
