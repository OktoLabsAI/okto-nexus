"""Fence interrupted local openings using Core's positive admission protocol.

A missing receipt is not proof of non-execution. Persist the association first,
then let Core's admission CAS exclude the original producer before releasing
capacity and closing the Server session. This applies to every local harness.
"""
import asyncio
import json
import time

from nexus_connector_core import CoreError, EventCursor, OperationKey, SessionKey, project_r4_bound_receipt
from nexus_connector_core.preopen_refusal_r4 import prepare_r4_preopen_refusal, persist_r4_preopen_refusal
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.sqlite.execution_receipts import append_execution_receipt


class EmbeddedPreopenRecovery:
    def __init__(self, owner):
        self.owner = owner

    def _rows(self, agent_id):
        owner = self.owner
        with owner.factory.unit_of_work(write=False) as uow:
            owner.verify(uow=uow)
            return [dict(r) for r in uow.connection.execute(
                "SELECT p.*,o.expected_revisions_json,l.stream_epoch,f.refusal_json,r.report_json "
                "FROM execution_local_publications p JOIN execution_operations o USING(server_id,executor_id,operation_id) "
                "JOIN execution_local_streams l ON l.server_id=p.server_id AND l.executor_id=p.executor_id "
                "AND l.session_id=p.session_id AND l.opening_operation_id=p.operation_id "
                "JOIN execution_sessions s ON s.server_id=p.server_id AND s.executor_id=p.executor_id "
                "AND s.session_id=p.session_id "
                "LEFT JOIN execution_local_preopen_fences f USING(server_id,executor_id,operation_id) "
                "LEFT JOIN execution_preopen_refusals r USING(server_id,executor_id,operation_id) "
                "WHERE p.server_id=? AND p.executor_id=? AND o.subject_agent_id=? AND o.action='runtime.open' "
                "AND s.local_retirement_json IS NULL "
                "AND (f.operation_id IS NOT NULL OR NOT EXISTS (SELECT 1 FROM execution_receipts x "
                "WHERE x.server_id=p.server_id AND x.executor_id=p.executor_id AND x.operation_id=p.operation_id)) "
                "ORDER BY p.rowid LIMIT 32769",
                (owner.channel.server_id, owner.channel.executor_id, agent_id))]

    def _prepare(self, row):
        owner = self.owner
        with owner.factory.unit_of_work() as uow:
            owner.verify(uow=uow)
            key = (row['server_id'], row['executor_id'], row['operation_id'])
            previous = uow.connection.execute('SELECT refusal_json FROM execution_local_preopen_fences '
                'WHERE server_id=? AND executor_id=? AND operation_id=?', key).fetchone()
            if previous:
                return json.loads(previous[0])
            binding = json.loads(row['binding_json'])
            refusal = prepare_r4_preopen_refusal(binding['source'], prior_binding=binding,
                session_owner_generation=json.loads(row['expected_revisions_json'])['session_owner_generation'],
                recovery=dict(connection_id=owner.channel.connection_id,
                              connection_generation=owner.channel.connection_generation))
            uow.connection.execute('INSERT INTO execution_local_preopen_fences VALUES(?,?,?,?)',
                (*key, canonical_json(refusal).decode()))
            return refusal

    def _commit(self, report):
        owner, source = self.owner, report['refusal']['source']
        with owner.factory.unit_of_work() as uow:
            owner.verify(uow=uow)
            append_execution_receipt(None, uow=uow, recovery_owner=owner.channel,
                preopen_embedded_owner=owner, preopen=report, frame=report['receipt'])
            # Keep the original association for audit. The refusal has its own
            # binding, and must never be republished through the original one.
            uow.connection.execute('UPDATE execution_local_publications SET terminal=1 '
                'WHERE server_id=? AND executor_id=? AND operation_id=?',
                (source['server_id'], source['executor_id'], source['operation_id']))
            uow.connection.execute('UPDATE execution_local_streams SET drained=1 '
                'WHERE server_id=? AND executor_id=? AND session_id=?',
                (source['server_id'], source['executor_id'], source['session_id']))
    def _checkpoint(self, report):
        owner, source = self.owner, report['refusal']['source']
        with owner.factory.unit_of_work() as uow:
            owner.verify(uow=uow)
            # The durable refusal excludes native opening. Capacity and an
            # empty stream were proved before _commit; tool cleanup has now
            # completed as well. A cleanup failure leaves this checkpoint absent.
            row = uow.connection.execute('SELECT s.owner_generation,s.local_retirement_revision,l.stream_epoch '
                'FROM execution_sessions s JOIN execution_local_streams l '
                'USING(server_id,executor_id,session_id) WHERE s.server_id=? AND s.executor_id=? '
                'AND s.session_id=?',
                (source['server_id'], source['executor_id'], source['session_id'])).fetchone()
            from .embedded_retirement import EmbeddedRetirement
            EmbeddedRetirement(owner).commit(source['session_id'], dict(
                server_id=source['server_id'], executor_id=source['executor_id'], session_id=source['session_id'],
                opening_operation_id=source['operation_id'], owner_generation=row['owner_generation'],
                stream_epoch=row['stream_epoch'], committed_sequence=0,
                release_kind='preopen_refusal', retirement_revision=row['local_retirement_revision']), uow=uow)

    async def recover(self, agent_id):
        owner = self.owner
        rows = await asyncio.to_thread(self._rows, agent_id)
        if len(rows) > 32768:
            raise CoreError('CAPACITY_EXCEEDED', 'embedded_preopen_recovery')
        for row in rows:
            binding = json.loads(row['binding_json'])
            if binding['source']['connection_generation'] >= owner.channel.connection_generation:
                continue  # Never fence a producer belonging to this live owner.
            key = OperationKey(row['server_id'], row['executor_id'], row['operation_id'])
            session = SessionKey(key.server_id, key.executor_id, row['session_id'])
            ledger = await owner.host._ledger()

            async def recover(journal):
                # Existing native admission always follows normal recovery;
                # exception flags or an absent process cannot replace it.
                receipt = await journal.get_receipt(key)
                claim = await journal.get_session_claim(session)
                if row['refusal_json'] is None and (receipt is not None or claim is not None):
                    return
                if claim is not None or await journal.get_process_birth(session) is not None:
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_claim')
                cursor = EventCursor(key.server_id, key.executor_id, session.session_id, row['stream_epoch'])
                if await journal.contiguous_watermark(cursor):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_events')
                refusal = await asyncio.to_thread(self._prepare, row)
                await asyncio.to_thread(owner.verify)
                fact = await persist_r4_preopen_refusal(journal, refusal)
                frame = project_r4_bound_receipt(refusal['binding'], fact, key=key, receipt_revision=1)
                if await journal.get_session_claim(session) is not None:
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_claim')
                capacity = await ledger.capacity_for_operation(key, action='runtime.open',
                    now=time.monotonic(), boot_id=owner.capacity_boot_id)
                if capacity is not None and (capacity.request.unit != 'new_session'
                        or capacity.consumption is None
                        or capacity.consumption.opening_operation_id != key.operation_id
                        or capacity.consumption.opening_intent_hash != binding['source']['intent_hash']
                        or any(getattr(capacity.request.scope, name) != value
                               for name, value in json.loads(row['expected_revisions_json']).items())):
                    raise CoreError('SCOPE_MISMATCH', 'embedded_preopen_capacity')
                for resource in (journal, ledger):
                    slot = await resource.owned_slot_state(session)
                    if slot is not None and not slot.released and slot.opening_operation_id == key.operation_id:
                        await resource.release_owned_slot(key, session.session_id)
                if capacity is not None:
                    capacity = await ledger.release_capacity_slot(capacity.request, capacity.reservation_id,
                        now=time.monotonic(), boot_id=owner.capacity_boot_id)
                    if capacity.state != 'RELEASED':
                        raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_capacity')
                journal_slot = await journal.owned_slot_state(session)
                if journal_slot is not None and not journal_slot.released:
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_slot')
                slot = await ledger.owned_slot_state(session)
                slot_fact = None if slot is None else dict(server_id=slot.key.server_id,
                    executor_id=slot.key.executor_id, session_id=slot.key.session_id,
                    opening_operation_id=slot.opening_operation_id, released=slot.released)
                report = dict(refusal=refusal, receipt=frame,
                    capacity=None if capacity is None else capacity.to_dict(), slot=slot_fact)
                if row['report_json'] is not None:
                    # Retain the exact acknowledged report across later boots.
                    # The live slot checks above still precede this replay.
                    previous = json.loads(row['report_json'])
                    if previous['refusal'] != refusal or previous['receipt'] != frame or slot is not None and not slot.released:
                        raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_report')
                    report = previous
                await asyncio.to_thread(self._commit, report)
                await owner.tools.release_session(session.session_id)
                await asyncio.to_thread(self._checkpoint, report)

            await owner.host.with_history(executor_id=key.executor_id, session_id=session.session_id, read=recover)
