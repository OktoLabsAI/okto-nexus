"""Core compacts only committed capture; Server retains domain provenance."""
import threading
import time

from nexus_connector_core import CoreError, EventCursor
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_result_publication import emit, wait_result, current_turn, workspace
from test_message_workspace import call as send_message


def test_compaction_waits_for_server_commit_and_preserves_published_result(connected_local, monkeypatch):
    from okto_nexus.bootstrap import embedded_events
    from okto_nexus.application.retention import RetentionService
    from okto_nexus.domain.base import iso_plus
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation' WHERE endpoint_id=?",
                               (binding['endpoint_id'],))
    assert send_message(setup, monkeypatch, workspace_id=workspace(setup))['ok']
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    entered, release = threading.Event(), threading.Event()
    original = embedded_events.commit_execution_events
    def held(*args, **kwargs):
        entered.set()
        assert release.wait(15)
        return original(*args, **kwargs)
    monkeypatch.setattr(embedded_events, 'commit_execution_events', held)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    host = app.state.embedded_dispatch_owner.host
    async def compact():
        async def read(journal):
            return await journal.compact_acked(max_rows=128)
        return await host.with_history(executor_id=stream['executor_id'], session_id=stream['session_id'], read=read)
    try:
        # Hold the Server commit before observing pre-ACK compaction. A
        # terminal receipt can depend on that commit, so wait for it only
        # after releasing this barrier.
        emit(setup, native, turn, 'Retain this canonical result.', wait_for_terminal=False)
        assert entered.wait(10)
        assert client.portal.call(compact) == (0, 0)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_results').fetchone()[0] == 0
    finally:
        release.set()
    wait_receipt(setup, turn, stages=('SUCCEEDED',))
    published = wait_result(setup, 'PUBLISHED')
    deadline = time.monotonic() + 10
    while True:
        rows, size = client.portal.call(compact)
        if rows:
            break
        assert time.monotonic() < deadline
        time.sleep(.02)
    assert rows == 1 and size > 0
    async def expired_cursor():
        async def read(journal):
            cursor = EventCursor(stream['server_id'], stream['executor_id'], stream['session_id'], stream['stream_epoch'], 0)
            return [event async for event in journal.events(cursor)]
        return await host.with_history(executor_id=stream['executor_id'], session_id=stream['session_id'], read=read)
    with pytest.raises(CoreError) as gap:
        client.portal.call(expired_cursor)
    assert gap.value.code == 'EVENT_GAP'
    closed = admit(setup, binding, 'retention-close', 'runtime.close', session_id=turn['session_id'])
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    captured = client.get('/v1/runtime/operations/' + turn['operation_id'], headers=headers['subject']).json()['result']
    retained_tables = ('execution_event_ingress', 'execution_results', 'runtime_results', 'execution_receipts', 'delivery_outbox')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)] for table in retained_tables}
    future = iso_plus(deps.clock.now_iso(), 400 * 86400)
    from types import SimpleNamespace
    retention = RetentionService.from_deps(deps)
    retention._clock = SimpleNamespace(now_iso=lambda: future)
    report = retention.prune(max_batches=4)
    assert not report['dry_run']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert before == {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)] for table in retained_tables}
        assert uow.connection.execute('SELECT body FROM messages WHERE message_id=?',
                                      (published['publication_message_id'],)).fetchone()[0] == captured['output_text']
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    after = client.get('/v1/runtime/operations/' + turn['operation_id'], headers=headers['subject'])
    assert after.status_code == 200 and after.json()['result'] == captured, after.text
