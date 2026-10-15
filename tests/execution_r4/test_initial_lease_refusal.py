"""A real denied bootstrap accepts only its original terminal no-effect fact."""
import asyncio
import json

import pytest
from starlette.testclient import TestClient
from nexus_connector_core import (
    R4_PREVIEW_REVISION, OperationKey, encode_r4_frame, decode_control_frame,
    prepare_r4_lease_refusal, persist_r4_lease_refusal, project_r4_bound_receipt,
)
from nexus_connector_core.journal import open_journal
from nexus_connector_core.lease_denial import LEASE_DENIAL_REVISION
from nexus_connector_core.protocol import canonical_json
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
from test_ns09 import setup_authority, negotiate, admit


@pytest.mark.parametrize('cut', ['before_grant', 'before_applied'])
@pytest.mark.parametrize('fail_commit', [False, True])
def test_initial_denial_commits_exact_no_effect_receipt_and_closes_only_its_session(tmp_path, monkeypatch, cut, fail_commit):
    deps, app, access, operator, grant, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://127.0.0.1:8202', raise_server_exceptions=False) as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id,
                                control_capabilities=(LEASE_DENIAL_REVISION,))
            resolved = admit(deps, app)
            reservation = reserve_execution_dispatch(deps.connection_factory, server_id=server_id,
                executor_id=executor_id, remote_ready=True)
            opening = begin_execution_send(deps.connection_factory, reservation=reservation, remote_ready=True,
                fresh_publications=app.state.inventory_fresh_publications, access=access)
            request = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.renew',
                request_id='denied-original', grant_id=grant['grant_id'], expected_lease_serial=0,
                scope=resolved['scope'], connection_id=channel.connection_id,
                connection_generation=channel.connection_generation, purpose='initial')
            if cut == 'before_applied':
                ws.send_text(encode_r4_frame(request).decode())
                assert ws.receive_json()['type'] == 'lease.granted'
            ticket = issue_execution_ticket(deps.connection_factory, server_id=server_id,executor_id=executor_id,
                agent_id='subject',binding_id='binding',scopes=frozenset({'receipt:publish'})).ticket
            path = f'/v1/runtime/operations/{resolved["operation_id"]}/receipts'
            headers = {'Authorization': f'Bearer {ticket}'}
            unproven = {k: opening.frame[k] for k in ('protocol_major','contract_revision','server_id','executor_id',
                'binding_id','agent_id','session_id','connection_id','connection_generation','operation_id','intent_hash')}
            unproven.update(type='operation.receipt', receipt_revision=1,stage='FAILED',possible_effect=False,
                retry_safe=True,error_code='LEASE_REVALIDATION_REQUIRED')
            # Correctly shaped no-effect bytes are insufficient before the
            # Server actually records its denial of this original bootstrap.
            assert client.post(path,json=unproven,headers=headers).status_code == 409
            access.revoke(operator, grant_id=grant['grant_id'])
            ws.send_text(encode_r4_frame(request).decode())
            denial = decode_control_frame(canonical_json(ws.receive_json()), capabilities=(LEASE_DENIAL_REVISION,))
            assert denial['type'] == 'lease.denied' and denial['request'] == request
            proof = prepare_r4_lease_refusal(opening.frame, denial)
            async def local_fact():
                journal = await open_journal(tmp_path / 'core.db')
                try:
                    fact = await persist_r4_lease_refusal(journal, proof)
                    return project_r4_bound_receipt(proof['binding'], fact,
                        key=OperationKey(server_id,executor_id,resolved['operation_id']), receipt_revision=1)
                finally:
                    await journal.aclose()
            receipt = asyncio.run(local_fact())
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT state FROM execution_session_containment').fetchone()[0] == 'REQUESTED'
            for changed in (dict(receipt,possible_effect=True,retry_safe=False),
                            dict(receipt,error_code='OTHER'),dict(receipt,connection_generation=channel.connection_generation+1)):
                response = client.post(path, json=changed, headers=headers)
                assert response.status_code == 409, response.text
            if fail_commit:
                from okto_nexus.adapters.outbound.sqlite.execution_session_containment import SqliteSessionContainmentRepository
                original_commit = SqliteSessionContainmentRepository.complete_verified
                def fail_after_update(self, *args, **kwargs):
                    original_commit(self, *args, **kwargs)
                    raise OSError('Synthetic failure after obligation closure.')
                with monkeypatch.context() as patch:
                    patch.setattr(SqliteSessionContainmentRepository, 'complete_verified', fail_after_update)
                    assert client.post(path, json=receipt, headers=headers).status_code == 500
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 0
                    assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'OPEN_PENDING'
                    assert uow.connection.execute('SELECT state FROM execution_session_containment').fetchone()[0] == 'REQUESTED'
            response = client.post(path, json=receipt, headers=headers)
            assert response.status_code == 200, response.text
            assert client.post(path,json=receipt,headers=headers).json()['reused']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                conn = uow.connection
                assert tuple(conn.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('CLOSED','CLOSED')
                row = conn.execute('SELECT state,release_proof_json FROM execution_session_containment').fetchone()
                assert row['state'] == 'RELEASED' and json.loads(row['release_proof_json'])['receipt'] == receipt
                assert conn.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 1
                assert conn.execute('SELECT control_state FROM execution_executors WHERE executor_id=?',(executor_id,)).fetchone()[0] == 'CONTROL_READY'
