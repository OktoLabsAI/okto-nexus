"""Bounded related previews and exact read-only continuation per entry."""
# ruff: noqa: F811 -- imported pytest fixture is injected by its declared name
import copy
import json

from fastapi.testclient import TestClient
from nexus_connector_core import R4_PREVIEW_REVISION

from okto_nexus.application.execution_events import commit_execution_events
from okto_nexus.application.execution_leases import ExecutionChannel
from .test_entry_pages import scenario as scenario, all_groups, service_for, copy_session
from .test_fixtures import fixtures


def peer_questions(s):
    with s.factory.unit_of_work(write=False) as uow:
        c = uow.connection
        original = json.loads(c.execute('SELECT payload_json FROM execution_event_ingress LIMIT 1').fetchone()[0])
        owner = c.execute('SELECT * FROM execution_executors WHERE executor_id=?', (s.connections[0].executor_id,)).fetchone()
        channel = ExecutionChannel(owner['server_id'], owner['executor_id'], owner['owner_instance_id'], owner['generation'])
    for sequence in range(2, 6):
        event = copy.deepcopy(original)
        event['sequence'] = sequence
        for key in ('native_approval', 'native_approval_display'):
            event['payload'][key].update(request_id=70+sequence, request_hash=f'{sequence:064x}')
        frame = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='event.batch',
            server_id=channel.server_id, executor_id=channel.executor_id, binding_id='binding', agent_id='subject',
            session_id=s.sessions[0], stream_epoch='native-epoch', connection_id=channel.connection_id,
            connection_generation=channel.connection_generation, events=[event])
        commit_execution_events(s.factory, channel=channel, frame=frame, approvals=s.deps.approvals)


def conversation_results(s):
    with s.factory.unit_of_work() as uow:
        c, now = uow.connection, s.clock.now_iso()
        c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES('related-message','ws','operator','Synthetic related deliveries',?)", (now,))
        c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES('related-delivery','related-message','subject','unread',?)", (now,))
        c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,created_at,updated_at) VALUES('related-conversation','related-delivery','related-message','ws','operator','fixture','subject','ui-ep-2',1,'{}','fixture','fixture','related-conversation',?,?)", (now, now))
        operation = c.execute("SELECT * FROM execution_operations WHERE operation_id='ui-success'").fetchone()
        for i in range(5):
            op = f'related-result-{i}'
            fixtures._copy(c, 'execution_operations', operation, operation_id=op)
            c.execute("INSERT INTO execution_domain_deliveries VALUES(?,?,?,'related-conversation')", (operation['server_id'], operation['executor_id'], op))
            c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES(?,?,?,1,?,'SUCCEEDED',1,0,?)", (operation['server_id'], operation['executor_id'], op, operation['intent_hash'], now))
            c.execute("INSERT INTO execution_event_ingress VALUES(?,?,'ui-session-2','ui-historical-epoch',?,'own-synthetic-related','turn.completed','{}',?)", (operation['server_id'], operation['executor_id'], 20+i, now))
            c.execute("INSERT INTO execution_results VALUES(?,?,?,'ui-session-2','ui-historical-epoch',?,'Bounded synthetic related result',0,1,'success',?)", (operation['server_id'], operation['executor_id'], op, 20+i, now))


def related(s, partition, entry, group_id, cursor=None, limit=2):
    headers = {'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']}
    client = TestClient(s.app)
    try:
        return client.get(f'/api/v1/home/entries/{group_id}/children/{entry["id"]}/{partition}',
            params={k: v for k, v in dict(quick='all', cursor=cursor, limit=limit).items() if v is not None}, headers=headers)
    finally:
        client.close()


def assert_continuation(s, partition, entry, group, expected, id_key):
    preview = entry[partition + '_preview']
    assert len(preview) == 3 and entry[partition + '_total'] == 5
    assert entry['has_more_' + partition]
    values, cursor = list(preview), entry[partition + '_cursor']
    while cursor:
        response = related(s, partition, entry, group['id'], cursor=cursor)
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        page = response.json()['data']
        assert page['partition'] == partition and page['entry_id'] == entry['id']
        assert page['total'] == 5 and page['total_is_exact']
        values.extend(page['items'])
        cursor = page['next_cursor']
    assert {v[id_key] for v in values} == {v[id_key] for v in expected}
    assert len(values) == len({v[id_key] for v in values}) == 5
    assert {v[id_key]: v for v in values} == {v[id_key]: v for v in expected}
    bad = related(s, partition, entry, 'foreign-own-parent', cursor=entry[partition + '_cursor'])
    assert bad.status_code == 409
    assert related(s, partition, entry, group['id'], limit=101).status_code == 422
    other = 'results' if partition == 'attention' else 'attention'
    assert related(s, other, entry, group['id'], cursor=entry[partition + '_cursor']).status_code == 409
    foreign = dict(entry, id='foreign-own-entry')
    assert related(s, partition, foreign, group['id'], cursor=entry[partition + '_cursor']).status_code == 409
    return values


def test_attention_preview_and_pages_preserve_five_canonical_questions(scenario):
    s = scenario
    peer_questions(s)
    groups, _ = all_groups(service_for(s), s)
    group, entry = next((g, e) for g in groups for e in g['children'] if e['display_state'] == 'awaiting_operator')
    expected = [o for o in s.app.state.attention.read(context=s.operator, filters={'state': 'all'}, limit=100)['items']
                if o['operation_id'] == entry['target']['operation_id'] and o['kind'] == 'native_question_pending']
    assert len(entry['attention_refs']) == 3
    assert {a['attention_id'] for a in entry['actions'] if a['kind'] == 'attention'} <= set(entry['attention_refs'])
    with s.factory.unit_of_work(write=False) as uow:
        before = uow.connection.execute('SELECT COUNT(*) FROM execution_decisions').fetchone()[0]
    assert_continuation(s, 'attention', entry, group, expected, 'attention_id')
    assert all(o['source_revision'] and o['allowed_actions'] for o in entry['attention_preview'])
    assert 'private-marker' not in json.dumps(entry)
    with s.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_decisions').fetchone()[0] == before


def test_results_preview_and_pages_preserve_five_canonical_deliveries(scenario):
    s = scenario
    conversation_results(s)
    initial = next(r for r in s.read(section='results', limit=100)['items'] if r['source_ref']['id'].startswith('related-result-'))
    occurrence = initial['attention']
    s.app.state.attention.mark_seen(context=s.operator, attention_id=occurrence['attention_id'],
        source_revision=occurrence['source_revision'], preference_revision=occurrence['seen_state']['revision'])
    groups, _ = all_groups(service_for(s), s)
    group, entry = next((g, e) for g in groups for e in g['children'] if e['source_ref']['id'] == 'related-conversation')
    expected = [r for r in s.read(section='results', limit=100)['items'] if r['source_ref']['id'].startswith('related-result-')]
    assert len(entry['result_refs']) == 3
    with s.factory.unit_of_work(write=False) as uow:
        before = uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0]
    values = assert_continuation(s, 'results', entry, group, expected, 'id')
    assert all(r['view_state'] == 'unseen' for r in entry['results_preview'])
    assert values[-1]['view_state'] == 'seen'
    assert all('artifacts' in r and 'view_state' in r for r in entry['results_preview'])
    with s.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == before


def test_default_keeps_idle_configured_connection_while_active_does_not(scenario):
    s = scenario
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        endpoint = c.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='ui-ep-2'").fetchone()
        fixtures._copy(c, 'agent_endpoints', endpoint, endpoint_id='related-idle-endpoint')
        binding = c.execute("SELECT * FROM execution_bindings WHERE binding_id='ui-binding-2'").fetchone()
        fixtures._copy(c, 'execution_bindings', binding, binding_id='related-idle-binding', endpoint_id='related-idle-endpoint')
        closed = c.execute("SELECT * FROM execution_sessions WHERE session_id='ui-session-2'").fetchone()
        copy_session(c, closed, 'related-closed-session')
    service = service_for(s)
    default = service.read(context=s.operator)
    active = service.read(context=s.operator, filters={'quick': 'active'})
    assert any(g['connection'] and g['connection']['binding_id'] == 'related-idle-binding' for g in default['items'])
    assert not any(g['connection'] and g['connection']['binding_id'] == 'related-idle-binding' for g in active['items'])
    assert any((e['target'] or {}).get('session_id') == 'related-closed-session' for g in default['items'] for e in g['children'])
    assert not any((e['target'] or {}).get('session_id') == 'related-closed-session' for g in active['items'] for e in g['children'])
