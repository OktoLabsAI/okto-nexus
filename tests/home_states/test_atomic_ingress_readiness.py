"""Real embedded ingress/receipt transactions with an inert native peer."""
import importlib
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from nexus_connector_core import R4_PREVIEW_REVISION, RuntimeEvent

from okto_nexus.application import execution_events


@pytest.mark.parametrize('fault', ['none', 'gap', 'projection_failure', 'stream_failure'])
def test_atomic_ingress_is_ready_without_unmaintained_projection_checkpoint(tmp_path, monkeypatch, fault):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'execution_r4'))
    local = importlib.import_module('test_local_realization')
    dispatch = importlib.import_module('test_embedded_dispatch')
    generator = local.local_setup.__wrapped__(tmp_path, monkeypatch, SimpleNamespace(param='codex_app_server'))
    setup = next(generator)
    try:
        _, binding, native = dispatch.connect_local(setup)
        deps, app, client, headers, *_ = setup
        deps.config.feature_attention = True
        opened = dispatch.admit(setup, binding, 'atomic-open', 'runtime.start', new_session=True)
        dispatch.wait_receipt(setup, opened)
        turn = dispatch.admit(setup, binding, 'atomic-turn', 'turn.submit',
                              session_id=opened['scope']['session_id'], text='Synthetic work')
        dispatch.wait_receipt(setup, turn)
        owner = app.state.embedded_dispatch_owner
        with deps.connection_factory.unit_of_work(write=False) as uow:
            stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?',
                                                (opened['scope']['session_id'],)).fetchone())
        event_scope = tuple(stream[k] for k in ('server_id', 'executor_id', 'session_id', 'stream_epoch'))
        # Core journals the synthetic native event; the real publisher commits
        # results/native requests and watermark before returning its ACK.
        client.portal.call(native.native.queue.put, RuntimeEvent(*event_scope, 0, 'turn_state', 'fixture.complete',
            {'delivery_phase': 'terminal', 'delivery_outcome': 'success', 'output_text': 'Synthetic delivery'},
            operation_id=turn['operation_id']))
        dispatch.wait_receipt(setup, turn, stages=('SUCCEEDED',))

        def snapshot():
            names = ('execution_event_ingress', 'execution_event_watermarks', 'execution_results',
                     'execution_operations', 'execution_receipts', 'runtime_execution_grants', 'execution_bindings')
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return {name: [tuple(r) for r in uow.connection.execute('SELECT * FROM ' + name + ' ORDER BY rowid')]
                        for name in names}

        def read_card():
            response = client.get('/api/v1/home/harness-board', params={'presentation_version': 2}, headers=headers['operator'])
            assert response.status_code == 200, response.text
            return next(item for lane in response.json()['data']['columns'].values() for item in lane['items']
                        if item['kind'] == 'harness' and item['connection']['binding_id'] == binding['binding_id'])

        deadline = time.monotonic() + 30
        while True:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                saved = uow.connection.execute('SELECT * FROM execution_event_watermarks WHERE session_id=?',
                                               (stream['session_id'],)).fetchone()
                result = uow.connection.execute('SELECT * FROM execution_results WHERE operation_id=?', (turn['operation_id'],)).fetchone()
                if saved is not None and result is not None and result['terminal_sequence'] is not None:
                    watermark = dict(saved)
                    assert watermark['committed_contiguous'] >= result['terminal_sequence'] > 0
                    assert watermark['projected_through'] == 0 and watermark['gap_state'] == 'none'
                    assert result['output_text'] == 'Synthetic delivery'
                    break
            assert time.monotonic() < deadline, 'Canonical event projection did not finish'
            time.sleep(.02)
        before = snapshot()
        card = read_card()
        assert card['operational_status']['connection'] == 'connected'
        assert card['operational_status']['activity'] == 'idle'
        assert snapshot() == before

        if fault == 'projection_failure':
            sequence = watermark['committed_contiguous'] + 1
            event = asdict(RuntimeEvent(*event_scope, sequence, 'text_delta', 'fixture.projection',
                                       {'output_text': 'Uncommitted'}, operation_id=turn['operation_id']))
            frame = {k: stream[k] for k in ('server_id', 'executor_id', 'binding_id', 'agent_id', 'session_id', 'stream_epoch')}
            frame.update(type='event.batch', protocol_major=1, contract_revision=R4_PREVIEW_REVISION,
                         connection_id=owner.channel.connection_id,
                         connection_generation=owner.channel.connection_generation, events=[event])
            def fail(*args, **kwargs):
                raise RuntimeError('Synthetic projection failure')
            with monkeypatch.context() as patch:
                patch.setattr(execution_events, 'project_execution_result', fail)
                with pytest.raises(RuntimeError, match='Synthetic projection failure'):
                    execution_events.commit_execution_events(deps.connection_factory, channel=owner.channel,
                                                            frame=frame, embedded_owner=owner)
            assert snapshot() == before
            assert read_card()['operational_status'] == card['operational_status']
        elif fault == 'gap':
            from okto_nexus.bootstrap import embedded_events
            buffered, frame_base, lock = {}, {}, threading.Lock()

            def hold(factory, *, frame, **kwargs):
                with lock:
                    frame_base.update(deepcopy(frame))
                    buffered.update((e['sequence'], deepcopy(e)) for e in frame['events'])
                # The existing publisher treats this as retryable storage
                # deferral. Returning a false ACK would trigger containment.
                raise OSError('Synthetic publication hold')

            def commit(events):
                return execution_events.commit_execution_events(deps.connection_factory, channel=owner.channel,
                    frame=dict(frame_base, events=events), embedded_owner=owner)

            with monkeypatch.context() as patch:
                patch.setattr(embedded_events, 'commit_execution_events', hold)
                try:
                    async def enqueue():
                        for number in range(2):
                            await native.native.queue.put(RuntimeEvent(*event_scope, 0, 'text_delta', 'fixture.gap',
                                {'output_text': f'Journaled {number}'}, operation_id=turn['operation_id']))
                    client.portal.call(enqueue)
                    deadline = time.monotonic() + 30
                    while True:
                        with lock:
                            events = [deepcopy(buffered[k]) for k in sorted(buffered)]
                        if len(events) >= 2:
                            break
                        assert time.monotonic() < deadline, 'Core journal did not publish both retained events'
                        time.sleep(.02)
                    assert events[0]['sequence'] == watermark['committed_contiguous'] + 1
                    assert events[1]['sequence'] == events[0]['sequence'] + 1
                    assert commit([events[1]])['sequence'] == watermark['committed_contiguous']
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        saved = uow.connection.execute('SELECT committed_contiguous,gap_state FROM execution_event_watermarks '
                                                       'WHERE session_id=?', (stream['session_id'],)).fetchone()
                        assert tuple(saved) == (watermark['committed_contiguous'], 'pending')
                    before = snapshot()
                    after = read_card()['operational_status']
                    assert after['activity'] == after['connection'] == 'unknown'
                    assert snapshot() == before
                    assert commit([events[0]])['sequence'] == events[1]['sequence']
                finally:
                    # Resolve every captured REAL Core journal event before
                    # restoring its publisher, even if an assertion failed.
                    with lock:
                        retained = [deepcopy(buffered[k]) for k in sorted(buffered)]
                    if retained:
                        commit(retained)
            deadline = time.monotonic() + 30
            stream_key = (stream['session_id'], stream['stream_epoch'])
            while owner.events._acked.get(stream_key, 0) < retained[-1]['sequence']:
                assert time.monotonic() < deadline, 'Core ACK was not reconciled after filling the real gap'
                time.sleep(.02)
            assert read_card()['operational_status']['activity'] == 'idle'
        elif fault == 'stream_failure':
            recovering, recover_session = [], owner.agents.recover_session
            try:
                with monkeypatch.context() as patch:
                    # Hold only asynchronous containment scheduling, exposing
                    # the real interval between committed loss and cleanup.
                    patch.setattr(owner.agents, 'recover_session', lambda sid, **kwargs: recovering.append(sid))
                    client.portal.call(native.native.queue.put, None)
                    deadline = time.monotonic() + 30
                    while True:
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            failure = uow.connection.execute("SELECT e.sequence FROM execution_event_ingress e "
                                "JOIN execution_event_watermarks w USING(server_id,executor_id,session_id,stream_epoch) "
                                "WHERE e.session_id=? AND e.sequence<=w.committed_contiguous AND e.event_type='error' "
                                "AND json_extract(e.payload_json,'$.native_type')='core.event_pump_failed' "
                                "AND json_extract(e.payload_json,'$.payload.code')='EVENT_STREAM_UNAVAILABLE'",
                                (stream['session_id'],)).fetchone()
                        if failure is not None:
                            break
                        assert time.monotonic() < deadline, 'Core iterator failure was not committed'
                        time.sleep(.02)
                    from okto_nexus.adapters.outbound.sqlite.home_operational_facts import (
                        LEASES,
                        SESSIONS,
                        normalize,
                    )
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        params = {'server_id': stream['server_id'], 'workspace_id': binding['workspace_id']}
                        rows = [dict(r) for r in uow.connection.execute(SESSIONS, params)]
                        leases = [dict(r) for r in uow.connection.execute(LEASES, params)]
                    row = next(r for r in rows if r['session_id'] == stream['session_id'])
                    fact = next(f for f in normalize(rows, leases, lambda: None) if f.session_id == stream['session_id'])
                    assert row['gap_state'] == 'none' and row['stream_unavailable'] == 1
                    assert fact.authority_current and fact.control_current and not fact.runtime_ready
                    before = snapshot()
                    after = read_card()['operational_status']
                    assert after['activity'] == after['connection'] == 'unknown'
                    assert snapshot() == before
            finally:
                # Use the actual recovery owner after releasing the test hold.
                client.portal.call(recover_session, stream['session_id'])
        assert native.opens == 1
    finally:
        generator.close()
