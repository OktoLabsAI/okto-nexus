"""Home exact target -> canonical interrupt, with two owned fake pipe peers.

The subprocesses run only the repository's scripted JSON-RPC fixture through
Python. No Codex binary, account, provider, TCP listener or personal credential
is used. Canonical admission and Core dispatch remain real.
"""
# ruff: noqa: F401,F811,E402 -- imported pytest fixture dependencies
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[1]/'execution_r4'))

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_harness_canonical import qualified_bridge
from test_canonical_native_protocol_regressions import install_native
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_agent_recovery_isolation import eventually


def test_home_exact_target_interrupt_leaves_sibling_turn_and_process_alive(connected_local, record_property):
    setup, binding, _ = connected_local
    deps, app, client, headers, *_ = setup
    # Each fixture starts with thread-1/turn-1. Record PID at the fake peer's
    # logging boundary to prove routing rather than assuming native IDs global.
    source = _FAKE_SERVER_SOURCE.replace('def log(entry):\n',
        'def log(entry):\n    entry = dict(entry, fixture_pid=os.getpid())\n')
    assert source != _FAKE_SERVER_SOURCE
    peers, log = install_native(connected_local, source)
    sessions, turns = [], []
    try:
        for index in range(2):
            opened = admit(setup, binding, f'home-open-{index}', 'runtime.start', new_session=True)
            wait_receipt(setup, opened)
            sid = opened['scope']['session_id']
            sessions.append(sid)
            turn = admit(setup, binding, f'home-held-{index}', 'turn.submit',
                         session_id=sid, text='TRIGGER_HOLD')
            turns.append(turn)
            wait_receipt(setup, turn, stages=('SUBMITTED',))
        assert len(peers) == 2 and sessions[0] != sessions[1]
        states = [next(iter(peer._sessions_by_id.values())) for peer in peers]
        eventually(lambda: all(state.active_turn_id for state in states))
        pids = [peer._transport._proc.pid for peer in peers]
        assert pids[0] != pids[1]
        sibling_turn = states[1].active_turn_id

        response = client.get('/api/v1/home/work', headers=headers['operator'],
                              params={'workspace_id':binding['workspace_id']})
        assert response.status_code == 200, response.text
        items = response.json()['data']['items']
        target = next(row['detail_target'] for row in items
                      if row['detail_target'].get('operation_id') == turns[0]['operation_id'])
        assert target['session_id'] == sessions[0] and target['executor_id'] == binding['executor_id']
        resolved = client.get('/api/v1/home/target', headers=headers['operator'],
            params={'target':json.dumps(target), 'workspace_id':binding['workspace_id']})
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()['data']['target'] == target
        assert resolved.json()['data']['available'] is True
        forged = dict(target, session_id=sessions[1])
        assert client.get('/api/v1/home/target', headers=headers['operator'],
            params={'target':json.dumps(forged)}).status_code == 404

        # A stale turn must not reach either native peer. Then invoke the same
        # public harness control route used by CanonicalInspection on the
        # selected Home session and its exact current native turn.
        stale = client.post(f"/api/v1/harness/sessions/{target['session_id']}/interrupt",
            headers=headers['subject'], json={'idempotency_key':'home-stale-interrupt',
                                             'expected_turn_id':'stale-native-turn'})
        assert stale.status_code == 200, stale.text
        refused = wait_receipt(setup, stale.json()['data'], stages=('FAILED',))
        assert refused['possible_effect'] is False
        body = {'idempotency_key':'home-selected-interrupt','expected_turn_id':states[0].active_turn_id}
        interrupted = client.post(f"/api/v1/harness/sessions/{target['session_id']}/interrupt",
                                  headers=headers['subject'], json=body)
        assert interrupted.status_code == 200, interrupted.text
        control = interrupted.json()['data']
        wait_receipt(setup, control)
        wait_receipt(setup, turns[0], stages=('CANCELLED',))
        sibling = client.get('/v1/runtime/operations/'+turns[1]['operation_id'], headers=headers['subject'])
        assert sibling.status_code == 200 and sibling.json()['executor_stage'] == 'SUBMITTED'
        assert states[1].active_turn_id == sibling_turn
        assert peers[1]._transport._proc.pid == pids[1] and peers[1]._transport._proc.poll() is None
        wire = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
        controls = [row for row in wire if row.get('method') == 'turn/interrupt']
        assert len(controls) == 1 and controls[0]['fixture_pid'] == pids[0]
        with deps.connection_factory.unit_of_work(write=False) as uow:
            sibling_state = uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?', (sessions[1],)).fetchone()
            assert tuple(sibling_state) == ('READY','ACTIVE')
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE session_id=? AND action='turn.interrupt'", (sessions[1],)).fetchone()[0] == 0
        replay = client.post(f"/api/v1/harness/sessions/{target['session_id']}/interrupt",
                            headers=headers['subject'], json=body)
        assert replay.status_code == 200 and replay.json()['data']['operation_id'] == control['operation_id']
    finally:
        # Explicit canonical close for both owned fixture sessions, including
        # failures; retain Popen handles and require physical process exit.
        for index, sid in enumerate(sessions):
            state = next(iter(peers[index]._sessions_by_id.values()))
            if state.active_turn_id:
                interrupted = admit(setup, binding, f'home-cleanup-interrupt-{index}', 'turn.interrupt',
                    session_id=sid, target={'kind':'native_turn_id','expected_turn_id':state.active_turn_id})
                wait_receipt(setup, interrupted)
                wait_receipt(setup, turns[index], stages=('CANCELLED',))
            closed = admit(setup, binding, f'home-cleanup-{index}', 'runtime.close', session_id=sid)
            wait_receipt(setup, closed, stages=('SUCCEEDED',))
        exits = []
        for peer in peers:
            process = peer._transport._proc
            code = process.wait(timeout=10)
            # Canonical adapter close may terminate the owned pipe process;
            # physical exit, not a graceful fake-peer exit code, is required.
            assert code is not None
            exits.append({'pid': process.pid, 'exit_code': code})
        record_property('owned_fake_peer_exit', json.dumps(exits))
