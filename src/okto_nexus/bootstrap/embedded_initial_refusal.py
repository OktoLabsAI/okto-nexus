"""Finish authenticated pre-open lease refusals from their durable identity.

The Server denial and operation supply the association; Core owns the no-effect
receipt. No execution context, native stream or stopped process is invented.
"""
import asyncio
from copy import deepcopy
import json

from nexus_connector_core import (
    CoreError, CapacityReservation,
    prepare_r4_lease_refusal, persist_r4_lease_refusal,
)
from nexus_connector_core.lease_denial import lease_denial_frame


class InitialLeaseDenied(Exception):
    def __init__(self, pending_request=None):
        super().__init__('The initial lease was denied before native execution.')
        # Retain the authenticated request if committing its refusal failed.
        # This is retry input, never a substitute for a durable refusal proof.
        self.pending_request = deepcopy(pending_request)


class EmbeddedInitialRefusal:
    def __init__(self, owner):
        self.owner = owner
        self.repository = owner.access.session_containment.repository

    def records(self, *, agent_id=None, session_id=None, pending_only=True):
        owner = self.owner
        with owner.factory.unit_of_work(write=False) as uow:
            owner.verify(uow=uow)
            return self.repository.initial_refusal_records(uow, owner.channel,
                agent_id=agent_id, session_id=session_id, pending_only=pending_only)

    @staticmethod
    def proof(row):
        from ..application.execution_semantics import execution_wire_intent
        from nexus_connector_core import R4_PREVIEW_REVISION
        request = json.loads(row['request_json'])
        scope = json.loads(row['expected_revisions_json'])
        if scope != request['scope']:
            raise CoreError('SCOPE_MISMATCH', 'embedded_initial_refusal')
        frame = {'protocol_major': 1, 'contract_revision': R4_PREVIEW_REVISION,
            'type': 'operation.submit', **scope,
            **execution_wire_intent(json.loads(row['semantic_payload'])),
            'operation_id': row['operation_id'], 'intent_hash': row['intent_hash'],
            'connection_id': request['connection_id'], 'connection_generation': request['connection_generation'],
            'grant_id': request['grant_id']}
        proof = prepare_r4_lease_refusal(frame, lease_denial_frame(request))
        if row['binding_json'] is not None and json.loads(row['binding_json']) != proof['binding']:
            raise CoreError('OPERATION_CONFLICT', 'embedded_initial_refusal')
        return proof

    def bind(self, row, proof):
        owner = self.owner
        with owner.factory.unit_of_work() as uow:
            owner.verify(uow=uow)
            if not self.repository.bind_initial_refusal(uow, owner.channel,
                    operation_id=row['operation_id'], session_id=row['session_id'], binding=proof['binding']):
                raise CoreError('OPERATION_CONFLICT', 'embedded_initial_refusal')

    async def recover(self, *, agent_id=None, session_id=None, pending_only=True):
        owner = self.owner
        rows = await asyncio.to_thread(self.records, agent_id=agent_id, session_id=session_id,
                                       pending_only=pending_only)
        for row in rows:
            if session_id is None and (row['operation_id'] in owner.active_operations
                    or owner.sessions.get(row['session_id'], {}).get('initial_refusal')):
                continue
            proof = self.proof(row)
            # The denial committed before this binding, and both precede Core's
            # receipt. Retrying any cut uses the original request and operation.
            await asyncio.to_thread(self.bind, row, proof)
            async def persist(journal):
                return await persist_r4_lease_refusal(journal, proof)
            receipt = await owner.host.with_history(executor_id=owner.channel.executor_id,
                session_id=row['session_id'], read=persist)
            if row['reservation_json'] is not None:
                reserved = CapacityReservation.from_dict(json.loads(row['reservation_json']))
                capacity = await owner.execution_capacity()
                released = await capacity.release_capacity(reserved.request, reserved.reservation_id, 'REVOKED')
                if released.state != 'RELEASED':
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_initial_refusal_capacity')
            if not await owner.host.close_native_actions(executor_id=owner.channel.executor_id,
                    session_id=row['session_id'], timeout_seconds=5):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_initial_refusal_tools')
            await owner._publish(proof['binding'], receipt)
            await owner.tools.release_session(row['session_id'])
        return bool(rows)
