"""Canonical Core progress, not an invented RUNNING executor receipt."""
import importlib
import time
from pathlib import Path
from types import SimpleNamespace

from nexus_connector_core import RuntimeEvent


def test_submitted_core_started_event_proves_working_and_terminal_returns_idle(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'execution_r4'))
    local = importlib.import_module('test_local_realization')
    dispatch = importlib.import_module('test_embedded_dispatch')
    generator = local.local_setup.__wrapped__(tmp_path, monkeypatch, SimpleNamespace(param='codex_app_server'))
    setup = next(generator)
    turn, event_scope, native = None, None, None
    terminal_sent = False
    try:
        _, binding, native = dispatch.connect_local(setup)
        deps, _, client, headers, *_ = setup
        deps.config.feature_attention = True
        opened = dispatch.admit(setup, binding, 'productive-open', 'runtime.start', new_session=True)
        dispatch.wait_receipt(setup, opened)
        turn = dispatch.admit(setup, binding, 'productive-turn', 'turn.submit',
                              session_id=opened['scope']['session_id'], text='Synthetic productive work')
        assert dispatch.wait_receipt(setup, turn)['executor_stage'] == 'SUBMITTED'
        with deps.connection_factory.unit_of_work(write=False) as uow:
            stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?',
                                                (opened['scope']['session_id'],)).fetchone())
        event_scope = tuple(stream[k] for k in ('server_id', 'executor_id', 'session_id', 'stream_epoch'))
        client.portal.call(native.native.queue.put, RuntimeEvent(*event_scope, 0, 'turn_state', 'fixture.started',
            {'delivery_phase': 'started'}, operation_id=turn['operation_id']))
        deadline = time.monotonic() + 30
        while True:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                current = uow.connection.execute("SELECT e.sequence FROM execution_event_ingress e "
                    "JOIN execution_event_watermarks w USING(server_id,executor_id,session_id,stream_epoch) "
                    "WHERE e.session_id=? AND e.sequence<=w.committed_contiguous AND w.gap_state='none' "
                    "AND json_extract(e.payload_json,'$.operation_id')=? "
                    "AND json_extract(e.payload_json,'$.payload.delivery_phase')='started'",
                    (stream['session_id'], turn['operation_id'])).fetchone()
            if current is not None:
                break
            assert time.monotonic() < deadline, 'Actual Core started event was not committed'
            time.sleep(.02)

        def card():
            response = client.get('/api/v1/home/harness-board', params={'presentation_version': 2}, headers=headers['operator'])
            assert response.status_code == 200, response.text
            return next(item for lane in response.json()['data']['columns'].values() for item in lane['items']
                        if item['kind'] == 'harness' and item['connection']['binding_id'] == binding['binding_id'])

        receipt = client.get('/v1/runtime/operations/' + turn['operation_id'], headers=headers['subject']).json()
        assert receipt['executor_stage'] == 'SUBMITTED'
        legacy = client.get('/api/v1/home/work', headers=headers['operator'])
        assert legacy.status_code == 200, legacy.text
        work = next(item for item in legacy.json()['data']['items'] if item['detail_target'].get('operation_id') == turn['operation_id'])
        assert work['display_state'] == 'running'
        current = card()
        assert current['operational_status']['activity'] == 'working'
        assert current['operational_status']['running_sessions']['value'] == 1
        assert current['blocks_harness'] is False
        client.portal.call(native.native.queue.put, RuntimeEvent(*event_scope, 0, 'turn_state', 'fixture.complete',
            {'delivery_phase': 'terminal', 'delivery_outcome': 'success', 'output_text': 'Synthetic delivery'},
            operation_id=turn['operation_id']))
        terminal_sent = True
        dispatch.wait_receipt(setup, turn, stages=('SUCCEEDED',))
        assert card()['operational_status']['activity'] == 'idle'
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_receipts WHERE operation_id=? AND stage='RUNNING'",
                                          (turn['operation_id'],)).fetchone()[0] == 0
        assert native.opens == 1
    finally:
        try:
            if turn is not None and event_scope is not None and not terminal_sent:
                setup[2].portal.call(native.native.queue.put, RuntimeEvent(*event_scope, 0, 'turn_state', 'fixture.cleanup',
                    {'delivery_phase': 'terminal', 'delivery_outcome': 'success'}, operation_id=turn['operation_id']))
                dispatch.wait_receipt(setup, turn, stages=('SUCCEEDED',))
        finally:
            generator.close()
