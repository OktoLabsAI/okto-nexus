"""Installed-compatible Connector CLI registration against a real HTTP Server."""

import asyncio
from contextlib import redirect_stdout
import io
import json
import socket

import uvicorn

from test_binding_operator import onboarding


def test_cli_registers_and_reuses_executor_without_storing_bootstrap_secret(onboarding, tmp_path, monkeypatch):
    from okto_nexus_connector.cli.main import main
    from okto_nexus_connector.identity.vault import open_vault
    from okto_nexus_connector.platform import paths
    from okto_nexus_connector.services.executor_registration import ExecutorRegistrationService
    from okto_nexus_connector.storage.state_store import StateStore

    deps, client, headers, _ = onboarding
    root = paths.state_dir(tmp_path / 'registration-connector')
    store = StateStore(paths.state_file(root))
    store.update(lambda state: state.preferences.update({'vault.fallback_file.approved': True}))
    monkeypatch.setenv('OKTO_NEXUS_CONNECTOR_VAULT', 'file')
    key = headers['subject']['Authorization'].removeprefix('Bearer ')
    monkeypatch.setenv('OKTO_R4_LAB_REGISTRATION_KEY', key)

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
            raw = stream.getvalue()
            assert code == 0, raw
            assert key not in raw and 'nxt4_' not in raw
            return json.loads(raw)
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if serving.done(): await serving
                    await asyncio.sleep(0.01)
            imported = await cli('identity', 'add', '--server', f'http://127.0.0.1:{port}',
                '--alias', 'registration-agent', '--agent', 'subject',
                '--credential-env', 'OKTO_R4_LAB_REGISTRATION_KEY')
            first = await cli('executor', 'register', '--identity', 'registration-agent', '--label', 'Test host')
            again = await cli('executor', 'register', '--identity', 'registration-agent', '--label', 'Test host')
            assert first == again
            assert first['server_id'] == imported['server_id'] and first['state'] == 'REGISTERED'
            assert (await cli('executor', 'show', first['server_id'])) == first
            assert (await cli('executor', 'list')) == {'executors': [first]}
            state = store.load()
            assert len(state.execution_executors) == 1
            assert state.servers[first['server_id']].base_url == f'http://127.0.0.1:{port}'
            vault = open_vault(paths.vault_dir(root), approved_fallback=True)
            bootstrap = await ExecutorRegistrationService(StateStore(store.path), vault).bootstrap(
                server_id=first['server_id'])
            assert bootstrap.executor.executor_id == first['executor_id']
            assert bootstrap.ticket.startswith('nxt4_') and bootstrap.deadline_monotonic > 0
            assert bootstrap.ticket not in store.path.read_text() and key not in store.path.read_text()
            with deps.connection_factory.unit_of_work(write=False) as uow:
                rows = uow.connection.execute('SELECT executor_id,control_state FROM execution_executors '
                    'WHERE connector_id=?', (state.connector_id,)).fetchall()
                assert [tuple(row) for row in rows] == [(first['executor_id'], 'DISCONNECTED')]
                count = uow.connection.execute('SELECT COUNT(*) FROM execution_client_intents '
                    'WHERE actor_agent_id=? AND client_intent_id=?',
                    ('subject', first['client_intent_id'])).fetchone()[0]
                assert count == 1
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 5)
            sock.close()
    asyncio.run(run())
