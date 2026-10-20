"""Positive no-admission evidence has a checkpoint distinct from native exit."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError, OperationKey
from nexus_connector_core.journal import SQLiteJournal

from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery
from okto_nexus.bootstrap.embedded_retirement import EmbeddedRetirement
from okto_nexus.bootstrap.embedded_unopened_retirement import EmbeddedUnopenedRetirement
from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost
from test_local_recovery_lookup import history


def refused(tmp_path):
    reconciliation, factory, _ = history(tmp_path, 1)
    owner = reconciliation.owner
    owner.factory = factory
    owner.sessions, owner.worker_sessions = {}, {}
    owner.host = EmbeddedRuntimeHost((tmp_path / 'store').resolve())
    async def cleanup(_):
        pass
    owner.tools = SimpleNamespace(release_session=cleanup)
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_operations SET action='runtime.open'")
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='FAILED'")
        uow.connection.execute('INSERT INTO execution_dispatch_outbox '
            '(server_id,executor_id,operation_id,dispatch_state,last_error) '
            "VALUES('server','executor','open-0','RESOLVED_TERMINAL',?)",
            (json.dumps(dict(stage='dispatch', possible_effect=False, code='STALE_CONFIGURATION')),))
    return EmbeddedUnopenedRetirement(owner), factory


def checkpoint(factory):
    with factory.unit_of_work(write=False) as uow:
        return uow.connection.execute('SELECT local_retirement_json FROM execution_sessions').fetchone()[0]


@pytest.mark.asyncio
async def test_dispatch_refusal_retires_without_creating_journal_stream_or_result(tmp_path):
    retirement, factory = refused(tmp_path)
    assert EmbeddedAgentRecovery(retirement.owner)._pending_subjects() == {'agent'}
    page = EmbeddedRetirement(retirement.owner).pending('agent')
    assert len(page) == 1 and page[0]['stream_epoch'] is None
    assert await retirement.retire('session-0')
    proof = json.loads(checkpoint(factory))
    assert proof['release_kind'] == 'no_native_admission'
    assert proof['evidence_kind'] == 'dispatch_refusal'
    assert 'process_state' not in proof and 'stream_epoch' not in proof
    assert not retirement.owner.host.store_dir.exists()
    assert not EmbeddedRetirement(retirement.owner).pending('agent')
    assert not EmbeddedAgentRecovery(retirement.owner)._pending_subjects()
    with factory.unit_of_work(write=False) as uow:
        for table in ('execution_local_streams', 'execution_receipts', 'runtime_results'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', [
    "UPDATE execution_sessions SET lifecycle_state='OPEN_PENDING'",
    "UPDATE execution_dispatch_outbox SET last_error='{\"stage\":\"dispatch\",\"possible_effect\":true}'",
    "UPDATE execution_dispatch_outbox SET last_error=NULL",
    "UPDATE execution_operations SET admission_state='ACCEPTED'",
    "UPDATE execution_sessions SET lease_state='ACTIVE'",
    "INSERT INTO execution_local_streams(server_id,executor_id,session_id,stream_epoch,opening_operation_id,binding_id,agent_id) "
        "VALUES('server','executor','session-0','epoch','open-0','binding','agent')",
])
async def test_missing_or_conflicting_proof_does_not_retire(tmp_path, mutation):
    retirement, factory = refused(tmp_path)
    with factory.unit_of_work() as uow:
        uow.connection.execute(mutation)
    assert not await retirement.retire('session-0')
    assert checkpoint(factory) is None
    assert not retirement.owner.host.store_dir.exists()


@pytest.mark.asyncio
async def test_producer_and_cleanup_must_finish_before_checkpoint(tmp_path):
    retirement, factory = refused(tmp_path)
    pending = asyncio.get_running_loop().create_future()
    retirement.owner.worker_sessions[pending] = 'session-0'
    assert not await retirement.retire('session-0')
    assert checkpoint(factory) is None
    pending.set_result(None)
    cleanup = retirement.owner.tools.release_session
    async def fail(_):
        raise OSError('Retained tool cleanup')
    retirement.owner.tools.release_session = fail
    with pytest.raises(OSError, match='Retained tool cleanup'):
        await retirement.retire('session-0')
    assert checkpoint(factory) is None
    retirement.owner.tools.release_session = cleanup
    assert await retirement.retire('session-0')


@pytest.mark.asyncio
async def test_checkpoint_commit_failure_retains_obligation_and_retries(tmp_path):
    retirement, factory = refused(tmp_path)
    with factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_unopened BEFORE UPDATE OF local_retirement_json ON execution_sessions "
            "WHEN NEW.local_retirement_json IS NOT NULL BEGIN SELECT RAISE(ABORT,'checkpoint cut'); END")
    with pytest.raises(sqlite3.IntegrityError, match='checkpoint cut'):
        await retirement.retire('session-0')
    assert checkpoint(factory) is None
    with factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER fail_unopened')
    assert await retirement.retire('session-0')


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', [
    "UPDATE execution_dispatch_outbox SET last_error='{\"possible_effect\":true}'",
    "DELETE FROM execution_dispatch_outbox",
    "UPDATE execution_operations SET admission_state='ACCEPTED'",
])
async def test_changed_refusal_invalidates_checkpoint_transactionally(tmp_path, mutation):
    retirement, factory = refused(tmp_path)
    assert await retirement.retire('session-0')
    old = checkpoint(factory)
    with pytest.raises(RuntimeError, match='rollback'):
        with factory.unit_of_work() as uow:
            uow.connection.execute(mutation)
            assert uow.connection.execute('SELECT local_retirement_json FROM execution_sessions').fetchone()[0] is None
            raise RuntimeError('rollback')
    assert checkpoint(factory) == old
    with factory.unit_of_work() as uow:
        uow.connection.execute(mutation)
    assert checkpoint(factory) is None
    assert not await retirement.retire('session-0')


def test_changed_evidence_between_observation_and_commit_is_not_hidden(tmp_path):
    retirement, factory = refused(tmp_path)
    proof = retirement.snapshot('session-0')[0]
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_dispatch_outbox SET last_error="
            "'{\"stage\":\"dispatch\",\"possible_effect\":false,\"code\":\"DIFFERENT_REFUSAL\"}'")
    assert not retirement.commit('session-0', proof)
    assert checkpoint(factory) is None


def test_stale_owner_cannot_certify_non_admission(tmp_path):
    retirement, factory = refused(tmp_path)
    proof = retirement.snapshot('session-0')[0]
    def stale(**kwargs):
        raise CoreError('STALE_GENERATION', 'test')
    retirement.owner.verify = stale
    with pytest.raises(CoreError, match='STALE_GENERATION'):
        retirement.commit('session-0', proof)
    assert checkpoint(factory) is None


@pytest.mark.asyncio
async def test_occupied_slot_without_journal_prevents_retirement(tmp_path):
    retirement, factory = refused(tmp_path)
    host = retirement.owner.host
    try:
        ledger = await host._ledger()
        await ledger.reserve_owned_slot(OperationKey('server', 'executor', 'open-0'), 'session-0')
        with pytest.raises(CoreError, match='RECONCILIATION_REQUIRED'):
            await retirement.retire('session-0')
        assert checkpoint(factory) is None
        assert len((await ledger.owned_slot_page()).reservations) == 1
    finally:
        await host.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('resource', ['sidecar', 'missing_ledger', 'unknown_receipt'])
async def test_unverified_local_history_cannot_certify_non_admission(tmp_path, resource):
    retirement, factory = refused(tmp_path)
    host = retirement.owner.host
    host.store_dir.mkdir(parents=True)
    path = host._journal_path('executor', 'session-0')
    try:
        if resource == 'sidecar':
            path.with_name(path.name + '-wal').touch()
        else:
            journal = SQLiteJournal(path)
            try:
                if resource == 'unknown_receipt':
                    await journal.admit(OperationKey('server', 'executor', 'open-0'), 'unverified-intent', 'session-0')
            finally:
                await journal.aclose()
        with pytest.raises(CoreError):
            await retirement.retire('session-0')
        assert checkpoint(factory) is None
    finally:
        await host.shutdown()
