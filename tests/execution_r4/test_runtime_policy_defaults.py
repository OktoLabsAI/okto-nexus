"""Global defaults, agent inheritance and MCP-only enforcement at real boundaries."""
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_sender_sessions import configure, sender
from test_local_dashboard_execution import resolve, submit, keyless
from okto_nexus.domain.base import iso_plus


def read(setup, agent=None):
    path = '/api/v1/runtime-policy' if agent is None else f'/api/v1/agents/{agent}/runtime-policy'
    response = setup[2].get(path, headers=setup[3]['operator'])
    assert response.status_code == 200, response.text
    return response.json()['data']


def save(setup, *, agent=None, **changes):
    current = read(setup, agent)
    path = '/api/v1/runtime-policy' if agent is None else f'/api/v1/agents/{agent}/runtime-policy'
    return setup[2].put(path, headers=setup[3]['operator'], json=dict(
        expected_revision=current['revision'], runtime_enabled=current['runtime_enabled'],
        session_policy=current['session_policy']) | changes)


def test_global_disable_keeps_mcp_and_inbox_but_blocks_runtime(connected_local, monkeypatch):
    setup, binding, native = connected_local
    configure(setup, binding, 'shared')
    assert read(setup, 'subject')['runtime_enabled'] is None
    assert save(setup, runtime_enabled=False).status_code == 200
    assert read(setup, 'subject')['effective']['runtime_enabled'] is False
    mid = sender(setup, monkeypatch)('operator', 'MCP-only message')
    from test_pr34_remediation import tool
    who = tool(setup[2], setup[3]['subject']['Authorization'].removeprefix('Bearer '), 'agent_whoami', {})
    assert who['ok'], who
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM message_deliveries WHERE message_id=?', (mid,)).fetchone()[0] == 'unread'
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 0
        assert uow.connection.execute('SELECT revoked_at FROM runtime_execution_grants').fetchone()[0]
    response = setup[2].post('/v1/runtime/intents:resolve', headers=setup[3]['subject'], json=dict(
        client_intent_id='disabled-start', intent='runtime.start', binding_id=binding['binding_id'],
        workspace_binding_id=binding['workspace_binding_id'], new_session=True))
    assert response.status_code == 403 and response.json()['error']['code'] == 'PERMISSION_DENIED', response.text
    assert native.opens == 0


def test_agent_override_can_enable_global_off_and_return_to_inheritance(connected_local):
    setup, binding, native = connected_local
    assert save(setup, runtime_enabled=False, session_policy='per_sender').status_code == 200
    result = save(setup, agent='subject', runtime_enabled=True)
    assert result.status_code == 200, result.text
    assert result.json()['data']['effective'] == dict(runtime_enabled=True, session_policy='per_sender')
    grant = setup[2].post('/api/v1/harness/grants', headers=setup[3]['operator'], json=dict(
        actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=['open', 'send', 'interrupt', 'close'],
        max_executions=10, expires_at=iso_plus(setup[0].clock.now_iso(), 600)))
    assert grant.status_code == 200, grant.text
    opened = admit(setup, binding, 'override-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    assert native.opens == 1
    wait_receipt(setup, admit(setup, binding, 'override-close', 'runtime.close', session_id=opened['session_id']), stages=('SUCCEEDED',))
    assert save(setup, agent='subject', runtime_enabled=None).json()['data']['effective']['runtime_enabled'] is False
    assert save(setup, runtime_enabled=True).status_code == 200
    assert read(setup, 'subject')['effective']['runtime_enabled'] is True
    assert save(setup, agent='subject', runtime_enabled=False).status_code == 200
    assert read(setup, 'subject')['effective']['runtime_enabled'] is False


def test_global_changes_preserve_explicit_overrides_and_grants(connected_local):
    setup, binding, _ = connected_local
    assert save(setup, agent='subject', runtime_enabled=True, session_policy='shared').status_code == 200
    assert save(setup, runtime_enabled=False, session_policy='per_sender').status_code == 200
    assert read(setup, 'subject')['effective'] == dict(runtime_enabled=True, session_policy='shared')
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT revoked_at FROM runtime_execution_grants').fetchone()[0] is None


def test_disable_fences_previously_resolved_work(connected_local):
    setup, binding, native = connected_local
    keyless(setup)
    setup[3]['operator'] = {}
    resolved = resolve(setup, binding, 'before-disable', new_session=True).json()
    assert save(setup, agent='subject', runtime_enabled=False).status_code == 200
    assert submit(setup, resolved).status_code in (403, 409)
    assert native.opens == 0
    assert save(setup, agent='subject', runtime_enabled=True).status_code == 200
    grant = setup[2].post('/api/v1/harness/grants', json=dict(
        actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=['open', 'send', 'close'],
        max_executions=10, expires_at=iso_plus(setup[0].clock.now_iso(), 600)))
    assert grant.status_code == 200, grant.text
    assert submit(setup, resolved).status_code in (403, 409)  # reenabling never revives the old intent


def test_disabled_live_session_closes_on_lease_renewal(connected_local):
    setup, binding, native = connected_local
    opened = admit(setup, binding, 'disable-live', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    assert save(setup, agent='subject', runtime_enabled=False).status_code == 200
    owner = setup[1].state.embedded_dispatch_owner
    session_id = opened['session_id']
    setup[2].portal.call(owner._renew_owned, session_id, owner.sessions[session_id])
    assert native.native.stopped and owner.failure is None
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?',
                                             (session_id,)).fetchone()) == ('CLOSED', 'CLOSED')


def test_global_session_change_requires_only_affected_sessions_closed(connected_local):
    setup, binding, native = connected_local
    opened = admit(setup, binding, 'live-inherited', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    refused = save(setup, session_policy='per_sender')
    assert refused.status_code == 409, refused.text
    assert read(setup)['session_policy'] == 'shared'
    # Explicitly pinning the existing value need not interrupt the live session.
    assert save(setup, agent='subject', session_policy='shared').status_code == 200
    assert save(setup, session_policy='per_sender').status_code == 200
    assert read(setup, 'subject')['effective']['session_policy'] == 'shared'
    assert save(setup, agent='subject', session_policy=None).status_code == 409
    wait_receipt(setup, admit(setup, binding, 'live-close', 'runtime.close', session_id=opened['session_id']), stages=('SUCCEEDED',))


def test_policy_authorization_validation_and_compare_swap(connected_local):
    setup, _, _ = connected_local
    body = dict(expected_revision=1, runtime_enabled=False, session_policy='shared')
    assert setup[2].put('/api/v1/runtime-policy', headers=setup[3]['subject'], json=body).status_code == 403
    assert setup[2].put('/api/v1/agents/subject/runtime-policy', headers=setup[3]['subject'], json=body | dict(expected_revision=0)).status_code == 403
    assert save(setup, runtime_enabled=None).status_code == 422
    assert save(setup, session_policy='unknown').status_code == 422
    assert save(setup, runtime_enabled=False).status_code == 200
    assert setup[2].put('/api/v1/runtime-policy', headers=setup[3]['operator'], json=body).status_code == 409
