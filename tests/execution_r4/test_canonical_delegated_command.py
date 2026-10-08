"""A delegated sender retains its own scoped authority through native dispatch."""
import json
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_canonical_native_protocol_regressions import install_native
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_agent_recovery_isolation import create_agent, eventually
from okto_nexus.domain.base import iso_plus


def delegated(connected, actions=None):
    setup, binding, _ = connected
    peers, log = install_native(connected, _FAKE_SERVER_SOURCE)
    log.touch()
    caller = create_agent(setup, 'caller')
    response = setup[2].post('/api/v1/harness/grants', headers=setup[3]['operator'], json=dict(
        actor_agent_id='caller', endpoint_id=binding['endpoint_id'], actions=actions or ['send', 'read'],
        max_executions=1, expires_at=iso_plus(setup[0].clock.now_iso(), 600)))
    assert response.status_code == 200, response.text
    opened = admit(setup, binding, 'delegated-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    return setup, caller, opened['session_id'], response.json()['data'], peers, log


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_granted_sender_has_real_result_and_independent_budget(connected_local, surface):
    from test_pr34_remediation import tool
    setup, caller, sid, grant, peers, log = delegated(connected_local)
    client = setup[2]
    client.headers['host'] = '127.0.0.1:8000'
    body = dict(idempotency_key='delegated-send', payload=dict(text='CANONICAL_CALLER_RESULT'))
    def send():
        if surface == 'rest':
            return client.post(f'/api/v1/harness/sessions/{sid}/send', headers=caller[3]['subject'], json=body).json()
        return tool(client, caller[3]['subject']['Authorization'].removeprefix('Bearer '),
            'harness_send', dict(session_id=sid, **body))
    submitted = send()
    assert submitted['ok'], submitted
    op = submitted['data']['operation_id']
    wait_receipt(setup, submitted['data'], stages=('SUCCEEDED',))
    def read():
        response = client.get('/api/v1/harness/operations/' + op, headers=caller[3]['subject'])
        assert response.status_code == 200, response.text
        return response.json()['data'].get('result')
    eventually(read)
    result = read()
    assert result['delivery_outcome'] == 'success'
    output = result['output_text']
    assert all(value in output for value in ('CANONICAL_CALLER_RESULT', '"sender_agent_id": "caller"',
        '"recipient_agent_id": "subject"', op))
    replay = send()
    assert replay['ok'] and replay['data']['operation_id'] == op, replay
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT actor_agent_id,subject_agent_id FROM execution_operations WHERE operation_id=?', (op,)).fetchone()[:] == ('caller', 'subject')
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (grant['grant_id'],)).fetchone()[0] == 1
    body['idempotency_key'] = 'delegated-exhausted'
    rejected = send()
    assert not rejected['ok'] or rejected['data']['operation_id'] != op
    revoke = client.delete('/api/v1/harness/grants/' + grant['grant_id'], headers=setup[3]['operator'])
    assert revoke.status_code == 200, revoke.text
    assert client.get('/api/v1/harness/operations/' + op, headers=caller[3]['subject']).status_code == 403
    assert client.get('/v1/runtime/operations/' + op, headers=caller[3]['subject']).status_code == 403
    assert len(peers) == 1
    assert sum(json.loads(line).get('method') == 'turn/start' for line in log.read_text(encoding='utf-8').splitlines()) == 1
    wait_receipt(setup, admit(setup, connected_local[1], 'delegated-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))


def test_send_only_grant_cannot_read_results_even_through_replay(connected_local):
    setup, caller, sid, _, _, _ = delegated(connected_local, ['send'])
    client = setup[2]
    body = dict(idempotency_key='delegated-no-read', payload=dict(text='private result'))
    path = f'/api/v1/harness/sessions/{sid}/send'
    submitted = client.post(path, headers=caller[3]['subject'], json=body)
    assert submitted.status_code == 200, submitted.text
    operation = submitted.json()['data']
    wait_receipt(setup, operation, stages=('SUCCEEDED',))
    op = operation['operation_id']
    eventually(lambda: client.get('/api/v1/harness/operations/' + op,
        headers=setup[3]['subject']).json()['data'].get('result'))
    assert client.get('/api/v1/harness/operations/' + op, headers=caller[3]['subject']).status_code == 403
    assert client.get('/v1/runtime/operations/' + op, headers=caller[3]['subject']).status_code == 403
    replay = client.post(path, headers=caller[3]['subject'], json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()['data']['operation_id'] == op and replay.json()['data']['result'] is None


def test_revoked_delegation_is_rechecked_before_native_write(connected_local):
    setup, caller, sid, grant, peers, log = delegated(connected_local)
    client = setup[2]
    lock = setup[1].state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        submitted = client.post(f'/api/v1/harness/sessions/{sid}/send', headers=caller[3]['subject'],
            json=dict(idempotency_key='delegated-revoked', payload=dict(text='must not execute')))
        assert submitted.status_code == 200, submitted.text
        operation = submitted.json()['data']
        revoked = client.delete('/api/v1/harness/grants/' + grant['grant_id'], headers=setup[3]['operator'])
        assert revoked.status_code == 200, revoked.text
    finally:
        client.portal.call(lock.release)
    def refused():
        return client.get('/v1/runtime/operations/' + operation['operation_id'],
            headers=setup[3]['subject']).json()['admission_state'] == 'RESOLVED_TERMINAL'
    eventually(refused)
    assert len(peers) == 1
    assert not any(json.loads(line).get('method') == 'turn/start' for line in log.read_text(encoding='utf-8').splitlines())
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM execution_receipts WHERE operation_id=?',
            (operation['operation_id'],)).fetchone()[0] == 0
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?',
            (grant['grant_id'],)).fetchone()[0] == 0
