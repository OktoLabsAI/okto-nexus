"""Agent location restrictions use the canonical authority path, without workspace identity."""
import pytest
import time
import sqlite3
from test_local_realization import local_setup
from test_embedded_dispatch import connected_local, qualified_contract, admit, wait_receipt
from test_runtime_options import options_host, bind, grant, option
from test_binding_operator import onboarding


def save(setup, location, adapter=None, revision=0):
    return setup[2].put('/api/v1/agents/subject/execution-policy', headers=setup[3]['operator'], json=dict(
        expected_revision=revision, execution_location=location, local_adapter_id=adapter))


def test_all_is_rejected_and_new_agents_default_to_local(local_setup):
    result = local_setup[2].get('/api/v1/agents/subject/execution-policy', headers=local_setup[3]['operator'])
    assert result.json()['data']['execution_location'] == 'local'
    assert save(local_setup, 'all', 'codex_app_server').status_code == 422
    with local_setup[0].connection_factory.unit_of_work() as uow:
        with pytest.raises(sqlite3.IntegrityError):
            uow.connection.execute('INSERT INTO agent_execution_policies VALUES(?,?,?,?)',
                                   ('subject', 'all', 'codex_app_server', 1))


def test_local_restriction_rechecks_admission_and_preserves_close(connected_local):
    setup, binding, native = connected_local
    opened = admit(setup, binding, 'policy-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    _, _, client, headers, *_ = setup
    original = client.get('/api/v1/agents/subject/execution-policy', headers=headers['operator'])
    assert original.status_code == 200, original.text
    assert 'workspace_id' not in original.json()['data']
    resolve = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json=dict(
        client_intent_id='before-restrict', intent='turn.submit', binding_id=binding['binding_id'],
        workspace_binding_id=binding['workspace_binding_id'], session_id=opened['session_id'], text='must not execute'))
    assert resolve.status_code == 200, resolve.text
    assert save(setup, 'remote').status_code == 200
    body = {k: resolve.json()[k] for k in ('client_intent_id','operation_id','resolution_revision','intent_hash')}
    assert client.post('/v1/runtime/operations', headers=headers['subject'], json=body).status_code in (403,409)
    response = client.get('/v1/agents/subject/runtime-options', headers=headers['operator'], params=dict(
        executor_id=binding['executor_id'], workspace_id=binding['workspace_id']))
    choice = next(row for row in response.json()['options'] if row['binding'])
    assert not choice['can_start'] and not choice['can_prepare'] and not choice['can_bind']
    assert 'EXECUTION_LOCATION_RESTRICTED' in choice['policy_reasons']
    assert save(setup, 'local', 'codex_app_server', revision=0).status_code == 409
    assert client.put('/api/v1/agents/subject/execution-policy', headers=headers['subject'], json=dict(
        expected_revision=1, execution_location='remote')).status_code == 403
    wait_receipt(setup, admit(setup,binding,'policy-close','runtime.close',session_id=opened['session_id']), stages=('SUCCEEDED',))
    assert native.opens == 1 and native.native.sent == []


@pytest.mark.parametrize('location,allowed', [('local',False),('remote',True)])
def test_remote_location_policy_is_enforced_in_runtime_resolution(options_host, location, allowed):
    deps, client, headers, scope = options_host
    binding = bind(options_host)
    grant(options_host,binding)
    response = client.put('/api/v1/agents/subject/execution-policy', headers=headers['operator'], json=dict(
        expected_revision=1, execution_location=location, local_adapter_id='pi_rpc'))
    assert response.status_code == 200, response.text
    _, row = option(options_host)
    assert row['can_start'] is allowed
    response = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json=dict(
        client_intent_id='location-open', intent='runtime.start', binding_id=binding['binding_id'],
        workspace_binding_id=binding['workspace_binding_id'], new_session=True))
    if allowed:
        assert response.status_code == 200, response.text
        assert response.json()['can_submit']
    else:
        assert response.status_code == 403, response.text


def test_local_integration_restriction_does_not_create_authority(connected_local):
    setup,binding,native = connected_local
    assert save(setup,'local','pi_rpc').status_code == 200
    response=setup[2].post('/v1/runtime/intents:resolve',headers=setup[3]['subject'],json=dict(
        client_intent_id='wrong-local',intent='runtime.start',binding_id=binding['binding_id'],
        workspace_binding_id=binding['workspace_binding_id'],new_session=True))
    assert response.status_code == 403, response.text
    assert native.opens == 0


def test_policy_change_after_admission_prevents_native_dispatch(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        opened = admit(setup, binding, 'admitted-before-restrict', 'runtime.start', new_session=True)
        assert save(setup, 'remote').status_code == 200
    finally:
        client.portal.call(lock.release)
    until = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT dispatch_state,last_error FROM execution_dispatch_outbox '
                'WHERE operation_id=?', (opened['operation_id'],)).fetchone()
        if row['dispatch_state'] == 'RESOLVED_TERMINAL':
            assert 'CONFLICT' in row['last_error'], dict(row)
            break
        assert time.monotonic() < until, dict(row)
        time.sleep(.02)
    assert native.opens == 0


def test_old_writer_cannot_bypass_execution_policy(connected_local):
    setup, binding, native = connected_local
    deps = setup[0]
    opened = admit(setup, binding, 'writer-fence-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    with sqlite3.connect(deps.config.db_path) as old:
        # Model a pre-upgrade connection with only its original capabilities.
        old.create_function('nexus_runtime_writer_v1', 0, lambda: 1)
        old.create_function('nexus_connection_policy_v1', 0, lambda: 1)
        assert save(setup, 'remote').status_code == 200
        for table, column in (('execution_operations','operation_id'),
                              ('execution_dispatch_outbox','operation_id'),
                              ('execution_leases','lease_serial'),
                              ('agent_execution_policies','revision')):
            assert old.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] > 0
            with pytest.raises(sqlite3.IntegrityError, match='agent_execution_policy_writer_incompatible'):
                old.execute(f'UPDATE {table} SET {column}={column}')
            old.rollback()
    wait_receipt(setup, admit(setup, binding, 'writer-fence-close', 'runtime.close',
        session_id=opened['session_id']), stages=('SUCCEEDED',))
    assert native.opens == 1
