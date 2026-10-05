"""Canonical output is scoped, replay-safe and committed with its event ACK."""
import sqlite3
import time

import pytest
from nexus_connector_core import RuntimeEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_event_ingress import ingress, commit
from test_reconciliation import recovery
from test_binding_operator import onboarding


def test_public_operation_history_returns_canonical_output(connected_local):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    opened = admit(setup, binding, 'result-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    sent = admit(setup, binding, 'result-turn', 'turn.submit', session_id=opened['scope']['session_id'], text='Review')
    wait_receipt(setup, sent)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    for category, payload in (
        ('text_delta', dict(output_text='Old draft')),
        ('text_snapshot', dict(output_text='Final')),
        ('text_delta', dict(output_text=' answer')),
        ('turn_state', dict(delivery_phase='terminal', delivery_outcome='success', output_text='.')),
    ):
        client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
            stream['session_id'], stream['stream_epoch'], 0, category, 'fixture.output', payload,
            operation_id=sent['operation_id']))
    wait_receipt(setup, sent, stages=('SUCCEEDED',))
    until = time.monotonic() + 10
    while True:
        response = client.get('/v1/runtime/operations/' + sent['operation_id'], headers=headers['subject'])
        assert response.status_code == 200, response.text
        result = response.json()['result']
        if result:
            break
        assert time.monotonic() < until
        time.sleep(.02)
    assert result['output_text'] == 'Final answer.'
    assert result['output_event_count'] == 4 and not result['output_truncated']
    assert result['delivery_outcome'] == 'success' and result['stream_epoch'] == stream['stream_epoch']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_results').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM harness_events').fetchone()[0] == 0
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    wait_receipt(setup, admit(setup, binding, 'result-close', 'runtime.close', session_id=stream['session_id']), stages=('SUCCEEDED',))


def result_frame(ingress, sequence, category, payload):
    factory, _, frame = ingress
    # The focused ingress fixture's existing admitted operation is a turn here.
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_operations SET action='turn.submit' WHERE operation_id='close'")
    return {**frame, 'events': [{**frame['events'][0], 'sequence': sequence, 'category': category, 'payload': payload}]}


def read(ingress):
    with ingress[0].unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT * FROM execution_results').fetchone()
        return dict(row) if row else None


def test_result_waits_for_gap_and_replay_cannot_append_twice(ingress):
    end = result_frame(ingress, 3, 'turn_state', dict(delivery_phase='terminal', delivery_outcome='success'))
    assert commit(ingress, end) is None and read(ingress) is None
    first = result_frame(ingress, 1, 'text_delta', dict(output_text='one'))
    assert commit(ingress, first)['sequence'] == 1
    second = result_frame(ingress, 2, 'text_delta', dict(output_text=' two'))
    assert commit(ingress, second)['sequence'] == 3
    saved = read(ingress)
    assert saved['output_text'] == 'one two' and saved['terminal_sequence'] == 3
    assert commit(ingress, first)['sequence'] == 3
    assert read(ingress) == saved
    late = result_frame(ingress, 4, 'text_snapshot', dict(output_text='replacement'))
    assert commit(ingress, late)['sequence'] == 4
    assert read(ingress) == saved


def test_result_and_watermark_rollback_together(ingress):
    frame = result_frame(ingress, 1, 'text_delta', dict(output_text='private'))
    with ingress[0].unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER result_failure BEFORE INSERT ON execution_event_watermarks BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError):
        commit(ingress, frame)
    assert read(ingress) is None
    with ingress[0].unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_event_ingress').fetchone()[0] == 0


def test_result_bounds_utf8_and_snapshot_resets_truncation(ingress, monkeypatch):
    from okto_nexus.application import execution_results
    monkeypatch.setattr(execution_results, 'OUTPUT_LIMIT', 5)
    commit(ingress, result_frame(ingress, 1, 'text_delta', dict(output_text='ééé')))
    assert read(ingress)['output_text'] == 'éé' and read(ingress)['output_truncated']
    commit(ingress, result_frame(ingress, 2, 'text_snapshot', dict(output_text='done')))
    commit(ingress, result_frame(ingress, 3, 'turn_state', dict(delivery_phase='terminal', delivery_outcome='success')))
    assert read(ingress)['output_text'] == 'done' and not read(ingress)['output_truncated']
