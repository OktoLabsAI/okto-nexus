"""Scoped budgets and revalidation survive the legacy-to-Core cutover."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_unbounded_local_grants import issue
from okto_nexus.domain.base import iso_plus


def invoke_command(setup, monkeypatch, transport, session, body):
    client, headers = setup[2:4]
    if transport == 'rest':
        return client.post(f'/api/v1/harness/sessions/{session}/send', headers=headers['subject'], json=body).json()
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers['host'] = '127.0.0.1:8000'
    return tool(client, headers['subject']['Authorization'].removeprefix('Bearer '),
                'harness_send', dict(session_id=session, **body))


def open_scoped(connected, *, budget=10):
    setup, binding, native = connected
    deps = setup[0]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='replaced'")
    issued = issue(setup, binding, expires_at=iso_plus(deps.clock.now_iso(), 600), max_executions=budget)
    assert issued.status_code == 200, issued.text
    grant = issued.json()['data']
    opened = admit(setup, binding, 'scoped-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    return setup, binding, native, grant, opened['session_id']


def test_concurrent_turns_charge_the_last_grant_slot_once(connected_local):
    setup, binding, native, grant, session = open_scoped(connected_local, budget=1)
    client, headers = setup[2:4]
    barrier = Barrier(2)
    def submit(index):
        barrier.wait(timeout=5)
        body = dict(idempotency_key='last-budget-' + str(index), payload=dict(text='one authorized turn'))
        return body, client.post(f'/api/v1/harness/sessions/{session}/send', headers=headers['subject'], json=body)
    lock = setup[1].state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (1, 2)))
    finally:
        client.portal.call(lock.release)
    # R4 records intent before spending the grant at dispatch. Both requests
    # may be admitted, but only one is allowed to reach the native harness.
    assert all(r.status_code == 200 for _, r in results), [r.text for _, r in results]
    accepted = [r.json()['data'] for _, r in results if r.status_code == 200]
    assert accepted
    import time
    deadline = time.monotonic() + 10
    while True:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            states = [dict(row) for row in uow.connection.execute(
                "SELECT o.dispatch_state,o.last_error FROM execution_dispatch_outbox o JOIN execution_operations p USING(operation_id) WHERE p.action='turn.submit'")]
        if len(native.native.sent) == 1 and any(s['dispatch_state'] == 'RESOLVED_TERMINAL' and 'PERMISSION_DENIED' in (s['last_error'] or '') for s in states):
            break
        assert time.monotonic() < deadline, states
        time.sleep(.02)
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?',
                                      (grant['grant_id'],)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == len(accepted)
    assert len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'budget-close', 'runtime.close', session_id=session), stages=('SUCCEEDED',))


@pytest.mark.parametrize('transport', ['rest', 'mcp'])
def test_spent_grant_can_recover_its_recorded_operation_without_another_effect(connected_local, monkeypatch, transport):
    setup, _, native, grant, session = open_scoped(connected_local, budget=1)
    _, _, client, headers, *_ = setup
    body = dict(idempotency_key='recover-spent', payload=dict(text='one authorized effect'))
    if transport == 'rest':
        def invoke():
            response = client.post(f'/api/v1/harness/sessions/{session}/send', headers=headers['subject'], json=body)
            assert response.status_code == 200, response.text
            return response.json()
    else:
        monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
        from test_pr34_remediation import tool
        client.headers['host'] = '127.0.0.1:8000'
        def invoke():
            return tool(client, headers['subject']['Authorization'].removeprefix('Bearer '),
                        'harness_send', dict(session_id=session, **body))
    first = invoke()
    assert first['ok'], first
    wait_receipt(setup, first['data'])
    replay = invoke()
    assert replay['ok'] and replay['data']['reused'], replay
    assert replay['data']['operation_id'] == first['data']['operation_id']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (grant['grant_id'],)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert len(native.native.sent) == 1


@pytest.mark.parametrize('transports', [('rest', 'rest'), ('mcp', 'mcp'), ('rest', 'mcp')])
def test_concurrent_command_replay_keeps_one_effect_and_immutable_payload(connected_local, monkeypatch, transports):
    setup, _, native, grant, session = open_scoped(connected_local, budget=1)
    barrier = Barrier(2)
    body = dict(idempotency_key='same-concurrent-command', payload=dict(text='immutable original'))
    def invoke(transport):
        barrier.wait(timeout=5)
        return invoke_command(setup, monkeypatch, transport, session, body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(invoke, transports))
    assert all(r['ok'] for r in replies), replies
    assert len({r['data']['operation_id'] for r in replies}) == 1
    wait_receipt(setup, replies[0]['data'])
    changed = dict(body, payload=dict(text='replacement must not execute'))
    for transport in set(transports):
        rejected = invoke_command(setup, monkeypatch, transport, session, changed)
        assert not rejected['ok'] and rejected['error']['code'] == 'CONFLICT', rejected
        repeated = invoke_command(setup, monkeypatch, transport, session, body)
        assert repeated['ok'] and repeated['data']['operation_id'] == replies[0]['data']['operation_id']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (grant['grant_id'],)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert len(native.native.sent) == 1


def test_revoked_grant_cannot_recover_previously_authorized_send(connected_local, monkeypatch):
    setup, _, native, grant, session = open_scoped(connected_local, budget=1)
    body = dict(idempotency_key='revoked-replay', payload=dict(text='authorized before revocation'))
    first = invoke_command(setup, monkeypatch, 'rest', session, body)
    assert first['ok'], first
    wait_receipt(setup, first['data'])
    revoked = setup[2].delete('/api/v1/harness/grants/' + grant['grant_id'], headers=setup[3]['operator'])
    assert revoked.status_code == 200, revoked.text
    for transport in ('rest', 'mcp'):
        denied = invoke_command(setup, monkeypatch, transport, session, body)
        assert not denied['ok'] and denied['error']['code'] == 'PERMISSION_DENIED', denied
    assert len(native.native.sent) == 1


@pytest.mark.parametrize('change', ['revoke', 'expire', 'credential', 'permissions', 'profile', 'configuration'])
def test_authority_change_denies_rest_and_mcp_before_native_send(connected_local, monkeypatch, change):
    setup, binding, native, grant, session = open_scoped(connected_local)
    deps, _, client, headers, *_ = setup
    if change == 'revoke':
        response = client.delete('/api/v1/harness/grants/' + grant['grant_id'], headers=headers['operator'])
        assert response.status_code == 200, response.text
    else:
        with deps.connection_factory.unit_of_work() as uow:
            if change == 'expire':
                uow.connection.execute("UPDATE runtime_execution_grants SET expires_at='2000-01-01T00:00:00Z'")
            elif change == 'credential':
                uow.connection.execute("UPDATE runtime_execution_grants SET credential_binding='different-key-hash'")
            elif change == 'permissions':
                uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'", ('{"messages":{"send_direct":false}}',))
            elif change == 'profile':
                uow.connection.execute('UPDATE runtime_profiles SET revision=revision+1')
            else:
                uow.connection.execute('UPDATE execution_realizations SET revision=revision+1')
    body = dict(session_id=session, payload=dict(text='must not execute'), idempotency_key='authority-' + change)
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers['host'] = '127.0.0.1:8000'
    result = tool(client, headers['subject']['Authorization'].removeprefix('Bearer '), 'harness_send', body)
    assert not result['ok'] and result['error']['code'] in ('PERMISSION_DENIED', 'CONFLICT'), result
    body.pop('session_id')
    response = client.post(f'/api/v1/harness/sessions/{session}/send', headers=headers['subject'], json=body)
    assert response.status_code in (403, 409), response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 0
    assert native.native.sent == []
