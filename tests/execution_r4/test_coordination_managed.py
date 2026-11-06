"""Coordination recovery preserves managed authority and canonical delivery effects.

Public MCP and real SQLite/admission/dispatch are exercised with temporary state
and synthetic native peers; these cases do not qualify a provider.
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import test_canonical_delivery as canonical
import test_mcp_session_capabilities as managed
from okto_nexus.application.handoff_provenance import PREFIX as HANDOFF_CREATOR_PREFIX
from okto_nexus.application.message_session_origin import runtime_key
from okto_nexus.application.runtime_actor_authority import MANAGED_MESSAGE_PREFIX


opening = managed.opening
local_setup = canonical.local_setup
connected_local = canonical.connected_local
qualified_contract = canonical.qualified_contract
qualified_bridge = canonical.qualified_bridge


def arguments(operation, **changes):
    data = dict(workspace_id='ws', from_agent_id='subject', client_request_id='managed-request',
                target=dict(strategy='direct', agent_id='other'))
    data.update(dict(subject='Managed coordination', body='Please review this design.')
                if operation == 'message_create'
                else dict(visibility='eligible', payload=dict(objective='Review this design.')))
    return data | changes


def create(state, cap, operation, **changes):
    return managed.envelope(managed.rpc(state, cap['capability'], operation, arguments(operation, **changes)))


def recover(state, cap, operation, **changes):
    return managed.envelope(managed.rpc(state, cap['capability'], 'coordination_request_get',
        dict(workspace_id='ws', operation=operation, client_request_id='managed-request') | changes))


def snapshot(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return snapshot_connection(uow.connection)


def snapshot_connection(connection):
    values = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
              for table in ('messages', 'message_deliveries', 'handoffs', 'approvals',
                'coordination_requests', 'delivery_outbox', 'execution_operations',
                'execution_domain_deliveries', 'execution_client_intents', 'execution_sessions',
                'execution_dispatch_outbox', 'execution_message_origins', 'execution_handoff_origins')}
    values['used_executions'] = connection.execute(
        'SELECT COALESCE(SUM(used_executions),0) FROM runtime_execution_grants').fetchone()[0]
    values['events'] = [tuple(row) for row in connection.execute(
        "SELECT event_id,type FROM events WHERE type IN "
        "('message.created','handoff.created','approval.requested','approval.granted') ORDER BY event_id")]
    return values


def assert_reference(data, operation, *, state='created'):
    resource = 'message_id' if operation == 'message_create' else 'handoff_id'
    assert data['status'] == data['request_receipt']['state'] == state
    assert data['request_receipt']['actor_agent_id'] == 'subject'
    assert data['request_receipt']['workspace_id'] == 'ws'
    assert data['request_receipt']['operation'] == operation
    assert data['request_receipt']['client_request_id'] == 'managed-request'
    assert set(data) <= {'status', 'workspace_id', 'request_receipt', 'reused', resource, 'approval_id'}
    if state == 'created':
        assert data[resource] == data['request_receipt']['resource_id']
    return resource


@pytest.mark.parametrize('opening', ['strict'], indirect=True)
@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_managed_request_replay_and_recovery_keep_one_object_and_runtime_origin(opening, operation):
    cap = managed.activate(opening, actions=['tools/call', operation, 'coordination_request_get'])
    first = create(opening, cap, operation)
    assert first['ok'], first
    resource = assert_reference(first['data'], operation)
    assert first['data']['reused'] is False
    before = snapshot(opening[0])
    for response in (create(opening, cap, operation), recover(opening, cap, operation)):
        assert response['ok'], response
        assert_reference(response['data'], operation)
        assert response['data']['reused'] is True
        assert response['data']['request_receipt'] == first['data']['request_receipt']
    assert snapshot(opening[0]) == before
    changed = create(opening, cap, operation, **{
        'body' if operation == 'message_create' else 'payload': 'Different intent'})
    assert not changed['ok'] and changed['error']['code'] == 'CONFLICT', changed
    assert changed['error']['details']['reason'] == 'CLIENT_REQUEST_CONTENT_CONFLICT'
    assert snapshot(opening[0]) == before
    origin_table = 'execution_message_origins' if operation == 'message_create' else 'execution_handoff_origins'
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            f'SELECT source_session_key FROM {origin_table} WHERE {resource}=?',
            (first['data'][resource],)).fetchone()
        assert row[0] == runtime_key(cap['scope'])
        assert uow.connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_managed_recovery_requires_its_explicit_tool_action(opening, operation):
    cap = managed.activate(opening, actions=['tools/call', operation])
    assert create(opening, cap, operation)['ok']
    before = snapshot(opening[0])
    denied = recover(opening, cap, operation)
    assert not denied['ok'] and denied['error']['code'] == 'PERMISSION_DENIED', denied
    assert snapshot(opening[0]) == before


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_managed_request_cannot_escape_workspace_or_actor_scope(opening, operation):
    cap = managed.activate(opening, actions=['tools/call', operation, 'coordination_request_get'])
    assert create(opening, cap, operation)['ok']
    before = snapshot(opening[0])
    for changes in ({'workspace_id': 'elsewhere'}, {'from_agent_id': 'other'}):
        denied = create(opening, cap, operation, **changes)
        assert not denied['ok'] and denied['error']['code'] == 'PERMISSION_DENIED', denied
    outside = recover(opening, cap, operation, workspace_id='elsewhere')
    assert not outside['ok'] and outside['error']['code'] == 'PERMISSION_DENIED', outside
    # Recovery derives the actor from authentication, even for the same request ID.
    other = dict(capability=opening[1].state.test_agent_keys['other'])
    hidden = recover(opening, other, operation)
    assert not hidden['ok'] and hidden['error']['code'] == 'NOT_FOUND', hidden
    assert snapshot(opening[0]) == before


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_revoked_managed_capability_cannot_replay_or_recover(opening, operation):
    cap = managed.activate(opening, actions=['tools/call', operation, 'coordination_request_get'])
    assert create(opening, cap, operation)['ok']
    before = snapshot(opening[0])
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_session_capabilities SET revoked_at=?',
                               (opening[0].clock.now_iso(),))
    assert managed.rpc(opening, cap['capability'], operation, arguments(operation)).status_code == 401
    assert managed.rpc(opening, cap['capability'], 'coordination_request_get', dict(
        workspace_id='ws', operation=operation, client_request_id='managed-request')).status_code == 401
    assert snapshot(opening[0]) == before


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
@pytest.mark.parametrize('revoke', [False, True])
def test_managed_pending_request_preserves_origin_and_revalidates_approval_authority(
        opening, monkeypatch, operation, revoke):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_hitl import _attach, _rule
    deps, app = opening[:2]
    deps.config.feature_hitl = True
    _attach(deps, 'subject', governance=[_rule(operation, 'require_approval')])
    cap = managed.activate(opening, actions=['tools/call', operation, 'coordination_request_get'])
    pending = create(opening, cap, operation)
    assert pending['ok'], pending
    resource = assert_reference(pending['data'], operation, state='pending_approval')
    assert pending['data']['reused'] is False
    before = snapshot(deps)
    for response in (create(opening, cap, operation), recover(opening, cap, operation)):
        assert response['ok'], response
        assert_reference(response['data'], operation, state='pending_approval')
        assert response['data']['reused'] is True
        assert response['data']['approval_id'] == pending['data']['approval_id']
    assert snapshot(deps) == before
    approval_id = pending['data']['approval_id']
    recorded = deps.approvals.get_approval(approval_id=approval_id)['request_payload']['kwargs']
    assert recorded['_source_session_key'] == runtime_key(cap['scope'])
    binding_field, prefix = (('_managed_message_binding', MANAGED_MESSAGE_PREFIX)
                             if operation == 'message_create' else ('_creator_binding', HANDOFF_CREATOR_PREFIX))
    assert recorded['_coordination']['authority_binding'] == recorded[binding_field]
    assert recorded[binding_field].startswith(prefix)
    assert recorded['_coordination']['actor_agent_id'] == 'subject'
    assert recorded['_coordination']['approval_id'] == approval_id
    assert cap['capability'] not in json.dumps(recorded)
    assert app.state.test_agent_keys['subject'] not in json.dumps(recorded)
    if revoke:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE execution_session_capabilities SET revoked_at=?', (deps.clock.now_iso(),))
    decision = TestClient(app, base_url='https://127.0.0.1:8202').post(
        f'/api/v1/approvals/{approval_id}/decision', json=dict(decision='approve'),
        headers={'Authorization': 'Bearer ' + app.state.test_agent_keys['operator']})
    assert decision.status_code == (403 if revoke else 200), decision.text
    if revoke:
        assert snapshot(deps) == before
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT state,resource_id FROM coordination_requests').fetchone()[:] == (
                'pending_approval', None)
        return
    result = decision.json()['data']['executed_result']
    assert_reference(result, operation)
    assert result['approval_id'] == approval_id
    assert result['request_receipt']['expires_at'] == pending['data']['request_receipt']['expires_at']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        table = 'execution_message_origins' if operation == 'message_create' else 'execution_handoff_origins'
        assert uow.connection.execute(f'SELECT source_session_key FROM {table} WHERE {resource}=?',
            (result[resource],)).fetchone()[0] == runtime_key(cap['scope'])
        assert uow.connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
        assert json.loads(uow.connection.execute('SELECT executed_result FROM approvals WHERE approval_id=?',
            (approval_id,)).fetchone()[0]) == result
    after = snapshot(deps)
    assert recover(opening, cap, operation)['data']['request_receipt'] == result['request_receipt']
    assert create(opening, cap, operation)['data']['request_receipt'] == result['request_receipt']
    assert snapshot(deps) == after


def test_message_request_retry_has_one_canonical_delivery_and_one_execution_charge(connected_local, monkeypatch):
    setup, binding, native = connected_local
    canonical.enable(setup, binding)
    before = snapshot(setup[0])
    first = canonical.send(setup, monkeypatch, client_request_id='canonical-message')
    assert first['ok'] and first['data']['status'] == 'created', first
    assert first['data']['reused'] is False
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute(
            "SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
    try:
        canonical.wait_receipt(setup, turn)
        admitted = snapshot(setup[0])
        assert admitted['delivery_outbox'] == before['delivery_outbox'] + 1
        assert admitted['execution_operations'] == before['execution_operations'] + 2
        assert admitted['used_executions'] == before['used_executions'] + 1
        for _ in range(3):
            again = canonical.send(setup, monkeypatch, client_request_id='canonical-message')
            assert again['ok'] and again['data']['reused'] is True, again
            assert again['data']['request_receipt'] == first['data']['request_receipt']
        assert snapshot(setup[0]) == admitted
        assert native.opens == 1 and len(native.native.sent) == 1
    finally:
        closed = canonical.admit(setup, binding, 'coordination-close', 'runtime.close', session_id=turn['session_id'])
        canonical.wait_receipt(setup, closed, stages=('SUCCEEDED',))


def test_late_receipt_insert_failure_rolls_back_canonical_delivery_and_execution_charge(connected_local, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite.coordination_requests import SqliteCoordinationRequestRepo
    setup, binding, native = connected_local
    deps = setup[0]
    canonical.enable(setup, binding)
    before = snapshot(deps)
    observed = []
    original = SqliteCoordinationRequestRepo.record

    def capture_before_insert(repo, uow, *args, **kwargs):
        observed.append(snapshot_connection(uow.connection))
        return original(repo, uow, *args, **kwargs)

    monkeypatch.setattr(SqliteCoordinationRequestRepo, 'record', capture_before_insert)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('CREATE TRIGGER reject_coordination_receipt BEFORE INSERT ON coordination_requests '
                               "BEGIN SELECT RAISE(ABORT,'injected late coordination receipt failure'); END")
    failed = canonical.send(setup, monkeypatch, client_request_id='canonical-rollback')
    assert not failed['ok'], failed
    assert len(observed) == 1
    assert observed[0]['delivery_outbox'] == before['delivery_outbox'] + 1
    assert observed[0]['execution_operations'] == before['execution_operations'] + 2
    # Execution is charged by dispatch after commit; the rejected admission must
    # leave neither dispatchable work nor a charge behind.
    assert observed[0]['used_executions'] == before['used_executions']
    assert snapshot(deps) == before
    assert native.opens == 0
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER reject_coordination_receipt')
    retried = canonical.send(setup, monkeypatch, client_request_id='canonical-rollback')
    assert retried['ok'] and retried['data']['reused'] is False, retried
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute(
            "SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
    try:
        canonical.wait_receipt(setup, turn)
        after = snapshot(deps)
        assert after['coordination_requests'] == before['coordination_requests'] + 1
        assert after['delivery_outbox'] == before['delivery_outbox'] + 1
        assert after['execution_operations'] == before['execution_operations'] + 2
        assert after['used_executions'] == before['used_executions'] + 1
        assert native.opens == 1 and len(native.native.sent) == 1
    finally:
        closed = canonical.admit(setup, binding, 'coordination-rollback-close', 'runtime.close',
                                 session_id=turn['session_id'])
        canonical.wait_receipt(setup, closed, stages=('SUCCEEDED',))
