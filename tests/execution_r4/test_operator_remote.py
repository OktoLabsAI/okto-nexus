"""Operator HTTP admission and remote WSS lease; no native provider is launched."""
from fastapi.testclient import TestClient
from nexus_connector_core import R4_PREVIEW_REVISION, encode_r4_frame
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
from test_ns09 import setup_authority, negotiate


def test_operator_remote_opening_keeps_subject_lane_and_grant(tmp_path, monkeypatch):
    deps, app, access, _, canonical, _, info, revisions, link, lane, server, executor = setup_authority(tmp_path, monkeypatch)
    headers = {'Authorization': 'Bearer ' + app.state.test_agent_keys['operator']}
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                headers={'Authorization': 'Bearer ' + link}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane, server, executor)
            response = client.post('/v1/runtime/intents:resolve', headers=headers, json={
                'client_intent_id': 'remote-operator-open', 'intent': 'runtime.start',
                'agent_id': 'subject', 'binding_id': 'binding',
                'workspace_binding_id': 'wxb', 'new_session': True})
            assert response.status_code == 200, response.text
            resolved = response.json()
            body = {name: resolved[name] for name in (
                'client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')}
            admitted = client.post('/v1/runtime/operations', headers=headers, json=body)
            assert admitted.status_code == 202, admitted.text
            reservation = reserve_execution_dispatch(deps.connection_factory,
                server_id=server, executor_id=executor, remote_ready=True, channel=channel)
            sent = begin_execution_send(deps.connection_factory, reservation=reservation,
                remote_ready=True, channel=channel, access=access,
                fresh_publications=app.state.inventory_fresh_publications)
            assert sent.scope['agent_id'] == 'subject' and sent.grant_id == canonical['grant_id']
            request = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION,
                type='lease.renew', request_id='operator-initial', grant_id=sent.grant_id,
                expected_lease_serial=0, scope=sent.scope, connection_id=channel.connection_id,
                connection_generation=channel.connection_generation, purpose='initial')
            ws.send_text(encode_r4_frame(request).decode())
            granted = ws.receive_json()
            assert granted['type'] == 'lease.granted', granted
            assert granted['scope'] == sent.scope
            assert granted['grant_id'] == canonical['grant_id']
            assert client.post('/v1/runtime/operations', headers=headers, json=body).status_code == 200
            history = client.get('/v1/runtime/intents/remote-operator-open', headers=headers)
            assert history.status_code == 200
            assert history.json()['operation']['operation_id'] == resolved['operation_id']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert tuple(uow.connection.execute('SELECT actor_agent_id,subject_agent_id FROM execution_operations').fetchone()) == ('operator', 'subject')
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 1
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 1
