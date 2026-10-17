"""Verified terminal checkpoints survive restart without hiding new obligations."""
from contextlib import contextmanager
import json
import sqlite3
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import CoreError

from okto_nexus.bootstrap.embedded_retirement import EmbeddedRetirement
from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery
from okto_nexus.bootstrap.embedded_reconciliation import EmbeddedReconciliation
from test_embedded_dispatch import connected_local, admit, wait_receipt, qualified_contract
from test_local_realization import local_setup
from test_embedded_inventory import app_for
from test_local_pending_queries import pending_history


def checkpoint_fixture(tmp_path):
    owner, _, factory, _ = pending_history(tmp_path, 1, pending=1)
    # SQL boundary fixture only; native release proof production is exercised
    # below with the real Core lifecycle and a deterministic native adapter.
    owner.factory = factory
    proof = dict(server_id='server', executor_id='executor', session_id='session-0',
        opening_operation_id='open-0', owner_generation=1, stream_epoch='epoch',
        committed_sequence=0, release_kind='resource_released')
    with factory.unit_of_work(write=False) as uow:
        proof['retirement_revision'] = uow.connection.execute(
            'SELECT local_retirement_revision FROM execution_sessions').fetchone()[0]
    return EmbeddedRetirement(owner), factory, proof


def state(factory):
    with factory.unit_of_work(write=False) as uow:
        return tuple(uow.connection.execute('SELECT s.local_retirement_json,p.terminal,l.drained '
            'FROM execution_sessions s JOIN execution_local_publications p USING(server_id,executor_id,session_id) '
            'JOIN execution_local_streams l USING(server_id,executor_id,session_id)').fetchone())


def test_checkpoint_and_retirement_flags_commit_or_roll_back_together(tmp_path):
    retirement, factory, proof = checkpoint_fixture(tmp_path)
    with factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_checkpoint BEFORE UPDATE OF local_retirement_json ON execution_sessions "
            "WHEN NEW.local_retirement_json IS NOT NULL BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='injected failure'):
        retirement.commit('session-0', proof)
    assert state(factory) == (None, 0, 0)
    with factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER fail_checkpoint')
    retirement.commit('session-0', proof)
    raw, terminal, drained = state(factory)
    assert json.loads(raw) == dict(version=1, **proof)
    assert (terminal, drained) == (1, 1)
    fresh = dict(proof, retirement_revision=retirement.snapshot('session-0'))
    assert retirement.commit('session-0', fresh) is True
    assert state(factory) == (raw, 1, 1)
    # The occupied-slot path clears only the checkpoint, never invents a release.
    retirement.invalidate('session-0')
    assert state(factory) == (None, 1, 1)


@pytest.mark.parametrize('field,value', [('owner_generation', 2), ('opening_operation_id', 'other'),
    ('session_id', 'other'), ('executor_id', 'other'), ('server_id', 'other'),
    ('stream_epoch', 'other'), ('committed_sequence', 1)])
def test_mismatched_retirement_proof_cannot_retire_obligations(tmp_path, field, value):
    retirement, factory, proof = checkpoint_fixture(tmp_path)
    with pytest.raises(CoreError):
        retirement.commit('session-0', dict(proof, **{field: value}))
    assert state(factory) == (None, 0, 0)


@pytest.mark.parametrize('mutation', [
    "UPDATE execution_local_publications SET terminal=0",
    "UPDATE execution_local_streams SET drained=0",
    "UPDATE execution_sessions SET owner_generation=2",
    "UPDATE execution_sessions SET lifecycle_state='READY'",
    "UPDATE execution_sessions SET lifecycle_state='FAILED'",
    "UPDATE execution_sessions SET lease_state='ACTIVE'",
    "UPDATE execution_sessions SET stream_epoch='new-epoch'",
])
def test_new_obligation_invalidates_checkpoint_in_its_own_transaction(tmp_path, mutation):
    retirement, factory, proof = checkpoint_fixture(tmp_path)
    retirement.commit('session-0', proof)
    original = state(factory)
    with pytest.raises(RuntimeError, match='rollback'):
        with factory.unit_of_work() as uow:
            uow.connection.execute(mutation)
            assert uow.connection.execute('SELECT local_retirement_json FROM execution_sessions').fetchone()[0] is None
            raise RuntimeError('rollback')
    assert state(factory) == original
    with factory.unit_of_work() as uow:
        uow.connection.execute(mutation)
    assert state(factory)[0] is None


@pytest.mark.parametrize('mutation', [
    "UPDATE execution_local_publications SET terminal=0",
    "INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch) "
        "VALUES('server','executor','session-0','epoch')",
    "INSERT INTO execution_event_ingress(server_id,executor_id,session_id,stream_epoch,sequence,"
        "event_hash,event_type,payload_json,received_at) "
        "VALUES('server','executor','session-0','epoch',1,'hash','text_delta','{}','now')",
])
def test_new_obligation_between_proof_and_checkpoint_cannot_be_hidden(tmp_path, mutation):
    retirement, factory, proof = checkpoint_fixture(tmp_path)
    with factory.unit_of_work() as uow:
        uow.connection.execute(mutation)
    before = state(factory)
    assert retirement.commit('session-0', proof) is False
    assert state(factory) == before == (None, 0, 0)


def test_stale_owner_cannot_commit_checkpoint(tmp_path):
    retirement, factory, proof = checkpoint_fixture(tmp_path)
    def fenced(**kwargs):
        raise CoreError('STALE_GENERATION', 'test_owner')
    retirement.owner.verify = fenced
    with pytest.raises(CoreError, match='STALE_GENERATION'):
        retirement.commit('session-0', proof)
    assert state(factory) == (None, 0, 0)


@pytest.mark.asyncio
async def test_retirement_backfill_resumes_committed_sessions_in_bounded_batches(tmp_path, monkeypatch):
    owner, _, factory, _ = pending_history(tmp_path, 300, pending=0)
    owner.factory = factory
    owner.sessions, owner.worker_sessions = {}, {}
    with factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_sessions SET local_retirement_json=NULL')
    async def noop(*args, **kwargs):
        pass
    owner.tools = SimpleNamespace(release_session=noop)
    owner._recover_publications = noop
    observed = []
    async def release(self, session_id, **kwargs):
        # This test isolates durable batching with synthetic release facts.
        # Core proof correctness is covered by the restart tests below.
        observed.append(session_id)
        return dict(server_id='server', executor_id='executor', session_id=session_id,
            opening_operation_id=session_id.replace('session-', 'open-'), owner_generation=1,
            stream_epoch='epoch', committed_sequence=0, release_kind='resource_released')
    monkeypatch.setattr(EmbeddedReconciliation, 'release_session', release)
    original = EmbeddedRetirement.commit
    def cut(self, session_id, proof, **kwargs):
        if len(observed) == 65:
            raise OSError('interrupted checkpoint batch')
        return original(self, session_id, proof, **kwargs)
    monkeypatch.setattr(EmbeddedRetirement, 'commit', cut)
    with pytest.raises(OSError, match='interrupted checkpoint batch'):
        await EmbeddedAgentRecovery(owner)._retire_closed('agent')
    def completed():
        with factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT COUNT(*) FROM execution_sessions '
                'WHERE local_retirement_json IS NOT NULL').fetchone()[0]
    assert completed() == 64
    monkeypatch.setattr(EmbeddedRetirement, 'commit', original)
    observed.clear()
    fresh = EmbeddedAgentRecovery(owner)
    await fresh._retire_closed('agent')
    assert completed() == 192 and len(observed) == 128
    await fresh._retire_closed('agent')
    assert completed() == 300 and len(observed) == 236
    assert set(observed) == {f'session-{i}' for i in range(64, 300)}
    await fresh._retire_closed('agent')
    assert len(observed) == 236


@pytest.mark.parametrize('adapter,occupied', [('pi_rpc', False), ('codex_app_server', False),
    ('claude_stream', False), ('pi_rpc', True)])
def test_restart_uses_verified_retirement_unless_core_still_owns_resources(tmp_path, monkeypatch, adapter, occupied):
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, SimpleNamespace(param=adapter)) as setup:
        setup, binding, native = connected_local.__wrapped__(setup)
        deps, app, client, *_ = setup
        opened = admit(setup, binding, 'checkpoint-open', 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        session_id = opened['scope']['session_id']
        closed = admit(setup, binding, 'checkpoint-close', 'runtime.close', session_id=session_id)
        wait_receipt(setup, closed, stages=('SUCCEEDED',))
        owner = app.state.embedded_dispatch_owner
        path = owner.host._journal_path(owner.channel.executor_id, session_id)
        deadline = time.monotonic() + 20
        while True:
            client.portal.call(owner.agents._retire_closed, 'subject')
            with deps.connection_factory.unit_of_work(write=False) as uow:
                raw = uow.connection.execute('SELECT local_retirement_json FROM execution_sessions WHERE session_id=?',
                    (session_id,)).fetchone()[0]
            if raw:
                break
            assert time.monotonic() < deadline
            time.sleep(.02)
        checkpoint = json.loads(raw)
        assert checkpoint['release_kind'] == 'resource_released'
        assert checkpoint['process_state'] == 'EXITED'
        assert checkpoint['opening_operation_id'] == opened['operation_id']
        assert native.opens == 1 and native.native.stopped

    from okto_nexus.bootstrap import runtime_host
    original = runtime_host.open_journal
    if occupied:
        # Disposable test store: model a restored occupied ledger overriding
        # the Server certificate. No actual process is created or killed.
        with sqlite3.connect(tmp_path/'home/core-runtime/owned-slots.db') as db:
            db.execute('UPDATE owned_slot_reservations SET released=0')
    reads = []
    async def reject_retired_journal(journal_path):
        if journal_path == path:
            reads.append(journal_path)
            assert occupied, 'Already verified journal must not be reopened at restart'
        return await original(journal_path)
    monkeypatch.setattr(runtime_host, 'open_journal', reject_retired_journal)
    deps, app = app_for(tmp_path / 'home')
    with TestClient(app):
        owner = app.state.embedded_dispatch_owner
        if occupied:
            assert 'subject' in owner.agents.blocked
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT local_retirement_json FROM execution_sessions WHERE session_id=?',
                    (session_id,)).fetchone()[0] is None
            with sqlite3.connect(tmp_path/'home/core-runtime/owned-slots.db') as db:
                db.execute('UPDATE owned_slot_reservations SET released=1')
        deadline = time.monotonic() + 20
        while 'subject' in owner.agents.blocked:
            assert time.monotonic() < deadline, repr(owner.agents.errors)
            time.sleep(.02)
        assert owner.pump is not None and native.opens == 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            retained = uow.connection.execute('SELECT local_retirement_json FROM execution_sessions WHERE session_id=?',
                (session_id,)).fetchone()[0]
        if occupied:
            assert reads and retained is not None
        else:
            assert retained == raw and not reads
