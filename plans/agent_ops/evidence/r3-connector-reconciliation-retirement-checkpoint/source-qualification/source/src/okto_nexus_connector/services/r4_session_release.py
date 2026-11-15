"""Build one release report from public Core facts and acknowledged history."""
import asyncio
from hashlib import sha256
import logging
from typing import Protocol

from nexus_connector_core import (
    CoreError, EventCursor, OperationKey, SessionKey, project_r4_bound_receipt, project_r4_resource_release,
)
from nexus_connector_core.protocol import canonical_json
from nexus_connector_core.session_release import SESSION_RELEASE_REVISION, SessionReceiptDigest, encode_session_release, decode_session_release

from ..storage.r4_publications import R4PublicationStore
from ..storage.r4_events import R4EventStore
from ..storage.r4_session_releases import R4SessionReleaseStore


async def retire_resolved_checkpoint(store, request, journal, *, sequence, digest):
    """Retire an exact Server-accepted direct or reconciliation release proof."""
    events=R4EventStore.for_state(store)
    releases=R4SessionReleaseStore.for_state(store)
    scope={**request['scope'], 'stream_epoch':request['stream_epoch']}
    await asyncio.to_thread(events.retire,scope,sequence=sequence,
        release_id=request['release_id'],
        release_digest=digest)
    await journal.retire_reconciliation_claim(
        SessionKey(request['scope']['server_id'],request['scope']['executor_id'],
                   request['scope']['session_id']),
        operation_id=request['opening_operation_id'],
        release_id=request['release_id'],release_digest=digest)
    # The three stores cannot commit atomically. A lost final marker causes
    # recovery to repeat both idempotent checkpoints, never to invent an ACK.
    await asyncio.to_thread(releases.mark_checkpoints_retired,request)


async def retire_accepted_event(store, request, journal):
    """Checkpoint a direct session.release ACK after its outbox commit."""
    await retire_resolved_checkpoint(store,request,journal,
        sequence=request['sequence'],
        digest=sha256(encode_session_release(request)).hexdigest())


async def retire_reconciliation_checkpoint(store, proof, digest, journal):
    """Retire a recorded accepted recovery, never inventing a direct release."""
    opening = proof['observation']['opening']
    watermark = proof['observation']['watermark']
    key = SessionKey(opening['server_id'],opening['executor_id'],opening['session_id'])
    claim = await journal.get_session_claim(key)
    launch = await journal.get_process_launch(key)
    # Core admission never replaces a claimed session/opening generation, and
    # process-launch transitions cannot undo a fence/stop proof or replace its
    # identity. These facts therefore survive the awaits below; retirement also
    # CAS-checks the original opening operation. Mutable event progress is
    # checked separately, including by the event store's atomic retirement.
    if (claim is None or claim.opening_operation_id != opening['operation_id']
            or claim.opening_connection_generation != opening['connection_generation']
            or claim.opening_owner_generation != opening['session_owner_generation']
            or launch is None or launch.identity.key != key
            or launch.identity.opening_operation_id != opening['operation_id']
            or launch.identity.connection_generation != opening['connection_generation']
            or launch.identity.owner_generation != opening['session_owner_generation']
            or launch.producer_fenced is not True or launch.stop_proof != 'CONTAINER_STOPPED'):
        raise CoreError('RECONCILIATION_REQUIRED','reconciliation_checkpoint_owner')
    facts = await journal.drain_snapshot()
    def same(row):
        return (row['server_id'],row['executor_id'],row['session_id']) == (
            key.server_id,key.executor_id,key.session_id)
    if (facts['truncated'] or any(same(row) for row in facts['operations'])
            or any(same(row) for row in facts['streams'])
            or any(same(row) and row.get('stream_epoch') != opening['stream_epoch']
                   for name in ('claims','watermarks') for row in facts[name])
            or await journal.contiguous_watermark(EventCursor(
                key.server_id,key.executor_id,key.session_id,opening['stream_epoch'])) != watermark['sequence']):
        raise CoreError('RECONCILIATION_REQUIRED','reconciliation_checkpoint_stream')
    # Existing stores independently CAS the exact stream and immutable opening.
    # A crash between them retries the same proof ID/digest, not a new receipt.
    proof_id = 'reconcile_' + digest
    events = R4EventStore.for_state(store)
    await asyncio.to_thread(events.retire,opening,sequence=watermark['sequence'],
                            release_id=proof_id,release_digest=digest)
    await journal.retire_reconciliation_claim(key,operation_id=opening['operation_id'],
        release_id=proof_id,release_digest=digest)
    await asyncio.to_thread(R4SessionReleaseStore.for_state(store).mark_reconciliation_checkpoint_retired,
                            proof,digest)


class R4SessionReleaseReporter:
    def __init__(self, store, host):
        self.publications = R4PublicationStore.for_state(store)
        self.events = R4EventStore.for_state(store)
        self.host = host
        self.store = store

    async def retire_accepted(self, request):
        await retire_accepted_event(self.store, request,
                                    await self.host.ensure_history_journal())

    async def report(self, *, scope, connection_id, connection_generation):
        """Observe a session after its owner drains runtime/native-tool producers.

        This proof builder performs no stop, replay, authority renewal or ACK.
        Publication and its durable retry lifetime remain host responsibilities.
        """
        journal = await self.host.ensure_history_journal()
        ledger = await self.host.ensure_ledger()
        key = SessionKey(scope['server_id'],scope['executor_id'],scope['session_id'])
        claim = await journal.get_session_claim(key)
        if (claim is None or claim.opening_owner_generation != scope['session_owner_generation']
                or claim.opening_connection_generation != connection_generation):
            raise CoreError('RECONCILIATION_REQUIRED', 'session_release_claim')
        slot = await ledger.owned_slot_state(key)
        if slot is None or not slot.released:
            raise CoreError('RECONCILIATION_REQUIRED', 'session_release_slot')
        after, opening, proof = '', None, None
        digest = SessionReceiptDigest()
        # Existing Core journal bounds each session's operation history. The
        # extra budget prevents an unbounded adapter scan if history is corrupt.
        for _ in range(128):
            page = await asyncio.to_thread(self.publications.session_page,
                key.server_id, key.executor_id, key.session_id, after=after)
            if not page:
                break
            for row in page:
                metadata, receipt, binding = row['metadata'], row['receipt'], row['binding']
                if receipt is None or binding is None or not row['acknowledged']:
                    raise CoreError('RECONCILIATION_REQUIRED', 'session_release_publication')
                operation_key = OperationKey(key.server_id,key.executor_id,metadata['operation_id'])
                fact = await journal.get_receipt(operation_key)
                if fact is None or project_r4_bound_receipt(binding, fact, key=operation_key,
                        receipt_revision=receipt['receipt_revision']) != receipt:
                    # The normal retained publisher must commit this newer fact.
                    # Observing old acknowledged bytes alone is insufficient.
                    raise CoreError('RECONCILIATION_REQUIRED', 'session_release_receipt')
                digest.add(receipt)
                if metadata['operation_id'] == claim.opening_operation_id:
                    if (any(metadata[k] != scope[k] for k in ('server_id','executor_id','binding_id',
                            'agent_id','session_id','session_owner_generation'))
                            or metadata['connection_id'] != connection_id
                            or metadata['connection_generation'] != connection_generation):
                        raise CoreError('SCOPE_MISMATCH', 'session_release_opening')
                    opening = row
                    proof = project_r4_resource_release(binding, claim, slot, fact)
                after = metadata['operation_id']
        else:
            raise CoreError('CAPACITY_EXCEEDED', 'session_release_history')
        if opening is None or proof is None or not opening['metadata'].get('stream_epoch'):
            raise CoreError('RECONCILIATION_REQUIRED', 'session_release_opening')
        epoch = opening['metadata']['stream_epoch']
        cursor = EventCursor(key.server_id,key.executor_id,key.session_id,epoch)
        sequence = await journal.contiguous_watermark(cursor)
        remaining = journal.events(EventCursor(key.server_id,key.executor_id,key.session_id,epoch,sequence))
        try:
            async for _ in remaining:
                raise CoreError('EVENT_GAP', 'session_release_stream')
        finally:
            close = getattr(remaining, 'aclose', None)
            if close is not None: await close()
        progress = await asyncio.to_thread(self.events.read, opening['metadata'])
        if progress['remote_acked'] != sequence or progress['core_applied'] != sequence:
            raise CoreError('EVENT_GAP', 'session_release_stream')
        count, receipt_digest = digest.snapshot()
        request = dict(contract_revision=SESSION_RELEASE_REVISION, type='session.release',
            server_id=key.server_id, executor_id=key.executor_id, connection_id=connection_id,
            connection_generation=connection_generation, scope=scope, opening_operation_id=claim.opening_operation_id,
            opening_intent_hash=opening['receipt']['intent_hash'], proof_digest=proof['proof_digest'],
            stream_epoch=epoch, sequence=sequence, receipt_count=count, receipt_digest=receipt_digest)
        # A deferred report can be superseded when receipt/event history moves.
        # Every distinct observation has a distinct ID; unknown outcomes must
        # replay the original stored bytes, never rebuild under the same ID.
        request['release_id'] = 'release_' + sha256(canonical_json(request)).hexdigest()
        return decode_session_release(encode_session_release(request))


class SessionReleaseOutbox(Protocol):
    def pending(self, *, scope, connection_id, connection_generation): ...
    def prepare(self, request): ...
    def acknowledge(self, reply): ...


class SessionReleaseRecoveryOutbox(Protocol):
    def reconcile_page(self, ack, observations, *, after=0, limit=128): ...
    def resolved_checkpoint_page(self, server_id, executor_id, *, after=0, limit=128): ...
    def record_reconciliation_checkpoints(self, ack, observations): ...
    def reconciliation_checkpoint_page(self, server_id, executor_id, *, after=0, limit=128): ...


class R4SessionReleasePublisher:
    """Publish durable observations; the caller owns and joins this producer.

    Only a correlated deferred response permits a new observation. An unknown
    result retains the old request, including across reconstruction of this
    service. Reconnection under another generation uses global reconciliation,
    never rewriting this original channel's proof or native operation.
    """
    def __init__(self, outbox: SessionReleaseOutbox, reporter, publish, *, on_accepted=None):
        self.outbox, self.reporter, self.publish = outbox, reporter, publish
        self.on_accepted=on_accepted

    async def run(self, *, scope, connection_id, connection_generation, stop_event):
        identity = dict(scope=scope, connection_id=connection_id,
                        connection_generation=connection_generation)
        while not stop_event.is_set():
            request = await asyncio.to_thread(self.outbox.pending, **identity)
            if request is None:
                request = await self.reporter.report(**identity)
                request = await asyncio.to_thread(self.outbox.prepare, request)
            if stop_event.is_set():
                return False
            reply = await self.publish(request, stop_event=stop_event)
            # Shutdown/caller cancellation does not discard an ACK already
            # received: this retained producer commits it before returning.
            await asyncio.to_thread(self.outbox.acknowledge, reply)
            if reply['type'] == 'session.release.accepted':
                if self.on_accepted is not None:
                    try:
                        await self.on_accepted(request)
                    except Exception as error:
                        logging.getLogger(__name__).warning(
                            'Terminal event checkpoint deferred: type=%s code=%s stage=%s',
                            type(error).__name__,getattr(error,'code',None),getattr(error,'stage',None))
                return True
            try:
                await asyncio.wait_for(stop_event.wait(), .25)
            except TimeoutError:
                pass
        return False
