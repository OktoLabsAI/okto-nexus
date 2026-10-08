"""Routing preference changes do not retarget an established native turn."""
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_identity_lifecycle import second_binding
from test_canonical_grant_regressions import mcp_helpers
from test_pr34_remediation import tool


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_priority_change_preserves_original_controls_and_selects_new_delivery(connected_local, monkeypatch, surface):
    setup, first, native = connected_local
    deps, _, client, headers, *_ = setup
    second = second_binding(setup, monkeypatch)
    for binding in (first, second):
        enable(setup, binding)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE agent_endpoints SET priority=-10 WHERE endpoint_id=?', (second['endpoint_id'],))
    client.headers['host'] = '127.0.0.1:8000'
    opened = admit(setup, first, 'original-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    peer = native.native
    sid = opened['session_id']
    alternative = admit(setup, second, 'alternative-open', 'runtime.start', new_session=True)
    wait_receipt(setup, alternative)
    spare = native.native
    assert spare is not peer and not spare.sent
    turn = admit(setup, first, 'original-turn', 'turn.submit', session_id=sid, text='Original target')
    wait_receipt(setup, turn)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        revision = uow.connection.execute('SELECT revision FROM agent_endpoints WHERE endpoint_id=?', (second['endpoint_id'],)).fetchone()[0]
        grant = dict(uow.connection.execute('SELECT * FROM runtime_execution_grants WHERE endpoint_id=?', (second['endpoint_id'],)).fetchone())
    changed = client.patch('/api/v1/harness/endpoints/' + second['endpoint_id'], headers=headers['operator'],
        json=dict(expected_revision=revision, priority=10))
    assert changed.status_code == 200, changed.text
    assert changed.json()['data']['revision'] == revision + 1
    for verb in ('steer', 'interrupt'):
        args = dict(idempotency_key='original-' + verb)
        if verb == 'steer':
            args.update(payload=dict(text='Only the original turn'), expected_turn_id='turn-from-native')
        if surface == 'rest':
            response = client.post(f'/api/v1/harness/sessions/{sid}/{verb}', headers=headers['subject'], json=args)
            result = response.json()
        else:
            result = tool(client, headers['subject']['Authorization'].removeprefix('Bearer '),
                'harness_' + verb, dict(session_id=sid, **args))
        assert result['ok'], result
        wait_receipt(setup, result['data'])
        assert result['data']['scope']['session_id'] == sid
    assert [verb for verb, _ in peer.sent] == ['send_turn', 'steer', 'interrupt']
    fresh = send(setup, monkeypatch)
    assert fresh['ok'], fresh
    domain = fresh['data']['runtime_operations'][0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        selected = uow.connection.execute('SELECT endpoint_id FROM delivery_outbox WHERE operation_id=?', (domain,)).fetchone()[0]
        original_grant = dict(uow.connection.execute('SELECT * FROM runtime_execution_grants WHERE grant_id=?', (grant['grant_id'],)).fetchone())
        fresh_turn = uow.connection.execute("SELECT p.operation_id FROM execution_domain_deliveries m JOIN execution_operations p USING(server_id,executor_id,operation_id) WHERE m.domain_operation_id=? AND p.action='turn.submit'", (domain,)).fetchone()[0]
    assert selected == second['endpoint_id'] and original_grant['revoked_at'] is None
    wait_receipt(setup, dict(operation_id=fresh_turn))
    assert native.opens == 2 and native.native is spare
    assert [verb for verb, _ in native.native.sent] == ['send_turn']
    assert [verb for verb, _ in peer.sent] == ['send_turn', 'steer', 'interrupt']
    wait_receipt(setup, admit(setup, first, 'close-original', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))
    wait_receipt(setup, admit(setup, second, 'close-alternative', 'runtime.close', session_id=alternative['session_id']), stages=('SUCCEEDED',))


@pytest.mark.parametrize('sql,dimension', [
    ("UPDATE agents SET permissions='{\"messages\":{\"send_direct\":false}}' WHERE agent_id='subject'", 'authorization'),
    ("UPDATE agents SET metadata='{\"priority_test\":\"changed\"}' WHERE agent_id='subject'", 'configuration'),
    ("UPDATE agents SET api_key_hash='rotated-fixture-key' WHERE agent_id='subject'", 'credential_epoch'),
    ("UPDATE agents SET is_active=0 WHERE agent_id='subject'", 'authorization'),
])
def test_priority_edit_preserves_preexisting_authority_changes(connected_local, sql, dimension):
    from dataclasses import replace
    from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    before = current_agent_revisions(deps.connection_factory, agent_id='subject')[1]
    with deps.connection_factory.unit_of_work() as uow:
        revision = uow.connection.execute('SELECT revision FROM agent_endpoints WHERE endpoint_id=?', (binding['endpoint_id'],)).fetchone()[0]
        uow.connection.execute(sql)
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='existing-revocation'")
    response = client.patch('/api/v1/harness/endpoints/' + binding['endpoint_id'], headers=headers['operator'],
        json=dict(expected_revision=revision, priority=17))
    assert response.status_code == 200, response.text
    after = current_agent_revisions(deps.connection_factory, agent_id='subject', require_active=False)[1]
    assert after == replace(before, **{dimension: getattr(before, dimension) + 1})
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert all(row[0] == 'existing-revocation' for row in uow.connection.execute('SELECT revoked_at FROM runtime_execution_grants'))
    assert native.opens == 0
