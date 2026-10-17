"""Historical checkpoint work cannot hold readiness or live publication hostage."""
import asyncio
from contextlib import contextmanager
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery
from okto_nexus.bootstrap.embedded_retirement import EmbeddedRetirement
from okto_nexus.bootstrap.embedded_retirement_maintenance import EmbeddedRetirementMaintenance
from test_embedded_dispatch import local_setup, connect_local, admit, wait_receipt, qualified_contract
from test_embedded_inventory import app_for
from test_agent_recovery_isolation import eventually


@pytest.mark.parametrize('adapter', ['codex_app_server', 'claude_stream', 'pi_rpc'])
def test_restart_is_ready_and_publishes_new_response_while_retirement_waits(tmp_path, monkeypatch, adapter):
    from test_sender_sessions import Peers, configure, sender, turn_for, complete
    old_session = None
    restarted = False
    entered = threading.Event()
    release = asyncio.Event()
    calls = []
    original = EmbeddedAgentRecovery._retire_session

    async def delayed(self, agent_id, row):
        if not restarted:
            return  # Leave a real closed session without its optimization checkpoint.
        if row['session_id'] == old_session:
            calls.append(row['session_id'])
            entered.set()
            await release.wait()
        return await original(self, agent_id, row)

    monkeypatch.setattr(EmbeddedAgentRecovery, '_retire_session', delayed)
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, SimpleNamespace(param=adapter)) as setup:
        setup, binding, _ = connect_local(setup)
        opened = admit(setup, binding, 'old-open', 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        old_session = opened['session_id']
        wait_receipt(setup, admit(setup, binding, 'old-close', 'runtime.close', session_id=old_session), stages=('SUCCEEDED',))
    restarted = True
    deps, app = app_for(tmp_path/'home')
    with TestClient(app) as client:
        owner = app.state.embedded_dispatch_owner
        current = (deps, app, client, setup[3], *setup[4:])
        peers = Peers()
        owner.native_factory = peers
        try:
            eventually(lambda: owner.agents.initialized and 'subject' not in owner.agents.blocked)
            assert entered.wait(10), 'Independent retirement worker was not scheduled'
            task = owner.agents.retirement.tasks['subject']
            pump = owner.pump
            with deps.connection_factory.unit_of_work(write=False) as uow:
                row = uow.connection.execute('SELECT lifecycle_state,lease_state,local_retirement_json '
                    'FROM execution_sessions WHERE session_id=?', (old_session,)).fetchone()
                assert tuple(row) == ('CLOSED', 'CLOSED', None)
            configure(current, binding, 'per_sender')
            turn = turn_for(current, sender(current, monkeypatch)('operator', 'New work while history waits'))
            wait_receipt(current, turn)
            complete(current, peers, turn, 'Live response is independent of historical checkpoint work')
            assert owner.pump is pump and owner.failure is None
            assert not owner._stopping.is_set() and 'subject' not in owner.agents.blocked
            assert owner.agents.retirement.tasks['subject'] is task and not task.done()
            assert calls == [old_session], 'Slow maintenance was duplicated'
        finally:
            client.portal.call(release.set)
        def checkpointed():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return uow.connection.execute('SELECT local_retirement_json FROM execution_sessions '
                    'WHERE session_id=?', (old_session,)).fetchone()[0] is not None
        eventually(checkpointed, seconds=20)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1


@pytest.mark.asyncio
async def test_pending_cursor_wraps_without_starving_other_sessions_and_joins_shutdown(tmp_path):
    from test_local_pending_queries import pending_history
    owner, _, factory, _ = pending_history(tmp_path, 3, pending=0)
    owner.factory = factory
    owner._stopping = asyncio.Event()
    with factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_sessions SET local_retirement_json=NULL')
    visited = []
    entered, release = asyncio.Event(), asyncio.Event()
    async def retire(agent_id, row):
        visited.append(row['session_id'])
        if len(visited) == 1:
            raise OSError('Unavailable history for the first session')
        if len(visited) == 2:
            entered.set()
            await release.wait()
    agents = SimpleNamespace(owner=owner, blocked=set(), _retire_session=retire)
    worker = EmbeddedRetirementMaintenance(agents)
    worker.tick({'agent'})
    await worker.tasks['agent']
    assert visited == ['session-0'] and worker.errors['agent'] == 'OSError'
    worker.retry_at.clear()
    worker.tick({'agent'})
    await asyncio.wait_for(entered.wait(), 5)
    retained = worker.tasks['agent']
    worker.tick({'agent'})
    assert worker.tasks['agent'] is retained
    owner._stopping.set()
    closing = asyncio.create_task(worker.close())
    await asyncio.sleep(0)
    assert not closing.done(), 'Shutdown must join retained history work'
    release.set()
    await closing
    owner._stopping.clear()  # Test scheduler continuation only; not a production owner restart.
    for _ in range(3):
        worker.retry_at.clear()
        worker.tick({'agent'})
        await worker.tasks['agent']
    assert visited == ['session-0', 'session-1', 'session-2', 'session-0']
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions '
            'WHERE local_retirement_json IS NOT NULL').fetchone()[0] == 0


@pytest.mark.asyncio
async def test_recovering_agent_does_not_start_historical_maintenance():
    owner = SimpleNamespace(_stopping=asyncio.Event())
    worker = EmbeddedRetirementMaintenance(SimpleNamespace(owner=owner, blocked={'agent'}))
    worker.tick({'agent'})
    assert not worker.tasks


@pytest.mark.parametrize('code', ['RECOVERY_CONTAINER_STOPPED', 'RECOVERY_AGENT_READY'])
def test_retryable_recovery_evidence_write_failure_still_propagates(code):
    from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner
    from okto_nexus.errors import ErrorCode, OktoNexusError
    def unavailable():
        raise OktoNexusError(ErrorCode.DB_ERROR, 'Writer busy', {}, retryable=True)
    owner = SimpleNamespace(factory=SimpleNamespace(unit_of_work=unavailable))
    with pytest.raises(OktoNexusError):
        EmbeddedDispatchOwner._recovery_event(owner, code, 'Required recovery record')
