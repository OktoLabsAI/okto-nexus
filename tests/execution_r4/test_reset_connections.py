"""Resetting history preserves configured connections and their authority."""
import pytest
import time

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send


def test_reset_remote_close_uses_authenticated_dashboard_operator(monkeypatch):
    import asyncio
    import sqlite3
    from contextlib import contextmanager
    from types import SimpleNamespace
    from okto_nexus.bootstrap import database_reset
    from okto_nexus.domain.runtime_context import RuntimeRequestContext

    db = sqlite3.connect(':memory:', check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE execution_sessions (server_id TEXT, executor_id TEXT,
            binding_id TEXT, workspace_binding_id TEXT, session_id TEXT, lifecycle_state TEXT,
            lease_state TEXT);
        CREATE TABLE execution_executors (server_id TEXT, executor_id TEXT, kind TEXT);
        CREATE TABLE execution_bindings (server_id TEXT, executor_id TEXT,
            binding_id TEXT, endpoint_id TEXT);
        CREATE TABLE agent_endpoints (endpoint_id TEXT, agent_id TEXT);
        INSERT INTO execution_executors VALUES ('srv', 'exe', 'remote');
        INSERT INTO execution_bindings VALUES ('srv', 'exe', 'bind', 'ep');
        INSERT INTO agent_endpoints VALUES ('ep', 'remote-agent');
        INSERT INTO execution_sessions VALUES ('srv', 'exe', 'bind', 'wxb', 'ses', 'READY', 'ACTIVE');
    ''')

    @contextmanager
    def unit_of_work(*, write=False):
        yield SimpleNamespace(connection=db)

    factory = SimpleNamespace(unit_of_work=unit_of_work)
    app = SimpleNamespace(state=SimpleNamespace(deps=SimpleNamespace(connection_factory=factory),
        inventory_fresh_publications=None))
    from okto_nexus.bootstrap import execution_authority
    from okto_nexus.application import execution_intents, execution_admission
    monkeypatch.setattr(execution_authority, 'build_execution_access', lambda deps: object())
    observed = []

    def resolve(factory, *, context, request, **kwargs):
        observed.append((context.actor_agent_id, context.authentication_source,
            context.trusted_local_operator, request['intent']))
        return dict(can_submit=True, client_intent_id=request['client_intent_id'],
            operation_id='close-op', resolution_revision=1, intent_hash='hash')

    def submit(factory, *, context, request, **kwargs):
        db.execute("UPDATE execution_sessions SET lifecycle_state='CLOSED' WHERE session_id='ses'")

    monkeypatch.setattr(execution_intents, 'resolve_execution_intent', resolve)
    monkeypatch.setattr(execution_admission, 'submit_execution_operation', submit)
    context = RuntimeRequestContext(None, 'operator_session', trusted_local_operator=True)
    asyncio.run(database_reset._close_remote_sessions(app, context))
    assert observed == [('operator', 'operator_session', True, 'runtime.close')]


@pytest.mark.parametrize('active', [False, True])
def test_reset_preserves_configured_local_connection_and_can_deliver_again(connected_local, monkeypatch, active):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    old_native = None
    if active:
        assert send(setup, monkeypatch)['ok']
        with deps.connection_factory.unit_of_work(write=False) as uow:
            old_turn = dict(uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        wait_receipt(setup, old_turn)
        old_native = native.native
    tables = ('agents', 'agent_endpoints', 'runtime_profiles', 'runtime_execution_grants',
        'execution_bindings', 'execution_workspace_bindings', 'execution_realizations',
        'execution_local_realizations', 'execution_installation', 'runtime_policy_defaults', 'workspaces',
        'one_shot_policy_settings', 'one_shot_host_limits', 'runtime_mcp_presets',
        'execution_embedded_store_bindings')
    # Seed unrelated history without starting a native turn.
    with deps.connection_factory.unit_of_work() as uow:
        from okto_nexus.application import one_shot_settings, runtime_mcp_presets
        defaults = one_shot_settings.read(uow.connection)['settings']
        one_shot_settings.save(uow.connection, expected_revision=1,
            settings=defaults | dict(max_parallel=10, warm_instances=5))
        agent_id = uow.connection.execute('SELECT agent_id FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone()[0]
        one_shot_settings.save(uow.connection, agent_id=agent_id, expected_revision=0,
            settings={'max_parallel': 8})
        uow.connection.execute('INSERT INTO one_shot_host_limits VALUES(?,?)', (binding['executor_id'], 20))
        runtime_mcp_presets.save(uow.connection, endpoint_id=binding['endpoint_id'], expected_revision=0,
            servers=[dict(name='example', transport='stdio', command='example-mcp', enabled=False)])
        workspace = uow.connection.execute('SELECT workspace_id FROM agent_endpoints WHERE endpoint_id=?', (binding['endpoint_id'],)).fetchone()[0]
        deps.repos.messages.create(uow, message_id='before-reset', workspace_id=workspace,
            from_agent_id='operator', body='History to remove', created_at=deps.clock.now_iso())
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)] for table in tables}
    response = client.post('/api/v1/admin/reset?keep_agents=true', headers=headers['operator'])
    assert response.status_code in (200, 202), response.text
    deadline = time.monotonic() + 30
    while response.json()['data'].get('pending') and time.monotonic() < deadline:
        time.sleep(.1)
        response = client.get('/api/v1/admin/reset', headers=headers['operator'])
        assert response.status_code in (200, 202), response.text
    assert response.status_code == 200, response.text
    assert not response.json()['data'].get('pending'), response.text
    if active:
        assert old_native.stopped
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in tables:
            if table == 'agents':
                # Authentication updates presence, never keys or identity.
                names = [r[1] for r in uow.connection.execute('PRAGMA table_info(agents)')]
                ignored = names.index('last_seen_at')
                trim = lambda rows: [r[:ignored] + r[ignored+1:] for r in rows]
                assert trim([tuple(r) for r in uow.connection.execute('SELECT * FROM agents')]) == trim(before[table])
            elif table == 'execution_embedded_store_bindings':
                rows = [tuple(r) for r in uow.connection.execute(
                    'SELECT * FROM execution_embedded_store_bindings ORDER BY reset_generation')]
                assert rows[:-1] == before[table]
                assert len(rows) == len(before[table]) + 1
                assert rows[-1][0] == 1 and rows[-1][1] != rows[0][1]
            else:
                assert [tuple(r) for r in uow.connection.execute('SELECT * FROM ' + table)] == before[table], table
        assert uow.connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM message_deliveries').fetchone()[0] == 0
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
    enable(setup, binding)
    delivered = send(setup, monkeypatch)
    assert delivered['ok'], delivered
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        stores = uow.connection.execute('SELECT reset_generation,store_id FROM '
            'execution_embedded_store_bindings ORDER BY reset_generation').fetchall()
        assert len(stores) == 2 and [row[0] for row in stores] == [0, 1]
        assert stores[0][1] != stores[1][1]
    wait_receipt(setup, turn)
    assert native.opens == (2 if active else 1) and len(native.native.sent) == 1
    # Reset must restore the immutable-history fence before admitting work.
    import sqlite3
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_delivery_attempt_events').fetchone()[0] > 0
        with pytest.raises(sqlite3.IntegrityError, match='runtime_attempt_history_is_immutable'):
            uow.connection.execute('DELETE FROM runtime_delivery_attempt_events')
    wait_receipt(setup, admit(setup, binding, 'reset-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))


def test_reset_retains_history_until_native_stops(connected_local, monkeypatch):
    import threading
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'pending-reset-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    release = threading.Event()
    close = native.native.close
    async def held_close():
        if not release.is_set():
            return 'unknown'
        return await close()
    monkeypatch.setattr(native.native, 'close', held_close)
    try:
        response = client.post('/api/v1/admin/reset', headers=headers['operator'])
        assert response.status_code == 202, response.text
        task = app.state.database_reset_task
        repeated = client.post('/api/v1/admin/reset', headers=headers['operator'])
        assert repeated.status_code == 202
        assert app.state.database_reset_task is task
        assert client.post('/api/v1/admin/reset?keep_agents=false', headers=headers['operator']).status_code == 409
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] > 0
        assert deps.runtime_admission_fence.closed
    finally:
        release.set()
        deadline = time.monotonic() + 30
        while not app.state.database_reset_task.done():
            assert time.monotonic() < deadline
            time.sleep(.05)
    assert client.get('/api/v1/admin/reset', headers=headers['operator']).status_code == 200
    assert not deps.runtime_admission_fence.closed
    assert native.native.stopped


def test_reset_preserves_installation_observation_without_reprobing(connected_local, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    from okto_nexus.bootstrap import embedded_inventory
    from okto_nexus.application import execution_local_observations as observations

    setup, _, _ = connected_local
    deps, app, client, _, _, candidate, _ = setup
    raw = replace(candidate, trust='untrusted')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=tuple(c for c in (raw,) if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    calls = []
    async def probe(selected):
        calls.append(selected)
        return replace(selected, version='0.999.0')
    monkeypatch.setattr(observations, 'probe_version', probe)
    client.portal.call(app.state.embedded_inventory_owner.refresh)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = [tuple(r) for r in uow.connection.execute('SELECT * FROM execution_local_observations')]
    assert len(before) == 1 and len(calls) == 1
    test_reset_preserves_configured_local_connection_and_can_deliver_again(connected_local, monkeypatch, False)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert [tuple(r) for r in uow.connection.execute('SELECT * FROM execution_local_observations')] == before
    assert len(calls) == 1


def test_failed_drain_keeps_history_and_resumes_admission(connected_local, monkeypatch):
    from okto_nexus.bootstrap import database_reset
    from okto_nexus.errors import ErrorCode, OktoNexusError
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'failed-reset-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    async def unavailable(*args):
        raise OktoNexusError(ErrorCode.CONFLICT, 'Remote stop could not be confirmed.', {})
    monkeypatch.setattr(database_reset, '_close_remote_sessions', unavailable)
    response = client.post('/api/v1/admin/reset', headers=headers['operator'])
    assert response.status_code == 409
    assert not deps.runtime_admission_fence.closed
    assert not deps.runtime_dispatcher._quiescing.is_set()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] > 0
        assert uow.connection.execute('SELECT generation FROM runtime_reset_generation').fetchone()[0] == 0
    wait_receipt(setup, admit(setup, binding, 'failed-reset-close', 'runtime.close', session_id=opened['session_id']), stages=('SUCCEEDED',))


def test_reset_generation_survives_backup_and_cold_start(tmp_path, monkeypatch, request):
    from contextlib import contextmanager
    from test_canonical_backup_artifacts import procedure
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.inbound.http.app import build_app
    from fastapi.testclient import TestClient
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, request) as setup:
        connected = connected_local.__wrapped__(setup)
        test_reset_preserves_configured_local_connection_and_can_deliver_again(connected, monkeypatch, True)
        home = setup[0].config.home_dir
    snapshot = tmp_path / 'reset-snapshot'
    report = procedure.backup(home, snapshot, stopped=True)
    assert any(name.startswith('core-runtime-reset-1/session-') for name in report['files'])
    restored = procedure.restore(snapshot, tmp_path / 'restored-reset', stopped=True)
    deps = bootstrap({}, ['--home', str(restored), '--feature-harness-integrations', 'true'])
    with TestClient(build_app(deps)) as client:
        assert client.get('/healthz').status_code == 200
        assert client.app.state.embedded_core_host.store_dir.name == 'core-runtime-reset-1'
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0] == 'CONTROL_READY'


@pytest.mark.parametrize('keep_agents', [False, True])
def test_failed_history_reset_rolls_back_data_and_immutability_fence(connected_local, monkeypatch, keep_agents):
    import sqlite3
    from okto_nexus.application import database_reset

    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    assert send(setup, monkeypatch)['ok']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
    wait_receipt(setup, turn)
    wait_receipt(setup, admit(setup, binding, 'rollback-close', 'runtime.close', session_id=turn['session_id']))
    # Closing unfinished work also publishes an asynchronous caller notice.
    # Include that committed message in the baseline instead of racing it;
    # rollback must preserve the complete message rows, including the notice.
    from test_embedded_owner_replacement import wait_until
    def notice_published():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute(
                "SELECT 1 FROM execution_release_notifications n "
                "JOIN execution_delivery_releases r USING(domain_operation_id) "
                "WHERE r.operation_id=? AND n.state='PUBLISHED'",
                (turn['operation_id'],)).fetchone()
    wait_until(notice_published)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)]
            for table in ('messages', 'runtime_delivery_attempt_events', 'execution_bindings')}
        assert before['runtime_delivery_attempt_events']
    clear = database_reset.clear_operational_history
    def fail_after_clear(conn, **kwargs):
        # Draining may append terminal attempt observations before deletion.
        before['runtime_delivery_attempt_events'] = [tuple(row) for row in conn.execute(
            'SELECT * FROM runtime_delivery_attempt_events ORDER BY sequence')]
        clear(conn, **kwargs)
        assert conn.execute('SELECT COUNT(*) FROM runtime_delivery_attempt_events').fetchone()[0] == 0
        raise sqlite3.OperationalError('injected failure before reset commit')
    monkeypatch.setattr(database_reset, 'clear_operational_history', fail_after_clear)
    response = client.post('/api/v1/admin/reset', params={'keep_agents': str(keep_agents).lower()}, headers=headers['operator'])
    deadline = time.monotonic() + 30
    while response.status_code in (200, 202) and response.json()['data'].get('pending') and time.monotonic() < deadline:
        time.sleep(.1)
        response = client.get('/api/v1/admin/reset', headers=headers['operator'])
    assert response.status_code == 503, response.text
    assert not deps.runtime_admission_fence.closed
    with deps.connection_factory.unit_of_work() as uow:
        for table, rows in before.items():
            restored = [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)]
            if table == 'runtime_delivery_attempt_events':
                assert set(rows) <= set(restored)
            else:
                assert restored == rows
        assert uow.connection.execute('SELECT generation FROM runtime_reset_generation').fetchone()[0] == 0
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
        with pytest.raises(sqlite3.IntegrityError, match='runtime_attempt_history_is_immutable'):
            uow.connection.execute('DELETE FROM runtime_delivery_attempt_events')
