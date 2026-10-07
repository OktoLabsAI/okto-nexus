"""Authenticated MCP lifecycle uses the approved Core realization."""
import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_pr34_remediation import tool


def invoke(setup, name, body):
    setup[2].headers['host'] = '127.0.0.1:8000'
    return tool(setup[2], setup[3]['subject']['Authorization'].removeprefix('Bearer '), name, body)


def open_body(setup, binding):
    return dict(agent_id='subject', kind='codex', project_root=str(setup[-1]),
                endpoint_id=binding['endpoint_id'], idempotency_key='mcp-lifecycle-open')


def test_mcp_lifecycle_preserves_identity_and_exact_core_verbs(connected_local):
    setup, binding, native = connected_local
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET role='reviewer',metadata=?,capabilities=? WHERE agent_id='subject'",
                               ('{"keep":"profile"}', '{"review":true}'))
        before = tuple(uow.connection.execute("SELECT role,metadata,capabilities,api_key_hash FROM agents WHERE agent_id='subject'").fetchone())
    opened = invoke(setup, 'harness_open', open_body(setup, binding))
    assert opened['ok'], opened
    wait_receipt(setup, opened['data'])
    session = opened['data']['scope']['session_id']
    assert opened['data']['scope']['agent_id'] == 'subject'
    invalid = invoke(setup, 'harness_send', dict(session_id=session, payload=None, idempotency_key='missing-payload'))
    assert not invalid['ok'] and invalid['error']['code'] == 'VALIDATION_ERROR', invalid
    for action, extra in [
        ('send', dict(payload=dict(text='MCP turn'))),
        ('steer', dict(payload=dict(text='MCP steering'), expected_turn_id='turn-from-native')),
        ('interrupt', {}), ('close', {}),
    ]:
        args = dict(session_id=session, idempotency_key='mcp-' + action, **extra)
        response = invoke(setup, 'harness_' + action, args)
        assert response['ok'], response
        wait_receipt(setup, response['data'], stages=('SUCCEEDED',) if action == 'close' else ('SUBMITTED',))
        replay = invoke(setup, 'harness_' + action, args)
        assert replay['ok'] and replay['data']['operation_id'] == response['data']['operation_id'], replay
    viewed = invoke(setup, 'harness_get', dict(session_id=session))
    assert viewed['ok'] and viewed['data']['lifecycle_state'] == 'CLOSED', viewed
    assert native.opens == 1 and native.native.stopped
    assert [verb for verb, _ in native.native.sent] == ['send_turn', 'steer', 'interrupt']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute("SELECT role,metadata,capabilities,api_key_hash FROM agents WHERE agent_id='subject'").fetchone()) == before
        assert uow.connection.execute('SELECT COUNT(*) FROM harness_sessions').fetchone()[0] == 0


@pytest.mark.parametrize('change', [
    dict(kind='not-a-kind'),
    dict(backend=dict(provider='zai', model='glm-5.3', extra_args=['--foo'])),
    dict(backend=dict(env=dict(CODEX_HOME='/tmp/unapproved'))),
    dict(backend=dict(provider='zai')),
    dict(backend=dict(env='not-an-object')),
    dict(substrate='attach', target_pid=12345, backend=dict(env=dict(X='1'))),
])
@pytest.mark.parametrize('transport', ['rest', 'mcp'])
def test_canonical_open_rejects_unapproved_kind_and_backend_before_effect(connected_local, change, transport):
    setup, binding, native = connected_local
    payload = dict(open_body(setup, binding), **change)
    if transport == 'mcp':
        result = invoke(setup, 'harness_open', payload)
        assert not result['ok'] and result['error']['code'] == 'VALIDATION_ERROR', result
    else:
        response = setup[2].post('/api/v1/harness/sessions', headers=setup[3]['subject'], json=payload)
        assert response.status_code == 422, response.text
    assert native.opens == 0
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
