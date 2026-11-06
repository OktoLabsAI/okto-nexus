"""Passive generic approval review and generation-fenced canonical decisions."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_hitl import _attach, _client, _count, _ok, _rule, _ws_id, make_env
from test_coordination_creation import create, prepare
import test_pr34_remediation as coordination_fixtures

sys.path.insert(0, str(Path(__file__).parent / 'execution_r4'))
import test_binding_operator as binding_fixtures  # noqa: E402
import test_native_decisions as native_fixtures  # noqa: E402

from okto_nexus.adapters.outbound.sqlite.attention_approvals import SOURCE_SQL, build_policy
from okto_nexus.application.attention_approvals import project
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.attention import instant
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

runtime = coordination_fixtures.runtime
onboarding = binding_fixtures.onboarding
decision_state = native_fixtures.decision_state
opening = native_fixtures.opening


@pytest.fixture(autouse=True)
def isolated_inventory(monkeypatch):
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=()))


@pytest.fixture
def env(tmp_path):
    return make_env(tmp_path, feature_hitl=True)


def read(uow, deps, *, now=None, workspace_id=None, agent_id=None, context=None):
    now = now or deps.clock.now_iso()
    context = context or RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    policy = build_policy(uow, config=deps.config, access=build_execution_access(deps),
        context=context, now=now, decision_registry=deps.approvals.attention_decision_actions())
    rows = [json.loads(row['facts']) for row in uow.connection.execute(SOURCE_SQL,
        dict(now=now, workspace_id=workspace_id, agent_id=agent_id))]
    return rows, policy, now


def snapshot(deps, **kwargs):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows, policy, now = read(uow, deps, **kwargs)
        return [project(row, now, policy)[0] for row in rows]


def pending(env, action='message_create'):
    deps, tools, root = env
    _attach(deps, 'alpha', governance=[_rule(action, 'require_approval')])
    arguments = dict(project_root=root, from_agent_id='alpha',
        target=dict(strategy='direct', agent_id='beta'))
    arguments.update(dict(subject='private-subject-marker', body='private-body-marker')
        if action == 'message_create' else dict(visibility='eligible', payload={'objective': 'private-payload-marker'}))
    result = _ok(tools[action](**arguments))
    assert result['status'] == 'pending_approval'
    return result['approval_id']


def intercepted(env, *, action='message_create', **kwargs):
    deps, tools, root = env
    workspace = _ws_id(tools, root)
    with deps.connection_factory.unit_of_work() as uow:
        return deps.approvals.intercept(uow, workspace_id=workspace, agent_id='alpha',
            action=action, policy_id='inline#r0', kwargs=kwargs)['approval_id']


def by_id(deps, approval_id, **kwargs):
    return next(item for item in snapshot(deps, **kwargs) if item['source_id'] == approval_id)


def after(value):
    return (instant(value) + timedelta(seconds=1)).isoformat()


@pytest.mark.parametrize('action', ['message_create', 'handoff_create'])
def test_canonical_governance_approval_is_metadata_only_and_decidable_after_flag_off(env, action):
    deps, _, _ = env
    approval_id = pending(env, action)
    first = by_id(deps, approval_id)
    assert first['kind'] == 'approval_pending' and first['resolution'] == 'open'
    assert first['allowed_actions'] == ['inspect_approval', 'decide_approval']
    assert first['next_change_at'] is None
    deps.config.feature_hitl = False
    assert by_id(deps, approval_id)['allowed_actions'] == first['allowed_actions']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows, policy, now = read(uow, deps)
        encoded = json.dumps(rows + [project(row, now, policy)[0] for row in rows])
        assert all(value not in encoded for value in ('private-body-marker', 'private-subject-marker',
            'private-payload-marker', 'request_payload', 'api_key_hash', 'authority_binding'))
    with _client(deps) as client:
        detail = _ok(client.get(f'/api/v1/approvals/{approval_id}').json())
        assert type(detail['decision_revision']) is int
        result = client.post(f'/api/v1/approvals/{approval_id}/decision', json={
            'decision': 'approve', 'expected_decision_revision': detail['decision_revision']})
        assert result.status_code == 200, result.text
    completed = by_id(deps, approval_id)
    assert completed['attention_id'] == first['attention_id']
    assert completed['resolution'] == 'resolved'
    assert completed['allowed_actions'] == ['inspect_approval']


@pytest.mark.parametrize('final_decision', ['approve', 'reject'])
def test_http_stale_generation_cannot_decide_after_failed_executor_reverts(env, monkeypatch, final_decision):
    deps, _, _ = env
    approval_id = pending(env)
    first = by_id(deps, approval_id)
    calls = []

    def counted(arguments):
        # A successful rejection separately sends its canonical operator notice.
        if arguments.get('from_agent_id') == 'alpha':
            calls.append(None)
        return original(arguments)

    with _client(deps) as client:
        # build_app registers the real HTTP executors; count the final wiring.
        original = deps.approvals._executors['message_create']
        monkeypatch.setitem(deps.approvals._executors, 'message_create', counted)
        url = f'/api/v1/approvals/{approval_id}'
        old = _ok(client.get(url).json())['decision_revision']
        # Re-execution still enforces the original sender's current permission.
        _attach(deps, 'alpha', governance=[_rule('message_create', 'deny')])
        rejected = client.post(url + '/decision', json={'decision': 'approve', 'expected_decision_revision': old})
        assert rejected.status_code == 403, rejected.text
        current = _ok(client.get(url).json())
        assert current['status'] == 'pending' and current['decision_revision'] > old
        assert len(calls) == 1 and _count(deps, 'messages') == 0
        still_reviewable = by_id(deps, approval_id)
        assert still_reviewable['attention_id'] == first['attention_id']
        assert still_reviewable['source_revision'] != first['source_revision']
        assert still_reviewable['allowed_actions'] == ['inspect_approval', 'decide_approval']
        before = (current, _count(deps, 'events'), _count(deps, 'messages'))
        for stale_decision in ('approve', 'reject'):
            stale = client.post(url + '/decision', json={
                'decision': stale_decision, 'expected_decision_revision': old})
            assert stale.status_code == 409, stale.text
            assert stale.json()['error']['code'] == 'CONFLICT'
            assert len(calls) == 1
            assert (_ok(client.get(url).json()), _count(deps, 'events'), _count(deps, 'messages')) == before
        if final_decision == 'approve':
            _attach(deps, 'alpha')
        fresh = client.post(url + '/decision', json={
            'decision': final_decision, 'expected_decision_revision': current['decision_revision']})
        assert fresh.status_code == 200, fresh.text
        assert len(calls) == (2 if final_decision == 'approve' else 1)
        assert _ok(client.get(url).json())['status'] == ('approved' if final_decision == 'approve' else 'rejected')


@pytest.mark.parametrize('revision', [True, False, -1, 1.5, '0', [], {}])
def test_decision_revision_is_strict_in_application_and_http(env, revision):
    deps, _, _ = env
    approval_id = pending(env)
    with pytest.raises(OktoNexusError) as failure:
        deps.approvals.decide(approval_id=approval_id, decision='reject', decided_by='operator',
            expected_decision_revision=revision)
    assert str(failure.value.code) == 'VALIDATION_ERROR'
    with _client(deps) as client:
        response = client.post(f'/api/v1/approvals/{approval_id}/decision', json={
            'decision': 'reject', 'expected_decision_revision': revision})
        assert response.status_code == 422, response.text
    assert deps.approvals.get_approval(approval_id=approval_id)['decision_revision'] == 0


def test_snapshot_registry_is_inert_and_does_not_predict_approve_business_gates(env):
    deps, _, _ = env
    callbacks = []
    deps.approvals.register_decision_validator('synthetic', lambda *a, **k: callbacks.append(k))
    registry = deps.approvals.attention_decision_actions()
    assert registry['synthetic'] == {'executor': False, 'validator': True, 'transactional': False}
    assert registry['message_create']['executor'] is True
    registry['message_create']['executor'] = False
    assert deps.approvals.attention_decision_actions()['message_create']['executor'] is True
    assert callbacks == []


@pytest.mark.parametrize('mode', ['validator', 'transactional'])
def test_stale_revision_is_checked_before_registered_decision_handler(env, mode):
    deps = env[0]
    approval_id = intercepted(env, action='synthetic')
    calls = []

    def handler(*args, **kwargs):
        calls.append(kwargs)
        return {}

    if mode == 'validator':
        deps.approvals.register_decision_validator('synthetic', handler)
    else:
        deps.approvals.register_transactional_decision('synthetic', handler)
    with pytest.raises(OktoNexusError) as error:
        deps.approvals.decide(approval_id=approval_id, decision='reject', decided_by='operator',
            expected_decision_revision=1)
    assert str(error.value.code) == 'CONFLICT' and calls == []
    assert deps.approvals.get_approval(approval_id=approval_id)['status'] == 'pending'


def test_http_engine_generic_approval_summary_pages_and_seen_do_not_decide(env):
    deps, tools, root = env
    first_id = pending(env)
    second_id = pending(env, 'handoff_create')
    workspace = _ws_id(tools, root)
    with _client(deps) as client:
        filters = dict(workspace_id=workspace, agent_id='alpha', kind='approval_pending')
        first = _ok(client.get('/api/v1/attention', params=filters).json())
        summary = _ok(client.get('/api/v1/attention/summary', params=filters).json())
        assert first['total'] == summary['total'] == 2
        assert first['counts'] == summary['counts']
        assert first['snapshot_revision'] == summary['snapshot_revision']
        assert {item['source_id'] for item in first['items']} == {first_id, second_id}
        assert all(item['allowed_actions'] == ['inspect_approval', 'decide_approval'] for item in first['items'])
        page = _ok(client.get('/api/v1/attention', params=dict(filters, limit=1)).json())
        rest = _ok(client.get('/api/v1/attention', params=dict(filters, limit=1, cursor=page['next_cursor'])).json())
        assert page['items'] + rest['items'] == first['items'] and rest['next_cursor'] is None
        item = first['items'][0]
        before = [_ok(client.get(f'/api/v1/approvals/{aid}').json()) for aid in (first_id, second_id)]
        changed = client.post(f"/api/v1/attention/{item['attention_id']}/seen", json={
            'source_revision': item['source_revision'], 'preference_revision': 0})
        assert changed.status_code == 200, changed.text
        viewed = _ok(changed.json())['item']
        assert viewed['seen_state']['seen'] and viewed['resolution'] == 'open'
        assert viewed['allowed_actions'] == item['allowed_actions']
        assert [_ok(client.get(f'/api/v1/approvals/{aid}').json()) for aid in (first_id, second_id)] == before
        listing = _ok(client.get('/api/v1/approvals', params={'workspace': workspace}).json())
        assert all(type(row['decision_revision']) is int for row in listing['items'])
        assert all(marker not in json.dumps(first) for marker in (
            'private-subject-marker', 'private-body-marker', 'private-payload-marker', 'request_payload'))


@pytest.mark.parametrize('recipient,expected', [
    ('operator', ['inspect_approval', 'decide_approval']),
    ('beta', ['inspect_approval']), (None, ['inspect_approval']),
    ('', ['inspect_approval']), (7, ['inspect_approval']),
])
def test_generic_directed_recipient_is_not_borrowed_from_operator(env, recipient, expected):
    approval_id = intercepted(env, recipient_agent_id=recipient, body='private-body-marker')
    assert by_id(env[0], approval_id)['allowed_actions'] == expected


def test_generic_governance_has_no_invented_ttl_and_unknown_action_is_inspect_only(env):
    ordinary = intercepted(env, expires_at='2000-01-01T00:00:00Z')
    unknown = intercepted(env, action='future.unwired', recipient_agent_id='operator')
    assert by_id(env[0], ordinary)['allowed_actions'] == ['inspect_approval', 'decide_approval']
    assert by_id(env[0], ordinary)['next_change_at'] is None
    assert by_id(env[0], unknown)['allowed_actions'] == ['inspect_approval']


@pytest.mark.parametrize('payload', ['malformed', '[]', '{"kwargs": []}', '{"kwargs": null}'])
def test_malformed_payload_retains_inspectable_reference(env, payload):
    approval_id = pending(env)
    deps = env[0]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE approvals SET request_payload=? WHERE approval_id=?', (payload, approval_id))
    item = by_id(deps, approval_id)
    assert item['freshness'] == 'unavailable' and item['allowed_actions'] == ['inspect_approval']


def test_archive_keeps_same_history_and_removes_decision(env):
    deps = env[0]
    approval_id = pending(env)
    before = by_id(deps, approval_id)
    deps.approvals.archive(approval_id=approval_id, archived_by='operator')
    item = by_id(deps, approval_id)
    assert item['attention_id'] == before['attention_id']
    assert item['resolution'] == 'resolved' and item['allowed_actions'] == ['inspect_approval']


@pytest.mark.parametrize('runtime', [False], indirect=True)
@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_coordination_approval_uses_correlated_receipt_and_passive_expiry(runtime, operation):
    deps = runtime[0]
    deps.config.feature_hitl = True
    args = prepare(runtime, operation)
    _attach(deps, 'caller', governance=[_rule(operation, 'require_approval')])
    result = _ok(create(runtime, operation, args))
    approval_id = result['approval_id']
    first = by_id(deps, approval_id)
    assert first['allowed_actions'] == ['inspect_approval', 'decide_approval']
    for sql in (
        'DELETE FROM coordination_requests',
        "UPDATE coordination_requests SET state='created',resource_id='missing-resource'",
        "UPDATE coordination_requests SET workspace_id='foreign'",
        "UPDATE coordination_requests SET client_request_id='foreign'",
        "UPDATE coordination_requests SET request_hash='different'",
    ):
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('SAVEPOINT changed')
            uow.connection.execute(sql)
            rows, policy, now = read(uow, deps)
            item, = project(rows[0], now, policy)
            assert item['allowed_actions'] == ['inspect_approval'], sql
            uow.connection.execute('ROLLBACK TO changed')
            uow.connection.execute('RELEASE changed')
    expired = by_id(deps, approval_id, now=after(result['request_receipt']['expires_at']))
    assert expired['resolution'] == 'expired' and expired['allowed_actions'] == ['inspect_approval']
    assert expired['attention_id'] == first['attention_id']
    assert deps.approvals.get_approval(approval_id=approval_id)['status'] == 'pending'


def test_binding_proposal_correlates_revision_scope_and_deadline_without_deciding(onboarding):
    deps, client, headers, prepare_body = onboarding
    _, _, approval_id = binding_fixtures.prepare_delegated(client, headers, prepare_body)
    first = by_id(deps, approval_id)
    assert first['allowed_actions'] == ['inspect_approval', 'decide_approval']
    for sql in (
        "UPDATE execution_proposals SET status='APPLIED'",
        'UPDATE execution_proposals SET proposal_revision=proposal_revision+1',
        "UPDATE execution_proposals SET diff_hash='changed'",
        "UPDATE execution_proposals SET expected_revisions_json=json_set(expected_revisions_json,'$.operator_approval_id','other')",
    ):
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('SAVEPOINT changed')
            uow.connection.execute(sql)
            rows, policy, now = read(uow, deps)
            assert project(rows[0], now, policy)[0]['allowed_actions'] == ['inspect_approval'], sql
            uow.connection.execute('ROLLBACK TO changed')
            uow.connection.execute('RELEASE changed')
    expired = by_id(deps, approval_id, now=after(first['next_change_at']))
    assert expired['resolution'] == 'expired' and expired['allowed_actions'] == ['inspect_approval']
    assert deps.approvals.get_approval(approval_id=approval_id)['status'] == 'pending'
    denied = binding_fixtures.decide_binding(client, headers, approval_id, 'reject')
    assert denied.status_code == 200, denied.text
    assert by_id(deps, approval_id)['resolution'] == 'resolved'


def test_canonical_native_not_duplicated_or_orphan_promoted_to_generic_decision(decision_state):
    deps, _, _ = decision_state
    assert snapshot(deps) == []
    with deps.connection_factory.unit_of_work() as uow:
        row = uow.connection.execute('SELECT canonical_request_id,expires_at FROM execution_native_requests').fetchone()
        uow.connection.execute('DELETE FROM execution_native_requests')
    item = by_id(deps, row['canonical_request_id'])
    assert item['allowed_actions'] == ['inspect_approval']
    assert item['freshness'] == 'unavailable'
    old = by_id(deps, row['canonical_request_id'], now=after(row['expires_at']))
    assert old['resolution'] == 'expired'
    assert old['freshness'] == 'unavailable'


@pytest.mark.parametrize('action', ['execution.native.respond', 'runtime_native_approval'])
def test_legacy_orphan_never_promises_generic_decision(env, action):
    approval_id = intercepted(env, action=action, recipient_agent_id='operator', expires_at='not-a-time')
    item = by_id(env[0], approval_id)
    assert item['allowed_actions'] == ['inspect_approval'] and item['freshness'] == 'unavailable'


def test_retained_legacy_expiry_is_history_without_current_native_authority(env):
    deps = env[0]
    approval_id = intercepted(env, action='runtime_native_approval', recipient_agent_id='beta')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows, policy, now = read(uow, deps)
    facts, = rows
    facts['legacy'] = {'state': 'PENDING', 'expires_at': now}
    item, = project(facts, after(now), policy)
    assert item['source_id'] == approval_id and item['resolution'] == 'expired'
    assert item['allowed_actions'] == ['inspect_approval'] and item['freshness'] == 'stale'


def test_source_is_pure_scope_filtered_and_constant_queries(env, monkeypatch):
    deps = env[0]
    pending(env)
    assert snapshot(deps, workspace_id='foreign') == []
    assert snapshot(deps, agent_id='foreign') == []
    with deps.connection_factory.unit_of_work() as uow:
        conn, statements = uow.connection, []
        conn.set_trace_callback(statements.append)
        try:
            rows, policy, now = read(uow, deps)
        finally:
            conn.set_trace_callback(None)
        count = len(statements)
        original = dict(conn.execute('SELECT * FROM approvals').fetchone())
        for index in range(24):
            clone = dict(original, approval_id=f'apr_batch_{index}')
            conn.execute('INSERT INTO approvals(' + ','.join(clone) + ') VALUES (' + ','.join('?' for _ in clone) + ')',
                tuple(clone.values()))
        statements.clear()
        changes = conn.total_changes
        conn.set_trace_callback(statements.append)
        try:
            many, _, _ = read(uow, deps)
        finally:
            conn.set_trace_callback(None)
        assert len(many) == 25 and len(statements) == count
        assert count <= 3 and conn.total_changes == changes
    with monkeypatch.context() as pure:
        pure.setattr(deps.connection_factory, 'unit_of_work', lambda **_: pytest.fail('Unexpected projection SQL'))
        pure.setattr(deps.clock, 'now_iso', lambda: pytest.fail('Unexpected projection clock'))
        assert project(deepcopy(rows[0]), now, deepcopy(policy)) == project(rows[0], now, policy)
