"""One authorized SQLite snapshot, exclusive columns and independent cursors."""
# ruff: noqa: F811 -- imported pytest fixture is injected by its declared name
from contextlib import contextmanager
import json
from threading import get_ident

from fastapi.testclient import TestClient
import pytest

from okto_nexus.domain import home_board
from okto_nexus.domain.home_entries import EntryRecord, EntryRelations, ConnectionContext
from okto_nexus.domain.home_entry_pages import filters
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

from .test_entry_pages import scenario, service_for  # noqa: F401
from .test_passive_effects import TABLES


def board(s, **kwargs):
    return s.app.state.home_entries.read(context=s.operator, partition='board', **kwargs)


def test_exclusive_columns_precedence_retention_and_reported_context():
    now = '2026-11-16T12:00:00.000000Z'
    item = EntryRecord('entry', 'work', {}, 'ws', 'agent', 'Work', 'running', 'confirmed', None)
    item.results = [dict(id='result', view_state='unseen', created_at='2026-11-13T12:00:00.000000Z')]
    assert home_board.column_for(item, now) == 'active'
    item.attention = [dict(active=True, freshness='current', resolution='open', category='action_required', allowed_actions=['respond'])]
    assert home_board.column_for(item, now) == 'needs_you'
    item.attention[0]['allowed_actions'] = []
    item.display_state = 'completed'
    assert home_board.column_for(item, now) == 'results'
    item.results[0]['view_state'] = 'seen'
    assert home_board.column_for(item, now) is None
    item.results[0]['view_state'] = 'not_tracked'
    assert home_board.column_for(item, now) == 'results'
    item.kind, item.evidence = 'external', 'reported'
    assert home_board.column_for(item, now) == 'active'
    for kind in ('connection', 'session'):
        item.kind, item.display_state = kind, 'offline'
        assert home_board.column_for(item, now) == 'active'


def test_board_summary_uses_only_retained_scoped_entries_and_unique_refs():
    now = '2026-11-16T12:00:00.000000Z'
    seen = EntryRecord('seen', 'work', {}, 'ws', 'agent', 'Old result', 'completed', 'confirmed', None,
        results=[dict(id='seen-result', view_state='seen', created_at='2026-11-13T12:00:00.000000Z')])
    states = dict.fromkeys(('work', 'results', 'attention', 'connections', 'sessions', 'correlations', 'external'), 'ready')
    relation = EntryRelations([seen], [], states, 0)

    def read(**scope):
        return home_board.page(relation, scope=filters(dict(quick='all', **scope)),
            server_id='server', principal='human', now=now)

    empty = read()
    assert all(column['total'] == 0 for column in empty['columns'].values())
    assert all(count['value'] == 0 and count['total_is_exact'] for count in empty['summary'].values())
    unseen = EntryRecord('unseen', 'work', {}, 'ws', 'agent', 'Unseen result', 'completed', 'confirmed', None,
        results=[dict(id='unseen-result', view_state='unseen', created_at='2026-11-13T12:00:00.000000Z')],
        connection=ConnectionContext('server', 'executor', 'ws', 'binding', 'wxb', 'agent', harness_id='codex_app_server'))
    relation.entries.append(unseen)
    assert read()['summary']['unseen_results']['value'] == 1
    for scope in ({'harness': 'claude_stream'}, {'state': 'running'}):
        scoped = read(**scope)
        assert all(column['total'] == 0 for column in scoped['columns'].values())
        assert scoped['summary']['unseen_results'] == dict(value=0, total_is_exact=True, unit='results')
    # The same canonical result reference cannot inflate aggregate counts.
    unseen.results.append(dict(unseen.results[0]))
    assert read()['summary']['results']['value'] == read()['summary']['unseen_results']['value'] == 1
    unseen.results[0]['view_state'] = 'not_tracked'
    unknown = read()
    assert unknown['summary']['unseen_results']['value'] is None
    assert not unknown['summary']['unseen_results']['total_is_exact']
    assert unknown['coverage']['result_tracking'] == 'partial'


def test_resolved_orphan_attention_is_not_active_but_informative_open_attention_remains():
    entry = EntryRecord('notice', 'attention', {}, 'ws', 'agent', 'Needs attention',
        'outcome_unknown', 'confirmed', None,
        attention=[dict(active=False, freshness='current', resolution='resolved', category='watch', allowed_actions=['inspect_approval'])])
    now = '2026-11-16T12:00:00.000000Z'
    assert home_board.column_for(entry, now) is None
    entry.attention[0].update(active=True, resolution='open')
    assert home_board.column_for(entry, now) == 'active'
    assert entry.display_state == 'outcome_unknown' and entry.results == []
    entry.attention[0].update(category='action_required', allowed_actions=['inspect_recovery'])
    assert home_board.column_for(entry, now) == 'needs_you'


def test_sqlite_board_is_one_read_no_writes_and_entries_are_disjoint(scenario, monkeypatch):
    s = scenario
    original, calls, statements = s.factory.unit_of_work, [], []
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
    value = board(s, limit=100)
    assert calls == [{'write': False}]
    assert value['status'] == 'ready'
    assert set(value['columns']) == set(home_board.COLUMNS)
    ids = [e['id'] for column in value['columns'].values() for e in column['items']]
    assert ids and len(ids) == len(set(ids))
    assert all(c['total'] == len(c['items']) for c in value['columns'].values())
    assert value['scope']['quick'] == 'all' and value['scope']['include_recent_results'] is False
    assert all(e['group_id'] and e['entry_revision'] == value['entry_revision']
               for c in value['columns'].values() for e in c['items'])
    assert any(e['kind'] == 'external' for e in value['columns']['active']['items'])
    assert not any('event_journal' in sql.lower() or 'transcript' in sql.lower() for sql in statements)


def test_http_column_pagination_details_and_all_scope_fences(scenario):
    s = scenario
    client = TestClient(s.app)
    headers = {'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']}
    try:
        first = client.get('/api/v1/home/board?limit=1', headers=headers)
        assert first.status_code == 200 and first.headers['cache-control'] == 'no-store'
        value = first.json()['data']
        name, lane = next((n, c) for n, c in value['columns'].items() if c['has_more'])
        ids, cursor = [e['id'] for e in lane['items']], lane['next_cursor']
        original_cursor = cursor
        while cursor:
            response = client.get('/api/v1/home/board/' + name, params={'cursor': cursor, 'limit': 1}, headers=headers)
            assert response.status_code == 200, response.text
            page = response.json()['data']
            assert page['revision'] == value['revision'] and page['entry_revision'] == value['entry_revision']
            ids.extend(e['id'] for e in page['items'])
            cursor = page['next_cursor']
        assert len(ids) == len(set(ids)) == lane['total']
        for path, params in [('/home/board/' + next(n for n in home_board.COLUMNS if n != name), {'cursor': original_cursor}),
                             ('/home/board/' + name, {'cursor': original_cursor, 'workspace_id': 'ws'})]:
            assert client.get('/api/v1' + path, params=params, headers=headers).status_code == 409
        entry = lane['items'][0]
        detail = client.get('/api/v1/home/entries/' + entry['group_id'] + '/children', params={'quick': 'all'}, headers=headers)
        assert detail.status_code == 200 and detail.json()['data']['revision'] == entry['entry_revision']
        for suffix in ('?quick=all', '?limit=101', '?limit=1&limit=2', '?unknown=1'):
            assert client.get('/api/v1/home/board' + suffix, headers=headers).status_code == 422
        assert client.get('/api/v1/home/board/invalid', headers=headers).status_code == 422
        assert client.get('/api/v1/home/board/active?cursor=invalid', headers=headers).status_code == 422
        with s.factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE handoffs SET updated_at='2026-11-16T12:00:01.000000Z' WHERE handoff_id='ui-unassigned'")
        assert client.get('/api/v1/home/board/' + name, params={'cursor': original_cursor}, headers=headers).status_code == 409
    finally:
        client.close()


def test_principal_scope_and_partial_budget_are_explicit(scenario, monkeypatch):
    s, service = scenario, service_for(scenario)
    context = RuntimeRequestContext(None, 'operator_session', trusted_local_operator=True)
    first = service.read(context=context, principal='human-a', partition='board', limit=1)
    name, lane = next((n, c) for n, c in first['columns'].items() if c['has_more'])
    with pytest.raises(OktoNexusError) as error:
        service.read(context=context, principal='human-b', partition='board', group_id=name, cursor=lane['next_cursor'])
    assert error.value.code == 'CONFLICT'
    monkeypatch.setattr(service.queries, 'external', lambda *a, **k: (_ for _ in ()).throw(__import__('sqlite3').OperationalError('own source failure')))
    partial = service.read(context=s.operator, partition='board')
    assert partial['status'] == 'partial' and partial['source_status']['external'] == 'unavailable'
    assert all(c['total'] is None and not c['total_is_exact'] for c in partial['columns'].values())
    monkeypatch.setattr(service, 'QUERY_SECONDS', -1)
    unavailable = service.read(context=s.operator, partition='board')
    assert unavailable['status'] == 'unavailable' and unavailable['revision'] is None
    assert unavailable['entry_revision'] is None and unavailable['inventory']['connections']['value'] is None
    assert all(c['items'] == [] and c['total'] is None for c in unavailable['columns'].values())


def test_unauthorized_board_never_reads_relations(scenario, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('unauthorized relation read')

    s = scenario
    monkeypatch.setattr(s.app.state.home_entries.queries, 'read', forbidden)
    client = TestClient(s.app)
    try:
        response = client.get('/api/v1/home/board', headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['other']})
        assert response.status_code == 403
        assert response.headers['cache-control'] == 'no-store'
    finally:
        client.close()


def test_repeated_http_board_and_columns_preserve_canonical_tables(scenario):
    s = scenario

    def snapshot():
        with s.factory.unit_of_work(write=False) as uow:
            return {table: sorted(json.dumps(dict(row), sort_keys=True) for row in
                                 uow.connection.execute('SELECT * FROM ' + table)) for table in TABLES}

    before = snapshot()
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
    try:
        for _ in range(2):
            assert client.get('/api/v1/home/board').status_code == 200
            for name in home_board.COLUMNS:
                assert client.get('/api/v1/home/board/' + name).status_code == 200
        assert snapshot() == before
        assert not s.app.state.connection_tests.tests
    finally:
        client.close()


def test_sqlite_retains_old_unseen_and_drops_old_seen_canonical_result(scenario):
    s = scenario
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("DELETE FROM execution_session_containment WHERE session_id='ui-session-2'")
        # Historical canonical read facts only: no dispatch/provider is invoked.
        c.execute("INSERT INTO execution_event_ingress VALUES(?,?,'ui-session-2','board-historical-epoch',2,'board-synthetic-event','turn.completed','{}',?)",
                  (s.connections[0].server_id, s.connections[0].executor_id, s.clock.now_iso()))
        c.execute("INSERT INTO execution_results VALUES(?,?,'ui-success','ui-session-2','board-historical-epoch',2,'Bounded synthetic result',0,1,'success',?)",
                  (s.connections[0].server_id, s.connections[0].executor_id, s.clock.now_iso()))
        c.execute("UPDATE execution_receipts SET received_at='2026-11-14T12:00:00.000000Z' WHERE operation_id='ui-success'")
        c.execute("UPDATE execution_results SET captured_at='2026-11-14T12:00:00.000000Z' WHERE operation_id='ui-success'")
    result = s.read(section='results')['items'][0]
    assert result['view_state'] == 'unseen'
    first = board(s, limit=100)
    located = [(name, e) for name, lane in first['columns'].items() for e in lane['items'] if result['id'] in e['result_refs']]
    assert len(located) == 1 and located[0][0] in ('results', 'needs_you')
    attention = result['attention']
    s.app.state.attention.mark_seen(context=s.operator, attention_id=attention['attention_id'],
        source_revision=attention['source_revision'], preference_revision=attention['seen_state']['revision'])
    seen = board(s, limit=100)
    assert all(result['id'] not in e['result_refs'] for lane in seen['columns'].values() for e in lane['items'])
    assert seen['revision'] != first['revision']
    scoped = board(s, filters={'workspace_id': 'ws'}, limit=100)
    assert all(e['workspace_id'] == 'ws' for lane in scoped['columns'].values() for e in lane['items'])
