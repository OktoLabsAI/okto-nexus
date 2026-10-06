from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from nexus_connector_core import R4_PREVIEW_REVISION, encode_r4_frame
import pytest
from starlette.websockets import WebSocketDisconnect

from test_ns09 import setup_authority, negotiate


@pytest.mark.parametrize('invalid', [None, 'revoked', 'expired'])
def test_live_connection_renews_proofs_without_changing_owner(tmp_path, monkeypatch, invalid):
    deps, app, _, _, _, _, info, revisions, ticket, lane_ticket, server, executor = setup_authority(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                headers={'Authorization': 'Bearer ' + ticket}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server, executor,
                control_capabilities=('connection_renewal_v1', 'heartbeat_ack_v1'))
            base = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, server_id=server,
                executor_id=executor, connection_id=channel.connection_id, connection_generation=channel.connection_generation)
            for index in range(3):
                with deps.connection_factory.unit_of_work() as uow:
                    conn = uow.connection
                    original = dict(conn.execute('SELECT * FROM execution_control_lanes').fetchone())
                    expires = datetime.now(timezone.utc) + timedelta(seconds=-1 if invalid == 'expired' else 30)
                    conn.execute('UPDATE execution_link_tickets SET expires_at=?', (expires.isoformat(),))
                    if invalid == 'revoked':
                        conn.execute('UPDATE execution_link_tickets SET revoked_at=? WHERE binding_id IS NOT NULL', (datetime.now(timezone.utc).isoformat(),))
                ws.send_text(encode_r4_frame(dict(base, type='connection.renew', request_id=f'renew-{index}')).decode())
                if invalid:
                    with pytest.raises(WebSocketDisconnect) as closed:
                        ws.receive_json()
                    assert closed.value.code == 4403
                    break
                reply = ws.receive_json()
                assert reply == dict(base, type='connection.renewed', request_id=f'renew-{index}', expires_in=600, binding_ids=['binding'])
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    renewed = dict(uow.connection.execute('SELECT * FROM execution_control_lanes').fetchone())
                    assert {k:v for k,v in renewed.items() if k != 'expires_at'} == {k:v for k,v in original.items() if k != 'expires_at'}
                    assert datetime.fromisoformat(renewed['expires_at']) > expires
                ws.send_text(encode_r4_frame(dict(base, type='heartbeat')).decode())
                assert ws.receive_json() == dict(base, type='heartbeat')


@pytest.mark.parametrize('stale', [False, True])
def test_short_disconnect_resumes_same_lane_and_generation(tmp_path, monkeypatch, stale):
    deps, app, _, _, _, _, info, revisions, ticket, lane_ticket, server, executor = setup_authority(tmp_path, monkeypatch)
    url = f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link'
    headers = {'Authorization': 'Bearer ' + ticket}
    capabilities = ['connection_renewal_v1', 'heartbeat_ack_v1', 'connection_resume_v1']
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(url, headers=headers, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server, executor, control_capabilities=capabilities)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            lane = dict(uow.connection.execute('SELECT * FROM execution_control_lanes').fetchone())
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_connection_resumes').fetchone()[0] == 1
        with client.websocket_connect(url, headers=headers, subprotocols=['nxl.v1']) as ws:
            base = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, server_id=server, executor_id=executor)
            ws.send_text(encode_r4_frame(dict(base, type='hello', link_attempt_id='resume',
                core_version=info['core_version'], management_revision=info['management_revision'],
                supported_nxl=[R4_PREVIEW_REVISION], snapshot_formats=[info['executor_snapshot_format']],
                control_capabilities=capabilities, resume_connection_id=channel.connection_id,
                resume_connection_generation=channel.connection_generation + int(stale))).decode())
            if stale:
                with pytest.raises(WebSocketDisconnect) as closed:
                    ws.receive_json()
                assert closed.value.code == 4403
                return
            welcome = ws.receive_json()
            assert welcome['resumed'] is True
            assert welcome['connection_id'] == channel.connection_id
            assert welcome['connection_generation'] == channel.connection_generation
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert dict(uow.connection.execute('SELECT * FROM execution_control_lanes').fetchone()) == lane
            ws.send_text(encode_r4_frame(dict(base, type='heartbeat', connection_id=channel.connection_id,
                connection_generation=channel.connection_generation)).decode())
            assert ws.receive_json()['type'] == 'heartbeat'
