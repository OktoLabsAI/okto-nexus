"""Transactional receipt projection; protocol peers here are synthetic.

NS09 separately exercises the installed Core's actual open and turn receipts.
"""

import pytest
from fastapi.testclient import TestClient

from nexus_connector_core import R4_PREVIEW_REVISION
from okto_nexus.adapters.outbound.sqlite.execution_receipts import append_execution_receipt
from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket, verify_execution_ticket
from okto_nexus.application.execution_dispatch import begin_execution_send, reserve_execution_dispatch
from okto_nexus.application.execution_leases import ExecutionLeaseService
from okto_nexus.errors import OktoNexusError
from test_ns09 import setup_authority, negotiate, admit


@pytest.mark.parametrize('replace_owner', [False, True])
def test_open_receipt_requires_dispatch_and_commits_readiness_atomically(tmp_path, monkeypatch, replace_owner):
    deps, app, access, _, canonical, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    factory = deps.connection_factory
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id)
            resolved = admit(deps, app)
            scope = resolved['scope']
            issued = issue_execution_ticket(factory, server_id=server_id, executor_id=executor_id,
                binding_id='binding', agent_id='subject', scopes=frozenset({'receipt:publish'}))
            principal = verify_execution_ticket(factory, ticket=issued.ticket, server_id=server_id,
                executor_id=executor_id, binding_id='binding', scope='receipt:publish')
            receipt = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='operation.receipt',
                server_id=server_id, executor_id=executor_id, binding_id='binding', agent_id='subject',
                session_id=scope['session_id'], operation_id=resolved['operation_id'], intent_hash=resolved['intent_hash'],
                connection_id=channel.connection_id, connection_generation=channel.connection_generation,
                receipt_revision=1, stage='SUBMITTED', native_id='synthetic-native', possible_effect=True, retry_safe=False)
            with pytest.raises(OktoNexusError, match='matching authorized dispatch'):
                append_execution_receipt(factory, principal=principal, frame=receipt)
            service = ExecutionLeaseService(factory=factory, access=access,
                fresh_publications=app.state.inventory_fresh_publications)
            grant = service.issue(dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.renew',
                scope=scope, request_id='lease', grant_id=canonical['grant_id'], expected_lease_serial=0,
                connection_id=channel.connection_id, connection_generation=channel.connection_generation, purpose='initial'),
                channel=channel)
            ack = {key: grant[key] for key in ('protocol_major','contract_revision','scope','request_id','grant_id','lease_id','lease_serial')}
            service.applied(dict(**ack, type='lease.applied', connection_id=channel.connection_id,
                connection_generation=channel.connection_generation, application_stage='INSTALLED'), channel=channel)
            reservation = reserve_execution_dispatch(factory, server_id=server_id, executor_id=executor_id, remote_ready=True)
            begin_execution_send(factory, reservation=reservation, remote_ready=True,
                fresh_publications=app.state.inventory_fresh_publications, access=access)
            with pytest.raises(OktoNexusError, match='matching authorized dispatch'):
                append_execution_receipt(factory, principal=principal, frame={**receipt, 'connection_id':'wrong-connection'})
            if replace_owner:
                with factory.unit_of_work() as uow:
                    uow.connection.execute("UPDATE execution_executors SET owner_instance_id='next',generation=generation+1 WHERE executor_id=?",
                                           (executor_id,))
            else:
                with factory.unit_of_work() as uow:
                    uow.connection.execute("CREATE TRIGGER fail_session_ready BEFORE UPDATE OF lifecycle_state ON execution_sessions "
                                           "WHEN NEW.lifecycle_state='READY' BEGIN SELECT RAISE(ABORT,'session projection fault'); END")
                with pytest.raises(Exception, match='session projection fault'):
                    append_execution_receipt(factory, principal=principal, frame=receipt)
                with factory.unit_of_work() as uow:
                    assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 0
                    assert uow.connection.execute('SELECT admission_state FROM execution_operations').fetchone()[0] == 'ACCEPTED'
                    assert uow.connection.execute('SELECT dispatch_state FROM execution_dispatch_outbox').fetchone()[0] == 'SENDING'
                    assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'OPEN_PENDING'
                    uow.connection.execute('DROP TRIGGER fail_session_ready')
            assert not append_execution_receipt(factory, principal=principal, frame=receipt).reused
            assert append_execution_receipt(factory, principal=principal, frame=receipt).reused
            with factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == (
                    'OPEN_PENDING' if replace_owner else 'READY')
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 1
                assert uow.connection.execute('SELECT admission_state FROM execution_operations').fetchone()[0] == 'DISPATCHED'
