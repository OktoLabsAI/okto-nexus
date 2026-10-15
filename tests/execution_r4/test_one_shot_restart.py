from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_embedded_inventory import app_for
from test_sender_sessions import Peers, configure, sender, turn_for, complete
from test_one_shot_runtime import query, wait_until


@pytest.mark.parametrize('terminal_recorded', [False, True])
def test_restart_settles_previous_call_without_replay_and_resumes_queue(tmp_path, monkeypatch, terminal_recorded):
    from okto_nexus.bootstrap import server_runtime
    first_peers, next_peers = Peers(), Peers()
    with monkeypatch.context() as patch, contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
        setup, binding, _ = connected_local.__wrapped__(setup)
        setup[1].state.embedded_dispatch_owner.native_factory = first_peers
        # Keep the commit-to-publication boundary open until the next server
        # owner, while preserving actual Core journals and native shutdown.
        from okto_nexus.application import one_shot_runtime
        configure(setup, binding, 'one_shot')
        send = sender(setup, monkeypatch)
        first = turn_for(setup, send('operator', 'before restart'))
        wait_receipt(setup, first)
        patch.setattr(one_shot_runtime, 'tick', lambda deps: 0)
        queued_message = send('operator', 'queued across restart')
        if terminal_recorded:
            complete(setup, first_peers, first, 'Durable final response')
        headers = setup[3]
        assert query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='QUEUED'")[0][0] == 1
    original_start = server_runtime.start_runtime_services
    async def start(app, **kwargs):
        return await original_start(app, native_factory=next_peers)
    monkeypatch.setattr(server_runtime, 'start_runtime_services', start)
    deps, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        restarted = deps, app, client, headers
        wait_until(restarted, lambda: query(restarted, "SELECT count(*) FROM one_shot_calls WHERE state='RUNNING'")[0][0] == 1
            and query(restarted, "SELECT count(*) FROM one_shot_calls WHERE state IN ('SUCCEEDED','FAILED')")[0][0] == 1)
        next_turn = turn_for(restarted, queued_message)
        wait_receipt(restarted, next_turn)
        assert next_turn['session_id'] != first['session_id']
        assert len(first_peers.sessions) == 1 and len(next_peers.sessions) == 1
        old = query(restarted, 'SELECT state,outcome_json FROM one_shot_calls ORDER BY enqueued_at')[0]
        assert old['state'] == ('SUCCEEDED' if terminal_recorded else 'FAILED')
        complete(restarted, next_peers, next_turn, 'After restart')
        wait_until(restarted, lambda: not query(restarted, 'SELECT * FROM one_shot_slots'))
