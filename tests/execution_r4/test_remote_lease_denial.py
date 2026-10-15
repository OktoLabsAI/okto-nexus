"""Authenticated link replies preserve a denial's original lease correlation."""
import pytest
from starlette.testclient import TestClient
from nexus_connector_core import R4_PREVIEW_REVISION, encode_r4_frame, decode_control_frame
from nexus_connector_core.lease_denial import LEASE_DENIAL_REVISION
from nexus_connector_core.protocol import canonical_json

from okto_nexus.application.execution_intents import resolve_execution_intent
from okto_nexus.application.execution_admission import submit_execution_operation
from okto_nexus.domain.base import iso_plus
from test_ns09 import setup_authority, negotiate, admit


@pytest.mark.parametrize('capabilities', [(), ('nexus-lease-denial-v1',),
    ('nexus-session-release-v1',), ('nexus-lease-denial-v1', 'nexus-session-release-v1')])
@pytest.mark.parametrize('cut', ['before_grant', 'before_applied'])
def test_remote_running_work_revalidation_requires_negotiated_containment(tmp_path, monkeypatch, capabilities, cut):
    from okto_nexus.adapters.outbound.sqlite.execution_work_leases import SqliteRunningHandoffRepository
    from okto_nexus.application.execution_work_leases import RunningHandoff
    from test_session_containment_obligation import applied
    # Exercise real handshake, leases, work-authority rule and durable containment.
    # Only the running-work read port is controlled here; repository/domain work
    # joins and native shutdown are exercised by their separate integration suites.
    revoked_session = []
    original = SqliteRunningHandoffRepository.running
    def running(self, uow, scope):
        if scope['session_id'] in revoked_session:
            return (RunningHandoff({}, 1, 1, 'REJECTED', scope['agent_id']),)
        return original(self, uow, scope)
    monkeypatch.setattr(SqliteRunningHandoffRepository, 'running', running)
    deps, app, _, _, canonical, _, info, revisions, ticket, lane, sid, eid = setup_authority(tmp_path, monkeypatch)
    paired = len(capabilities) == 2
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{eid}/link',
                headers={'Authorization': f'Bearer {ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane, sid, eid, control_capabilities=capabilities)
            assert channel.supports_work_containment is paired
            opened = admit(deps, app)
            initial = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.renew',
                request_id='initial', grant_id=canonical['grant_id'], expected_lease_serial=0,
                scope=opened['scope'], **{k: v for k, v in channel.identity().items() if k.startswith('connection_')},
                purpose='initial')
            ws.send_text(encode_r4_frame(initial).decode())
            granted = ws.receive_json()
            assert granted['type'] == 'lease.granted'
            ws.send_text(encode_r4_frame(applied(granted, channel)).decode())
            ws.send_text(encode_r4_frame(initial).decode())
            assert ws.receive_json() == granted
            renewal = dict(initial, request_id='renew', purpose='renew', expected_lease_serial=1)
            if cut == 'before_applied':
                ws.send_text(encode_r4_frame(renewal).decode())
                granted = ws.receive_json()
                assert granted['type'] == 'lease.granted'
            revoked_session.append(opened['session_id'])
            if cut == 'before_applied':
                ws.send_text(encode_r4_frame(applied(granted, channel)).decode())
            ws.send_text(encode_r4_frame(renewal).decode())
            result = ws.receive_json()
            assert result['type'] == ('lease.denied' if paired else 'lease.granted'), result
            if paired:
                assert result['request'] == renewal
                ws.send_text(encode_r4_frame(renewal).decode())
                assert ws.receive_json() == result
            # Unrelated work can acquire a lease on the same live socket.
            other = resolve_execution_intent(deps.connection_factory, actor_agent_id='subject',
                request=dict(client_intent_id='sibling', intent='runtime.start', binding_id='binding',
                             workspace_binding_id='wxb', new_session=True), remote_ready=True,
                fresh_publications=app.state.inventory_fresh_publications)
            assert other['can_submit'], other['blockers']
            submit_execution_operation(deps.connection_factory, actor_agent_id='subject',
                request={k: other[k] for k in ('client_intent_id','operation_id','resolution_revision','intent_hash')},
                remote_ready=True, fresh_publications=app.state.inventory_fresh_publications)
            sibling = dict(initial, request_id='sibling', scope=other['scope'])
            ws.send_text(encode_r4_frame(sibling).decode())
            assert ws.receive_json()['type'] == 'lease.granted'
            with deps.connection_factory.unit_of_work(write=False) as uow:
                obligations = uow.connection.execute('SELECT session_id,state FROM execution_session_containment').fetchall()
                assert [tuple(row) for row in obligations] == ([(opened['session_id'], 'REQUESTED')] if paired else [])
                assert uow.connection.execute('SELECT control_state FROM execution_executors WHERE executor_id=?',
                                              (eid,)).fetchone()[0] == 'CONTROL_READY'


@pytest.mark.parametrize('negotiated', [False, True])
@pytest.mark.parametrize('cut', ['before_grant', 'before_applied'])
def test_one_refused_lease_does_not_consume_or_authorize_another_session(tmp_path, monkeypatch, negotiated, cut):
    deps, app, access, operator, canonical, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    capabilities = (LEASE_DENIAL_REVISION,) if negotiated else ()
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
                headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane_ticket, server_id, executor_id,
                                control_capabilities=capabilities)
            bad = admit(deps, app)
            good = resolve_execution_intent(deps.connection_factory, actor_agent_id='subject',
                request=dict(client_intent_id='independent-open', intent='runtime.start',
                    binding_id='binding', workspace_binding_id='wxb', new_session=True),
                remote_ready=True, fresh_publications=app.state.inventory_fresh_publications)
            assert good['can_submit'], good['blockers']
            submit_execution_operation(deps.connection_factory, actor_agent_id='subject',
                request={k: good[k] for k in ('client_intent_id','operation_id','resolution_revision','intent_hash')},
                remote_ready=True, fresh_publications=app.state.inventory_fresh_publications)
            other_grant = access.issue(operator, actor_agent_id='subject', endpoint_id='ep',
                actions=['open','send','close','interrupt'], max_executions=2,
                expires_at=iso_plus(deps.clock.now_iso(), 600))
            def request(resolved, gid, identity):
                return dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.renew',
                    request_id=identity, grant_id=gid, expected_lease_serial=0, scope=resolved['scope'],
                    connection_id=channel.connection_id, connection_generation=channel.connection_generation,
                    purpose='initial')
            refused = request(bad, canonical['grant_id'], 'refused-request')
            healthy = request(good, other_grant['grant_id'], 'healthy-request')
            if cut == 'before_applied':
                ws.send_text(encode_r4_frame(refused).decode())
                granted = ws.receive_json()
                assert granted['type'] == 'lease.granted'
            access.revoke(operator, grant_id=canonical['grant_id'])
            if cut == 'before_applied':
                applied = {k: granted[k] for k in ('protocol_major','contract_revision','request_id',
                    'grant_id','lease_id','lease_serial','scope')}
                applied.update(type='lease.applied', application_stage='INSTALLED',
                    connection_id=channel.connection_id, connection_generation=channel.connection_generation)
                ws.send_text(encode_r4_frame(applied).decode())
                if not negotiated:
                    assert ws.receive_json()['type'] == 'error'
            ws.send_text(encode_r4_frame(refused).decode())
            denied = decode_control_frame(canonical_json(ws.receive_json()), capabilities=capabilities)
            assert denied['code'] == 'LEASE_REVALIDATION_REQUIRED'
            assert denied['type'] == ('lease.denied' if negotiated else 'error')
            if negotiated:
                assert denied['request'] == refused
            ws.send_text(encode_r4_frame(healthy).decode())
            granted = ws.receive_json()
            assert granted['type'] == 'lease.granted' and granted['request_id'] == healthy['request_id']
            assert granted['scope'] == healthy['scope']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute("SELECT count(*) FROM execution_leases WHERE session_id=? AND status='ACTIVE'",
                    (bad['session_id'],)).fetchone()[0] == 0
                assert uow.connection.execute('SELECT control_state FROM execution_executors WHERE executor_id=?',
                    (executor_id,)).fetchone()[0] == 'CONTROL_READY'
