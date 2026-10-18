"""Retire proven non-admission without inventing an executed stream or exit."""
import asyncio
import hashlib
import json
import time

from nexus_connector_core import (
    CapacityConsumption, CapacityReservation, CoreError, OperationKey, OperationReceipt, SessionKey,
)


class EmbeddedUnopenedRetirement:
    def __init__(self, owner):
        self.owner = owner

    def _read(self, session_id, *, uow):
        owner, db = self.owner, uow.connection
        owner.verify(uow=uow)
        key = owner.channel.server_id, owner.channel.executor_id, session_id
        session = db.execute('SELECT * FROM execution_sessions WHERE server_id=? '
            'AND executor_id=? AND session_id=?', key).fetchone()
        if (session is None or session['lifecycle_state'] not in ('FAILED', 'CLOSED')
                or session['lease_state'] not in ('NONE', 'CLOSED') or session['stream_epoch'] is not None):
            return None
        for table in ('execution_local_streams', 'execution_event_watermarks', 'execution_event_ingress'):
            if db.execute(f'SELECT 1 FROM {table} WHERE server_id=? AND executor_id=? '
                    'AND session_id=? LIMIT 1', key).fetchone():
                return None
        operations = db.execute('SELECT operation_id,action,intent_hash,admission_state '
            'FROM execution_operations WHERE server_id=? AND executor_id=? AND session_id=?', key).fetchall()
        opening = next((r for r in operations if r['operation_id'] == session['open_operation_id']), None)
        if opening is None or opening['action'] != 'runtime.open' or any(
                row['admission_state'] != 'RESOLVED_TERMINAL' for row in operations):
            return None
        publications = db.execute('SELECT operation_id,binding_json,terminal FROM execution_local_publications '
            'WHERE server_id=? AND executor_id=? AND session_id=?', key).fetchall()
        receipts = db.execute('SELECT r.* FROM execution_receipts r JOIN execution_operations o '
            'USING(server_id,executor_id,operation_id) WHERE o.server_id=? AND o.executor_id=? '
            'AND o.session_id=? ORDER BY r.receipt_revision', key).fetchall()
        startup = db.execute('SELECT refusal_json,report_json,accepted_at '
            'FROM execution_local_startup_refusals WHERE server_id=? AND executor_id=? '
            'AND operation_id=? AND session_id=?', (*key[:2], opening['operation_id'], session_id)).fetchone()
        binding = None
        if publications or receipts:
            # Only the authenticated refusal of the original opening qualifies.
            # A missing stream for anything possibly executed stays unverified.
            if (startup is not None and startup['accepted_at'] is not None
                    and not publications and len(receipts) == 1):
                from nexus_connector_core.startup_refusal_link import decode_startup_refusal
                report = decode_startup_refusal(startup['report_json'].encode())
                if (report['refusal'] != json.loads(startup['refusal_json'])
                        or report['receipt'] != json.loads(receipts[0]['canonical_frame'])
                        or report['capacity'] is None and db.execute(
                            'SELECT 1 FROM execution_capacity_admissions WHERE server_id=? '
                            'AND executor_id=? AND session_id=?', key).fetchone()):
                    return None
                binding = report['refusal']['binding']
                if (receipts[0]['operation_id'] != opening['operation_id']
                        or receipts[0]['stage'] != 'FAILED'
                        or receipts[0]['error_code'] != 'PREPARATION_FAILED'
                        or receipts[0]['possible_effect'] or not receipts[0]['retry_safe']):
                    return None
                evidence_kind = 'startup_refusal'
                evidence = [startup['refusal_json'], startup['report_json'], receipts[0]['canonical_frame']]
            elif (len(publications) != 1 or not receipts or publications[0]['terminal'] != 1
                    or publications[0]['operation_id'] != opening['operation_id']
                    or any(r['operation_id'] != opening['operation_id'] or r['stage'] != 'FAILED'
                        or r['error_code'] != 'LEASE_REVALIDATION_REQUIRED'
                        or r['possible_effect'] or not r['retry_safe'] for r in receipts)):
                return None
            else:
                denial = db.execute('SELECT * FROM execution_session_containment WHERE server_id=? '
                    'AND executor_id=? AND session_id=? AND owner_generation=?',
                    (*key, session['owner_generation'])).fetchone()
                if (denial is None or denial['state'] != 'RELEASED'
                        or denial['opening_operation_id'] != opening['operation_id']
                        or denial['opening_intent_hash'] != opening['intent_hash']
                        or json.loads(denial['request_json']).get('purpose') != 'initial'):
                    return None
                from .embedded_initial_refusal import EmbeddedInitialRefusal
                rows = self.owner.access.session_containment.repository.initial_refusal_records(
                    uow, owner.channel, session_id=session_id, pending_only=False)
                if len(rows) != 1:
                    return None
                binding = EmbeddedInitialRefusal.proof(rows[0])['binding']
                evidence_kind = 'initial_lease_refusal'
                evidence = [denial['request_json'], publications[0]['binding_json'], receipts[-1]['canonical_frame']]
        else:
            dispatch = db.execute('SELECT dispatch_state,last_error FROM execution_dispatch_outbox '
                'WHERE server_id=? AND executor_id=? AND operation_id=?', (*key[:2], opening['operation_id'])).fetchone()
            error = json.loads(dispatch['last_error'] or '{}') if dispatch else {}
            if (session['lifecycle_state'] != 'FAILED' or dispatch is None
                    or dispatch['dispatch_state'] != 'RESOLVED_TERMINAL'
                    or error.get('possible_effect') is not False
                    or not (error.get('stage') == 'dispatch' or (
                        error.get('code') == 'LOCAL_PREOPEN_FAILED'
                        and error.get('proof') == 'fenced_owner_no_publication_no_core_claim_receipt_or_slot'))):
                return None
            evidence_kind, evidence = 'dispatch_refusal', [dispatch['last_error']]
        capacity = db.execute('SELECT reservation_json,consumption_json FROM execution_capacity_admissions '
            'WHERE server_id=? AND executor_id=? AND session_id=?', key).fetchone()
        evidence.append(dict(capacity) if capacity else None)
        proof = dict(version=1, server_id=key[0], executor_id=key[1], session_id=session_id,
            opening_operation_id=opening['operation_id'], owner_generation=session['owner_generation'],
            opening_intent_hash=opening['intent_hash'],
            retirement_revision=session['local_retirement_revision'], release_kind='no_native_admission',
            evidence_kind=evidence_kind,
            evidence_digest=hashlib.sha256(json.dumps(evidence, separators=(',', ':')).encode()).hexdigest())
        return proof, binding, dict(capacity) if capacity else None

    def snapshot(self, session_id):
        with self.owner.factory.unit_of_work(write=False) as uow:
            return self._read(session_id, uow=uow)

    def commit(self, session_id, proof):
        with self.owner.factory.unit_of_work() as uow:
            current = self._read(session_id, uow=uow)
            if current is None or current[0] != proof:
                return False
            uow.connection.execute('UPDATE execution_sessions SET local_retirement_json=? '
                'WHERE server_id=? AND executor_id=? AND session_id=?',
                (json.dumps(proof, sort_keys=True, separators=(',', ':')),
                 self.owner.channel.server_id, self.owner.channel.executor_id, session_id))
            return True

    async def retire(self, session_id):
        owner = self.owner
        if any(sid == session_id and not task.done() for task, sid in owner.worker_sessions.items()):
            return False
        if owner.sessions.get(session_id, {}).get('executor') is not None:
            return False
        candidate = await asyncio.to_thread(self.snapshot, session_id)
        if candidate is None:
            return False
        proof, binding, admission = candidate
        key = SessionKey(proof['server_id'], proof['executor_id'], session_id)
        operation = OperationKey(key.server_id, key.executor_id, proof['opening_operation_id'])
        path = owner.host._journal_path(key.executor_id, session_id)
        journal_present = await asyncio.to_thread(path.is_file)
        if not journal_present:
            if binding is not None or any(await asyncio.gather(*[
                    asyncio.to_thread(path.with_name(path.name + suffix).exists) for suffix in ('-wal', '-shm')])):
                raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_unopened_retirement')
        else:
            async def inspect(journal):
                claims = await journal.claimed_sessions(key.server_id, key.executor_id, limit=1)
                slots = await journal.owned_slot_page(limit=1)
                if (claims.claims or claims.next_after_rowid is not None or slots.reservations
                        or await journal.get_process_birth(key) is not None
                        or await journal.get_process_launch(key) is not None):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_unopened_resources')
                receipt = await journal.get_receipt(operation)
                expected = (OperationReceipt(operation.operation_id, binding['core_intent_hash'],
                    'FAILED', False, True, session_id,
                    error_code='PREPARATION_FAILED' if proof['evidence_kind'] == 'startup_refusal'
                    else 'LEASE_REVALIDATION_REQUIRED')
                    if binding is not None else None)
                if receipt != expected:
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_unopened_receipt')
            await owner.host.with_history(executor_id=key.executor_id, session_id=session_id, read=inspect)
        ledger_present = await asyncio.to_thread((owner.host.store_dir / 'owned-slots.db').is_file)
        if journal_present and not ledger_present:
            raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_unopened_ledger')
        if ledger_present:
            ledger = await owner.host._ledger()
            slot = await ledger.owned_slot_state(key)
            if slot is not None:
                opening = slot.opening_operation_id
                if opening != operation.operation_id:
                    opening = await ledger.capacity_opening_for_slot(slot)
                if not slot.released or opening != operation.operation_id:
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_unopened_slot')
        if admission is not None:
            original = CapacityReservation.from_dict(json.loads(admission['reservation_json']))
            consumption = CapacityConsumption.from_dict(json.loads(admission['consumption_json']))
            if not ledger_present:
                raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_unopened_capacity')
            # Historical release inspection does not re-authorize the old
            # request through the current generation's productive API.
            await asyncio.to_thread(owner.verify)
            observed = await (await owner.host._ledger()).get_capacity_slot(original.request,
                now=time.monotonic(), boot_id=owner.capacity_boot_id)
            if (observed is None or observed.state != 'RELEASED' or observed.request != original.request
                    or observed.reservation_id != original.reservation_id
                    or original.request.scope.server_id != key.server_id
                    or original.request.scope.executor_id != key.executor_id
                    or original.request.scope.session_id != session_id
                    or consumption.opening_operation_id != operation.operation_id
                    or consumption.opening_intent_hash != proof['opening_intent_hash']
                    or observed.capacity_revision < original.capacity_revision
                    or observed.consumption not in (None, consumption)):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_unopened_capacity')
        await owner.tools.release_session(session_id)
        if any(sid == session_id and not task.done() for task, sid in owner.worker_sessions.items()):
            return False
        return await asyncio.to_thread(self.commit, session_id, proof)
