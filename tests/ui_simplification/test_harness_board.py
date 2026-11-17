"""R3 registered cards: complete relations, shared proofs, no synthetic harness."""
# ruff: noqa: F811 -- imported pytest fixtures are injected by declared name
from contextlib import contextmanager
import json
from threading import get_ident
import time

from fastapi.testclient import TestClient
import pytest

from okto_nexus.domain import home_harness_board as harness
from okto_nexus.domain.attention import occurrence
from okto_nexus.domain.home_entries import ConnectionContext, EntryRecord, EntryRelations
from okto_nexus.domain.home_entry_pages import filters
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

from .test_entry_pages import scenario, large_scenario  # noqa: F401
from .test_entry_relations import link_handoff, copy_session
from .test_fixtures import fixtures
from .test_passive_effects import TABLES


def read(s, **kwargs):
    return s.app.state.home_entries.read(context=s.operator, partition='harness_board', **kwargs)


def cards(value):
    return [card for lane in value['columns'].values() for card in lane['items'] if card['kind'] == 'harness']


def test_registered_cards_are_complete_and_unlinked_origins_are_not_harnesses(scenario):
    s = scenario
    value = read(s, limit=100)
    items = cards(value)
    with s.factory.unit_of_work(write=False) as uow:
        expected = uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0]
    assert expected == len(items) == value['inventory']['registered_harnesses']['value']
    assert len({c['id'] for c in items}) == expected
    assert len({c['connection']['binding_id'] for c in items}) == expected
    assert all(c['context_state'] == 'registered' and c['target']['kind'] == 'connection' for c in items)
    assert all(c['connection']['agent_id'] == 'subject' for c in items)
    assert any(e['source_ref']['id'] == 'ui-unassigned' for e in value['unlinked']['items']) or value['unlinked']['has_more']
    fallback = s.app.state.home_entries.read(context=s.operator, partition='harness_unlinked', limit=100)
    assert any(e['kind'] == 'external' for e in fallback['items'])
    assert any(e['source_ref']['id'] == 'ui-unassigned' and e['target'] for e in fallback['items'])
    assert all(e['shared_reference'] is False for e in fallback['items'])


def test_shared_logical_work_keeps_two_proven_bindings_and_original_detail_identity(scenario):
    s = scenario
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        link_handoff(c, s.clock.now_iso())
        operations = c.execute("SELECT * FROM execution_operations WHERE action='turn.submit'").fetchall()
        chosen = {}
        for row in operations:
            chosen.setdefault(row['binding_id'], row)
        assert len(chosen) == 2
        for row in chosen.values():
            c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,?,'entry-domain')",
                (row['server_id'], row['executor_id'], row['operation_id']))
    value = read(s, limit=100, preview=100)
    shared = [(card, child) for card in cards(value) for child in card['children'] if child['source_ref']['id'] == 'ui-handoff-0']
    assert len(shared) == 2
    assert len({child['id'] for _, child in shared}) == 1
    assert len({card['connection']['binding_id'] for card, _ in shared}) == 2
    assert all(child['shared_reference'] for _, child in shared)
    assert shared[0][1]['group_id'] == shared[1][1]['group_id']
    assert shared[0][1]['group_id'] not in {card['id'] for card, _ in shared}
    unique_work = {e['id'] for card in cards(value) for e in card['children'] if e['kind'] == 'work'}
    unique_work.update(e['id'] for e in value['unlinked']['items'] if e['kind'] == 'work')
    assert value['summary']['activities']['value'] == len(unique_work)
    # Existing agent filter follows work origin/receiver semantics, not card labels.
    selected = read(s, filters={'agent_id': 'operator'}, limit=100, preview=100)
    assert any(c['connection']['agent_id'] == 'subject' and c['children'] for c in cards(selected))
    assert not cards(read(s, filters={'agent_id': 'no-such-agent'}, limit=100))


def test_server_events_cover_all_children_and_deduplicate_delivery_watch():
    now = '2026-11-16T12:00:00.000000Z'
    c = ConnectionContext('server', 'executor', 'ws', 'binding', 'wxb', 'agent', harness_id='codex_app_server')
    children = [EntryRecord(f'work-{i}', 'work', {}, 'ws', 'agent', 'Work', 'running', 'confirmed', None,
        registered_connections=(c,)) for i in range(9)]
    question = occurrence(kind='approval_pending', source_type='approval', source_id='question',
        episode=1, source_revision=1, first_detected_at=now, last_changed_at=now,
        workspace_id='ws', agent_id='agent', category='action_required', allowed_actions=['decide_approval'])
    children[-1].attention.append(question)
    result_watch = occurrence(kind='result_unseen', source_type='execution_result', source_id='delivery',
        episode=1, source_revision=1, first_detected_at=now, last_changed_at=now, workspace_id='ws', result_id='result')
    children[0].attention.append(result_watch)
    children[0].results.append(dict(id='result', created_at=now, view_state='unseen', detail_target=None, attention=result_watch))
    relations = EntryRelations(children, [], dict.fromkeys(('work', 'results', 'attention', 'connections', 'sessions', 'correlations', 'external'), 'ready'), 1, (c,))
    value = harness.page(relations, scope=filters({'quick': 'all'}), server_id='server', principal='human', now=now, preview=3)
    card = cards(value)[0]
    assert card['children_total'] == 9 and card['events_total'] > 3
    assert card['events_preview'][0]['attention']['attention_id'] == question['attention_id']
    assert card['events_preview'][0]['entry']['id'] == children[-1].id
    assert card['events_summary']['attention'] == 1 and card['events_summary']['results'] == 1
    assert len(cards(value)) == 1
    assert any(item['kind'] == 'request' for item in value['columns']['needs_you']['items'])


def test_http_card_children_unlinked_cursor_scope_and_revision(large_scenario):
    s = large_scenario
    headers = {'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']}
    client = TestClient(s.app, headers=headers)
    try:
        first = client.get('/api/v1/home/harness-board?limit=100&preview=1')
        assert first.status_code == 200 and first.headers['cache-control'] == 'no-store'
        value = first.json()['data']
        card = next(c for c in cards(value) if c['has_more_children'])
        ids, cursor = [e['id'] for e in card['children']], card['children_cursor']
        saved = cursor
        while cursor:
            response = client.get('/api/v1/home/harness-board/cards/' + card['id'] + '/children', params={'cursor': cursor, 'limit': 2})
            assert response.status_code == 200, response.text
            page = response.json()['data']
            assert page['revision'] == value['revision'] and page['entry_revision'] == value['entry_revision']
            ids.extend(e['id'] for e in page['items'])
            cursor = page['next_cursor']
        assert len(ids) == len(set(ids)) == card['children_total']
        other = next(c for c in cards(value) if c['id'] != card['id'])
        assert client.get('/api/v1/home/harness-board/cards/' + other['id'] + '/children', params={'cursor': saved}).status_code == 409
        fallback_ids, cursor = [], None
        while True:
            response = client.get('/api/v1/home/harness-board/unlinked', params={'limit': 25, **({'cursor': cursor} if cursor else {})})
            assert response.status_code == 200
            page = response.json()['data']
            fallback_ids.extend(e['id'] for e in page['items'])
            cursor = page['next_cursor']
            if not cursor:
                break
        assert len(fallback_ids) == len(set(fallback_ids)) >= 125
        for suffix in ('?quick=all', '?limit=101', '?limit=1&limit=2'):
            assert client.get('/api/v1/home/harness-board' + suffix).status_code == 422
        for scope in ({'workspace_id': 'ws'}, {'host': 'other-host'}, {'harness': 'pi_rpc'}, {'agent_id': 'B'}):
            assert client.get('/api/v1/home/harness-board/cards/' + card['id'] + '/children', params={'cursor': saved, **scope}).status_code in (404, 409)
        with s.factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE handoffs SET updated_at='2026-11-16T12:00:01.000000Z' WHERE handoff_id='ui-unassigned'")
        assert client.get('/api/v1/home/harness-board/cards/' + card['id'] + '/children', params={'cursor': saved}).status_code == 409
    finally:
        client.close()


def test_one_uow_no_new_source_query_or_productive_changes(scenario, monkeypatch):
    s = scenario
    original, traces = s.factory.unit_of_work, []
    reader = get_ident()

    def snapshot():
        with original(write=False) as uow:
            return {name: sorted(json.dumps(dict(row), sort_keys=True) for row in uow.connection.execute('SELECT * FROM ' + name)) for name in TABLES}

    before = snapshot()

    @contextmanager
    def traced(*args, **kwargs):
        with original(*args, **kwargs) as uow:
            if get_ident() != reader:
                yield uow
                return
            statements = []
            changes = uow.connection.total_changes
            uow.connection.set_trace_callback(statements.append)
            try:
                yield uow
                assert uow.connection.total_changes == changes
            finally:
                uow.connection.set_trace_callback(None)
                traces.append((kwargs, statements))

    monkeypatch.setattr(s.factory, 'unit_of_work', traced)
    s.app.state.home_entries.read(context=s.operator, partition='board')
    value = read(s)
    assert len(traces) == 2 and all(kw == {'write': False} for kw, _ in traces)
    assert len(traces[0][1]) + 1 == len(traces[1][1])
    assert not any('event_journal' in sql.lower() or 'transcript' in sql.lower() for _, trace in traces for sql in trace)
    assert snapshot() == before and not s.app.state.connection_tests.tests
    print('HARNESS_BOARD_SAMPLE=' + json.dumps(dict(sql_statements=len(traces[1][1]), read_uows=1, writes=0,
        harnesses=value['inventory']['registered_harnesses']['value'], payload_bytes=len(json.dumps(value).encode()))))


def test_unknown_registry_budget_principal_and_auth_are_fail_closed(scenario, monkeypatch):
    s = scenario
    service = s.app.state.home_entries
    context = RuntimeRequestContext(None, 'operator_session', trusted_local_operator=True)
    first = service.read(context=context, principal='human-a', partition='harness_board', preview=1)
    card = next(c for c in cards(first) if c['has_more_children'])
    with pytest.raises(OktoNexusError) as error:
        service.read(context=context, principal='human-b', partition='harness_children', group_id=card['id'], cursor=card['children_cursor'])
    assert error.value.code == 'CONFLICT'
    original = service.queries.read

    def unknown(*args, **kwargs):
        relation = original(*args, **kwargs)
        relation.connections = None
        relation.source_status['connections'] = 'unavailable'
        return relation

    monkeypatch.setattr(service.queries, 'read', unknown)
    partial = read(s)
    assert not cards(partial) and partial['status'] == 'partial'
    assert partial['unlinked']['total'] is None and partial['coverage']['harness_linkage'] == 'unknown'
    assert partial['inventory']['registered_harnesses']['value'] is None
    monkeypatch.setattr(service, 'QUERY_SECONDS', -1)
    exhausted = read(s)
    assert exhausted['revision'] is None and exhausted['entry_revision'] is None
    assert exhausted['unlinked']['items'] == [] and all(lane['total'] is None for lane in exhausted['columns'].values())
    monkeypatch.setattr(service.queries, 'read', lambda *a, **k: pytest.fail('must authorize first'))
    client = TestClient(s.app)
    try:
        assert client.get('/api/v1/home/harness-board', headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['other']}).status_code == 403
    finally:
        client.close()


def test_real_native_input_metadata_and_snooze_preserve_waiting_harness(scenario):
    s = scenario
    first = read(s, limit=100)
    own = next(c for c in cards(first) if c['connection']['binding_id'] == 'binding')
    assert first['coverage']['blocking'] == 'ready'
    assert own['blocks_harness'] is True and own['activity_state'] == 'waiting_for_user'
    request = own['blocking_requests'][0]['request']
    s.app.state.attention.snooze(context=s.operator, attention_id=request['attention_id'],
        source_revision=request['source_revision'], preference_revision=request['seen_state']['revision'],
        until='2026-11-16T12:30:00.000000Z')
    snoozed = read(s, limit=100)
    own = next(c for c in cards(snoozed) if c['connection']['binding_id'] == 'binding')
    assert own['blocks_harness'] is True and own['reminder_snoozed'] is True
    assert own['blocking_requests'][0]['notification_visible'] is False


def add_parallel_running_read_fact(s):
    """Schema-valid synthetic read fact, not an extra admission/native process."""
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        session = c.execute('SELECT * FROM execution_sessions WHERE session_id=?', (s.sessions[0],)).fetchone()
        copy_session(c, session, 'r3-parallel-session')
        operation = c.execute("SELECT * FROM execution_operations WHERE session_id=? AND action='turn.submit'", (s.sessions[0],)).fetchone()
        scope = dict(json.loads(operation['expected_revisions_json']), session_id='r3-parallel-session')
        fixtures._copy(c, 'execution_operations', operation, operation_id='r3-parallel-operation',
            session_id='r3-parallel-session', expected_revisions_json=json.dumps(scope), admission_state='DISPATCHED')
        dispatch = c.execute('SELECT * FROM execution_dispatch_outbox WHERE operation_id=?', (operation['operation_id'],)).fetchone()
        fixtures._copy(c, 'execution_dispatch_outbox', dispatch, operation_id='r3-parallel-operation',
            dispatch_state='DISPATCHED', last_receipt_revision=1)
        c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES(?,?,'r3-parallel-operation',1,?,'RUNNING',1,0,?)",
            (operation['server_id'], operation['executor_id'], operation['intent_hash'], s.clock.now_iso()))


def test_real_parallel_work_and_bearer_detail_revisions_after_extra_query(large_scenario):
    s = large_scenario
    add_parallel_running_read_fact(s)
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
    try:
        response = client.get('/api/v1/home/harness-board?limit=100')
        assert response.status_code == 200
        value = response.json()['data']
        own = next(c for c in cards(value) if c['connection']['binding_id'] == 'binding')
        from okto_nexus.adapters.outbound.sqlite.home_entries import HARNESS_BLOCKING
        with s.factory.unit_of_work(write=False) as uow:
            diagnostic = [json.loads(row[0]) for row in uow.connection.execute(HARNESS_BLOCKING,
                dict(server_id=s.connections[0].server_id, workspace_id='ws'))]
        diagnostic = [row for row in diagnostic if row.get('operation_id') == 'r3-parallel-operation']
        assert own['blocks_harness'] is False and own['activity_state'] == 'working', json.dumps(dict(sources=value['source_status'], parallel=diagnostic))
        assert own in value['columns']['active']['items']
        question = next(item for item in value['columns']['needs_you']['items'] if item['kind'] == 'request'
            and item['request']['kind'] == 'native_question_pending')
        assert [ref['connection']['binding_id'] for ref in question['harness_refs']] == ['binding']
        assert any(item['kind'] == 'delivery' for item in value['columns']['results']['items'])
        original = question['entry']
        detail = client.get('/api/v1/home/entries/' + original['group_id'] + '/children', params={'quick': 'all', 'limit': 100})
        assert detail.status_code == 200 and detail.json()['data']['revision'] == original['entry_revision']
        for card in cards(value):
            children = client.get('/api/v1/home/harness-board/cards/' + card['id'] + '/children', params={'limit': 100})
            assert children.status_code == 200
            for entry in children.json()['data']['items']:
                if entry['has_more_sessions']:
                    related = client.get('/api/v1/home/entries/' + entry['group_id'] + '/children/' + entry['id'] + '/sessions',
                        params={'quick': 'all', 'cursor': entry['sessions_cursor']})
                    assert related.status_code == 200, related.text
                    assert related.json()['data']['revision'] == entry['entry_revision']
    finally:
        client.close()


@pytest.mark.parametrize('registered', [1, 10, 100])
def test_metadata_query_count_is_constant_at_registered_volumes(scenario, monkeypatch, record_property, registered):
    s = scenario
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        # Move only the synthetic second registration to another project. Its
        # historical session/work remains historical and is never reassigned.
        workspace = c.execute("SELECT * FROM workspaces WHERE workspace_id='ws'").fetchone()
        fixtures._copy(c, 'workspaces', workspace, workspace_id='r3-other-workspace')
        wxb = c.execute("SELECT * FROM execution_workspace_bindings WHERE workspace_binding_id='wxb'").fetchone()
        fixtures._copy(c, 'execution_workspace_bindings', wxb, workspace_binding_id='r3-other-wxb', workspace_id='r3-other-workspace')
        c.execute("UPDATE agent_endpoints SET workspace_id='r3-other-workspace' WHERE endpoint_id='ui-ep-2'")
        c.execute("UPDATE execution_bindings SET workspace_binding_id='r3-other-wxb' WHERE binding_id='ui-binding-2'")
        endpoint = c.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='ep'").fetchone()
        binding = c.execute("SELECT * FROM execution_bindings WHERE binding_id='binding'").fetchone()
        for index in range(registered - 1):
            fixtures._copy(c, 'agent_endpoints', endpoint, endpoint_id=f'r3-volume-ep-{index}')
            fixtures._copy(c, 'execution_bindings', binding, binding_id=f'r3-volume-binding-{index}', endpoint_id=f'r3-volume-ep-{index}')
    original, reader, traces = s.factory.unit_of_work, get_ident(), []

    @contextmanager
    def traced(*args, **kwargs):
        with original(*args, **kwargs) as uow:
            if get_ident() != reader:
                yield uow
                return
            statements = []
            changes = uow.connection.total_changes
            uow.connection.set_trace_callback(statements.append)
            try:
                yield uow
                assert uow.connection.total_changes == changes
            finally:
                uow.connection.set_trace_callback(None)
                traces.append((kwargs, statements))

    monkeypatch.setattr(s.factory, 'unit_of_work', traced)
    service = s.app.state.home_entries
    service.read(context=s.operator, partition='board', filters={'workspace_id': 'ws'})
    start = time.perf_counter()
    value = service.read(context=s.operator, partition='harness_board', filters={'workspace_id': 'ws'})
    elapsed = (time.perf_counter() - start) * 1000
    assert value['inventory']['registered_harnesses']['value'] == registered
    assert len(traces) == 2 and all(kwargs == {'write': False} for kwargs, _ in traces)
    assert len(traces[1][1]) == len(traces[0][1]) + 1
    assert sum('WITH latest AS MATERIALIZED' in sql for sql in traces[1][1]) == 1
    assert not any('event_journal' in sql.lower() or 'transcript' in sql.lower() for sql in traces[1][1])
    record_property('harness_board_sample', json.dumps(dict(registered=registered, read_uows=1, writes=0,
        sql_statements=len(traces[1][1]), preceding_board_sql=len(traces[0][1]), elapsed_ms=round(elapsed, 3),
        payload_bytes=len(json.dumps(value).encode()), sampling='one finite source-first read, not a p95/SLO')))
