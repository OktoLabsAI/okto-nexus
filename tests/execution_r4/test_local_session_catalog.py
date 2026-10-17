"""Bounded metadata recovery, independently from native resource proofs."""
from contextlib import contextmanager
import asyncio
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError, OwnedSlotPage, OwnedSlotReservation, SessionKey

from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery
from okto_nexus.bootstrap.embedded_reconciliation import EmbeddedReconciliation
from okto_nexus.bootstrap.embedded_session_catalog import EmbeddedSessionCatalog
from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from test_local_recovery_lookup import history
from test_local_realization import local_setup
from test_embedded_dispatch import connected_local, admit, wait_receipt, qualified_contract


def catalog_fixture(tmp_path, count):
    reconciliation, factory, stats = history(tmp_path, count)
    owner = reconciliation.owner
    owner.factory = factory
    owner.host = EmbeddedRuntimeHost(tmp_path / 'store')
    owner.deps = SimpleNamespace(clock=SimpleNamespace(now_iso=lambda: '2026-10-17T00:00:00Z'))
    owner.channel.connection_generation = 2
    verify = owner.verify
    owner.verify = lambda *, uow=None: verify(uow=uow)
    return EmbeddedSessionCatalog(owner), factory, stats


def test_backfill_is_atomic_resumable_and_does_not_create_native_stores(tmp_path, monkeypatch):
    catalog, factory, _ = catalog_fixture(tmp_path, 300)
    def count():
        with factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT COUNT(*) FROM execution_sessions '
                'WHERE local_journal_name IS NOT NULL').fetchone()[0]
    original = catalog._name
    calls = []
    def fault(session_id):
        calls.append(session_id)
        if len(calls) == 10:
            raise OSError('interrupted catalog transaction')
        return original(session_id)
    monkeypatch.setattr(catalog, '_name', fault)
    with pytest.raises(OSError, match='interrupted catalog'):
        catalog.backfill_page()
    assert count() == 0
    monkeypatch.setattr(catalog, '_name', original)
    assert catalog.backfill_page() == 128 and count() == 128
    resumed = EmbeddedSessionCatalog(catalog.owner)
    assert resumed.backfill_page() == 128 and count() == 256
    assert resumed.backfill_page() == 44 and count() == 300
    assert resumed.backfill_page() == 0
    assert not catalog.owner.host.store_dir.exists()


def test_registration_requires_exact_canonical_session_and_current_owner(tmp_path):
    catalog, factory, _ = catalog_fixture(tmp_path, 2)
    catalog.register('session-0')
    catalog.register('session-0')
    catalog.verify_names({catalog._name('session-0')})
    with pytest.raises(CoreError, match='SCOPE_MISMATCH'):
        catalog.register('missing')
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET local_journal_name='wrong.db' "
            "WHERE session_id='session-0'")
    with pytest.raises(CoreError, match='SCOPE_MISMATCH'):
        catalog.register('session-0')
    def fenced(**kwargs):
        raise CoreError('STALE_GENERATION', 'test_owner')
    catalog.owner.verify = fenced
    with pytest.raises(CoreError, match='STALE_GENERATION'):
        catalog.register('session-1')
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT local_journal_name FROM execution_sessions "
            "WHERE session_id='session-1'").fetchone()[0] is None


def test_upgrade_preserves_existing_sessions_and_retirement_before_backfill(tmp_path):
    catalog, factory, _ = catalog_fixture(tmp_path, 3)
    with factory.unit_of_work() as uow:
        db = uow.connection
        db.execute("UPDATE execution_sessions SET local_retirement_json='{\"version\":1}'")
        db.execute('DROP TRIGGER execution_local_journal_identity_changed')
        db.execute('DROP INDEX idx_execution_sessions_local_journal')
        db.execute('DROP INDEX idx_execution_sessions_local_uncatalogued')
        db.execute('ALTER TABLE execution_sessions DROP COLUMN local_journal_name')
        db.execute('DELETE FROM schema_migrations WHERE version=145')
    MigrationRunner(factory).apply()
    MigrationRunner(factory).apply()
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions '
            'WHERE local_retirement_json IS NOT NULL AND local_journal_name IS NULL').fetchone()[0] == 3
        assert uow.connection.execute('SELECT COUNT(*) FROM schema_migrations WHERE version=145').fetchone()[0] == 1
    assert catalog.backfill_page() == 3
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions '
            'WHERE local_retirement_json IS NOT NULL AND local_journal_name IS NOT NULL').fetchone()[0] == 3


@pytest.mark.asyncio
async def test_directory_audit_is_bounded_and_rejects_unattributed_files_and_missing_ledger(tmp_path):
    catalog, _, _ = catalog_fixture(tmp_path, 300)
    await catalog.backfill()
    store = catalog.owner.host.store_dir
    store.mkdir()
    for index in range(300):
        (store / catalog._name(f'session-{index}')).touch()
    ledger = store / 'owned-slots.db'
    ledger.touch()
    (store / (catalog._name('session-0') + '-wal')).touch()
    original = catalog.verify_names
    sizes = []
    def measured(names):
        sizes.append(len(names))
        original(names)
    catalog.verify_names = measured
    assert await catalog.audit_files() is True
    assert len(sizes) == 3 and max(sizes) <= 128
    unknown = store / 'unattributed.db'
    unknown.touch()
    with pytest.raises(CoreError, match='JOURNAL_UNAVAILABLE'):
        await catalog.audit_files()
    unknown.unlink()
    ledger.unlink()
    with pytest.raises(CoreError, match='JOURNAL_UNAVAILABLE'):
        await catalog.audit_files()


@pytest.mark.asyncio
@pytest.mark.parametrize('count', [1_000, 10_000, 100_000])
async def test_catalog_lookup_and_startup_sql_cost_ignore_verified_history(tmp_path, count, record_property, monkeypatch):
    catalog, factory, stats = catalog_fixture(tmp_path, count)
    owner = catalog.owner
    # Synthetic completed metadata backfill, not native process evidence.
    with factory.unit_of_work() as uow:
        uow.connection.executemany('UPDATE execution_sessions SET local_journal_name=?, '
            "local_retirement_json=? WHERE server_id='server' AND executor_id='executor' AND session_id=?",
            ((catalog._name(f'session-{i}'), '{"version":1}' if i < count-3 else None,
              f'session-{i}') for i in range(count)))
    def instruction():
        stats['steps'] += 1
        return 0
    await owner.host._ledger()
    @contextmanager
    def measured_uow(*, write=True):
        with factory.unit_of_work(write=write) as uow:
            uow.connection.set_progress_handler(instruction, 1)
            try:
                yield uow
            finally:
                uow.connection.set_progress_handler(None, 0)
    owner.factory = SimpleNamespace(unit_of_work=measured_uow)
    catalog.verify_names({catalog._name('session-0'), catalog._name(f'session-{count-1}')})
    record_property('history_sessions', count)
    record_property('catalog_lookup_vm_steps', stats['steps'])
    assert stats['steps'] < 200
    def no_history_map(*args, **kwargs):
        pytest.fail('Startup must not load the historical session map')
    monkeypatch.setattr(EmbeddedReconciliation, '_records', no_history_map)
    recovery = EmbeddedAgentRecovery(owner)
    states = []
    recovery._state = lambda agent, state: states.append((agent, state))
    before = stats['steps']
    await recovery.initialize()
    record_property('startup_sql_vm_steps', stats['steps']-before)
    assert stats['steps']-before < 1000
    assert recovery.blocked == {'agent'} and states == [('agent', 'RECOVERING')]
    assert recovery.initialized
    # The valid physical ledger is constant-size; journal enumeration remains
    # a separate cost from the historical Server SQL lookup.
    assert (owner.host.store_dir / 'owned-slots.db').exists()
    await owner.host.shutdown()


@pytest.mark.asyncio
async def test_ledger_sidecar_without_ledger_is_not_an_empty_store(tmp_path):
    catalog, _, _ = catalog_fixture(tmp_path, 0)
    store = catalog.owner.host.store_dir
    store.mkdir()
    (store / 'owned-slots.db-wal').touch()
    with pytest.raises(CoreError, match='JOURNAL_UNAVAILABLE'):
        await catalog.audit_files()


@pytest.mark.asyncio
async def test_fresh_start_binds_ledger_before_admission_and_replacement_is_refused(tmp_path):
    catalog, factory, _ = catalog_fixture(tmp_path, 0)
    owner = catalog.owner
    first = owner.host
    try:
        await EmbeddedAgentRecovery(owner).initialize()
        with factory.unit_of_work(write=False) as uow:
            bound = uow.connection.execute('SELECT store_id FROM execution_embedded_store_bindings '
                'WHERE reset_generation=0').fetchone()[0]
        assert bound == await (await first._ledger()).physical_store_id()
        await first.shutdown()
        owner.host = EmbeddedRuntimeHost(tmp_path / 'replacement')
        with pytest.raises(CoreError, match='JOURNAL_UNAVAILABLE'):
            await EmbeddedAgentRecovery(owner).initialize()
        second = await owner.host._ledger()
        assert await second.physical_store_id() != bound
        with pytest.raises(CoreError, match='PROFILE_DRIFT'):
            await EmbeddedAgentRecovery(owner).initialize()
    finally:
        await first.shutdown()
        if owner.host is not first:
            await owner.host.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('session_id', ['session-1', 'unknown'])
async def test_occupied_slot_is_attributed_by_exact_lookup_not_history_map(tmp_path, monkeypatch, session_id):
    catalog, factory, _ = catalog_fixture(tmp_path, 300)
    owner = catalog.owner
    owner.host.store_dir.mkdir()
    (owner.host.store_dir / 'owned-slots.db').touch()
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET local_retirement_json='{\"version\":1}'")
    async def holds(*args, **kwargs):
        return 0
    async def page(**kwargs):
        return OwnedSlotPage((OwnedSlotReservation(SessionKey('server', 'executor', session_id), 'provisional'),), 1, None)
    async def opening(slot):
        return 'open-1'
    async def physical_store_id():
        return 'store_' + 'a' * 32
    async def ledger():
        return SimpleNamespace(release_fenced_capacity_holds=holds, owned_slot_page=page,
            capacity_opening_for_slot=opening, physical_store_id=physical_store_id)
    owner.host._ledger = ledger
    original, lookups = EmbeddedReconciliation._records, []
    def exact(self, agent_id=None, *, session_id=None, **kwargs):
        assert session_id is not None
        lookups.append(session_id)
        return original(self, agent_id, session_id=session_id, **kwargs)
    monkeypatch.setattr(EmbeddedReconciliation, '_records', exact)
    recovery = EmbeddedAgentRecovery(owner)
    recovery._state = lambda *args: None
    if session_id == 'unknown':
        with pytest.raises(CoreError, match='SCOPE_MISMATCH'):
            await recovery.initialize()
        assert not recovery.initialized
    else:
        await recovery.initialize()
        assert recovery.blocked == {'agent'}
        with factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT local_retirement_json FROM execution_sessions "
                "WHERE session_id='session-1'").fetchone()[0] is None
    assert lookups == [session_id]


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'codex_app_server', 'claude_stream'], indirect=True)
def test_real_composition_registers_canonical_location_before_journal_creation(local_setup, monkeypatch):
    setup, binding, _ = connected_local.__wrapped__(local_setup)
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    from okto_nexus.bootstrap import runtime_host
    original, observed = runtime_host.open_journal, []
    async def inspect(path, *args, **kwargs):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT session_id FROM execution_sessions '
                'WHERE local_journal_name=?', (path.name,)).fetchone()
            assert row is not None, 'Journal creation preceded durable canonical registration'
            observed.append(row[0])
        return await original(path, *args, **kwargs)
    monkeypatch.setattr(runtime_host, 'open_journal', inspect)
    opened = admit(setup, binding, 'catalog-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    assert observed == [opened['scope']['session_id']]
    closed = admit(setup, binding, 'catalog-close', 'runtime.close', session_id=opened['scope']['session_id'])
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    original_scan = os.scandir
    def no_agent_directory_scan(path):
        if isinstance(path, (str, os.PathLike)) and Path(path) == owner.host.store_dir:
            pytest.fail('Agent recovery enumerated the entire shared directory')
        return original_scan(path)
    monkeypatch.setattr(os, 'scandir', no_agent_directory_scan)
    async def recover():
        await owner.agents.fail('subject', OSError('Test scoped recovery after close'))
        await owner.retry_recovery('subject')
        deadline = time.monotonic() + 20
        while 'subject' in owner.agents.blocked:
            assert time.monotonic() < deadline, repr(owner.agents.errors)
            await asyncio.sleep(.02)
    client.portal.call(recover)
    assert 'subject' not in owner.agents.blocked
