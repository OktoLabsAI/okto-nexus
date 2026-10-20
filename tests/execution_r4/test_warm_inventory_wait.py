"""Initial discovery is a prerequisite, not four failed native startups."""
import time

import pytest

from test_embedded_dispatch import local_setup, connected_local, qualified_contract
from test_one_shot_runtime import query, wait_until
from test_sender_sessions import Peers, configure
from okto_nexus.application import one_shot_runtime
from okto_nexus.application.one_shot_settings import read, save


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'claude_stream', 'codex_app_server'], indirect=True)
@pytest.mark.parametrize('observation', ['missing', 'expired', 'different_sequence'])
def test_waiting_for_current_inventory_does_not_grow_warm_failure_backoff(
        connected_local, monkeypatch, observation):
    setup, binding, _ = connected_local
    deps, app = setup[:2]
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    with deps.connection_factory.unit_of_work() as uow:
        current = read(uow.connection)
        save(uow.connection, expected_revision=current['revision'],
             settings=current['settings'] | {'max_parallel': 5, 'warm_instances': 4})
    original = deps.execution_fresh_publications
    pending = dict(original)
    key = next(iter(pending))
    receipt = pending[key]
    if observation == 'missing':
        pending.clear()
    elif observation == 'expired':
        pending[key] = (receipt[0], time.monotonic() - 121, *receipt[2:])
    else:
        pending[key] = (receipt[0] - 1, *receipt[1:])
    with monkeypatch.context() as scoped:
        scoped.setattr(deps, 'execution_fresh_publications', pending)
        for _ in range(3):
            one_shot_runtime.tick(deps)
        assert not peers.sessions
        assert not query(setup, 'SELECT * FROM execution_sessions')
        assert not query(setup, 'SELECT * FROM one_shot_slots')
        assert not query(setup, 'SELECT * FROM one_shot_warm_backoff')
    # The real publication is usable again. The next pass can reserve all
    # four starts without waiting through a synthetic failure penalty.
    one_shot_runtime.tick(deps)
    assert len(query(setup, 'SELECT * FROM one_shot_slots')) == 4
    wait_until(setup, lambda: len(query(setup, "SELECT * FROM one_shot_slots WHERE state='WARM'")) == 4)
    assert len(peers.sessions) == 4
    assert not query(setup, 'SELECT * FROM one_shot_warm_backoff')
