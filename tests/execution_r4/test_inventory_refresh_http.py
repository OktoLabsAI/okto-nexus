"""Refresh requests and correlated publication over HTTP with a real WSS owner."""
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from nexus_connector_core import R4_PREVIEW_REVISION, __version__, encode_r4_frame

from test_binding_operator import onboarding
from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
from okto_nexus.adapters.outbound.execution.core_inventory import local_inventory_snapshot, protocol_info


def validate(name, value):
    schema = json.loads((Path(__file__).parents[2] / 'plans/contratos/http-target.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator({'$defs': schema['$defs'], '$ref': '#/$defs/' + name}).validate(value)


def test_http_refresh_scope_and_capacity(onboarding):
    deps, client, headers, prepared = onboarding
    path = f"/v1/runtime/executors/{prepared['executor_id']}/inventory:refresh"
    body = {'client_intent_id': 'refresh'}
    protocol = client.get('/v1/connections/protocol')
    assert protocol.status_code == 200
    validate('ProtocolInfo', protocol.json())
    assert protocol.json()['inventory_refresh_supported'] is True
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=headers['other']).status_code == 404
    assert client.post(path, json={**body, 'agent_id': 'subject'}, headers=headers['subject']).status_code == 400
    assert client.post(path + '?agent_id=subject', json=body, headers=headers['subject']).status_code == 422
    first = client.post(path, json=body, headers=headers['subject'])
    assert first.status_code == 202, first.text
    validate('RefreshView', first.json())
    assert first.json()['state'] == 'OFFLINE'
    assert first.headers['Cache-Control'] == 'no-store'
    assert client.post(path, json=body, headers=headers['subject']).json() == first.json()
    for index in range(31):
        assert client.post(path, json={'client_intent_id': str(index)}, headers=headers['subject']).status_code == 202
    assert client.post(path, json={'client_intent_id': 'overflow'}, headers=headers['subject']).status_code == 429
    assert client.post(path, json=body, headers=headers['subject']).status_code == 202


@pytest.mark.parametrize('revoke_after_verify', [False, True])
def test_http_claim_publication_and_transactional_revocation(onboarding, monkeypatch, revoke_after_verify):
    deps, client, headers, prepared = onboarding
    factory = deps.connection_factory
    server = ensure_execution_installation(factory).server_id
    executor = prepared['executor_id']
    root = f'/v1/runtime/executors/{executor}'
    ticket = issue_execution_ticket(factory, server_id=server, executor_id=executor,
                                   agent_id='subject', binding_id=None)
    authorization = {'Authorization': 'Bearer ' + ticket.ticket}
    intent = {'client_intent_id': 'remote-refresh'}
    assert client.post(root + '/inventory:refresh', json=intent, headers=headers['subject']).status_code == 202
    assert client.post(root + '/inventory:claim-refresh', json={'producer_instance_id': 'wrong'},
                       headers=headers['subject']).status_code == 403
    base = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION,
                server_id=server, executor_id=executor)
    with client.websocket_connect(f'wss://127.0.0.1:8202{root}/link',
            headers=authorization, subprotocols=['nxl.v1']) as ws:
        ws.send_text(encode_r4_frame(dict(base, type='hello', link_attempt_id='refresh-link',
            core_version=__version__, management_revision=protocol_info()['management_revision'],
            supported_nxl=[R4_PREVIEW_REVISION], snapshot_formats=[protocol_info()['executor_snapshot_format']],
            control_capabilities=[])).decode())
        welcome, request = ws.receive_json(), ws.receive_json()
        channel = dict(base, connection_id=welcome['connection_id'],
                       connection_generation=welcome['connection_generation'])
        ws.send_text(encode_r4_frame(dict(channel, type='reconcile.report',
            reconcile_id=request['reconcile_id'], cursor=request['cursor'], next_cursor=None,
            complete=True, receipts=[], claims=[], stream_watermarks=[], ownership_facts=[])).decode())
        assert ws.receive_json()['type'] == 'reconcile.accepted'
        claim = {'producer_instance_id': welcome['connection_id']}
        assert client.post(root + '/inventory:claim-refresh', json={'producer_instance_id': 'other'},
                           headers=authorization).status_code == 409
        if revoke_after_verify:
            from okto_nexus.adapters.inbound.http import runtime_v1
            original = runtime_v1.verify_execution_ticket
            def verified_then_revoked(*args, **kwargs):
                verified = original(*args, **kwargs)
                with factory.unit_of_work() as uow:
                    uow.connection.execute("UPDATE execution_link_tickets SET revoked_at=? WHERE ticket_id=?",
                                           (deps.clock.now_iso(), verified.ticket_id))
                return verified
            monkeypatch.setattr(runtime_v1, 'verify_execution_ticket', verified_then_revoked)
            refused = client.post(root + '/inventory:claim-refresh', json=claim, headers=authorization)
            assert refused.status_code == 403, refused.text
            with factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_inventory_refresh_deliveries').fetchone()[0] == 0
            return
        delivered = client.post(root + '/inventory:claim-refresh', json=claim, headers=authorization)
        assert delivered.status_code == 200, delivered.text
        validate('InventoryRefreshClaimView', delivered.json())
        assert client.post(root + '/inventory:claim-refresh', json=claim, headers=authorization).json() == delivered.json()
        snapshot = local_inventory_snapshot([], server_id=server, executor_id=executor,
            producer_instance_id=welcome['connection_id'], publication_sequence=2)
        bad = client.put(root + '/inventory', json=snapshot,
            headers={**authorization, 'X-Nexus-Inventory-Refresh': 'wrong'})
        assert bad.status_code == 409, bad.text
        assert client.post(root + '/inventory:refresh', json=intent, headers=headers['subject']).json()['state'] == 'REQUESTED'
        correlated = {**authorization, 'X-Nexus-Inventory-Refresh': delivered.json()['delivery_id']}
        for _ in range(2):
            accepted = client.put(root + '/inventory', json=snapshot, headers=correlated)
            assert accepted.status_code == 200, accepted.text
        assert client.post(root + '/inventory:refresh', json=intent, headers=headers['subject']).json()['state'] == 'UPDATED'
        assert client.post(root + '/inventory:claim-refresh', json=claim, headers=authorization).json()['delivery_id'] is None
        with factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 0
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
