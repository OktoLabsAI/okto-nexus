"""Disposable receipts and injected OS calls; no personal task registration."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from unittest.mock import Mock

import pytest

from okto_nexus.adapters.inbound.cli.service import run_service
from okto_nexus.adapters.inbound.cli.supervised_service import run as run_supervised
from okto_nexus.adapters.outbound.service_manager.context import atomic_json, read_json
from okto_nexus.adapters.outbound.service_manager.installation import (
    CONTROL_NAME, INSTALLATION_NAME, ServerInstallation, SUPERVISOR)
from okto_nexus.adapters.outbound.service_manager.windows_tasks import TaskConflict, TaskObservation, WindowsTasks
from okto_nexus.application.service_lifecycle import ServiceLifecycle
from test_service_start import make_adapter

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows installer host paths and principal')


class FakeTasks:
    def __init__(self):
        self.tasks, self.calls = {}, []
        self.after_create = None

    def read(self, name):
        return self.tasks.get(name)

    def validate(self, name, xml):
        pass

    def create(self, name, xml):
        assert name not in self.tasks, 'CREATE must never overwrite'
        self.calls.append(('create', name))
        observation = self.tasks[name] = TaskObservation(xml, 3, True, 0)
        if self.after_create:
            self.after_create()
        return observation

    def start(self, name, expected):
        assert self.tasks[name].digest == expected
        self.calls.append(('start', name))
        self.tasks[name] = replace(self.tasks[name], state=2)

    def delete(self, name, expected):
        assert self.tasks[name].digest == expected
        assert not self.tasks[name].active
        self.calls.append(('delete', name))
        del self.tasks[name]


@pytest.fixture
def host(tmp_path):
    adapter = make_adapter(tmp_path)
    tasks = FakeTasks()
    adapter.installation = ServerInstallation(adapter.home, adapter.database, tasks=tasks)
    return adapter, tasks


def install(host):
    adapter, tasks = host
    result = adapter.install_user_service()
    assert result.get('installation_state') == 'installed', result
    return adapter, tasks, read_json(adapter.home / INSTALLATION_NAME)


def test_install_is_scoped_idempotent_and_preserves_context(host, tmp_path):
    adapter, tasks, receipt = install(host)
    original = (adapter.home / 'service-context.json').read_bytes()
    second = adapter.install_user_service()
    assert second['installation_state'] == 'installed'
    assert tasks.calls == [('create', receipt['name'])]
    assert (adapter.home / 'service-context.json').read_bytes() == original
    assert adapter.installation.name != ServerInstallation(tmp_path / 'another', tmp_path / 'another.db', tasks=tasks).name
    xml = tasks.read(receipt['name']).xml
    assert 'pythonw.exe' in xml and '-I -m ' in xml
    assert 'InteractiveToken' in xml and 'LeastPrivilege' in xml
    assert receipt['token'] in xml
    assert not (adapter.home / 'nexus.db').exists()


def test_foreign_task_conflicts_before_context_or_os_mutation(host):
    adapter, tasks = host
    tasks.tasks[adapter.installation.name] = TaskObservation('<foreign/>', 3, True, 0)
    result = adapter.prepare_install()
    assert result['reason'] == 'FOREIGN_SERVICE_DEFINITION'
    assert not tasks.calls and not adapter.home.exists()


@pytest.mark.parametrize('operation', ['start', 'uninstall_user_service', 'install_user_service'])
def test_edited_task_is_retained_for_every_mutation(host, operation):
    adapter, tasks, receipt = install(host)
    current = tasks.tasks[receipt['name']]
    edited = replace(current, xml=current.xml.replace('<Hidden>false</Hidden>', '<Hidden>true</Hidden>'))
    tasks.tasks[receipt['name']] = edited
    result = getattr(adapter, operation)()
    assert result['reason'] == 'SERVICE_DEFINITION_CHANGED'
    assert tasks.read(receipt['name']) == edited
    assert tasks.calls == [('create', receipt['name'])]


def test_changed_context_does_not_rewrite_or_launch(host):
    adapter, tasks, receipt = install(host)
    context_path = adapter.home / 'service-context.json'
    context = read_json(context_path)
    context['arguments'].extend(['--port', '9001'])
    atomic_json(context_path, context)
    assert adapter.start()['reason'] == 'SERVICE_CONTEXT_CHANGED'
    assert tasks.calls == [('create', receipt['name'])]


def test_installed_start_uses_scheduler_and_reuses_pending_task(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    spawn = Mock(side_effect=AssertionError('detached fallback'))
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.subprocess.Popen', spawn)
    assert adapter.start()['reason'] == 'SUPERVISOR_PENDING'
    assert adapter.start()['reason'] == 'SUPERVISOR_PENDING'
    assert tasks.calls == [('create', receipt['name']), ('start', receipt['name'])]
    assert not spawn.called
    view = adapter.inspect()
    assert view['state'] == 'starting' and view['supervisor'] == SUPERVISOR
    assert view['user_service']['available_before_login'] is False
    assert view['user_service']['available_after_logout'] is False


def test_creation_response_loss_does_not_overwrite_or_adopt_existing_task(host):
    adapter, tasks = host
    tasks.after_create = Mock(side_effect=OSError('response lost'))
    result = adapter.install_user_service()
    assert result['reason'] == 'SUPERVISOR_UNAVAILABLE'
    assert read_json(adapter.home / INSTALLATION_NAME)['state'] == 'installing'
    assert adapter.install_user_service()['reason'] == 'INSTALLATION_PENDING'
    assert len(tasks.calls) == 1


def test_creation_failed_before_effect_retries_same_durable_intent(host, monkeypatch):
    adapter, tasks = host
    create = tasks.create
    monkeypatch.setattr(tasks, 'create', Mock(side_effect=OSError('unavailable')))
    assert adapter.install_user_service()['reason'] == 'SUPERVISOR_UNAVAILABLE'
    token = read_json(adapter.home / INSTALLATION_NAME)['token']
    monkeypatch.setattr(tasks, 'create', create)
    assert adapter.install_user_service()['installation_state'] == 'installed'
    assert read_json(adapter.home / INSTALLATION_NAME)['token'] == token


def test_persisted_native_response_is_recoverable_without_creating_again(host):
    adapter, tasks, receipt = install(host)
    atomic_json(adapter.home / INSTALLATION_NAME, {**receipt, 'state': 'installing'})
    assert adapter.install_user_service()['installation_state'] == 'installed'
    assert tasks.calls == [('create', receipt['name'])]


def test_uninstall_waits_for_task_exit_then_preserves_all_user_data(host):
    adapter, tasks, receipt = install(host)
    adapter.database.write_bytes(b'preserve database')
    (adapter.home / 'credentials.sentinel').write_bytes(b'preserve credentials')
    tasks.tasks[receipt['name']] = replace(tasks.tasks[receipt['name']], state=4)
    assert adapter.uninstall_user_service()['reason'] == 'SUPERVISOR_STILL_ACTIVE'
    tasks.tasks[receipt['name']] = replace(tasks.tasks[receipt['name']], state=3)
    assert adapter.uninstall_user_service()['installation_state'] == 'absent'
    assert adapter.database.read_bytes() == b'preserve database'
    assert (adapter.home / 'credentials.sentinel').read_bytes() == b'preserve credentials'
    assert (adapter.home / 'service-context.json').exists()
    assert adapter.uninstall_user_service()['installation_state'] == 'absent'
    assert tasks.calls == [('create', receipt['name']), ('delete', receipt['name'])]


def test_lost_removal_response_recovers_only_from_positive_absence(host):
    adapter, tasks, receipt = install(host)
    atomic_json(adapter.home / INSTALLATION_NAME, {**receipt, 'state': 'removing'})
    del tasks.tasks[receipt['name']]
    service = ServiceLifecycle(adapter, monotonic=lambda: 0, sleep=Mock())
    assert service.uninstall_user_service()['installation_state'] == 'absent'
    assert not (adapter.home / INSTALLATION_NAME).exists()


def test_uninstall_without_home_is_passive(host):
    adapter, tasks = host
    assert adapter.uninstall_user_service()['installation_state'] == 'absent'
    assert not adapter.home.exists() and not tasks.calls


def test_supervised_entry_suppresses_recovery_after_explicit_stop(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    adapter.installation.begin_stop('stopped-generation')
    serve = Mock(side_effect=AssertionError('stop must not reopen admission'))
    monkeypatch.setattr('okto_nexus.adapters.inbound.cli.serve.run_serve', serve)
    assert run_supervised(adapter.home, adapter.database, receipt['token'], installation=adapter.installation) == 0
    assert not serve.called and not adapter.database.exists()


def test_supervised_entry_is_foreground_fenced_and_uses_saved_context(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    original_cwd, original_environment = os.getcwd(), dict(os.environ)
    def foreground(arguments, environment, *, acquired_lock, supervisor):
        assert acquired_lock.owned and supervisor == SUPERVISOR
        assert os.getcwd() == adapter.context['cwd']
        assert dict(os.environ) == {key.upper(): value for key, value in environment.items()}
        assert environment == adapter.context['environment']
        assert arguments == adapter.context['arguments']
        adapter.installation.begin_stop(acquired_lock.generation)
        return 1  # even uncertain shutdown must not trigger recovery after stop
    serve = Mock(side_effect=foreground)
    monkeypatch.setattr('okto_nexus.adapters.inbound.cli.serve.run_serve', serve)
    assert run_supervised(adapter.home, adapter.database, 'wrong', installation=adapter.installation) == 2
    assert run_supervised(adapter.home, adapter.database, receipt['token'], installation=adapter.installation) == 0
    serve.assert_called_once()
    assert os.getcwd() == original_cwd and dict(os.environ) == original_environment
    assert read_json(adapter.home / 'service-supervisor-exit.json')['exit_code'] == 1
    assert adapter.inspect()['shutdown_outcome'] == 'unconfirmed'


def test_failed_supervised_start_remains_nonzero_for_bounded_os_recovery(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    monkeypatch.setattr('okto_nexus.adapters.inbound.cli.serve.run_serve', Mock(return_value=1))
    assert run_supervised(adapter.home, adapter.database, receipt['token'], installation=adapter.installation) == 1


def test_facade_preflights_then_drains_before_registration_or_removal():
    adapter = Mock()
    adapter.prepare_install.return_value = {'state': 'ready', 'installation_prepared': True}
    service = ServiceLifecycle(adapter, monotonic=lambda: 0, sleep=Mock())
    service.stop = Mock(return_value={'state': 'stopping', 'wait_timed_out': True})
    assert service.install_user_service()['wait_timed_out']
    adapter.install_user_service.assert_not_called()
    adapter.inspect.return_value = {'state': 'ready'}
    assert service.uninstall_user_service()['wait_timed_out']
    adapter.uninstall_user_service.assert_not_called()
    service.stop.return_value = {'state': 'stopped', 'shutdown_outcome': 'drained'}
    service.install_user_service()
    adapter.install_user_service.assert_called_once()
    service.uninstall_user_service()
    adapter.uninstall_user_service.assert_called_once()


@pytest.mark.parametrize('argv', [['install'], ['install', '--user'], ['uninstall'], ['start', '--start-at-login']])
def test_cli_requires_explicit_user_and_logon_scope(argv):
    with pytest.raises(SystemExit) as error:
        run_service(argv)
    assert error.value.code == 2


def test_native_adapter_never_overwrites_and_checks_fingerprint_before_mutation(monkeypatch):
    xml = '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Settings/></Task>'
    registered = Mock(Xml=xml, State=3, Enabled=True, LastTaskResult=0)
    folder = Mock()
    folder.RegisterTask.return_value = registered
    folder.GetTask.return_value = registered
    backend = WindowsTasks()
    backend._service = Mock()
    backend._service.GetFolder.return_value = folder
    observation = backend.create('selected', xml)
    folder.RegisterTask.assert_called_once_with('selected', xml, 2, None, None, 3, None)
    registered.Xml = xml.replace('<Settings/>', '<Settings><Hidden>true</Hidden></Settings>')
    with pytest.raises(TaskConflict):
        backend.start('selected', observation.digest)
    with pytest.raises(TaskConflict):
        backend.delete('selected', observation.digest)
    registered.Run.assert_not_called()
    registered.Stop.assert_not_called()
    folder.DeleteTask.assert_not_called()


def test_stop_persists_recovery_latch_before_request_and_never_stops_os_task(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    current = {'state': 'ready', 'instance_id': receipt['instance_id'], 'generation': 'current', 'supervisor': SUPERVISOR}
    monkeypatch.setattr(adapter, '_inspect_process', lambda **_: current)
    opener = Mock()
    def open_request(request, **kwargs):
        assert read_json(adapter.home / CONTROL_NAME)['desired'] == 'draining'
        assert json.loads(request.data)['generation'] == 'current'
        raise TimeoutError('observation only')
    opener.open.side_effect = open_request
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.build_opener', lambda *_: opener)
    result = adapter.request_stop(current, timeout=.1)
    assert result['shutdown']['state'] == 'UNCONFIRMED'
    assert tasks.calls == [('create', receipt['name'])]
    assert adapter.start()['state'] == 'stopping'


def test_stale_stop_cannot_latch_new_generation(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    monkeypatch.setattr(adapter, '_inspect_process', lambda **_: {'state': 'ready', 'generation': 'new'})
    assert adapter.request_stop({'state': 'ready', 'generation': 'old'}, timeout=1)['reason'] == 'INSTANCE_CHANGED'
    assert read_json(adapter.home / CONTROL_NAME)['desired'] == 'running'


def test_different_home_cannot_install_another_supervisor_for_same_database(host, tmp_path):
    adapter, tasks, receipt = install(host)
    other = ServerInstallation(tmp_path / 'other-home', adapter.database, tasks=tasks)
    with pytest.raises(ValueError, match='SERVICE_DATABASE_CLAIM_CONFLICT'):
        other.prepare(adapter.context)
    with pytest.raises(ValueError, match='SERVICE_DATABASE_CLAIM_CONFLICT'):
        other.start()
    assert tasks.calls == [('create', receipt['name'])]


def test_lost_start_response_retains_pending_request_without_resubmission(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    start = Mock(side_effect=OSError('response lost'))
    monkeypatch.setattr(tasks, 'start', start)
    assert adapter.start()['reason'] == 'SUPERVISOR_UNAVAILABLE'
    assert adapter.inspect()['reason'] == 'SUPERVISOR_PENDING'
    assert adapter.start()['reason'] == 'SUPERVISOR_PENDING'
    start.assert_called_once()


def test_stop_before_scheduled_entry_starts_suppresses_it_without_force(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    adapter.start()
    service = ServiceLifecycle(adapter, monotonic=lambda: 0, sleep=Mock())
    # Simulate the already queued wrapper observing the latch and exiting.
    def finish(_):
        assert adapter.installation.control(receipt)['desired'] == 'draining'
        tasks.tasks[receipt['name']] = replace(tasks.tasks[receipt['name']], state=3)
    service.sleep = finish
    result = service.stop(timeout=1)
    assert result['state'] == 'stopped' and result['shutdown_outcome'] == 'drained'
    assert not adapter.database.exists()
    assert tasks.calls == [('create', receipt['name']), ('start', receipt['name'])]


def test_foreground_refuses_installed_integration_before_bootstrap(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    from okto_nexus.adapters.inbound.cli.serve import run_serve
    bootstrap = Mock(side_effect=AssertionError('bootstrap must not begin'))
    monkeypatch.setattr('okto_nexus.bootstrap.dependencies.bootstrap', bootstrap)
    assert run_serve(adapter.context['arguments'], adapter.context['environment']) == 1
    bootstrap.assert_not_called()


def test_later_user_login_is_distinct_from_crash_retry_after_stop(host, monkeypatch):
    adapter, tasks, receipt = install(host)
    adapter.installation.begin_stop('previous-generation')
    monkeypatch.setattr('okto_nexus.adapters.inbound.cli.supervised_service.windows_logon_session', lambda: 'later-login')
    serve = Mock(return_value=0)
    monkeypatch.setattr('okto_nexus.adapters.inbound.cli.serve.run_serve', serve)
    assert run_supervised(adapter.home, adapter.database, receipt['token'], installation=adapter.installation) == 0
    serve.assert_called_once()
    assert adapter.installation.control(receipt)['logon_session'] == 'later-login'
    assert adapter.installation.control(receipt)['desired'] == 'running'


def test_native_host_preflight_validates_without_registering_or_creating_home(tmp_path):
    adapter = make_adapter(tmp_path)
    installation = adapter.installation
    assert installation.tasks.read(installation.name) is None
    assert adapter.prepare_install()['installation_prepared']
    assert installation.tasks.read(installation.name) is None
    assert not adapter.home.exists()
