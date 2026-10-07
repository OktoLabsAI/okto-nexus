"""Resetting history preserves configured connections and their authority."""
import pytest
import time

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send


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
        'execution_local_realizations', 'execution_installation', 'runtime_policy_defaults', 'workspaces')
    # Seed unrelated history without starting a native turn.
    with deps.connection_factory.unit_of_work() as uow:
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
    wait_receipt(setup, turn)
    assert native.opens == (2 if active else 1) and len(native.native.sent) == 1
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
