"""Concurrent replay and compacted Core history retain public cursor authority."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from nexus_connector_core import RuntimeEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract
from test_canonical_event_views import start
from test_agent_recovery_isolation import create_agent, eventually
from test_canonical_grant_regressions import mcp_helpers
from test_pr34_remediation import tool


def reader(setup, session, surface, actor='subject', **params):
    client, headers = setup[2], setup[3]
    if surface == 'rest':
        return client.get(f'/api/v1/harness/sessions/{session}/events',
            headers=headers[actor], params=params).json()
    client.headers['host'] = '127.0.0.1:8000'
    return tool(client, headers[actor]['Authorization'].removeprefix('Bearer '),
        'harness_event_list', dict(session_id=session, **params))


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_concurrent_append_and_core_compaction_preserve_public_cursor(connected_local, surface):
    setup, _, native, session = start(connected_local)
    deps, app, client, *_ = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    def append(index):
        client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
            session, stream['stream_epoch'], 0, 'text_delta', 'fixture.output', dict(output_text=str(index))))
    for index in range(4):
        append(index)
    def committed():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT committed_contiguous FROM execution_event_watermarks').fetchone()
            return row[0] if row else 0
    eventually(lambda: committed() == 4)
    gate = threading.Event()
    def concurrent():
        assert gate.wait(5)
        append(4)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(concurrent)
        try:
            first = reader(setup, session, surface, limit=2)
            assert first['ok'], first
        finally:
            gate.set()
        future.result(timeout=5)
    eventually(lambda: committed() == 5)
    pages = [first]
    for cursor in (2, 4):
        pages.append(reader(setup, session, surface, after_sequence=cursor, limit=2))
    events = [e for p in pages for e in p['data']['events']]
    assert [e['sequence'] for e in events] == [1, 2, 3, 4, 5]
    assert [e['payload']['output_text'] for e in events] == list(map(str, range(5)))
    assert reader(setup, session, surface, after_sequence=5)['data']['events'] == []
    compacted = 0
    async def compact():
        async def read(journal):
            return await journal.compact_acked(max_rows=128)
        return await app.state.embedded_dispatch_owner.host.with_history(
            executor_id=stream['executor_id'], session_id=session, read=read)
    def all_compacted():
        nonlocal compacted
        compacted += client.portal.call(compact)[0]
        return compacted == 5
    eventually(all_compacted)
    replay = reader(setup, session, surface, limit=2)
    assert first['data']['committed_contiguous'] == 4
    assert replay == {**first, 'data': {**first['data'], 'committed_contiguous': 5}}


@pytest.mark.parametrize('arguments', [dict(limit=-1), dict(limit=0), dict(limit=1001), dict(after_sequence=-1)])
def test_replay_invalid_cursor_has_transport_parity_and_checks_authority_first(connected_local, arguments):
    setup, _, _, session = start(connected_local)
    foreign = create_agent(setup, 'foreign-reader')
    for surface in ('rest', 'mcp'):
        response = reader(setup, session, surface, **arguments)
        assert not response['ok'] and response['error']['code'] == 'VALIDATION_ERROR', response
        denied = reader(foreign, session, surface, **arguments)
        assert not denied['ok'] and denied['error']['code'] == 'PERMISSION_DENIED', denied
