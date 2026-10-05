"""Public event replay reads committed R4 facts with session authority."""
from pathlib import Path
import time

import pytest
from nexus_connector_core import RuntimeEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_event_ingress import ingress, commit
from test_reconciliation import recovery
from test_binding_operator import onboarding


def start(connected_local):
    setup, binding, native = connected_local
    opened = admit(setup, binding, 'event-view-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    return setup, binding, native, opened['scope']['session_id']


def publish(setup, native, session, count=3):
    deps, _, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?', (session,)).fetchone())
    for index in range(count):
        client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
            session, stream['stream_epoch'], 0, 'text_delta', 'fixture.output', dict(output_text=str(index))))
    deadline = time.monotonic() + 10
    while True:
        response = client.get(f'/v1/runtime/sessions/{session}/events', headers=headers['subject'])
        assert response.status_code == 200, response.text
        if response.json()['committed_contiguous'] == count:
            return response.json()
        assert time.monotonic() < deadline
        time.sleep(.02)


def test_mcp_rest_and_r4_event_replay_share_committed_history(connected_local, monkeypatch):
    setup, binding, native, session = start(connected_local)
    deps, _, client, headers, *_ = setup
    empty = client.get(f'/v1/runtime/sessions/{session}/events', headers=headers['subject'])
    assert empty.status_code == 200 and empty.json()['events'] == []
    page = publish(setup, native, session)
    assert [e['payload']['output_text'] for e in page['events']] == ['0', '1', '2']
    assert all(e['server_id'] == page['scope']['server_id'] for e in page['events'])
    def forbidden(*args, **kwargs):
        raise AssertionError('Canonical event replay reached the legacy supervisor')
    from okto_nexus.adapters.inbound.mcp.tools import harness
    monkeypatch.setattr(harness, 'build_service', forbidden)
    path = f'/api/v1/harness/sessions/{session}/events'
    first = client.get(path + '?limit=2', headers=headers['subject'])
    assert first.status_code == 200, first.text
    data = first.json()['data']
    assert data['count'] == 2 and data['has_more'] and data['next_after_sequence'] == 2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers['host'] = '127.0.0.1:8000'
    replay = tool(client, headers['subject']['Authorization'].removeprefix('Bearer '), 'harness_event_list',
        dict(session_id=session, after_sequence=2, executor_id=page['scope']['executor_id'], stream_epoch=page['stream_epoch']))
    assert replay['ok'], replay
    assert replay['data']['events'] == page['events'][2:] and not replay['data']['has_more']
    wait_receipt(setup, admit(setup, binding, 'event-view-close', 'runtime.close', session_id=session), stages=('SUCCEEDED',))
    closed = client.get(path, headers=headers['subject'])
    assert closed.status_code == 200 and closed.json()['data']['events'] == page['events']


def test_event_replay_rejects_foreign_scope_and_invalid_queries(connected_local):
    setup, binding, native, session = start(connected_local)
    deps, app, client, headers, *_ = setup
    page = publish(setup, native, session)
    path = f'/v1/runtime/sessions/{session}/events'
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agents(agent_id,created_at) VALUES('foreign',?)", (deps.clock.now_iso(),))
        key = app.state.auth.issue_key(uow, agent_id='foreign')
    assert client.get(path, headers={'Authorization': 'Bearer ' + key}).status_code == 404
    assert client.get(path).status_code == 401
    for query, status in [('executor_id=foreign', 404), ('stream_epoch=foreign', 404),
        ('after_sequence=-1', 422), ('limit=1001', 422), ('limit=0', 422), ('limit=1&limit=2', 422), ('unknown=x', 422)]:
        response = client.get(path + '?' + query, headers=headers['subject'])
        assert response.status_code == status, response.text
    assert client.get(path, headers=headers['operator']).json()['events'] == page['events']
    wait_receipt(setup, admit(setup, binding, 'scope-close', 'runtime.close', session_id=session), stages=('SUCCEEDED',))


def test_event_replay_bounds_bytes_and_detects_corrupted_storage(connected_local, monkeypatch):
    setup, binding, native, session = start(connected_local)
    deps, _, client, headers, *_ = setup
    page = publish(setup, native, session)
    from okto_nexus.application import execution_event_views
    with deps.connection_factory.unit_of_work(write=False) as uow:
        size = len(uow.connection.execute('SELECT payload_json FROM execution_event_ingress ORDER BY sequence LIMIT 1').fetchone()[0].encode())
    monkeypatch.setattr(execution_event_views, 'PAGE_BYTES', size + 1)
    path = f'/v1/runtime/sessions/{session}/events'
    limited = client.get(path, headers=headers['subject']).json()
    assert limited['count'] == 1 and limited['has_more'] and limited['next_after_sequence'] == 1
    wait_receipt(setup, admit(setup, binding, 'integrity-close', 'runtime.close', session_id=session), stages=('SUCCEEDED',))
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_event_ingress SET payload_json='{}' WHERE sequence=1")
    response = client.get(path, headers=headers['subject'])
    assert response.status_code == 500, response.text
    assert response.json()['error']['code'] == 'DB_ERROR'


def test_replay_does_not_expose_durable_events_above_contiguous_watermark(ingress, monkeypatch):
    from okto_nexus.application import execution_event_views
    factory, channel, frame = ingress
    # Authority is exercised by the public tests; this fixture isolates the
    # existing authenticated gap reducer and replay within the same real store.
    scope = dict(server_id=channel.server_id, executor_id=channel.executor_id, session_id='session')
    monkeypatch.setattr(execution_event_views, 'read_execution_session', lambda *a, **k: dict(scope=scope))
    def read():
        return execution_event_views.read_execution_events(factory, server_id=channel.server_id,
            session_id='session', context=None, access=None)
    third = {**frame, 'events': [{**frame['events'][0], 'sequence': 3}]}
    assert commit(ingress, third) is None
    assert read()['events'] == [] and read()['gap_pending']
    commit(ingress)
    page = read()
    assert [e['sequence'] for e in page['events']] == [1] and page['committed_contiguous'] == 1
    second = {**frame, 'events': [{**frame['events'][0], 'sequence': 2}]}
    commit(ingress, second)
    page = read()
    assert [e['sequence'] for e in page['events']] == [1, 2, 3] and not page['gap_pending']
    commit(ingress, frame)
    assert read() == page
