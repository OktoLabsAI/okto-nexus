import copy
from dataclasses import replace
import os
from pathlib import Path
import pytest
from nexus_connector_core.user_service_definition import windows_with_enabled

from okto_nexus import service_upgrade as protocol
from okto_nexus.adapters.outbound.service_manager.upgrade import ServerUpgradeHost
from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
from okto_nexus.adapters.outbound.service_manager.windows_tasks import TaskObservation
from test_service_start import make_adapter


def make_host(tmp_path):
    adapter = make_adapter(tmp_path)
    adapter.home.mkdir()
    tasks = FakeTasks()
    adapter.installation = ServerInstallation(adapter.home, adapter.database, tasks=tasks)
    host = ServerUpgradeHost(adapter)
    host.write(host.context_path, adapter.context)
    return host, tasks

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows host upgrade qualification')


class FakeTasks:
    def __init__(self):
        self.tasks, self.calls = {}, []
        self.lose_response = False

    def read(self, name):
        return self.tasks.get(name)

    def validate(self, name, xml):
        pass

    def create(self, name, xml):
        assert name not in self.tasks
        self.tasks[name] = TaskObservation(xml, 3, True, 0)
        return self.tasks[name]

    def replace(self, name, expected, xml):
        assert self.tasks[name].digest == expected
        assert not self.tasks[name].active
        self.calls.append('replace')
        self.tasks[name] = replace(self.tasks[name], xml=xml)
        if self.lose_response:
            self.lose_response = False
            raise OSError('lost update response')
        return self.tasks[name]


@pytest.fixture
def selection(tmp_path, monkeypatch):
    host, tasks = make_host(tmp_path)
    target = tmp_path / 'target'
    target.mkdir()
    executable = target / 'python.exe'
    executable.write_bytes(b'candidate executable')
    (target / 'pythonw.exe').write_bytes(b'candidate windowless executable')
    candidate = {'protocol': 2, 'distribution': protocol.probe.__module__.split('.')[0],
        'package': {'version': '1.3.0', 'digest': 'a' * 64},
        'core': {'version': '0.0.14', 'digest': 'b' * 64},
        'executable': str(executable), 'environment_prefix': str(target),
        'python_version': '3.13.1', 'python_digest': 'c' * 64}
    monkeypatch.setattr(protocol, 'probe', lambda path: copy.deepcopy(candidate))
    monkeypatch.setattr(protocol, 'installed_versions', lambda path: ('1.2.0', '0.0.14'))
    return host, tasks, candidate


def plan(selection, *, installed=False):
    host, tasks, candidate = selection
    if installed:
        context = host.read(host.context_path)
        if host.component == 'server':
            host.installation.install(context)
        else:
            host.installation.install()
        host.logon_session = lambda: 'test-logon'
    document = protocol.ServiceUpgrade(host).plan(candidate['executable'])
    return protocol.ServiceUpgrade(host), document


@pytest.mark.parametrize('installed', [False, True])
def test_explicit_apply_preserves_configuration_and_repeats_without_effect(selection, installed):
    host, tasks, _ = selection
    service, document = plan(selection, installed=installed)
    source = host.read(host.context_path)
    before = host.claim_snapshot(None)
    assert not tasks.calls and source == document['plan']['source_context']
    result = service.apply(document, document['plan_revision'])
    assert result['applied'] and result['migration_state'] == 'not_run_by_upgrade'
    target = host.read(host.context_path)
    for key in ('cwd', 'environment', 'arguments', 'root'):
        if key in source:
            assert target[key] == source[key]
    assert target['revision'] == 2 and target['executable'] != source['executable']
    assert host.read(host.launch_path)['state'] == 'upgrade_complete'
    assert host.read(host.completed_path)['plan']['source_context'] == source
    if installed:
        assert tasks.calls == ['replace']
        assert host.read(host.control_path)['desired'] == 'draining'
        assert host.read(host.installation_path)['token'] != document['plan']['source_receipt']['token']
        if host.component == 'server':
            assert host.claim_snapshot(None)['token'] != before['token']
    assert not service.apply(document, document['plan_revision'])['changed']
    assert tasks.calls == (['replace'] if installed else [])


@pytest.mark.parametrize('write_index', range(1, 9))
@pytest.mark.parametrize('after_write', [False, True])
def test_every_persistence_boundary_can_resume_same_plan(selection, monkeypatch, write_index, after_write):
    host, tasks, _ = selection
    service, document = plan(selection, installed=True)
    original = host.write
    count = 0
    def interrupted(path, value):
        nonlocal count
        count += 1
        if count == write_index and not after_write:
            raise OSError('injected interruption before write')
        original(path, value)
        if count == write_index and after_write:
            raise OSError('injected interruption after write')
    monkeypatch.setattr(host, 'write', interrupted)
    try:
        service.apply(document, document['plan_revision'])
    except OSError:
        pass
    else:
        assert count < write_index
    monkeypatch.setattr(host, 'write', original)
    assert service.apply(document, document['plan_revision'])['applied']
    assert tasks.calls == ['replace']
    assert host.read(host.context_path) == document['plan']['target_context']


def test_lost_native_response_keeps_fence_and_recognizes_only_exact_effect(selection):
    host, tasks, _ = selection
    service, document = plan(selection, installed=True)
    tasks.lose_response = True
    with pytest.raises(OSError):
        service.apply(document, document['plan_revision'])
    assert host.read(host.context_path)['upgrade_pending'] == document['plan_revision']
    with pytest.raises(Exception, match='SERVICE_UPGRADE_PENDING'):
        host.installation.set_enabled(False)
    with pytest.raises(Exception, match='SERVICE_UPGRADE_PENDING'):
        host.installation.uninstall()
    assert service.apply(document, document['plan_revision'])['applied']
    assert tasks.calls == ['replace']


def test_user_edit_after_lost_response_is_not_adopted(selection):
    host, tasks, _ = selection
    service, document = plan(selection, installed=True)
    tasks.lose_response = True
    with pytest.raises(OSError):
        service.apply(document, document['plan_revision'])
    name = host.installation.name
    tasks.tasks[name] = replace(tasks.tasks[name],
        xml=tasks.tasks[name].xml.replace('LeastPrivilege', 'HighestAvailable'))
    with pytest.raises(protocol.UpgradeError, match='UPGRADE_NATIVE_CONFLICT'):
        service.apply(document, document['plan_revision'])
    assert host.read(host.context_path)['upgrade_pending'] == document['plan_revision']
    assert tasks.calls == ['replace']


def test_disabled_task_remains_disabled(selection):
    host, tasks, _ = selection
    plan(selection, installed=True)
    name = host.installation.name
    native = tasks.tasks[name]
    tasks.tasks[name] = replace(native, xml=windows_with_enabled(native.xml, False), enabled=False, state=1)
    receipt = host.read(host.installation_path)
    host.write(host.installation_path, {**receipt, 'native_xml': tasks.tasks[name].xml, 'native_digest': tasks.tasks[name].digest})
    service, document = plan(selection)
    service.apply(document, document['plan_revision'])
    assert not tasks.tasks[name].enabled
    assert '<ns0:Enabled>false</ns0:Enabled>' in tasks.tasks[name].xml


@pytest.mark.parametrize('kind', ['review', 'context', 'target', 'native', 'missing_receipt', 'pending_launch', 'active'])
def test_conflicts_preserve_source_before_fencing(selection, kind):
    host, tasks, candidate = selection
    service, document = plan(selection, installed=True)
    original = host.read(host.context_path)
    expected = document['plan_revision']
    if kind == 'review':
        expected = '0' * 64
    elif kind == 'context':
        host.write(host.context_path, {**original, 'cwd': str(Path(original['cwd']).parent)})
    elif kind == 'target':
        candidate['package']['digest'] = 'd' * 64
    elif kind == 'native':
        name = host.installation.name
        tasks.tasks[name] = replace(tasks.tasks[name], xml=tasks.tasks[name].xml.replace('LeastPrivilege', 'HighestAvailable'))
    elif kind == 'missing_receipt':
        host.installation_path.unlink()
    elif kind == 'pending_launch':
        host.launch_path.parent.mkdir(parents=True, exist_ok=True)
        host.write(host.launch_path, {'state': 'pending', 'token': 'old'})
    elif kind == 'active':
        name = host.installation.name
        tasks.tasks[name] = replace(tasks.tasks[name], state=4)
    with pytest.raises(Exception):
        service.apply(document, expected)
    assert not host.read(host.context_path).get('upgrade_pending')
    assert not tasks.calls


def test_drain_receipt_must_match_reviewed_generation_and_latest_run(selection, monkeypatch):
    host, tasks, _ = selection
    monkeypatch.setattr(host, 'status', lambda: {'state': 'ready', 'generation': 'g1', 'active_version': '1.2.0'})
    service, document = plan(selection)
    monkeypatch.setattr(host, 'status', lambda: {'state': 'stopped'})
    with pytest.raises(protocol.UpgradeError, match='UPGRADE_DRAIN_UNCONFIRMED'):
        service.apply(document, document['plan_revision'])
    host.shutdown_path.parent.mkdir(parents=True, exist_ok=True)
    host.write(host.shutdown_path, {'state': 'DRAINED', 'generation': 'g1'})
    host.write(host.run_path, {'state': 'unconfirmed', 'instance_id': host.instance_id, 'generation': 'g2'})
    with pytest.raises(protocol.UpgradeError, match='UPGRADE_DRAIN_UNCONFIRMED'):
        service.apply(document, document['plan_revision'])
    host.write(host.run_path, {'state': 'drained', 'instance_id': host.instance_id, 'generation': 'g1'})
    assert service.apply(document, document['plan_revision'])['applied']
    assert not tasks.calls


def test_downgrade_and_unconfirmed_existing_runtime_are_refused(selection, monkeypatch):
    host, _, candidate = selection
    candidate['package']['version'] = '1.1.0'
    with pytest.raises(protocol.UpgradeError, match='UPGRADE_DOWNGRADE_REFUSED'):
        plan(selection)
    candidate['package']['version'] = '1.3.0'
    monkeypatch.setattr(host, 'runtime_exists', lambda: True)
    with pytest.raises(protocol.UpgradeError, match='UPGRADE_DRAIN_UNCONFIRMED'):
        plan(selection)


def test_hand_modified_plan_cannot_change_non_environment_configuration(selection):
    host, _, _ = selection
    service, document = plan(selection)
    document['plan']['target_context']['environment']['PATH'] = 'different'
    document['plan_revision'] = host.digest(document['plan'])
    with pytest.raises(protocol.UpgradeError, match='UPGRADE_PLAN_CONFLICT'):
        service.apply(document, document['plan_revision'])

def test_native_update_adapter_is_update_only_and_never_runs_registration_triggers(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks, TaskConflict
    from nexus_connector_core.user_service_definition import UserServiceDefinition, windows_logon_task, windows_definition_digest
    xml = windows_logon_task(UserServiceDefinition('connector', 'svc_' + 'a' * 64,
        'S-1-5-21-1', str(Path('C:/test/pythonw.exe')), ('-I', '-m', 'test'), 'C:/test'))
    task = SimpleNamespace(Xml=xml, State=3, Enabled=True, LastTaskResult=0)
    folder = SimpleNamespace(RegisterTask=Mock(return_value=task))
    adapter = WindowsTasks()
    monkeypatch.setattr(adapter, '_call', lambda operation: operation(folder))
    monkeypatch.setattr(adapter, '_task', lambda folder, name: task)
    expected = windows_definition_digest(xml)
    adapter.replace('selected', expected, xml)
    assert folder.RegisterTask.call_args.args == ('selected', xml, 52, None, None, 3, None)
    folder.RegisterTask.reset_mock()
    for state in (0, 2, 4):
        task.State = state
        with pytest.raises(TaskConflict):
            adapter.replace('selected', expected, xml)
    task.State = 3
    task.Xml = xml.replace('LeastPrivilege', 'HighestAvailable')
    with pytest.raises(TaskConflict):
        adapter.replace('selected', expected, xml)
    folder.RegisterTask.assert_not_called()


def test_pending_upgrade_blocks_direct_foreground_before_runtime_bootstrap(selection, monkeypatch):
    host, tasks, _ = selection
    service, document = plan(selection, installed=True)
    tasks.lose_response = True
    with pytest.raises(OSError):
        service.apply(document, document['plan_revision'])
    from okto_nexus.adapters.inbound.cli.serve import run_serve
    # A detached pending upgrade must fence the public foreground entry too.
    host.installation_path.unlink()
    host.installation.database_claim.unlink()
    monkeypatch.setattr('okto_nexus.bootstrap.dependencies.bootstrap',
        lambda *args: pytest.fail('bootstrap crossed pending upgrade fence'))
    assert run_serve(host.read(host.context_path)['arguments'], env={}) == 1
    assert not host.database.exists()


def test_installed_payload_change_is_detected_before_bootstrap(monkeypatch):
    from okto_nexus import service_environment
    observed = {'protocol': 2, 'package': {'version': '1.2.0', 'digest': 'a' * 64}}
    context = {'revision': 2}
    import hashlib
    import json
    context['environment_fingerprint'] = hashlib.sha256(json.dumps(observed, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    monkeypatch.setattr(service_environment, 'snapshot', lambda: observed)
    service_environment.verify_context(context)
    observed['package']['digest'] = 'b' * 64
    with pytest.raises(ValueError, match='SERVICE_ENVIRONMENT_CHANGED'):
        service_environment.verify_context(context)

def test_environment_probe_timeout_has_stable_actionable_diagnostic(monkeypatch):
    from okto_nexus import service_environment
    import subprocess
    def expired(_executable):
        raise subprocess.TimeoutExpired('selected-python', 60)
    monkeypatch.setattr(service_environment, '_probe', expired)
    with pytest.raises(service_environment.EnvironmentInspectionError) as caught:
        service_environment.probe('selected-python')
    assert caught.value.code == 'UPGRADE_ENVIRONMENT_UNAVAILABLE'
    assert caught.value.action


def test_plan_output_refuses_overwrite_and_round_trips_utf8(selection, tmp_path):
    _, document = plan(selection)
    output = tmp_path / 'review.json'
    protocol.save_plan(output, document)
    import json
    assert json.loads(output.read_text(encoding='utf-8')) == document
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        protocol.save_plan(output, {'replacement': True})
    assert output.read_bytes() == original

def test_context_edit_during_interruption_is_preserved(selection):
    host, tasks, _ = selection
    service, document = plan(selection, installed=True)
    tasks.lose_response = True
    with pytest.raises(OSError):
        service.apply(document, document['plan_revision'])
    changed = {**host.read(host.context_path), 'cwd': 'externally edited'}
    host.write(host.context_path, changed)
    with pytest.raises(protocol.UpgradeError, match='UPGRADE_CONTEXT_CONFLICT'):
        service.apply(document, document['plan_revision'])
    assert host.read(host.context_path) == changed
    assert tasks.calls == ['replace']


@pytest.mark.parametrize('change', ['token', 'generation', 'export', 'consoleless'])
def test_invalid_reviewed_references_are_rejected_before_durable_fence(selection, change):
    host, tasks, candidate = selection
    service, document = plan(selection, installed=True)
    if change == 'token':
        document['plan']['target_token'] = 'invalid'
    elif change == 'generation':
        document['plan']['source_generation'] = ['invalid']
    elif change == 'export':
        document['plan']['source_native_xml'] = document['plan']['source_native_xml'].replace('LeastPrivilege', 'HighestAvailable')
    else:
        Path(candidate['executable']).with_name('pythonw.exe').unlink()
    document['plan_revision'] = host.digest(document['plan'])
    with pytest.raises(protocol.UpgradeError):
        service.apply(document, document['plan_revision'])
    assert not host.read(host.context_path).get('upgrade_pending')
    assert not tasks.calls



def test_failure_after_shutdown_report_cannot_certify_latest_run_drained(selection, monkeypatch):
    from types import SimpleNamespace
    from okto_nexus.adapters.inbound.cli import serve
    from okto_nexus.adapters.outbound.service_manager.inspection import _held
    host, _, _ = selection
    deps = SimpleNamespace(config=SimpleNamespace(feature_harness_integrations=False))
    app = SimpleNamespace(state=SimpleNamespace(runtime_shutdown=SimpleNamespace(status=lambda: {'state': 'DRAINED'})))
    monkeypatch.setattr('okto_nexus.bootstrap.dependencies.bootstrap', lambda *args: deps)
    monkeypatch.setattr('okto_nexus.bootstrap.dependencies.maybe_auto_prune', lambda deps: None)
    monkeypatch.setattr('okto_nexus.adapters.inbound.http.app.build_app', lambda *args, **kwargs: app)
    monkeypatch.setattr('okto_nexus.adapters.inbound.cli.runtime_server.RuntimeServer',
        lambda *args: SimpleNamespace(run=lambda: None))
    monkeypatch.setattr(serve, '_watch_ready', lambda *args: None)
    monkeypatch.setattr(serve, '_warm_embeddings', lambda *args: None)
    def incomplete(_deps):
        raise RuntimeError('cleanup not confirmed')
    monkeypatch.setattr(serve, '_reap_live_harness_sessions', incomplete)
    with pytest.raises(RuntimeError, match='cleanup not confirmed'):
        serve.run_serve(host.read(host.context_path)['arguments'], env={})
    assert host.read(host.shutdown_path)['state'] == 'DRAINED'
    assert host.read(host.run_path)['state'] == 'unconfirmed'
    assert _held(host.home / 'nexus.serve.guard') is False
