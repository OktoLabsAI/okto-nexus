"""Settle one embedded opening refused before its Core executor existed.

The association is durable before the Core admission CAS. A missing native
receipt is never used as proof of non-execution or spare capacity.
"""
import asyncio
import json
import secrets
import time

from nexus_connector_core import CoreError, OperationKey, SessionKey, project_r4_bound_receipt
from nexus_connector_core.journal import open_journal
from nexus_connector_core.protocol import canonical_json
from nexus_connector_core.startup_refusal_r4 import (
    prepare_r4_startup_refusal, persist_r4_startup_refusal,
)
from nexus_connector_core.startup_refusal_link import (
    STARTUP_REFUSAL_REVISION, decode_startup_refusal, encode_startup_refusal,
)

from ..adapters.outbound.sqlite.execution_receipts import append_execution_receipt


class EmbeddedStartupRefusal:
    page_size = 128

    def __init__(self, owner):
        self.owner = owner

    def record(self, frame):
        """Bind the original authenticated dispatch before any Core mutation."""
        owner = self.owner
        refusal = prepare_r4_startup_refusal(frame)
        raw = canonical_json(refusal).decode()
        key = frame['server_id'], frame['executor_id'], frame['operation_id']
        with owner.factory.unit_of_work() as uow:
            owner.verify(uow=uow)
            conn = uow.connection
            operation = conn.execute('SELECT session_id,subject_agent_id,intent_hash,expected_revisions_json '
                'FROM execution_operations WHERE server_id=? AND executor_id=? AND operation_id=?', key).fetchone()
            dispatch = conn.execute('SELECT dispatch_grant_id,dispatch_connection_id,connection_generation '
                'FROM execution_dispatch_outbox WHERE server_id=? AND executor_id=? AND operation_id=?', key).fetchone()
            if (operation is None or dispatch is None
                    or operation['session_id'] != frame['session_id']
                    or operation['subject_agent_id'] != frame['agent_id']
                    or operation['intent_hash'] != frame['intent_hash']
                    or json.loads(operation['expected_revisions_json']) != refusal['scope']
                    or dispatch['dispatch_grant_id'] != frame['grant_id']
                    or dispatch['dispatch_connection_id'] != frame['connection_id']
                    or dispatch['connection_generation'] != frame['connection_generation']):
                raise CoreError('SCOPE_MISMATCH', 'embedded_startup_refusal')
            prior = conn.execute('SELECT refusal_json FROM execution_local_startup_refusals '
                'WHERE server_id=? AND executor_id=? AND operation_id=?', key).fetchone()
            if prior is not None:
                if prior['refusal_json'] != raw:
                    raise CoreError('OPERATION_CONFLICT', 'embedded_startup_refusal')
                return
            conn.execute('INSERT INTO execution_local_startup_refusals '
                '(server_id,executor_id,operation_id,session_id,agent_id,refusal_json) '
                'VALUES (?,?,?,?,?,?)', (*key, frame['session_id'], frame['agent_id'], raw))

    def _pending(self, *, session_id=None, agent_id=None):
        owner = self.owner
        with owner.factory.unit_of_work(write=False) as uow:
            owner.verify(uow=uow)
            predicate = ' AND session_id=?' if session_id is not None else ' AND agent_id=?'
            value = session_id if session_id is not None else agent_id
            rows = uow.connection.execute('SELECT * FROM execution_local_startup_refusals '
                'WHERE server_id=? AND executor_id=? AND accepted_at IS NULL' + predicate +
                ' ORDER BY operation_id LIMIT ?',
                (owner.channel.server_id, owner.channel.executor_id, value, self.page_size + 1)).fetchall()
            if len(rows) > self.page_size:
                raise CoreError('CAPACITY_EXCEEDED', 'embedded_startup_refusal')
            return [dict(row) for row in rows]

    async def recover(self, *, session_id=None, agent_id=None):
        """Recheck exact Core/Server facts and publish a terminal no-effect result."""
        owner = self.owner
        rows = await asyncio.to_thread(self._pending, session_id=session_id, agent_id=agent_id)
        settled = []
        for row in rows:
            await asyncio.to_thread(owner.verify)
            refusal = json.loads(row['refusal_json'])
            source = refusal['binding']['source']
            key = OperationKey(source['server_id'], source['executor_id'], source['operation_id'])
            session = SessionKey(key.server_id, key.executor_id, row['session_id'])
            if (source['session_id'] != row['session_id'] or source['agent_id'] != row['agent_id']):
                raise CoreError('SCOPE_MISMATCH', 'embedded_startup_refusal')
            if not await owner.host.close_native_actions(executor_id=key.executor_id,
                    session_id=session.session_id, timeout_seconds=5):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_startup_refusal_tools')
            ledger = await owner.host._ledger()

            async def fence(journal):
                if (await journal.get_session_claim(session) is not None
                        or await journal.get_process_birth(session) is not None):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_startup_refusal_claim')
                fact = await persist_r4_startup_refusal(journal, refusal)
                projected = project_r4_bound_receipt(refusal['binding'], fact,
                    key=key, receipt_revision=1)
                capacity = await ledger.capacity_for_operation(key,
                    action='runtime.open', now=time.monotonic(), boot_id=owner.capacity_boot_id)
                for resource in (journal, ledger):
                    slot = await resource.owned_slot_state(session)
                    if slot is not None and not slot.released:
                        capacity_slot = ('capacity:' + capacity.reservation_id) if capacity is not None else None
                        if slot.opening_operation_id not in (key.operation_id, capacity_slot):
                            raise CoreError('SCOPE_MISMATCH', 'embedded_startup_refusal_slot')
                        if slot.opening_operation_id == key.operation_id:
                            await resource.release_owned_slot(key, session.session_id)
                if capacity is not None:
                    if (capacity.request.unit != 'new_session' or capacity.consumption is None
                            or capacity.consumption.opening_operation_id != key.operation_id
                            or capacity.consumption.opening_intent_hash != source['intent_hash']
                            or any(getattr(capacity.request.scope, name) != source[name] for name in (
                                'server_id', 'executor_id', 'agent_id', 'binding_id',
                                'session_id', 'connection_generation'))
                            or capacity.request.scope.session_owner_generation
                                != refusal['scope']['session_owner_generation']):
                        raise CoreError('SCOPE_MISMATCH', 'embedded_startup_refusal_capacity')
                    capacity = await ledger.release_capacity_slot(capacity.request,
                        capacity.reservation_id, now=time.monotonic(), boot_id=owner.capacity_boot_id)
                    if capacity.state != 'RELEASED':
                        raise CoreError('RECONCILIATION_REQUIRED', 'embedded_startup_refusal_capacity')
                for resource in (journal, ledger):
                    slot = await resource.owned_slot_state(session)
                    if slot is not None and not slot.released:
                        raise CoreError('RECONCILIATION_REQUIRED', 'embedded_startup_refusal_slot')
                return projected, None if capacity is None else capacity.to_dict()

            path = owner.host._journal_path(key.executor_id, session.session_id)
            if await asyncio.to_thread(path.is_file):
                receipt, capacity = await owner.host.with_history(
                    executor_id=key.executor_id, session_id=session.session_id, read=fence)
            else:
                # Preparation can fail before RuntimeHost composes a runtime
                # or creates its journal. The retained refusal association
                # and joined producer authorize only this canonical journal.
                journal = await open_journal(path)
                try:
                    receipt, capacity = await fence(journal)
                finally:
                    await journal.aclose()
            old = json.loads(row['report_json']) if row['report_json'] else None
            if old is not None and (old['receipt'] != receipt or old['capacity'] != capacity):
                raise CoreError('OPERATION_CONFLICT', 'embedded_startup_refusal')
            report = decode_startup_refusal(encode_startup_refusal(dict(
                contract_revision=STARTUP_REFUSAL_REVISION, type='startup.refuse',
                request_id=old['request_id'] if old else 'startup_' + secrets.token_hex(16),
                server_id=key.server_id, executor_id=key.executor_id,
                connection_id=owner.channel.connection_id,
                connection_generation=owner.channel.connection_generation,
                refusal=refusal, receipt=receipt, capacity=capacity, native_absent=True)))
            def commit():
                with owner.factory.unit_of_work() as uow:
                    owner.verify(uow=uow)
                    append_execution_receipt(None, uow=uow, startup_owner=owner.channel,
                        startup_report=report, frame=receipt)
                    uow.connection.execute('UPDATE execution_local_startup_refusals '
                        'SET report_json=?,accepted_at=? WHERE server_id=? AND executor_id=? '
                        'AND operation_id=? AND accepted_at IS NULL',
                        (canonical_json(report).decode(), owner.deps.clock.now_iso(),
                         key.server_id, key.executor_id, key.operation_id))
            await asyncio.to_thread(commit)
            await owner.tools.release_session(session.session_id)
            if owner.deps.runtime_dispatcher is not None:
                owner.deps.runtime_dispatcher.wake()
            settled.append(session.session_id)
        return settled
