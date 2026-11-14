"""Bounded parent with injected native tasks, child handles and monotonic time."""
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from okto_nexus_connector.daemon import manager, service_supervisor
from okto_nexus_connector.daemon.lock import InstanceLock
from okto_nexus_connector.errors import ConnectorError
from okto_nexus_connector.platform import service_install, service_supervision
from okto_nexus_connector.platform.service_context import CONTROL, INSTALLATION, read_document, write_document
from okto_nexus_connector.platform.sysinfo import ProcessIdentity
from okto_nexus_connector.platform.user_service import UserService
from okto_nexus_connector.platform.windows_tasks import TaskObservation


class Tasks:
    def __init__(self):
        self.items, self.starts = {}, 0

    def read(self, name):
        return self.items.get(name)

    def validate(self, name, xml):
        pass

    def create(self, name, xml):
        self.items[name] = TaskObservation(xml, 3, True, 0)
        return self.items[name]

    def start(self, name, expected):
        assert self.items[name].digest == expected
        self.starts += 1
        self.items[name] = replace(self.items[name], state=2)

    def delete(self, name, expected):
        assert self.items[name].digest == expected
        del self.items[name]


@pytest.fixture
def selected(tmp_path, monkeypatch):
    if os.name != 'nt':
        pytest.skip('Windows user-service wrapper')
    tasks = Tasks()
    monkeypatch.setattr('okto_nexus_connector.platform.user_service.WindowsTasks', lambda: tasks)
    root = tmp_path / 'connector'
    assert service_install.install(root, dry_run=False)['installed']
    service = UserService(root, tasks=tasks)
    monkeypatch.setattr(service_supervisor, 'current_process_identity', lambda: ProcessIdentity(101, 'filetime:101'))
    monkeypatch.setattr(service_supervisor, 'windows_logon_session', lambda: 'logon-a')
    return root, tasks, service


def invoke(selected, spawn, *, sleep=None, probe=lambda _: 'exited'):
    root, _, service = selected
    now = [10.0]
    def advance(_):
        now[0] += 60
        if sleep:
            sleep()
    return service_supervisor.run(root, service.receipt()['token'], service=service,
        spawn=spawn, clock=lambda: now[0], sleep=advance,
        identify_child=lambda process: {'pid': process.pid, 'birth_token': 'filetime:' + str(process.pid)},
        probe=probe, acknowledge=fake_ack)


def fake_ack(root, record, *_args, **_kwargs):
    record.update(child=dict(record['launcher']), child_acknowledged=True)
    write_document(root / 'run' / service_supervision.RECEIPT, record)
    return SimpleNamespace(exited=lambda: True, wait=_args[-1].wait, close=lambda: None)


def child(pid, code):
    return SimpleNamespace(pid=pid, poll=lambda: code, wait=lambda: code)


def test_four_attempts_reserved_before_spawn_ready_does_not_reset_and_zero_exit_retries(selected):
    root, tasks, service = selected
    counts, moments = [], []
    def spawn(argv, **kwargs):
        record = read_document(root / 'run' / service_supervision.RECEIPT)
        assert record['phase'] == 'running' and record['child'] is None and not record['child_exit_confirmed']
        counts.append(record['attempts_started'])
        moments.append(record['next_retry_monotonic'])
        control = service.control(service.receipt())
        write_document(root / CONTROL, {**control, 'launch_requested': False})  # child READY behavior
        assert argv[argv.index('--supervisor-cycle') + 1] == control['cycle_id']
        assert argv[argv.index('--supervisor-nonce') + 1] == record['attempt_nonce']
        assert kwargs['stdin'] == service_supervisor.subprocess.DEVNULL
        return child(200 + len(counts), 0 if len(counts) == 1 else 3)
    assert invoke(selected, spawn) == 2
    record = read_document(root / 'run' / service_supervision.RECEIPT)
    assert counts == [1, 2, 3, 4]
    assert record['phase'] == 'exhausted' and record['last_exit_code'] == 3 and record['child_exit_confirmed']
    assert service.control(service.receipt())['desired'] == 'running'
    assert tasks.starts == 0  # the parent never asks Task Scheduler to retry


def test_stop_during_backoff_returns_zero_and_never_creates_another_child(selected):
    root, _, service = selected
    spawn = Mock(return_value=child(201, 3))
    assert invoke(selected, spawn, sleep=lambda: service.begin_stop(None)) == 0
    spawn.assert_called_once()
    record = read_document(root / 'run' / service_supervision.RECEIPT)
    assert record['phase'] == 'stopped' and record['attempts_started'] == 1


def test_backoff_starts_are_separated_by_sixty_monotonic_seconds(selected):
    root, _, service = selected
    now, starts = [0.0], []
    def spawn(*args, **kwargs):
        starts.append(now[0])
        return child(201, 3)
    result = service_supervisor.run(root, service.receipt()['token'], service=service,
        spawn=spawn, clock=lambda: now[0], sleep=lambda _: now.__setitem__(0, now[0] + 1),
        identify_child=lambda process: {'pid': process.pid, 'birth_token': 'filetime:201'}, acknowledge=fake_ack)
    assert result == 2 and starts == [0, 60, 120, 180]


def test_spawn_unknown_does_not_restart_or_reset_in_new_parent(selected):
    root, _, service = selected
    spawn = Mock(side_effect=OSError('synthetic unavailable spawn'))
    assert invoke(selected, spawn) == 2
    record = read_document(root / 'run' / service_supervision.RECEIPT)
    assert record['phase'] == 'unknown' and record['attempts_started'] == 1
    assert record['child'] is None and not record['child_exit_confirmed']
    assert invoke(selected, spawn) == 2
    spawn.assert_called_once()


def test_only_one_parent_can_hold_the_supervisor_guard(selected):
    root, _, _ = selected
    lock = service_supervision.guard(root)
    assert lock.acquire()
    spawn = Mock(side_effect=AssertionError('duplicate parent'))
    try:
        assert invoke(selected, spawn) == 2
        spawn.assert_not_called()
    finally:
        lock.release()


def test_existing_runtime_owner_blocks_new_supervisor_cycle(selected):
    root, _, _ = selected
    lock = InstanceLock(root / 'run')
    assert lock.acquire()
    spawn = Mock(side_effect=AssertionError('owner duplicated'))
    try:
        assert invoke(selected, spawn) == 2
        spawn.assert_not_called()
    finally:
        lock.release()


def test_exhausted_requires_explicit_stop_and_physical_exit_before_new_cycle(selected, monkeypatch):
    root, tasks, service = selected
    assert invoke(selected, lambda *a, **k: child(201, 3)) == 2
    monkeypatch.setattr(service_supervision, 'process_state', lambda _: 'exited')
    assert manager.status(root).reason == 'SUPERVISOR_RESTART_EXHAUSTED'
    old = read_document(root / 'run' / service_supervision.RECEIPT)
    with pytest.raises(ConnectorError, match='SUPERVISOR_OUTCOME_UNCONFIRMED'):
        service.start()
    service.begin_stop(None)
    assert manager.status(root).state == 'stopped'
    assert service.start()
    assert tasks.starts == 1
    assert service.control(service.receipt())['cycle_id'] != old['cycle_id']
    assert manager.status(root).reason == 'SUPERVISOR_PENDING'
    assert read_document(root / 'run' / service_supervision.RECEIPT)['attempts_started'] == 4


def test_lost_parent_with_unknown_child_blocks_start_and_uninstall(selected, monkeypatch):
    root, _, service = selected
    assert invoke(selected, Mock(side_effect=OSError('no spawn receipt'))) == 2
    monkeypatch.setattr(service_supervision, 'process_state', lambda _: 'exited')
    observed = manager.status(root)
    assert observed.state == 'unknown' and observed.reason == 'SUPERVISOR_OUTCOME_UNCONFIRMED'
    with pytest.raises(ConnectorError, match='SUPERVISOR_OUTCOME_UNCONFIRMED'):
        service.start()
    with pytest.raises(ConnectorError, match='SUPERVISOR_OUTCOME_UNCONFIRMED'):
        service.uninstall()


def test_stop_backoff_scope_does_not_settle_crashed_runtime_claims(selected, monkeypatch):
    root, _, _ = selected
    assert invoke(selected, lambda *a, **k: child(201, 3)) == 2
    monkeypatch.setattr(service_supervision, 'process_state', lambda _: 'exited')
    shutdown = root / 'run/shutdown.json'
    write_document(shutdown, {'generation': 'crashed-runtime', 'state': 'UNCONFIRMED', 'claims': 'retained'})
    before = shutdown.read_bytes()
    stopped = manager.stop(root, timeout=1)
    assert stopped['stopped'] and stopped['supervision_scope'] == 'supervisor_only'
    assert stopped['shutdown_outcome'] == 'unconfirmed'
    assert stopped['runtime_work_settlement'] == 'not_asserted'
    assert shutdown.read_bytes() == before


def test_restart_after_supervisor_only_stop_is_blocked_but_inactive_integration_can_be_removed(selected, monkeypatch):
    root, tasks, service = selected
    assert invoke(selected, lambda *a, **k: child(201, 3)) == 2
    monkeypatch.setattr(service_supervision, 'process_state', lambda _: 'exited')
    start = Mock(side_effect=AssertionError('unconfirmed runtime drain must not restart'))
    monkeypatch.setattr(manager, 'start', start)
    result = manager.restart(root, timeout=1)
    assert result['state'] == 'stopped' and result['stopped']
    assert result['shutdown_outcome'] == 'unconfirmed'
    assert result['runtime_work_settlement'] == 'not_asserted'
    start.assert_not_called()
    retained = root / 'retained-data.txt'
    retained.write_text('retained fixture data')
    service.uninstall()
    assert tasks.read(service.name) is None
    assert retained.read_text() == 'retained fixture data'


def test_terminal_receipt_does_not_report_stopped_while_parent_alive_or_task_active(selected, monkeypatch):
    root, tasks, service = selected
    assert invoke(selected, lambda *a, **k: child(201, 3), sleep=lambda: service.begin_stop(None)) == 0
    monkeypatch.setattr(service_supervision, 'process_state', lambda identity: 'alive' if identity['pid'] == 101 else 'exited')
    assert manager.status(root).state == 'stopping'
    monkeypatch.setattr(service_supervision, 'process_state', lambda _: 'exited')
    tasks.items[service.name] = replace(tasks.items[service.name], state=4)
    assert manager.status(root).state == 'stopping'
    tasks.items[service.name] = replace(tasks.items[service.name], state=3)
    assert manager.status(root).state == 'stopped'


def test_child_gate_requires_published_matching_identity_and_live_parent(selected, monkeypatch):
    root, _, service = selected
    def spawn(*args, **kwargs):
        return child(201, 3)
    assert invoke(selected, spawn) == 2
    path = root / 'run' / service_supervision.RECEIPT
    record = read_document(path)
    record.update(phase='running', child_exit_confirmed=False)
    write_document(path, record)
    lock = service_supervision.guard(root)
    assert lock.acquire()
    monkeypatch.setattr(service_supervision, 'process_state', lambda _: 'alive')
    monkeypatch.setattr('okto_nexus_connector.platform.sysinfo.current_process_identity', lambda: ProcessIdentity(201, 'filetime:201'))
    try:
        service_supervision.validate_child(root, service.receipt(), service.control(service.receipt()), record['cycle_id'], record['attempt_nonce'])
        with pytest.raises(ValueError):
            service_supervision.validate_child(root, service.receipt(), service.control(service.receipt()), 'wrong-cycle', record['attempt_nonce'])
        monkeypatch.setattr(service_supervision, 'process_state', lambda _: 'unknown')
        with pytest.raises(ValueError):
            service_supervision.validate_child(root, service.receipt(), service.control(service.receipt()), record['cycle_id'], record['attempt_nonce'])
    finally:
        lock.release()


def test_new_definition_does_not_delegate_retry_to_scheduler(selected):
    _, tasks, service = selected
    task = tasks.read(service.name)
    assert 'service_supervisor' in task.xml and 'RestartOnFailure' not in task.xml
    assert service.receipt()['supervision_mode'] == service_supervision.MODE


def test_retired_installation_receipt_requires_positive_old_process_exit(selected, monkeypatch):
    root, _, service = selected
    assert invoke(selected, lambda *a, **k: child(201, 3), sleep=lambda: service.begin_stop(None)) == 0
    new_installation = {**service.receipt(), 'token': 'f' * 32}
    monkeypatch.setattr(service_supervision, 'process_state', lambda _: 'unknown')
    with pytest.raises(ValueError):
        service_supervision.read_cycle(root, new_installation)
    monkeypatch.setattr(service_supervision, 'process_state', lambda _: 'exited')
    assert service_supervision.read_cycle(root, new_installation) is None


def test_old_native_restart_policy_is_rejected_without_editing_task(selected):
    root, tasks, service = selected
    task = tasks.read(service.name)
    xml = task.xml.replace('</Settings>', '<RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure></Settings>')
    changed = replace(task, xml=xml)
    tasks.items[service.name] = changed
    receipt = service.receipt()
    write_document(root / INSTALLATION, {**receipt, 'native_xml': xml, 'native_digest': changed.digest})
    with pytest.raises(ConnectorError, match='SERVICE_SUPERVISION_POLICY_CHANGED'):
        service.start()
    assert tasks.read(service.name).xml == xml and tasks.starts == 0


def test_windows_same_birth_process_observation_never_grants_termination():
    if os.name != 'nt':
        pytest.skip('Windows process observer')
    from okto_nexus_connector.platform.sysinfo import current_process_identity
    identity = current_process_identity().to_json()
    assert service_supervision.process_state(identity) == 'alive'
    assert service_supervision.process_state({'pid': identity['pid'], 'birth_token': 'unknown'}) == 'unknown'
    assert service_supervision.process_state({**identity, 'birth_token': 'filetime:1'}) == 'exited'


@pytest.mark.parametrize('stop_before_handshake', [False, True])
def test_real_venv_redirector_handshake_before_benign_bootstrap_and_both_exits(selected, monkeypatch, stop_before_handshake):
    """Own Python fixture only: no service, Task Scheduler mutation or provider."""
    root, _, service = selected
    from okto_nexus_connector.platform.sysinfo import current_process_identity
    monkeypatch.setattr(service_supervisor, 'current_process_identity', current_process_identity)
    connector_source = str(Path(__file__).resolve().parents[2] / 'src')
    import nexus_connector_core
    core_source = str(Path(nexus_connector_core.__file__).resolve().parents[1])
    program = '''
import sys,time
from pathlib import Path
sys.path[:0]=[sys.argv[1],sys.argv[2]]
from okto_nexus_connector.platform import service_supervision as S
from okto_nexus_connector.platform.service_context import CONTROL,INSTALLATION,read_document,write_document,launch_exclusion
from okto_nexus_connector.errors import ConnectorError
root=Path(sys.argv[3]); cycle,nonce=sys.argv[4:6]
deadline=time.monotonic()+60
while True:
    try:
        with launch_exclusion(root):
            installation=read_document(root/INSTALLATION); control=read_document(root/CONTROL)
            S.validate_child(root,installation,control,cycle,nonce)
            if control['desired']=='running':
                (root/'benign-bootstrap.json').write_text('acknowledged-before-bootstrap')
            write_document(root/CONTROL,{**control,'desired':'draining','launch_requested':False})
        break
    except ConnectorError as error:
        if error.code!='LIFECYCLE_BUSY' or time.monotonic()>=deadline: raise
        time.sleep(.05)
'''
    processes = []
    def spawn(argv, **kwargs):
        if stop_before_handshake:
            service.begin_stop(None)
        command = [argv[0], '-I', '-B', '-X', 'utf8', '-c', program, connector_source, core_source,
            str(root), argv[argv.index('--supervisor-cycle') + 1], argv[argv.index('--supervisor-nonce') + 1]]
        process = subprocess.Popen(command, **kwargs)
        processes.append(process)
        return process
    code = service_supervisor.run(root, service.receipt()['token'], service=service, spawn=spawn)
    assert code == 0 and len(processes) == 1 and processes[0].poll() == 0
    record = read_document(root / 'run' / service_supervision.RECEIPT)
    assert record['child_acknowledged'] and record['launcher_exit_confirmed'] and record['child_exit_confirmed']
    assert record['launcher']['pid'] == processes[0].pid
    assert record['child']['pid'] != record['launcher']['pid']  # this installed venv's real redirector
    assert (root / 'benign-bootstrap.json').exists() is (not stop_before_handshake)
    assert record['phase'] == 'stopped' and record['attempts_started'] == 1


@pytest.mark.parametrize('bad_field,bad_value', [('attempt_nonce', '0' * 32), ('parent_pid', 9999)])
def test_parent_refuses_stale_or_false_ancestry_handshake_before_ack(selected, bad_field, bad_value):
    root, _, service = selected
    assert invoke(selected, lambda *a, **k: child(201, 3)) == 2
    record = read_document(root / 'run' / service_supervision.RECEIPT)
    record.update(phase='running', child=None, child_exit_confirmed=False, launcher_exit_confirmed=False, child_acknowledged=False)
    write_document(root / 'run' / service_supervision.RECEIPT, record)
    declaration = {'revision': 1, 'instance_id': record['instance_id'], 'cycle_id': record['cycle_id'],
        'attempts_started': record['attempts_started'], 'attempt_nonce': record['attempt_nonce'],
        'pid': 301, 'birth_token': 'filetime:301', 'parent_pid': 201}
    declaration[bad_field] = bad_value
    write_document(service_supervision.handshake_path(root, record), declaration)
    runtime = SimpleNamespace(parent_pid=lambda: 201, exited=lambda: False, close=Mock())
    launcher = SimpleNamespace(poll=lambda: None)
    with pytest.raises(ValueError):
        service_supervisor.acknowledge_child(root, record, service.receipt(), service, launcher,
            clock=time.monotonic, sleep=lambda _: None, open_runtime=lambda identity: runtime)
    assert record['child_acknowledged'] is False


def test_failed_ack_publication_retains_parent_guard_until_both_owned_processes_exit(selected):
    root, _, service = selected
    events = []
    running = [True]
    def launcher_wait():
        assert service_supervision.guard(root).locked() is True
        events.append('launcher-exit')
        running[0] = False
        return 0
    process = SimpleNamespace(pid=201, poll=lambda: None if running[0] else 0, wait=launcher_wait)
    def runtime_wait():
        assert service_supervision.guard(root).locked() is True
        events.append('runtime-exit')
        return 3
    runtime = SimpleNamespace(wait=runtime_wait, close=lambda: events.append('runtime-close'))
    def fail_ack(root, record, *args, retain, **kwargs):
        retain(runtime)  # ancestry already verified; publication failure cannot abandon it
        raise OSError('synthetic ACK publication failure')
    result = service_supervisor.run(root, service.receipt()['token'], service=service,
        spawn=lambda *args, **kwargs: process,
        identify_child=lambda _: {'pid': 201, 'birth_token': 'filetime:201'}, acknowledge=fail_ack)
    assert result == 2 and events == ['launcher-exit', 'runtime-exit', 'runtime-close']
    assert service_supervision.guard(root).locked() is False
    assert read_document(root / 'run' / service_supervision.RECEIPT)['phase'] == 'unknown'


def test_retry_policy_uses_runtime_exit_code_not_redirector_exit(selected):
    root, _, service = selected
    now = [0.0]
    def acknowledged(root, record, *args, **kwargs):
        fake_ack(root, record, *args, **kwargs)
        return SimpleNamespace(exited=lambda: True, wait=lambda: 7, close=lambda: None)
    result = service_supervisor.run(root, service.receipt()['token'], service=service,
        spawn=lambda *a, **k: child(201, 0), clock=lambda: now[0], sleep=lambda _: now.__setitem__(0, now[0] + 60),
        identify_child=lambda _: {'pid': 201, 'birth_token': 'filetime:201'}, acknowledge=acknowledged)
    record = read_document(root / 'run' / service_supervision.RECEIPT)
    assert result == 2 and record['last_exit_code'] == 7 and record['launcher_exit_code'] == 0
    assert record['attempts_started'] == 4
