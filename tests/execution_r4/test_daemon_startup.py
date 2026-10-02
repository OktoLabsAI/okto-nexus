"""Real daemon startup from CLI registration, with HTTP/WSS and IPC.

The positive preview explicitly supplies synthetic Server qualification.
It qualifies automatic control startup, not providers or runtime effects.
"""

import asyncio
from contextlib import redirect_stdout
import io
import json
import socket

import pytest
import uvicorn
from nexus_connector_core import R4_PREVIEW_REVISION

from okto_nexus.adapters.inbound.http import connections_v1, executor_link
from test_binding_operator import onboarding


@pytest.mark.parametrize('qualified', [False, True])
def test_daemon_starts_registered_r4_control_without_legacy_fallback(onboarding, tmp_path, monkeypatch, qualified):
    from okto_nexus_connector.cli.main import main
    from okto_nexus_connector.daemon.app import DaemonApp
    from okto_nexus_connector.ipc.client import IPCClient
    from okto_nexus_connector.platform import paths
    from okto_nexus_connector.storage.state_store import StateStore

    deps, client, headers, _ = onboarding
    root = paths.state_dir(tmp_path / 'startup-connector')
    store = StateStore(paths.state_file(root))
    store.update(lambda state: state.preferences.update({'vault.fallback_file.approved': True}))
    monkeypatch.setenv('OKTO_NEXUS_CONNECTOR_VAULT', 'file')
    monkeypatch.setenv('OKTO_R4_LAB_REGISTRATION_KEY', headers['subject']['Authorization'].removeprefix('Bearer '))
    # A host without provider binaries still has an honest empty inventory.
    empty_path = tmp_path / 'empty-path'
    empty_path.mkdir()
    monkeypatch.setenv('PATH', str(empty_path))
    info = executor_link.protocol_info()
    assert info['remote_execution_ready'] and R4_PREVIEW_REVISION in info['nxl_accepted']
    if not qualified:
        # Explicit negative negotiation case; the installed product is now R4 ready.
        info = {**info, 'remote_execution_ready': False, 'nxl_accepted': []}
        monkeypatch.setattr(executor_link, 'protocol_info', lambda: info)
        monkeypatch.setattr(connections_v1, 'protocol_info', lambda: info)

    async def run():
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(client.app, lifespan='off', log_level='error'))
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        async def cli(*args):
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = await asyncio.to_thread(main,
                    ['--state-dir', str(root), '--json', '--non-interactive', *args])
            assert code == 0, stream.getvalue()
            return json.loads(stream.getvalue())
        daemon = running = None
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if serving.done(): await serving
                    await asyncio.sleep(0.01)
            await cli('identity', 'add', '--server', f'http://127.0.0.1:{port}', '--alias', 'startup-agent',
                '--agent', 'subject', '--credential-env', 'OKTO_R4_LAB_REGISTRATION_KEY')
            registered = await cli('executor', 'register', '--identity', 'startup-agent', '--label', 'Startup host')
            server_id, executor_id = registered['server_id'], registered['executor_id']
            last_generation = 0
            for boot in range(2 if qualified else 1):
                daemon = DaemonApp(root)
                running = asyncio.create_task(daemon.run_forever())
                def ipc(op):
                    with IPCClient(daemon.ipc.transport, daemon.ipc.address, daemon.lock.ensure_token()) as observer:
                        return observer.call(op)
                async with asyncio.timeout(10):
                    while True:
                        if running.done():
                            raise AssertionError(f'Daemon exited during startup: {await running}')
                        if daemon.ipc.address:
                            response = await asyncio.to_thread(ipc, 'status')
                            assert response['ok'], response
                            status = response['result']
                            control = status['r4_controls'].get(server_id)
                            if control and (control['control_ready'] if qualified else
                                            control['error_code'] == 'VERSION_INCOMPATIBLE'):
                                break
                        await asyncio.sleep(0.02)
                assert status['transports'] == {} and not control['execution_ready']
                assert control['executor_id'] == executor_id and control['publication_sequence'] >= boot + 1
                assert 'nxt4_' not in json.dumps(status)
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    executor = uow.connection.execute('SELECT control_state,generation FROM execution_executors '
                        'WHERE executor_id=?', (executor_id,)).fetchone()
                    inventory = uow.connection.execute('SELECT publication_sequence FROM execution_inventory_current '
                        'WHERE executor_id=?', (executor_id,)).fetchone()
                    assert inventory[0] == control['publication_sequence']
                    assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
                    assert uow.connection.execute('SELECT COUNT(*) FROM execution_control_lanes').fetchone()[0] == 0
                    if qualified:
                        assert executor['control_state'] == 'CONTROL_READY'
                        assert executor['generation'] > last_generation
                        last_generation = executor['generation']
                    else:
                        assert executor['control_state'] == 'DISCONNECTED'
                stopped = await asyncio.to_thread(ipc, 'shutdown')
                assert stopped['ok']
                assert await asyncio.wait_for(running, 10) == 0
                assert not daemon.r4_controls and not daemon.r4_executions
                running = None
            final = store.load().execution_executors[0]
            assert final.executor_id == executor_id and final.inventory_publication_sequence >= (2 if qualified else 1)
            assert 'nxt4_' not in store.path.read_text()
        finally:
            if running is not None:
                daemon.request_stop()
                await asyncio.wait_for(running, 35)
            server.should_exit = True
            await asyncio.wait_for(serving, 5)
            sock.close()
    asyncio.run(run())
