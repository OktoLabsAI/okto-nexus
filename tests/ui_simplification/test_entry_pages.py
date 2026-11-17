"""UI020/021 optional service/router; real SQLite, no production app wiring."""
import json

from fastapi.testclient import TestClient
import pytest

from okto_nexus.application.home_entries import HomeEntriesService
from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations
from okto_nexus.bootstrap.home_entries import install_home_entries
from okto_nexus.domain.home_entry_pages import cursor_decode
from okto_nexus.errors import OktoNexusError
from .test_fixtures import fixtures
from .test_entry_relations import copy_session, link_handoff


@pytest.fixture
def scenario(tmp_path):
    with fixtures.scenario(tmp_path / 'pages') as value:
        yield value


@pytest.fixture
def large_scenario(scenario):
    s = scenario
    with s.factory.unit_of_work() as uow:
        c, now = uow.connection, s.clock.now_iso()
        handoff = c.execute("SELECT * FROM handoffs WHERE handoff_id='ui-unassigned'").fetchone()
        for i in range(125):
            fixtures._copy(c, 'handoffs', handoff, handoff_id=f'page-bulk-{i:03}')
        link_handoff(c, now)
        opening = c.execute('SELECT * FROM execution_sessions WHERE session_id=?', (s.sessions[0],)).fetchone()
        first_turn = c.execute("SELECT * FROM execution_operations WHERE action='turn.submit' AND binding_id='binding'").fetchone()
        for i in range(25):
            sid, op = f'page-session-{i:02}', f'page-linked-{i:02}'
            copy_session(c, opening, sid)
            fixtures._copy(c, 'execution_operations', first_turn, operation_id=op, session_id=sid)
            c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,?,'entry-domain')",
                      (s.connections[0].server_id, s.connections[0].executor_id, op))
        second_turn = c.execute("SELECT * FROM execution_operations WHERE operation_id='ui-success'").fetchone()
        for i in range(8):
            fixtures._copy(c, 'execution_operations', second_turn, operation_id=f'page-child-{i:02}')
    return s


def read(service, s, **kwargs):
    return service.read(context=s.operator, filters={'quick': 'all'}, **kwargs)


def service_for(s):
    return HomeEntriesService(s.app.state.home, queries=SqliteHomeEntryRelations())


def all_groups(service, s, limit=7):
    items, cursor = [], None
    while True:
        value = read(service, s, limit=limit, cursor=cursor)
        assert value['status'] == 'ready', value
        items.extend(value['items'])
        cursor = value['next_cursor']
        if cursor is None:
            return items, value


def test_all_125_groups_children_and_25_sessions_are_reachable(large_scenario):
    s = large_scenario
    service = service_for(s)
    groups, final = all_groups(service, s)
    assert final['total'] == len(groups) >= 125
    assert len({g['id'] for g in groups}) == len(groups)
    broad = next(g for g in groups if g['connection'] and g['connection']['binding_id'] == 'ui-binding-2')
    assert broad['children_total'] == 10 and len(broad['children']) == 3
    children, cursor = list(broad['children']), broad['children_cursor']
    while cursor:
        page = read(service, s, partition='children', group_id=broad['id'], cursor=cursor, limit=2)
        children.extend(page['items'])
        cursor = page['next_cursor']
    assert len(children) == len({x['id'] for x in children}) == 10
    rich = next((g, e) for g in groups for e in g['children'] if e['source_ref']['id'] == 'ui-handoff-0')
    group, entry = rich
    assert entry['sessions_total'] == 25 and len(entry['sessions']) == 3
    sessions, cursor = list(entry['sessions']), entry['sessions_cursor']
    while cursor:
        page = read(service, s, partition='sessions', group_id=group['id'], entry_id=entry['id'], cursor=cursor, limit=7)
        sessions.extend(page['items'])
        cursor = page['next_cursor']
    assert len({(x['server_id'], x['executor_id'], x['session_id']) for x in sessions}) == len(sessions) == 25


def test_cursor_scope_parent_principal_and_material_revision_are_bound(scenario):
    s, service = scenario, service_for(scenario)
    first = read(service, s, limit=1)
    cursor = first['next_cursor']
    assert cursor
    for filters in ({'quick': 'all', 'workspace_id': 'ws'}, {'quick': 'active'}, {'quick': 'all', 'agent_id': 'B'}):
        with pytest.raises(OktoNexusError) as error:
            service.read(context=s.operator, filters=filters, cursor=cursor, limit=1)
        assert error.value.code == 'CONFLICT'
    with pytest.raises(OktoNexusError) as error:
        read(service, s, partition='children', group_id=first['items'][0]['id'], cursor=cursor)
    assert error.value.code == 'CONFLICT'
    with s.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET updated_at='2026-11-16T12:00:01.000000Z' WHERE handoff_id='ui-unassigned'")
    with pytest.raises(OktoNexusError) as error:
        read(service, s, cursor=cursor)
    assert error.value.code == 'CONFLICT'


def test_external_source_is_complete_reported_and_not_matched_by_agent(scenario):
    s, service = scenario, service_for(scenario)
    groups, page = all_groups(service, s)
    external = next(e for g in groups for e in g['children'] if e['kind'] == 'external')
    assert external['external'][0]['observed_instance_id'] == s.external['observed_instance_id']
    assert external['external'][0]['observational_only'] is True
    assert external['external'][0]['canonical_session_ref'] is None
    assert external['evidence'] == 'reported' and external['sessions_total'] == 0
    assert external['as_of'] == s.clock.now_iso()
    assert s.clock.now_iso() < external['next_refresh_at'] <= '2026-11-16T12:00:15.000000Z'
    assert page['summary']['external_instances']['value'] == 1
    assert page['summary']['activities']['unit'] == 'activities'


def test_quick_sender_receiver_harness_and_host_filters(scenario):
    s, service = scenario, service_for(scenario)
    needed = service.read(context=s.operator, filters={'quick': 'needs_you'})
    assert needed['summary']['occurrences']['value'] >= 1
    assert all(e['attention_refs'] for g in needed['items'] for e in g['children'])
    results = service.read(context=s.operator, filters={'quick': 'results', 'agent_id': 'operator'})
    assert results['summary']['results']['value'] == 1  # receiver result survives sender filter
    for agent in ('subject', 'B'):
        value = service.read(context=s.operator, filters={'quick': 'all', 'agent_id': agent})
        assert value['status'] == 'ready'
    native = service.read(context=s.operator, filters={'quick': 'all', 'harness': 'codex_app_server', 'host': s.connections[0].executor_id})
    assert native['items'] and all(g['connection'] for g in native['items'])
    missing = service.read(context=s.operator, filters={'quick': 'all', 'harness': 'unproven-harness'})
    assert missing['total'] == 0 and missing['total_is_exact']


def test_partial_external_and_budget_keep_unknown_totals(scenario, monkeypatch):
    s, service = scenario, service_for(scenario)
    monkeypatch.setattr(service.queries, 'external', lambda *a, **k: (_ for _ in ()).throw(__import__('sqlite3').OperationalError('own controlled source failure')))
    page = read(service, s)
    assert page['status'] == 'partial' and page['total'] is None
    assert page['source_status']['external'] == 'unavailable'
    assert page['summary']['activities']['value'] is None and page['items']
    monkeypatch.setattr(service, 'QUERY_SECONDS', -1)
    exhausted = read(service, s)
    assert exhausted['status'] == 'unavailable' and exhausted['total'] is None
    assert exhausted['next_cursor'] is None and exhausted['revision'] is None


def test_optional_http_router_exact_pages_and_no_store(scenario):
    s = scenario
    install_home_entries(s.app, s.app.state.home)
    client = TestClient(s.app)
    headers = {'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']}
    try:
        response = client.get('/api/v1/home/entries?quick=all&limit=1', headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        page = response.json()['data']
        group = page['items'][0]
        response = client.get('/api/v1/home/entries/' + group['id'] + '/children?quick=all', headers=headers)
        assert response.status_code == 200 and response.json()['data']['group_id'] == group['id']
        for suffix in ('?quick=all&extra=1', '?quick=all&quick=active', '?limit=101', '?limit=no'):
            response = client.get('/api/v1/home/entries' + suffix, headers=headers)
            assert response.status_code == 422 and response.headers['cache-control'] == 'no-store'
        assert 'cas_token' not in json.dumps(page)
    finally:
        client.close()


def test_http_global_budget_preserves_unknown_envelope_shape(scenario, monkeypatch):
    s = scenario
    service = install_home_entries(s.app, s.app.state.home)
    client = TestClient(s.app)
    headers = {'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']}
    try:
        normal = client.get('/api/v1/home/entries?quick=all', headers=headers).json()['data']
        monkeypatch.setattr(service, 'QUERY_SECONDS', -1)
        response = client.get('/api/v1/home/entries?quick=all', headers=headers)
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        value = response.json()['data']
        assert value['status'] == 'unavailable' and value['items'] == []
        assert value['revision'] is None and value['snapshot_id'] is None
        assert value['next_refresh_at'] is None and value['next_cursor'] is None
        assert value['coverage']['result_tracking'] == 'unknown'
        assert value['event_cursor'] == normal['event_cursor']
        assert value['event_low_watermark'] == normal['event_low_watermark']
        assert value['summary'].keys() == normal['summary'].keys()
        assert value['source_status'].keys() == normal['source_status'].keys()
        assert set(value['source_status'].values()) == {'unavailable'}
        for key, counter in value['summary'].items():
            assert counter == {'value': None, 'total_is_exact': False, 'unit': normal['summary'][key]['unit']}
    finally:
        client.close()


def test_malformed_cursor_and_wrong_parent_are_explicit(scenario):
    s, service = scenario, service_for(scenario)
    with pytest.raises(OktoNexusError) as error:
        read(service, s, cursor='not-a-cursor')
    assert error.value.code == 'VALIDATION_ERROR'
    with pytest.raises(OktoNexusError) as error:
        read(service, s, partition='children', group_id='absent-own-group')
    assert error.value.code == 'NOT_FOUND'
    with pytest.raises(OktoNexusError):
        cursor_decode('!', {}, 'revision')


def test_default_recent_window_and_retained_unseen_are_distinct_from_active(scenario):
    s, service = scenario, service_for(scenario)
    with s.factory.unit_of_work() as uow:
        uow.connection.execute("DELETE FROM execution_session_containment WHERE session_id='ui-session-2'")
        # Historical synthetic read fact, not a dispatch/event-commit claim.
        uow.connection.execute("INSERT INTO execution_event_ingress VALUES(?,?,'ui-session-2','ui-historical-epoch',2,'own-synthetic-event','turn.completed','{}',?)",
                              (s.connections[0].server_id, s.connections[0].executor_id, s.clock.now_iso()))
        uow.connection.execute("INSERT INTO execution_results VALUES(?,?,'ui-success','ui-session-2','ui-historical-epoch',2,'Bounded synthetic result',0,1,'success',?)",
                              (s.connections[0].server_id, s.connections[0].executor_id, s.clock.now_iso()))
    default = service.read(context=s.operator)
    active = service.read(context=s.operator, filters={'quick': 'active'})
    results = service.read(context=s.operator, filters={'quick': 'results'})
    assert default['scope']['include_recent_results'] is True
    assert active['scope']['include_recent_results'] is False
    def result_ids(page):
        return {r for g in page['items'] for e in g['children'] for r in e['result_refs']}
    assert result_ids(results) <= result_ids(default)
    assert not result_ids(active)
    with s.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_receipts SET received_at='2026-11-14T12:00:00.000000Z' WHERE operation_id='ui-success'")
        uow.connection.execute("UPDATE execution_results SET captured_at='2026-11-14T12:00:00.000000Z' WHERE operation_id='ui-success'")
    old = s.read(section='results')['items'][0]
    assert old['view_state'] == 'unseen'  # canonical occurrence/preferences, not assumed false
    assert old['id'] in result_ids(service.read(context=s.operator))
    attention = old['attention']
    s.app.state.attention.mark_seen(context=s.operator, attention_id=attention['attention_id'],
        source_revision=attention['source_revision'], preference_revision=attention['seen_state']['revision'])
    assert old['id'] not in result_ids(service.read(context=s.operator))
    assert old['id'] in result_ids(service.read(context=s.operator, filters={'quick': 'all'}))
    assert old['id'] in result_ids(service.read(context=s.operator, filters={'quick': 'results'}))
    with pytest.raises(OktoNexusError) as error:
        service.read(context=s.operator, filters={'include_recent_results': True})
    assert error.value.code == 'VALIDATION_ERROR'


def test_untracked_old_result_is_unknown_coverage_never_assumed_seen(scenario):
    s, service = scenario, service_for(scenario)
    with s.factory.unit_of_work() as uow:
        uow.connection.execute("DELETE FROM execution_session_containment WHERE session_id='ui-session-2'")
        uow.connection.execute("UPDATE execution_receipts SET received_at='2026-11-14T12:00:00.000000Z' WHERE operation_id='ui-success'")
    page = service.read(context=s.operator)
    assert page['status'] == 'partial' and page['total'] is None
    assert page['coverage']['result_tracking'] == 'partial'
    assert page['summary']['unseen_results']['value'] is None
    result = next(e for g in page['items'] for e in g['children'] if e['result_refs'])
    assert result['result_tracking'] == 'unknown'
    assert page['event_cursor'] >= 0 and 'event_low_watermark' in page


def test_context_labels_use_only_canonical_project_host_scalars(scenario):
    s, service = scenario, service_for(scenario)
    before, _ = all_groups(service, s)
    before_ids = {g['id'] for g in before}
    with s.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE workspaces SET display_name='Fixture project' WHERE workspace_id='ws'")
        uow.connection.execute("UPDATE execution_executors SET label='Fixture host' WHERE executor_id=?", (s.connections[0].executor_id,))
        uow.connection.execute("UPDATE agents SET metadata=? WHERE agent_id='subject'", ('{"display_name":"Fixture collaborator","private_extra":"must-not-be-exposed"}',))
    after, _ = all_groups(service, s)
    assert {g['id'] for g in after} == before_ids
    native = [g for g in after if g['connection']]
    assert native and all(g['label'] == 'Fixture collaborator · Fixture project · Fixture host' for g in native)
    assert all(g['agent_label'] == 'Fixture collaborator' for g in native)
    assert all(g['host_label'] == 'Fixture host' for g in native)
    assert 'must-not-be-exposed' not in json.dumps(after)
    for invalid in ('{invalid-json', '{"display_name":12}', json.dumps({'display_name': 'x'*121})):
        with s.factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET metadata=? WHERE agent_id='subject'", (invalid,))
        invalid_groups, _ = all_groups(service, s)
        assert all(g['agent_label'] is None for g in invalid_groups if g['connection'])


def test_external_generation_restart_gets_new_identity_without_inheriting_preferences(scenario):
    s, service = scenario, service_for(scenario)
    observations = s.app.state.home.observations
    with s.factory.unit_of_work(write=False) as uow:
        source = dict(uow.connection.execute('SELECT * FROM observation_sources WHERE source_id=?', (s.external['source_id'],)).fetchone())
        instance = dict(uow.connection.execute('SELECT * FROM observation_instances WHERE observed_instance_id=?', (s.external['observed_instance_id'],)).fetchone())
    token = observations.issue_token(context=s.operator, source_id=source['source_id'], body=dict(
        expected_revision=source['revision'], instance_grants=[dict(observed_instance_id=instance['observed_instance_id'], generation=instance['generation'])]))['token']
    observations.publish(token=token, payload=dict(schema_version=1, source_id=source['source_id'],
        observed_instance_id=instance['observed_instance_id'], generation=instance['generation'], sequence=2,
        state='blocked', evidence='reported', observed_at=s.clock.now_iso(), reason_code='external_input_required'))
    groups, _ = all_groups(service, s)
    old = next(e for g in groups for e in g['children'] if e['kind'] == 'external')
    assert old['attention_refs']
    assert len([e for g in groups for e in g['children'] if e['source_ref']['id'] == instance['observed_instance_id']]) == 1
    occurrence = next(o for o in s.app.state.attention.read(context=s.operator, filters={'state': 'all'})['items'] if o['attention_id'] == old['attention_refs'][0])
    s.app.state.attention.mark_seen(context=s.operator, attention_id=occurrence['attention_id'],
        source_revision=occurrence['source_revision'], preference_revision=occurrence['seen_state']['revision'])
    rotated = observations.rotate_instance(context=s.operator, source_id=source['source_id'],
        observed_instance_id=instance['observed_instance_id'], body=dict(expected_revision=source['revision'], expected_generation=instance['generation']))['instance']
    groups, _ = all_groups(service, s)
    new = next(e for g in groups for e in g['children'] if e['kind'] == 'external')
    assert new['id'] != old['id'] and new['target'] != old['target']
    assert new['target']['generation'] == rotated['generation']
    assert new['attention_refs'] == [] and new['result_refs'] == []
    assert new['external'][0]['canonical_session_ref'] is None
    assert new['external'][0]['last_report'] is None
    with pytest.raises(OktoNexusError) as error:
        s.app.state.home.resolve(context=s.operator, target=old['target'])
    assert error.value.code == 'NOT_FOUND'
    assert s.app.state.home.resolve(context=s.operator, target=new['target'])
    with s.factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT seen_at FROM attention_preferences WHERE attention_id=?', (old['attention_refs'][0],)).fetchone()
        assert row and row[0] is not None  # old preference retained, never transferred


def test_boolean_version_and_deep_cursor_are_validation_errors_not_server_errors(scenario):
    import base64
    s = scenario
    install_home_entries(s.app, s.app.state.home)
    headers = {'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']}
    client = TestClient(s.app)
    try:
        normal = client.get('/api/v1/home/entries?quick=all&limit=1', headers=headers).json()['data']
        cursor = normal['next_cursor']
        parsed = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
        parsed['v'] = True
        boolean = base64.urlsafe_b64encode(json.dumps(parsed).encode()).decode().rstrip('=')
        deep_raw = '{"v":1,"binding":{"scope":' + '['*1100 + '0' + ']'*1100 + '},"revision":"x","key":[0,"","x"]}'
        deep = base64.urlsafe_b64encode(deep_raw.encode()).decode().rstrip('=')
        assert len(deep) <= 4096
        for value in (boolean, deep):
            response = client.get('/api/v1/home/entries', params={'quick': 'all', 'cursor': value}, headers=headers)
            assert response.status_code == 422  # existing canonical VALIDATION_ERROR mapper
            assert response.json()['error']['code'] == 'VALIDATION_ERROR'
            assert response.headers['cache-control'] == 'no-store'
    finally:
        client.close()


def test_single_read_uow_no_journal_or_transcript_and_one_size_sample(large_scenario, monkeypatch):
    s, service = large_scenario, service_for(large_scenario)
    from contextlib import contextmanager
    original, calls, statements, source_rows = s.factory.unit_of_work, [], [], []
    original_collect = service.queries._collect
    def collect(cursor, decode, check_budget=None):
        value = original_collect(cursor, decode, check_budget)
        source_rows.append(len(value))
        return value
    monkeypatch.setattr(service.queries, '_collect', collect)
    from threading import get_ident
    reader = get_ident()
    @contextmanager
    def traced(*args, **kwargs):
        with original(*args, **kwargs) as uow:
            if get_ident() != reader:
                yield uow
                return
            calls.append(kwargs)
            before = uow.connection.total_changes
            uow.connection.set_trace_callback(statements.append)
            try:
                yield uow
                assert uow.connection.total_changes == before
            finally:
                uow.connection.set_trace_callback(None)
    monkeypatch.setattr(s.factory, 'unit_of_work', traced)
    value = read(service, s)
    assert calls == [{'write': False}]
    assert value['total'] >= 125 and len(value['items']) == 10
    assert not any('event_journal' in sql.lower() or 'transcript' in sql.lower() for sql in statements)
    # Existing RESULTS reads only a bounded preview, not the full output body.
    assert all('substr(x.output_text,1,401)' in sql.lower() for sql in statements if 'output_text' in sql.lower())
    sample = dict(groups=value['total'], returned_groups=len(value['items']), source_rows=source_rows,
                  sql_statements=len(statements), payload_bytes=len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()),
                  cost='O(N+relationships); not O(page)', read_uows=len(calls), writes=0)
    print('UI020_SAMPLE=' + json.dumps(sample, sort_keys=True))
