"""SVC-T23/T24: real Server process replacement, synthetic remote native peer.

The Connector stays alive, but its previous work and native session are already
closed. This does not claim that a native session survives Server failure. All
credentials, journals and processes are disposable; no provider or OS service is
used. The child selects the same product imports as the qualification runner.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import site
import socket
import subprocess
import sys
import time

import httpx
import pytest


LAUNCHER = """
import sys
from types import SimpleNamespace
# dependency_paths
# product_paths
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.adapters.inbound.cli.serve import run_serve
embedded_inventory.discover_local_candidates = lambda **_: SimpleNamespace(candidates=())
if sys.argv[1] == 'service':
    from okto_nexus.adapters.inbound.cli.service import run_service
    raise SystemExit(run_service(sys.argv[2:]))
raise SystemExit(run_serve(sys.argv[1:]))
"""


class RestartServer:
    """Own only the child launched here; never signal the runner's console."""

    def __init__(self, root):
        import okto_nexus
        import nexus_connector_core
        from okto_nexus.bootstrap.dependencies import bootstrap

        self.root = root
        self.home = root / 'server-home'
        self.deps = bootstrap({}, ['--home', str(self.home),
            '--feature-harness-integrations', 'true', '--feature-hitl', 'true',
            '--embedding-mode', 'off'])
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.origin = f'http://127.0.0.1:{self.port}'
        self.client = httpx.Client(base_url=self.origin, trust_env=False, timeout=10)
        dependencies = site.getsitepackages() + [site.getusersitepackages()]
        products = [str(Path(module.__file__).resolve().parent.parent)
                    for module in (okto_nexus, nexus_connector_core)]
        self.launcher = root / 'restart-server.py'
        self.launcher.write_text(LAUNCHER.replace('# dependency_paths',
            f'sys.path.extend({dependencies!r})').replace('# product_paths',
            f'sys.path[:0] = {products!r}'), encoding='utf-8')
        isolated = root / 'child-profile'
        isolated.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP'}}
        self.env.update(PATH=str(Path(os.environ.get('SYSTEMROOT', 'C:/Windows')) / 'System32'),
            HOME=str(isolated), USERPROFILE=str(isolated), APPDATA=str(isolated),
            LOCALAPPDATA=str(isolated), PYTHONIOENCODING='utf-8', OKTO_NEXUS_NO_BANNER='1')
        self.children = []
        self.logs = []

    def start(self):
        log = (self.root / f'server-{len(self.children) + 1}.log').open('w', encoding='utf-8')
        self.logs.append(log)
        process = subprocess.Popen([sys.executable, '-I', str(self.launcher),
            '--home', str(self.home), '--host', '127.0.0.1', '--port', str(self.port),
            '--project-root', str(self.root), '--harness-root', str(self.root),
            '--feature-harness-integrations', 'true', '--feature-hitl', 'true',
            '--embedding-mode', 'off'], cwd=self.root, env=self.env,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.children.append(process)
        deadline = time.monotonic() + 30
        while True:
            assert process.poll() is None, 'Disposable Server exited; inspect private server log'
            try:
                if self.client.get('/healthz').status_code == 200:
                    return process.pid
            except httpx.HTTPError:
                pass
            assert time.monotonic() < deadline, 'Disposable Server did not become ready'
            time.sleep(.05)

    def crash_and_wait_for_owner_expiry(self):
        process = self.children[-1]
        assert process.poll() is None
        process.kill()
        assert process.wait(timeout=10) != 0
        # Like NS14-01, respect the old durable dispatcher lease. Do not delete
        # or fast-forward authority records to make replacement succeed.
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT lease_expires_at FROM runtime_dispatcher_owner '
                "WHERE owner_key='dispatcher'").fetchone()
        if row is not None:
            remaining = (datetime.fromisoformat(row[0].replace('Z', '+00:00'))
                         - datetime.now(timezone.utc)).total_seconds()
            assert remaining <= 45
            if remaining > 0:
                time.sleep(remaining + .1)

    def cleanup(self):
        for process in self.children:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        for log in self.logs:
            log.close()
        self.client.close()
        self.deps.connection_factory.close()

    def stop(self):
        result = subprocess.run([sys.executable, '-I', str(self.launcher), 'service',
            'stop', '--home', str(self.home), '--host', '127.0.0.1', '--port', str(self.port),
            '--json', '--timeout', '40'],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=50)
        assert result.returncode == 0, 'Canonical stop failed; owned child will be cleaned up'
        assert json.loads(result.stdout)['shutdown_outcome'] == 'drained'
        assert self.children[-1].wait(timeout=10) == 0


def stable_facts(project):
    """Compare authority and limits, excluding ordinary transport/audit clocks."""
    agents = project.rows('agents')
    subject = next(row for row in agents if row['agent_id'] == project.agent_id)
    return {
        'installation': project.rows('execution_installation'),
        'subject': {key: value for key, value in subject.items()
                    if key not in {'last_seen_at', 'updated_at'}},
        'workspaces': project.rows('workspaces'),
        'bindings': project.rows('execution_bindings'),
        'workspace_bindings': project.rows('execution_workspace_bindings'),
        'profiles': project.rows('runtime_profiles'),
        'grants': project.rows('runtime_execution_grants'),
        'finish': project.rows('connection_setup_commits'),
        'executor_ids': sorted((row['server_id'], row['executor_id'], row['kind'])
                               for row in project.rows('execution_executors')),
    }


@pytest.mark.parametrize('grant_state', ['expired', 'revoked', 'valid'])
def test_server_restart_preserves_remote_binding_limits_and_invalid_grant(tmp_path, monkeypatch, grant_state):
    from remote_renewal_helpers import RemoteProject
    from okto_nexus.application.terminal_connection import ConnectionError, PREFIX

    server = RestartServer(tmp_path)
    project = None

    async def scenario():
        nonlocal project
        old_pid = await asyncio.to_thread(server.start)
        project = RemoteProject((server.deps, server.client), tmp_path, monkeypatch, actions=3)
        await project.start()
        completed = await project.send_and_complete(request_id='completed-before-server-restart')
        await project.close_session(completed['scope']['session_id'])
        await project.eventually(lambda: project.control.status()['execution_ready'])
        original_generation = project.control.connection.state.connection_generation
        original_daemon_task = project.daemon_task
        original_binding = deepcopy(project.binding)
        original_state = project.store.load()
        old_grant, = project.rows('runtime_execution_grants')
        assert old_grant['max_executions'] == 3 and old_grant['used_executions'] == 1
        if grant_state == 'revoked':
            await asyncio.to_thread(project.call, 'DELETE', '/api/v1/harness/grants/' + old_grant['grant_id'])
        elif grant_state == 'expired':
            # Honest temporal fixture: expire only this grant, without extending
            # any ticket, lease, timeout or changing the Server clock.
            with server.deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute('UPDATE runtime_execution_grants SET expires_at=? WHERE grant_id=?',
                    ('2000-01-01T00:00:00Z', old_grant['grant_id']))
        before = stable_facts(project)
        permissions = json.loads(before['subject']['permissions'])
        assert permissions['limits']['messages_per_minute'] == 60
        assert permissions['limits']['max_recipients'] == 10
        operations = deepcopy(project.rows('execution_operations'))
        receipts = deepcopy(project.rows('execution_receipts'))
        native, _, _ = project.native.opened[completed['scope']['session_id']]
        assert native.stopped and len(native.sent) == 1

        await asyncio.to_thread(server.crash_and_wait_for_owner_expiry)
        assert project.daemon_task is original_daemon_task and not project.daemon_task.done()
        new_pid = await asyncio.to_thread(server.start)
        assert new_pid != old_pid
        # Production reconnect backs off up to 30s plus 20% jitter. This is an
        # observation deadline only: do not shorten retries or extend authority.
        await project.eventually(lambda: project.control.status()['execution_ready'] and
            project.control.connection.state.connection_generation > original_generation, timeout=90)
        await project.inventory_ready()
        assert stable_facts(project) == before
        current = project.store.load()
        assert current.connector_id == original_state.connector_id
        assert [(row.server_id, row.executor_id) for row in current.execution_executors] == [
            (row.server_id, row.executor_id) for row in original_state.execution_executors]
        assert project.binding == original_binding
        assert current.bindings == original_state.bindings
        mapping = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'endpoint_id',
                   'workspace_id', 'workspace_binding_id', 'realization_ref', 'binding_revision')
        assert [tuple(getattr(row, key) for key in mapping) for row in current.execution_bindings] == [
            tuple(getattr(row, key) for key in mapping) for row in original_state.execution_bindings]
        assert project.rows('execution_operations') == operations
        assert project.rows('execution_receipts') == receipts
        assert len(project.native.opened) == 1 and len(native.sent) == 1
        assert len(project.probes) == 1
        # A completed result stays historical. Returning transport connectivity
        # must not rerun the old task or regain the revoked/expired authority.
        observed = await project.operation(completed['submission_turn_operation_id'])
        assert observed['operation_id'] == completed['submission_turn_operation_id']
        if grant_state == 'valid':
            # Positive control: this same returned transport/authority can admit
            # new explicit work. Only that new work spends the next grant unit.
            second = await project.send_and_complete(request_id='explicit-after-server-restart')
            assert second['operation_id'] != completed['operation_id']
            assert second['scope']['session_id'] != completed['scope']['session_id']
            assert second['scope']['executor_id'] == completed['scope']['executor_id']
            assert second['scope']['binding_id'] == completed['scope']['binding_id']
            assert len(project.native.opened) == 2
            assert all(len(peer.sent) == 1 for peer, _, _ in project.native.opened.values())
            expected = deepcopy(before)
            expected['grants'][0]['used_executions'] = 2
            assert stable_facts(project) == expected
            original_ids = {row['operation_id'] for row in operations}
            assert [row for row in project.rows('execution_operations')
                    if row['operation_id'] in original_ids] == operations
            assert [row for row in project.rows('execution_receipts')
                    if row['operation_id'] in original_ids] == receipts
            await project.close_session(second['scope']['session_id'])
            project.assert_redacted()
            await project.close()
            await asyncio.to_thread(server.stop)
            return
        review = await asyncio.to_thread(project.work().authorization_review)
        assert review['current_grants'][0]['state'] == grant_state
        try:
            denied = await asyncio.to_thread(project.work().submit, 'Forbidden after restart',
                new_session=True, client_intent_id='denied-after-server-restart')
        except ConnectionError as error:
            assert error.code == 'PERMISSION_DENIED'
            assert not error.possible_effect
        else:
            # Canonical intent admission precedes the fresh dispatch guard. A
            # PENDING record is not a native admission or a renewed grant.
            assert 'operation_id' in denied, denied
            deadline = time.monotonic() + 25
            while True:
                refusal = await asyncio.to_thread(project.call, 'GET',
                    PREFIX + '/runtime/operations/' + denied['operation_id'])
                if refusal['error'] is not None:
                    break
                assert time.monotonic() < deadline, refusal
                await asyncio.sleep(.05)
            assert refusal['error']['code'] == 'PERMISSION_DENIED', refusal
            # RuntimeAccess intentionally sanitizes its message. The typed
            # authorization review above and unchanged authority snapshot prove
            # expired/revoked grant status; do not infer it from free text.
            assert refusal['error']['stage'] == 'dispatch', refusal
            assert refusal['possible_effect'] is False
            assert refusal['executor_stage'] is None
        original_ids = {row['operation_id'] for row in operations}
        assert [row for row in project.rows('execution_operations')
                if row['operation_id'] in original_ids] == operations
        assert len(project.native.opened) == 1 and len(native.sent) == 1
        assert stable_facts(project) == before
        project.assert_redacted()
        await project.close()
        await asyncio.to_thread(server.stop)

    async def run():
        try:
            await scenario()
        finally:
            if project is not None and project.daemon_task is not None and not project.daemon_task.done():
                await project.close()

    try:
        asyncio.run(run())
    finally:
        server.cleanup()
