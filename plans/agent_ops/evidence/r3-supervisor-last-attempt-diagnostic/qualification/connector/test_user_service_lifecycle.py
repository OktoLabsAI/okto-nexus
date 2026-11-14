"""Injected OS mutations and disposable instance state; no personal task writes."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import os
import threading
import time
from unittest.mock import Mock

import pytest
from nexus_connector_core.user_service_definition import windows_with_enabled

from okto_nexus_connector.cli.main import main
from okto_nexus_connector.daemon import manager
from okto_nexus_connector.daemon.lock import InstanceLock
from okto_nexus_connector.daemon.lock import _atomic_write
from okto_nexus_connector.daemon.service_process import run
from okto_nexus_connector.errors import ConnectorError
from okto_nexus_connector.platform import service_install
from okto_nexus_connector.platform.service_context import (
    CONTEXT, INSTALLATION, LAUNCH, execution_context, launch_exclusion,
    launch_environment, read_document, validate_context, write_document)
from okto_nexus_connector.platform.user_service import UserService, SUPERVISOR
from okto_nexus_connector.platform.windows_tasks import TaskObservation


class FakeTasks:
    def __init__(self):
        self.tasks, self.calls = {}, []

    def read(self, name):
        return self.tasks.get(name)

    def validate(self, name, xml):
        pass

    def create(self, name, xml):
        assert name not in self.tasks
        self.calls.append(('create', name))
        self.tasks[name] = TaskObservation(xml, 3, True, 0)
        return self.tasks[name]

    def start(self, name, expected):
        assert self.tasks[name].digest == expected
        self.calls.append(('start', name))
        self.tasks[name] = replace(self.tasks[name], state=2)

    def delete(self, name, expected):
        assert self.tasks[name].digest == expected and not self.tasks[name].active
        self.calls.append(('delete', name))
        del self.tasks[name]

    def set_enabled(self, name, expected, enabled):
        assert self.tasks[name].digest == expected
        self.calls.append(('enabled', name, enabled))
        self.tasks[name] = replace(self.tasks[name], enabled=enabled,
            xml=windows_with_enabled(self.tasks[name].xml, enabled))
        return self.tasks[name]


@pytest.fixture
def selected(tmp_path, monkeypatch):
    if os.name != 'nt':
        pytest.skip('Windows user-task host paths/principal')
    root = tmp_path / 'connector'
    tasks = FakeTasks()
    monkeypatch.setattr('okto_nexus_connector.platform.user_service.WindowsTasks', lambda: tasks)
    return root, tasks, UserService(root, tasks=tasks)


def installed(selected):
    root, tasks, service = selected
    assert service_install.install(root, dry_run=False)['installed']
    return root, tasks, service, service.receipt()


def test_failed_preownership_supervised_attempt_is_actionable_without_relaunch(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    service.start()
    monkeypatch.setattr('okto_nexus_connector.daemon.service_process.validate_context',
        Mock(side_effect=OSError('private startup detail')))
    monkeypatch.setattr(manager, 'run_foreground',
        Mock(side_effect=AssertionError('no runtime may bootstrap')))
    for _ in range(4):
        assert asyncio.run(run(root, receipt['token'], supervised=True, service=service)) == 2
    tasks.tasks[receipt['name']] = replace(tasks.tasks[receipt['name']], state=3, last_result=2)
    from okto_nexus_connector.platform.service_context import CONTROL
    before = (root / CONTROL).read_bytes()
    result = manager.status(root).to_json()
    assert result['reason'] == 'SUPERVISOR_LAST_ATTEMPT_FAILED', result
    assert result['state'] == 'unknown'
    assert result['user_service']['last_result'] == 2
    assert 'current launch and retry outcome are unconfirmed' in result['next_action']
    assert 'private startup detail' not in json.dumps(result)
    assert service.start() is True
    assert [call[0] for call in tasks.calls].count('start') == 1
    assert (root / CONTROL).read_bytes() == before
    stopped = manager.stop(root, timeout=1)
    assert stopped['stopped'] and stopped['shutdown_outcome'] == 'drained'
    assert service.control(receipt)['desired'] == 'draining'
    assert asyncio.run(run(root, receipt['token'], supervised=True, service=service)) == 0
    assert [call[0] for call in tasks.calls].count('start') == 1


@pytest.mark.parametrize('last_result', [1, 2, 3])
def test_failed_attempt_after_runtime_entry_remains_actionable_without_relaunch(selected, monkeypatch, last_result):
    root, tasks, service, receipt = installed(selected)
    service.start()
    from okto_nexus_connector.platform.service_context import CONTROL
    write_document(root / CONTROL, {**service.control(receipt), 'launch_requested': False})
    tasks.tasks[receipt['name']] = replace(tasks.tasks[receipt['name']], state=3, last_result=last_result)
    before = (root / CONTROL).read_bytes()
    result = manager.status(root)
    assert result.state == 'unknown' and result.reason == 'SUPERVISOR_LAST_ATTEMPT_FAILED'
    assert 'retry outcome are unconfirmed' in result.next_action
    ticks = iter([0, 0, 2, 2])
    with monkeypatch.context() as clock:
        clock.setattr('okto_nexus_connector.daemon.lifecycle.time.monotonic', lambda: next(ticks))
        clock.setattr('okto_nexus_connector.daemon.lifecycle.time.sleep', Mock())
        with pytest.raises(ConnectorError, match='SUPERVISOR_LAST_ATTEMPT_FAILED'):
            manager.start(root, timeout=1)
    assert (root / CONTROL).read_bytes() == before
    assert [call[0] for call in tasks.calls].count('start') == 1
    service.begin_stop(None)
    assert manager.status(root).state == 'stopped'


@pytest.mark.parametrize('state,last_result', [(2, 2), (4, 2), (0, 2), (3, 0), (3, 0x41303)])
def test_pending_supervisor_does_not_misattribute_stale_failure_or_status_code(selected, state, last_result):
    root, tasks, service, receipt = installed(selected)
    service.start()
    tasks.tasks[receipt['name']] = replace(tasks.tasks[receipt['name']], state=state, last_result=last_result)
    from okto_nexus_connector.platform.service_context import CONTROL
    before = (root / CONTROL).read_bytes()
    result = manager.status(root)
    assert result.reason == 'SUPERVISOR_PENDING'
    assert result.state == 'starting'
    assert (root / CONTROL).read_bytes() == before
    assert [call[0] for call in tasks.calls].count('start') == 1


def test_stale_supervisor_failure_waits_for_same_launch_to_become_ready(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    initial = manager._process_status(root)
    statuses = Mock(side_effect=[initial,
        replace(initial, state='unknown', reason='SUPERVISOR_LAST_ATTEMPT_FAILED'),
        replace(initial, state='starting', reason='SUPERVISOR_PENDING'),
        replace(initial, state='ready', reason=None, generation='same-launch', running=True, ipc_ok=True),
    ])
    monkeypatch.setattr(manager, 'status', statuses)
    monkeypatch.setattr('okto_nexus_connector.daemon.lifecycle.time.monotonic', lambda: 0)
    monkeypatch.setattr('okto_nexus_connector.daemon.lifecycle.time.sleep', Mock())
    result = manager.start(root, timeout=1)
    assert result['generation'] == 'same-launch' and result['started']
    assert statuses.call_count == 4
    assert [call[0] for call in tasks.calls].count('start') == 1


def test_failed_supervisor_observation_timeout_preserves_pending_effect(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    service.start()
    tasks.tasks[receipt['name']] = replace(tasks.tasks[receipt['name']], state=3, last_result=2)
    observed = manager.status(root)
    assert observed.reason == 'SUPERVISOR_LAST_ATTEMPT_FAILED'
    monkeypatch.setattr(manager, 'status', Mock(return_value=observed))
    ticks = iter([0, 0, 2, 2])
    monkeypatch.setattr('okto_nexus_connector.daemon.lifecycle.time.monotonic', lambda: next(ticks))
    monkeypatch.setattr('okto_nexus_connector.daemon.lifecycle.time.sleep', Mock())
    with pytest.raises(ConnectorError, match='SUPERVISOR_LAST_ATTEMPT_FAILED') as caught:
        manager.start(root, timeout=1)
    assert caught.value.possible_effect
    assert [call[0] for call in tasks.calls].count('start') == 1
    assert service.control(receipt)['launch_requested'] is True


def test_enable_disable_preserve_context_control_and_do_not_launch(selected):
    root, tasks, service, receipt = installed(selected)
    control = (root / 'service-control.json').read_bytes()
    context = (root / CONTEXT).read_bytes()
    assert service_install.set_enabled(root, False)['enablement_confirmed']
    assert service_install.status(root)['enabled'] is False
    assert manager.status(root).user_service['start_at_login'] is False
    assert service_install.set_enabled(root, False)['changed'] is False
    with pytest.raises(ConnectorError) as refused:
        service.start()
    assert refused.value.code == 'SERVICE_DISABLED'
    assert service_install.set_enabled(root, True)['enabled'] is True
    assert service_install.set_enabled(root, True)['changed'] is False
    assert tasks.calls == [('create', receipt['name']), ('enabled', receipt['name'], False), ('enabled', receipt['name'], True)]
    assert (root / 'service-control.json').read_bytes() == control
    assert (root / CONTEXT).read_bytes() == context
    assert service.receipt()['token'] == receipt['token']


def test_active_disable_does_not_stop_or_change_generation_control(selected):
    root, tasks, service, receipt = installed(selected)
    tasks.tasks[receipt['name']] = replace(tasks.tasks[receipt['name']], state=4)
    control = (root / 'service-control.json').read_bytes()
    result = service_install.set_enabled(root, False)
    assert result['process_action'] == 'none' and result['enabled'] is False
    assert tasks.read(receipt['name']).state == 4
    assert (root / 'service-control.json').read_bytes() == control


def test_enablement_response_loss_recovers_without_another_native_effect(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    setter = tasks.set_enabled
    def lose(name, expected, enabled):
        assert service.receipt()['enablement']['target'] is enabled
        setter(name, expected, enabled)
        raise OSError('response lost')
    monkeypatch.setattr(tasks, 'set_enabled', lose)
    with pytest.raises(OSError):
        service_install.set_enabled(root, False)
    assert manager.status(root).reason == 'SERVICE_ENABLEMENT_PENDING'
    with pytest.raises(ConnectorError) as opposite:
        service_install.set_enabled(root, True)
    assert opposite.value.code == 'SERVICE_ENABLEMENT_PENDING'
    assert service_install.set_enabled(root, False)['enablement_confirmed']
    assert tasks.calls == [('create', receipt['name']), ('enabled', receipt['name'], False)]
    assert 'enablement' not in service.receipt()


def test_native_failure_before_effect_retries_retained_enablement(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    setter = tasks.set_enabled
    monkeypatch.setattr(tasks, 'set_enabled', Mock(side_effect=OSError('not applied')))
    with pytest.raises(OSError):
        service_install.set_enabled(root, False)
    monkeypatch.setattr(tasks, 'set_enabled', setter)
    assert service_install.set_enabled(root, False)['enablement_confirmed']
    assert tasks.calls == [('create', receipt['name']), ('enabled', receipt['name'], False)]


def test_edit_after_enablement_response_loss_is_retained(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    setter = tasks.set_enabled
    def edit(name, expected, enabled):
        setter(name, expected, enabled)
        tasks.tasks[name] = replace(tasks.tasks[name], xml=tasks.tasks[name].xml.replace('LeastPrivilege', 'HighestAvailable'))
        raise OSError('response lost')
    monkeypatch.setattr(tasks, 'set_enabled', edit)
    with pytest.raises(OSError):
        service_install.set_enabled(root, False)
    edited = tasks.read(receipt['name'])
    with pytest.raises(ConnectorError) as refusal:
        service_install.set_enabled(root, False)
    assert refusal.value.code == 'SERVICE_ENABLEMENT_UNCONFIRMED'
    assert tasks.read(receipt['name']) == edited and len(tasks.calls) == 2
    with pytest.raises(ConnectorError) as uninstall_refusal:
        service.uninstall()
    assert uninstall_refusal.value.code == 'SERVICE_ENABLEMENT_PENDING'


def test_external_enablement_edit_without_our_intent_is_not_adopted(selected):
    root, tasks, service, receipt = installed(selected)
    task = tasks.read(receipt['name'])
    tasks.tasks[receipt['name']] = replace(task, xml=windows_with_enabled(task.xml, False), enabled=False)
    with pytest.raises(ConnectorError) as refusal:
        service_install.set_enabled(root, False)
    assert refusal.value.code == 'SERVICE_DEFINITION_CHANGED'
    assert len(tasks.calls) == 1


def test_disabled_queued_entry_does_not_bootstrap(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    assert service_install.set_enabled(root, False)['enablement_confirmed']
    foreground = Mock(side_effect=AssertionError('Disabled entry started'))
    monkeypatch.setattr(manager, 'run_foreground', foreground)
    assert asyncio.run(run(root, receipt['token'], supervised=True, service=service)) == 0
    foreground.assert_not_called()
    assert not (root / 'run/daemon.lock').exists()


def test_cli_disable_works_with_unavailable_context_then_enable_refuses(selected, capsys):
    root, tasks, service, receipt = installed(selected)
    context = read_document(root / CONTEXT)
    context['executable'] = str(root / 'removed-python.exe')
    write_document(root / CONTEXT, context)
    assert main(['--state-dir', str(root), 'service', 'disable', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['enabled'] is False
    assert main(['--state-dir', str(root), 'service', 'enable', '--json']) != 0
    assert len(tasks.calls) == 2


def test_enable_absent_instance_does_not_create_state(tmp_path, capsys):
    root = tmp_path / 'absent'
    assert main(['--state-dir', str(root), 'service', 'enable', '--json']) != 0
    result = json.loads(capsys.readouterr().out)
    assert 'USER_SERVICE_NOT_INSTALLED' in json.dumps(result)
    assert not root.exists()


def test_context_freezes_paths_and_backend_without_copying_credentials(tmp_path):
    context = execution_context(tmp_path, env={**os.environ, 'API_KEY': 'secret-sentinel',
        'PYTHONPATH': 'injected', 'OKTO_NEXUS_CONNECTOR_VAULT': 'file'})
    assert 'secret-sentinel' not in json.dumps(context)
    assert 'PYTHONPATH' not in context['environment']
    assert context['environment']['OKTO_NEXUS_CONNECTOR_VAULT'] == 'file'
    assert context['cwd'] == str(tmp_path.resolve())
    assert validate_context(tmp_path, context) == context


def test_existing_proxy_reference_is_resolved_for_launch_but_never_persisted(tmp_path):
    from okto_nexus_connector.storage.state_store import StateStore
    StateStore(tmp_path / 'state.json').update(lambda state: state.preferences.update(
        {'network.proxy': {'mode': 'manual', 'url_env': 'CORP_PROXY'}}))
    inherited = {'CORP_PROXY': 'https://user:synthetic-secret@proxy.example:443', 'API_KEY': 'not-copied'}
    context = execution_context(tmp_path, env={**os.environ, **inherited})
    resolved = launch_environment(tmp_path, context, inherited=inherited)
    assert resolved['CORP_PROXY'] == inherited['CORP_PROXY']
    assert 'API_KEY' not in resolved
    assert 'synthetic-secret' not in json.dumps(context)
    assert 'synthetic-secret' not in (tmp_path / 'state.json').read_text(encoding='utf-8')


def test_proxy_reference_cannot_replace_interpreter_environment(tmp_path):
    from okto_nexus_connector.storage.state_store import StateStore
    StateStore(tmp_path / 'state.json').update(lambda state: state.preferences.update(
        {'network.proxy': {'mode': 'manual', 'url_env': 'PYTHONPATH'}}))
    with pytest.raises(ConnectorError, match='PROXY_CONFIGURATION_INVALID'):
        launch_environment(tmp_path, execution_context(tmp_path), inherited={'PYTHONPATH': 'http://proxy.example'})


def test_status_of_service_and_dry_run_do_not_create_root(tmp_path, capsys):
    root = tmp_path / 'absent'
    assert main(['--state-dir', str(root), 'service', 'status', '--json']) == 0
    assert not root.exists()
    assert main(['--state-dir', str(root), 'service', 'install', '--dry-run', '--json']) == 0
    assert not root.exists()
    assert main(['--state-dir', str(root), 'daemon', 'stop', '--json']) == 0
    assert not root.exists()


def test_launch_selection_without_receipt_is_observed_as_starting(tmp_path):
    with launch_exclusion(tmp_path):
        current = manager.status(tmp_path)
        assert current.state == 'starting' and current.reason == 'CONCURRENT_START'


def test_pending_launch_is_not_repeated_or_given_terminal_environment(tmp_path, monkeypatch):
    spawn = Mock(return_value=Mock(pid=999999))
    monkeypatch.setattr(manager, '_spawn', spawn)
    monkeypatch.setenv('API_KEY', 'secret-sentinel')
    for _ in range(2):
        with pytest.raises(ConnectorError, match='STARTUP_PENDING'):
            manager.start(tmp_path, timeout=.02)
    spawn.assert_called_once()
    context, command = spawn.call_args.args
    assert 'secret-sentinel' not in json.dumps(context)
    assert command[1:4] == ['-I', '-m', 'okto_nexus_connector.daemon.service_process']
    assert read_document(tmp_path / 'run' / LAUNCH)['state'] == 'pending'


def test_production_foreground_owns_lock_before_state_or_vault_initialization(tmp_path, monkeypatch):
    owner = InstanceLock(tmp_path / 'run')
    assert owner.acquire()
    factory = Mock(side_effect=AssertionError('bootstrap before ownership'))
    monkeypatch.setattr('okto_nexus_connector.daemon.app.DaemonApp', factory)
    try:
        with pytest.raises(ConnectorError, match='DAEMON_ALREADY_RUNNING'):
            asyncio.run(manager.run_foreground(tmp_path))
        factory.assert_not_called()
        assert not (tmp_path / 'state.json').exists()
        assert not (tmp_path / 'vault').exists()
    finally:
        owner.release()


def test_install_repeated_is_scoped_and_noop(selected):
    root, tasks, service, receipt = installed(selected)
    context = (root / CONTEXT).read_bytes()
    assert service_install.install(root, dry_run=False)['already_installed']
    assert tasks.calls == [('create', service.name)]
    assert (root / CONTEXT).read_bytes() == context
    assert not (root / 'state.json').exists()
    assert service.name != UserService(root / 'other', tasks=tasks).name


def test_foreign_and_legacy_tasks_never_get_overwritten(selected):
    root, tasks, service = selected
    tasks.tasks[service.name] = TaskObservation('<foreign/>', 3, True, 0)
    with pytest.raises(ConnectorError, match='FOREIGN_SERVICE_DEFINITION'):
        service_install.install(root, dry_run=False)
    del tasks.tasks[service.name]
    tasks.tasks['okto-nexus-connector'] = TaskObservation('<legacy/>', 3, True, 0)
    with pytest.raises(ConnectorError, match='LEGACY_SERVICE_REVIEW_REQUIRED'):
        service_install.install(root, dry_run=False)
    assert not root.exists() and not tasks.calls


@pytest.mark.parametrize('operation', ['start', 'install', 'uninstall'])
def test_edited_native_definition_prevents_mutation(selected, operation):
    root, tasks, service, receipt = installed(selected)
    current = tasks.tasks[service.name]
    tasks.tasks[service.name] = replace(current, xml=current.xml.replace('<Hidden>false</Hidden>', '<Hidden>true</Hidden>'))
    with pytest.raises(ConnectorError, match='SERVICE_DEFINITION_CHANGED'):
        getattr(service, operation)()
    assert tasks.calls == [('create', service.name)]


def test_installed_start_never_spawns_detached_or_resubmits_pending(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    spawn = Mock(side_effect=AssertionError('detached fallback'))
    monkeypatch.setattr(manager, '_spawn', spawn)
    for _ in range(2):
        with pytest.raises(ConnectorError, match='SUPERVISOR_PENDING'):
            manager.start(root, timeout=.02)
    assert tasks.calls == [('create', service.name), ('start', service.name)]
    assert manager.status(root).supervisor == SUPERVISOR and not spawn.called


def test_native_creation_failure_retains_same_intent_and_unknown_task(selected, monkeypatch):
    root, tasks, service = selected
    real = tasks.create
    def lost(name, xml):
        real(name, xml)
        raise OSError('response lost')
    monkeypatch.setattr(tasks, 'create', lost)
    with pytest.raises(OSError):
        service_install.install(root, dry_run=False)
    assert service.receipt()['state'] == 'installing'
    with pytest.raises(ConnectorError, match='INSTALLATION_PENDING'):
        service_install.install(root, dry_run=False)
    assert len(tasks.calls) == 1


def test_persisted_native_creation_response_completes_without_registration(selected):
    root, tasks, service, receipt = installed(selected)
    write_document(root / INSTALLATION, {**receipt, 'state': 'installing'})
    assert service_install.install(root, dry_run=False)['installed']
    assert len(tasks.calls) == 1


def test_uninstall_requires_inactive_task_and_preserves_data(selected):
    root, tasks, service, receipt = installed(selected)
    (root / 'state.json').write_text('retained state')
    tasks.tasks[service.name] = replace(tasks.tasks[service.name], state=4)
    with pytest.raises(ConnectorError, match='SUPERVISOR_STILL_ACTIVE'):
        service_install.uninstall(root, dry_run=False)
    tasks.tasks[service.name] = replace(tasks.tasks[service.name], state=3)
    assert service_install.uninstall(root, dry_run=False)['uninstalled']
    assert (root / 'state.json').read_text() == 'retained state'
    assert (root / CONTEXT).exists()
    assert service_install.uninstall(root, dry_run=False)['uninstalled']
    assert tasks.calls == [('create', service.name), ('delete', service.name)]


def test_lost_delete_response_recovers_positive_absence(selected):
    root, tasks, service, receipt = installed(selected)
    write_document(root / INSTALLATION, {**receipt, 'state': 'removing'})
    del tasks.tasks[service.name]
    assert service_install.uninstall(root, dry_run=False)['uninstalled']
    assert not (root / INSTALLATION).exists()


def test_supervised_stop_latch_suppresses_same_login_and_allows_later_login(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    (root / 'run').mkdir(exist_ok=True)
    service.begin_stop('generation')
    foreground = Mock(side_effect=AssertionError('suppressed retry admitted work'))
    monkeypatch.setattr(manager, 'run_foreground', foreground)
    assert asyncio.run(run(root, receipt['token'], supervised=True, service=service)) == 0
    foreground.assert_not_called()
    async def same_foreground(path, *, acquired_lock, supervisor):
        assert acquired_lock.held and supervisor == SUPERVISOR
        assert path == root and os.getcwd() == str(root)
        assert 'PYTHONPATH' not in os.environ
        service.begin_stop('next-generation')
        return 1
    monkeypatch.setattr(manager, 'run_foreground', same_foreground)
    monkeypatch.setattr('okto_nexus_connector.daemon.service_process.windows_logon_session', lambda: 'later-login')
    assert asyncio.run(run(root, receipt['token'], supervised=True, service=service)) == 0
    assert read_document(root / 'run' / 'service-exit.json')['exit_code'] == 1


def test_native_preflight_on_worker_thread_creates_no_task_or_state(tmp_path):
    if os.name != 'nt':
        pytest.skip('Windows native validate-only')
    service = UserService(tmp_path / 'absent')
    async def preflight():
        assert await asyncio.to_thread(service.tasks.read, service.name) is None
        await asyncio.to_thread(service.prepare)
        assert await asyncio.to_thread(service.tasks.read, service.name) is None
    asyncio.run(preflight())
    assert not service.root.exists()


def test_lost_native_start_response_is_not_submitted_again(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    start = Mock(side_effect=OSError('response lost'))
    monkeypatch.setattr(tasks, 'start', start)
    for _ in range(2):
        with pytest.raises(ConnectorError):
            manager.start(root, timeout=.02)
    start.assert_called_once()
    assert manager.status(root).reason == 'SUPERVISOR_PENDING'


def test_cli_native_failure_is_structured_and_does_not_print_raw_error(selected, monkeypatch, capsys):
    root, tasks, service = selected
    monkeypatch.setattr(tasks, 'create', Mock(side_effect=OSError('secret-sentinel')))
    code = main(['--state-dir', str(root), '--non-interactive', 'service', 'install', '--json'])
    capture = capsys.readouterr()
    assert code != 0 and 'SERVICE_OPERATION_UNCONFIRMED' in capture.out
    assert 'secret-sentinel' not in capture.out + capture.err
    assert service.receipt()['state'] == 'installing'


def test_stop_latches_before_ipc_and_preserves_canonical_drain(selected, monkeypatch):
    root, tasks, service, receipt = installed(selected)
    current = manager.DaemonStatus(True, os.getpid(), 'loopback', '127.0.0.1:1', '0.0.12', '', None,
        True, state='ready', instance_id=service.instance_id, generation='current', supervisor=SUPERVISOR)
    observed = [current]
    monkeypatch.setattr(manager, '_process_status', lambda *_a, **_k: observed[0])
    monkeypatch.setattr(InstanceLock, 'load_token', lambda _: 'synthetic-local-token')
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    def shutdown(*_a, **_k):
        assert service.control(receipt)['desired'] == 'draining'
        write_document(root / 'run' / 'shutdown.json', {'generation': 'current', 'state': 'DRAINED'})
        observed[0] = replace(current, running=False, ipc_ok=False, state='stopped', generation='')
        return {'ok': True}
    client.call.side_effect = shutdown
    monkeypatch.setattr('okto_nexus_connector.daemon.lifecycle.IPCClient', Mock(return_value=client))
    result = manager.stop(root, timeout=1)
    assert result['shutdown_outcome'] == 'drained' and result['stopped']
    assert tasks.calls == [('create', service.name)]


def test_install_does_not_register_when_canonical_drain_is_pending(selected, monkeypatch):
    root, tasks, service = selected
    monkeypatch.setattr(manager, '_process_status', lambda *_: Mock(state='ready'))
    monkeypatch.setattr(manager, 'stop', Mock(return_value={'state': 'stopping', 'wait_timed_out': True}))
    assert not service_install.install(root, dry_run=False)['installed']
    assert not tasks.calls and not root.exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows reader sharing contract')
def test_atomic_lifecycle_write_waits_for_transient_reader(tmp_path):
    target = tmp_path / 'receipt.json'
    _atomic_write(target, b'old')
    reader = target.open('rb')
    def close_reader():
        time.sleep(.05)
        reader.close()
    closer = threading.Thread(target=close_reader)
    closer.start()
    try:
        _atomic_write(target, b'new')
    finally:
        closer.join(timeout=2)
        reader.close()
    assert target.read_bytes() == b'new'
    assert not list(tmp_path.glob('.tmp-*'))
