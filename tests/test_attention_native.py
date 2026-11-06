"""Pure native attention is equivalent to the canonical command's authority."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

# Reuse synthetic admitted turns and native ingress, never a personal provider.
sys.path.insert(0, str(Path(__file__).parent / 'execution_r4'))
import test_native_decisions as native_fixtures  # noqa: E402

from okto_nexus.adapters.outbound.sqlite.attention_native import SOURCE_SQL, build_policy
from okto_nexus.application.attention_native import project, require_live
from okto_nexus.application.execution_binding_proposals import _agent_guard
from okto_nexus.application.execution_native_facts import stamp
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

decision_state = native_fixtures.decision_state
opening = native_fixtures.opening


@pytest.fixture(autouse=True)
def isolated_native_inventory(monkeypatch):
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=()))


def read_snapshot(uow, deps, *, workspace_id=None, agent_id=None, now=None):
    now = now or deps.clock.now_iso()
    access = build_execution_access(deps)
    context = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    policy = build_policy(uow, config=deps.config, access=access, context=context, now=now)
    facts = [json.loads(row['facts']) for row in uow.connection.execute(SOURCE_SQL,
        dict(now=now, workspace_id=workspace_id, agent_id=agent_id))]
    return facts, policy, now


def snapshot(deps, **kwargs):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return read_snapshot(uow, deps, **kwargs)


@pytest.mark.parametrize('decision_state,kind,action', [
    (None, 'native_permission_pending', 'decide_native'),
    ('input', 'native_question_pending', 'respond_native'),
    ('agent_input', 'question_waiting_for_agent', None),
    ('mcp_permission', 'native_permission_pending', 'decide_native'),
], indirect=['decision_state'])
def test_canonical_native_ingress_projects_exact_recipient_and_existing_action(decision_state, kind, action):
    deps, _, _ = decision_state
    rows, policy, now = snapshot(deps)
    assert len(rows) == 1
    require_live(rows[0], now, policy)
    item, = project(rows[0], now, policy)
    assert item['kind'] == kind and item['resolution'] == 'open'
    assert item['allowed_actions'] == ['inspect_approval'] + ([action] if action else [])
    assert item['category'] == ('action_required' if action else 'watch')
    encoded = json.dumps(item)
    assert all(text not in encoded for text in ('private-marker', 'cas_token', 'operational_frame', 'request_payload', 'api_key_hash'))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT * FROM execution_native_requests').fetchone()
        assert deps.native_decisions._live(uow, row, json.loads(row['operational_frame_json'])) == rows[0]['request']['scope']


def test_projection_filters_scope_before_facts_and_does_not_write(decision_state):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = uow.connection.total_changes
        rows = list(uow.connection.execute(SOURCE_SQL, dict(now=deps.clock.now_iso(), workspace_id='foreign', agent_id=None)))
        assert rows == [] and uow.connection.total_changes == before
    assert snapshot(deps, agent_id='foreign')[0] == []


def test_project_uses_only_explicit_time_policy_and_facts(decision_state, monkeypatch):
    deps, _, _ = decision_state
    rows, policy, now = snapshot(deps)
    from nexus_connector_core import catalog
    # Restore before the application lifespan performs its own shutdown work.
    with monkeypatch.context() as pure:
        pure.setattr(deps.connection_factory, 'unit_of_work', lambda **_: pytest.fail('Unexpected projection SQL'))
        pure.setattr(deps.clock, 'now_iso', lambda: pytest.fail('Unexpected projection clock'))
        pure.setattr(catalog, 'get_runtime_catalog', lambda: pytest.fail('Unexpected global catalog'))
        assert project(deepcopy(rows[0]), now, deepcopy(policy)) == project(rows[0], now, policy)


def outcome(call):
    try:
        call()
        return None
    except OktoNexusError as error:
        return str(error.code)


def test_projection_and_canonical_command_reject_the_same_changed_authority(decision_state):
    deps, _, _ = decision_state
    # Each case changes a real canonical row. Refreshing the source digest in
    # selected cases reaches the downstream gate instead of only its guard.
    cases = [
        ('revisions', "UPDATE execution_agent_revisions SET authorization_revision=authorization_revision+1", False),
        ('inactive', "UPDATE agents SET is_active=0 WHERE agent_id='subject'", False),
        ('credential', "UPDATE agents SET api_key_hash='changed' WHERE agent_id='subject'", False),
        ('permissions', "UPDATE agents SET permissions='{}' WHERE agent_id='subject'", False),
        ('profile disabled', "UPDATE runtime_profiles SET enabled=0", True),
        ('native approvals disabled', "UPDATE runtime_profiles SET config=json_set(config,'$.disabled_capabilities',json('[\"approvals\"]'))", True),
        ('endpoint disabled', "UPDATE agent_endpoints SET enabled=0", False),
        ('quarantined', "UPDATE agent_endpoints SET health='quarantined'", False),
        ('grant revoked', "UPDATE runtime_execution_grants SET revoked_at='2000-01-01T00:00:00Z'", False),
        ('grant expired', "UPDATE runtime_execution_grants SET no_expiry=0,expires_at='2000-01-01T00:00:00Z'", False),
        ('grant cannot send', "UPDATE runtime_execution_grants SET actions='[\"open\"]'", False),
        ('lease expired', "UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z'", False),
        ('lease unapplied', "UPDATE execution_leases SET applied_at=NULL", False),
        ('lease connection', "UPDATE execution_leases SET connection_id='foreign'", False),
        ('session epoch', "UPDATE execution_sessions SET stream_epoch='foreign'", False),
        ('session lease', "UPDATE execution_sessions SET lease_state='NONE'", False),
        ('owner generation', "UPDATE execution_sessions SET owner_generation=owner_generation+1", False),
        ('turn terminal', "UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' WHERE action='turn.submit'", False),
        ('turn scope', "UPDATE execution_operations SET expected_revisions_json='{}' WHERE action='turn.submit'", False),
        ('lane disconnected', "UPDATE execution_control_lanes SET state='DISCONNECTED'", False),
        ('lane expired', "UPDATE execution_control_lanes SET expires_at='2000-01-01T00:00:00Z'", False),
        ('ticket revoked', "UPDATE execution_link_tickets SET revoked_at='2000-01-01T00:00:00Z'", False),
        ('ticket scopes', "UPDATE execution_link_tickets SET scopes_json='[]'", False),
        ('runtime disabled', "UPDATE runtime_policy_defaults SET runtime_enabled=0", True),
        ('execution location', "UPDATE agent_execution_policies SET execution_location='local' WHERE agent_id='subject'", True),
        ('recovery', "INSERT INTO execution_agent_recovery(server_id,executor_id,agent_id,generation,state,updated_at) SELECT server_id,executor_id,'subject',generation,'RECOVERING','2000-01-01T00:00:00Z' FROM execution_executors", False),
        ('containment', "INSERT INTO execution_session_containment(server_id,executor_id,session_id,owner_generation,opening_operation_id,opening_intent_hash,request_json,recorded_at) SELECT server_id,executor_id,session_id,owner_generation,open_operation_id,'test','{}','2000-01-01T00:00:00Z' FROM execution_sessions", False),
    ]
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        for label, sql, refresh in cases:
            conn.execute('SAVEPOINT authority_case')
            try:
                conn.execute(sql)
                if refresh:
                    conn.execute('UPDATE execution_client_intents SET source_guard_digest=?', (_agent_guard(conn, 'subject'),))
                rows, policy, now = read_snapshot(uow, deps)
                row = conn.execute('SELECT * FROM execution_native_requests').fetchone()
                command = outcome(lambda: deps.native_decisions._live(uow, row, json.loads(row['operational_frame_json'])))
                projection = outcome(lambda: require_live(rows[0], now, policy))
                assert command is not None, label
                assert projection == command, (label, command, projection)
                assert project(rows[0], now, policy)[0]['allowed_actions'] == ['inspect_approval'], label
            finally:
                conn.execute('ROLLBACK TO authority_case')
                conn.execute('RELEASE authority_case')


def test_exhausted_productive_budget_does_not_revoke_native_response(decision_state):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET unlimited_actions=0,used_executions=max_executions')
        rows, policy, now = read_snapshot(uow, deps)
        row = uow.connection.execute('SELECT * FROM execution_native_requests').fetchone()
        deps.native_decisions._live(uow, row, json.loads(row['operational_frame_json']))
        require_live(rows[0], now, policy)
        assert project(rows[0], now, policy)[0]['allowed_actions'][-1] == 'decide_native'


def test_recorded_operator_initiation_uses_the_same_current_guard(decision_state):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("UPDATE execution_operations SET actor_agent_id='operator' WHERE action='runtime.open'")
        conn.execute("UPDATE execution_client_intents SET actor_agent_id='operator',actor_guard_digest=? "
            "WHERE operation_id IN (SELECT operation_id FROM execution_operations WHERE action='runtime.open')",
            ('local-operator:' + _agent_guard(conn, 'operator'),))
        rows, policy, now = read_snapshot(uow, deps)
        row = conn.execute('SELECT * FROM execution_native_requests').fetchone()
        def command():
            return deps.native_decisions._live(uow, row, json.loads(row['operational_frame_json']))
        assert outcome(command) is None
        assert outcome(lambda: require_live(rows[0], now, policy)) is None
        conn.execute("UPDATE agents SET color='changed' WHERE agent_id='operator'")
        rows, policy, now = read_snapshot(uow, deps)
        assert outcome(command) == outcome(lambda: require_live(rows[0], now, policy)) == 'CONFLICT'
        assert project(rows[0], now, policy)[0]['allowed_actions'] == ['inspect_approval']


@pytest.mark.parametrize('state,resolution', [('EXPIRED', 'expired'), ('DECIDED', 'resolved'), ('STALE', 'resolved')])
def test_historical_request_without_approval_is_stable_and_non_actionable(decision_state, state, resolution):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_native_requests SET state=?', (state,))
        uow.connection.execute('DELETE FROM approvals')
    rows, policy, now = snapshot(deps)
    assert rows[0]['authority'] is None and rows[0]['runtime'] is None
    first, = project(rows[0], now, policy)
    later, = project(rows[0], (stamp(now) + timedelta(days=1)).isoformat(), policy)
    assert first == later
    assert first['resolution'] == resolution and first['allowed_actions'] == []
    assert first['next_change_at'] is None


def test_expiration_changes_resolution_without_writing_native_lifecycle(decision_state):
    deps, _, _ = decision_state
    rows, policy, now = snapshot(deps)
    first, = project(rows[0], now, policy)
    later, _, observed = snapshot(deps, now=rows[0]['request']['expires_at'])
    expired, = project(later[0], observed, policy)
    assert expired['attention_id'] == first['attention_id']
    assert expired['resolution'] == 'expired' and expired['allowed_actions'] == ['inspect_approval']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT state FROM execution_native_requests').fetchone()[0] == 'PENDING'
        assert uow.connection.execute('SELECT status FROM approvals').fetchone()[0] == 'pending'


def test_authority_deadline_is_earlier_than_native_request_expiry(decision_state):
    deps, _, _ = decision_state
    rows, policy, now = snapshot(deps)
    facts = rows[0]
    deadline = (stamp(now) + timedelta(seconds=1)).isoformat()
    facts['latest_lease']['valid_until_server'] = deadline
    before, = project(facts, now, policy)
    after, = project(facts, deadline, policy)
    assert before['next_change_at'] == stamp(deadline).isoformat(timespec='microseconds')
    assert before['allowed_actions'][-1] == 'decide_native'
    assert after['allowed_actions'] == ['inspect_approval']
    assert after['attention_id'] == before['attention_id']


def test_issued_renewal_keeps_only_a_compatible_applied_lease(decision_state):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        prior = dict(conn.execute('SELECT * FROM execution_leases ORDER BY lease_serial DESC LIMIT 1').fetchone())
        renewal = dict(prior, lease_serial=prior['lease_serial'] + 1,
            lease_id='attention-renewal', request_id='attention-renewal', status='ISSUED', applied_at=None,
            request_json=json.dumps(dict(json.loads(prior['request_json']), purpose='renew')))
        conn.execute('INSERT INTO execution_leases(' + ','.join(renewal) + ') VALUES ('
            + ','.join('?' for _ in renewal) + ')', tuple(renewal.values()))
        row = conn.execute('SELECT * FROM execution_native_requests').fetchone()
        def command():
            return deps.native_decisions._live(uow, row, json.loads(row['operational_frame_json']))
        rows, policy, now = read_snapshot(uow, deps)
        assert outcome(command) is None
        assert outcome(lambda: require_live(rows[0], now, policy)) is None
        assert project(rows[0], now, policy)[0]['allowed_actions'][-1] == 'decide_native'
        for field, value in [('scope_json', '{}'), ('connection_id', 'foreign'), ('connection_generation', 999),
                ('grant_id', 'foreign'), ('source_grant_revision', 999), ('allowed_actions_json', '[]')]:
            conn.execute('SAVEPOINT incompatible_renewal')
            try:
                conn.execute('UPDATE execution_leases SET ' + field + '=? WHERE lease_serial=?', (value, renewal['lease_serial']))
                rows, policy, now = read_snapshot(uow, deps)
                assert outcome(command) == outcome(lambda: require_live(rows[0], now, policy)) == 'CONFLICT', field
                assert project(rows[0], now, policy)[0]['allowed_actions'] == ['inspect_approval'], field
            finally:
                conn.execute('ROLLBACK TO incompatible_renewal')
                conn.execute('RELEASE incompatible_renewal')


@pytest.mark.parametrize('decision_state', ['input'], indirect=True)
def test_broken_domain_provenance_never_borrows_operator_recipient(decision_state):
    deps, _, _ = decision_state
    rows, policy, now = snapshot(deps)
    facts = rows[0]
    assert facts['source']['actor_agent_id'] == 'operator'
    assert project(facts, now, policy)[0]['allowed_actions'][-1] == 'respond_native'
    # This is the LEFT JOIN shape when the immutable delivery exists but its
    # source message is gone. The shared canonical recipient predicate must
    # not fall back to the turn's actor or approval display metadata.
    facts['domain_link_exists'] = True
    facts['domain_sender'] = None
    unknown, = project(facts, now, policy)
    assert unknown['allowed_actions'] == ['inspect_approval']
    assert unknown['freshness'] == 'unavailable' and unknown['category'] == 'watch'
    facts['domain_sender'] = 'other'
    other, = project(facts, now, policy)
    assert other['kind'] == 'question_waiting_for_agent'
    assert other['allowed_actions'] == ['inspect_approval']


def test_operator_response_requires_current_responder_and_authenticated_viewer(decision_state):
    deps, _, _ = decision_state
    rows, policy, now = snapshot(deps)
    facts = rows[0]
    for viewer in (dict(viewer_is_operator=False, viewer_actor='subject'),
                   dict(viewer_is_operator=True, viewer_actor='other')):
        item, = project(facts, now, dict(policy, **viewer))
        assert item['allowed_actions'] == ['inspect_approval']
    facts['operator']['agent']['is_active'] = 0
    item, = project(facts, now, policy)
    assert item['allowed_actions'] == ['inspect_approval']


def test_policy_and_source_query_count_is_constant_for_many_native_requests(decision_state):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        statements = []
        conn.set_trace_callback(statements.append)
        try:
            single, _, _ = read_snapshot(uow, deps)
        finally:
            conn.set_trace_callback(None)
        single_count = len(statements)
        source = dict(conn.execute('SELECT * FROM execution_native_requests').fetchone())
        approval = dict(conn.execute('SELECT * FROM approvals').fetchone())
        for index in range(24):
            clone = dict(source, canonical_request_id='attention-test-' + str(index), native_request_id_json=json.dumps(100 + index))
            for table, row in (('execution_native_requests', clone),
                               ('approvals', dict(approval, approval_id=clone['canonical_request_id']))):
                conn.execute('INSERT INTO ' + table + '(' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
        statements.clear()
        changes = conn.total_changes
        conn.set_trace_callback(statements.append)
        try:
            many, policy, now = read_snapshot(uow, deps)
            items = [project(facts, now, policy)[0] for facts in many]
        finally:
            conn.set_trace_callback(None)
        assert len(single) == 1 and len(many) == 25
        assert len(statements) == single_count == 3
        assert len({item['attention_id'] for item in items}) == 25
        assert all(item['allowed_actions'][-1] == 'decide_native' for item in items)
        assert conn.total_changes == changes


@pytest.mark.parametrize('decision_state,kind,action', [
    (None, 'native_permission_pending', 'decide_native'),
    ('input', 'native_question_pending', 'respond_native'),
    ('agent_input', 'question_waiting_for_agent', None),
], indirect=['decision_state'])
def test_http_engine_combines_native_and_parked_with_consistent_pages_and_passive_preferences(
        decision_state, kind, action, monkeypatch):
    deps, app, _ = decision_state
    rows, _, now = snapshot(deps)
    native = rows[0]['request']
    scope = native['scope']
    # Only the attention observation clock moves. Canonical ingress and live
    # socket ownership remain the real synthetic fixture's responsibility.
    clock = SimpleNamespace(iso=now)
    monkeypatch.setattr(app.state.attention, 'clock', SimpleNamespace(now_iso=lambda: clock.iso))
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        for suffix in ('a', 'b'):
            conn.execute('INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES(?,?,?,?,?)',
                ('attention-message-' + suffix, scope['workspace_id'], 'operator', 'private-attention-body', now))
        # Both canonical delivery rows enter parked in one statement, yielding
        # identical trigger timestamps and a real attention_id tiebreak.
        conn.execute('INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) '
            'VALUES(?,?,?,?,?),(?,?,?,?,?)',
            tuple(value for suffix in ('a', 'b') for value in
                ('attention-delivery-' + suffix, 'attention-message-' + suffix, scope['agent_id'], 'parked', now)))

    def domain_snapshot():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            tables = ('approvals', 'execution_native_requests', 'execution_decisions', 'execution_operations',
                'execution_dispatch_outbox', 'execution_sessions', 'execution_leases', 'message_deliveries')
            return {table: sorted((tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)), key=repr)
                for table in tables}

    def unpack(response):
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        envelope = response.json()
        assert envelope['ok'] is True
        assert all(secret not in response.text for secret in (
            'private-marker', 'private-attention-body', 'sensitive-input-marker',
            'cas_token', 'operational_frame', 'api_key_hash', 'request_payload'))
        return envelope['data']

    before = domain_snapshot()
    headers = {'x-api-key': app.state.test_agent_keys['operator']}
    base = '/api/v1/attention'
    filters = {'workspace_id': scope['workspace_id'], 'agent_id': scope['agent_id']}
    client = TestClient(app, base_url='https://127.0.0.1:8202', headers=headers)
    try:
        complete = unpack(client.get(base, params=filters))
        summary = unpack(client.get(base + '/summary', params=filters))
        assert complete['total'] == summary['total'] == 3
        assert complete['counts'] == summary['counts']
        assert complete['snapshot_revision'] == summary['snapshot_revision']
        assert {item['kind'] for item in complete['items']} == {kind, 'delivery_parked'}
        assert complete['items'] == sorted(complete['items'], key=lambda item:
            (-item['priority'], item['first_detected_at'], item['attention_id']))
        parked = [item for item in complete['items'] if item['kind'] == 'delivery_parked']
        assert parked[0]['first_detected_at'] == parked[1]['first_detected_at']
        pages, cursor = [], None
        for _ in range(3):
            params = dict(filters, limit=1)
            if cursor is not None:
                params['cursor'] = cursor
            page = unpack(client.get(base, params=params))
            assert page['total'] == complete['total'] and page['counts'] == summary['counts']
            assert page['snapshot_revision'] == complete['snapshot_revision']
            assert len(page['items']) == 1
            pages.extend(page['items'])
            cursor = page['next_cursor']
        assert cursor is None and pages == complete['items']
        assert len({item['attention_id'] for item in pages}) == 3
        for selected_kind, count in ((kind, 1), ('delivery_parked', 2)):
            query = dict(filters, kind=selected_kind)
            listing = unpack(client.get(base, params=query))
            counts = unpack(client.get(base + '/summary', params=query))
            assert listing['total'] == counts['total'] == len(listing['items']) == count
            assert listing['counts'] == counts['counts']
        assert unpack(client.get(base, params=dict(filters, workspace_id='foreign')))['total'] == 0
        item = next(item for item in complete['items'] if item['kind'] == kind)
        assert item['allowed_actions'] == ['inspect_approval'] + ([action] if action else [])
        marked = unpack(client.post(base + '/' + item['attention_id'] + '/seen', json={
            'source_revision': item['source_revision'], 'preference_revision': 0}))['item']
        assert marked['seen_state']['seen'] is True and marked['resolution'] == 'open'
        assert marked['allowed_actions'] == item['allowed_actions']
        assert domain_snapshot() == before
        clock.iso = (stamp(native['expires_at']) + timedelta(seconds=1)).isoformat()
        active = unpack(client.get(base, params=filters))
        assert active['total'] == 2 and all(value['kind'] == 'delivery_parked' for value in active['items'])
        historical = unpack(client.get(base, params=dict(filters, state='expired', kind=kind)))
        counts = unpack(client.get(base + '/summary', params=dict(filters, state='expired', kind=kind)))
        assert historical['total'] == counts['total'] == 1
        expired, = historical['items']
        assert expired['attention_id'] == item['attention_id'] and expired['seen_state']['seen'] is True
        assert expired['resolution'] == 'expired' and expired['allowed_actions'] == ['inspect_approval']
        assert domain_snapshot() == before
    finally:
        client.close()
