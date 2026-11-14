"""One parent, bounded child selection and fail-closed ownership; no OS tasks."""
from dataclasses import replace
import os
import time
from unittest.mock import Mock

import pytest

from test_user_service_installation import host as host, install
from okto_nexus.adapters.inbound.cli import service_supervisor as runner
from okto_nexus.adapters.outbound.service_manager import supervision
from okto_nexus.adapters.outbound.service_manager.context import atomic_json, read_json
from okto_nexus.adapters.outbound.service_manager.installation import CONTROL_NAME, InstallationError
from okto_nexus.adapters.outbound.service_manager.upgrade import ServerUpgradeHost
from okto_nexus.service_upgrade import UpgradeError
from okto_nexus.application.service_lifecycle import ServiceLifecycle


@pytest.fixture
def owned(request, monkeypatch):
    adapter, tasks, receipt = install(request.getfixturevalue('host'))
    clock = [0.0]
    children, selections = [], []
    monkeypatch.setattr(runner, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(runner, 'wall_time', lambda: 1000 + clock[0])
    monkeypatch.setattr(runner, 'sleep', lambda delay: clock.__setitem__(0, clock[0] + max(60, delay)))
    monkeypatch.setattr(runner, 'windows_logon_session', lambda: 'test-logon')
    monkeypatch.setattr(runner, 'own_birth', lambda: 800)
    monkeypatch.setattr(runner, 'handle_birth', lambda handle: 900 + handle)
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'alive' if pid == os.getpid() else 'exited')

    class Child:
        def __init__(self, code=3, callback=None):
            self.pid = 1000 + len(children)
            self._handle = self.pid
            self.code, self.callback, self.exited = code, callback, False

        def wait(self):
            value = read_json(adapter.home / supervision.RECORD_NAME)
            assert value['phase'] in {'running', 'unknown'}
            assert value['attempts_started'] == len(children)
            if self.callback:
                self.callback()
            self.exited = True
            return self.code

        def poll(self):
            return self.code if self.exited else None

    def spawn(command, **options):
        value = read_json(adapter.home / supervision.RECORD_NAME)
        assert value['phase'] == 'running' and value['child'] is None
        assert value['attempts_started'] == len(children) + 1
        assert 'creationflags' not in options and 'start_new_session' not in options
        assert command[1:5] == ['-I', '-B', '-X', 'utf8']
        assert command[-4] == '--supervisor-cycle' and command[-3] == value['cycle_id']
        assert command[-2] == '--supervisor-nonce' and command[-1] == value['attempt_nonce']
        selections.append(clock[0])
        child = Child()
        children.append(child)
        return child

    monkeypatch.setattr(runner.subprocess, 'Popen', spawn)
    class Runtime:
        def __init__(self, child):
            self.child = child
            self.pid, self.birth = child.pid + 100000, child._handle + 9000
        def poll(self): return self.child.poll()
        def wait(self):
            assert self.child.exited
            return self.child.code
        def close(self): pass
    def handshake(home, database, installation, token, record, launcher):
        assert read_json(home / supervision.RECORD_NAME)['launcher']['pid'] == launcher.pid
        return Runtime(launcher), {'parent_pid': launcher.pid}
    monkeypatch.setattr(runner, '_await_runtime', handshake)
    return adapter, tasks, receipt, clock, children, selections, Child


def run(owned):
    adapter, _, receipt, *_ = owned
    return runner.run(adapter.home, adapter.database, receipt['token'], installation=adapter.installation)


def stop(owned):
    adapter = owned[0]
    control = read_json(adapter.home / CONTROL_NAME)
    atomic_json(adapter.home / CONTROL_NAME, {**control, 'desired': 'draining'})


def test_one_parent_exhausts_exactly_four_children_and_preserves_delay(owned):
    assert run(owned) == 3
    adapter, _, _, _, children, selections, _ = owned
    assert len(children) == 4 and selections == [0, 60, 120, 180]
    value = read_json(adapter.home / supervision.RECORD_NAME)
    assert value['phase'] == 'exhausted' and value['attempts_started'] == 4
    assert value['child']['physical_exit'] is True and value['last_exit_code'] == 3


def test_stop_during_backoff_prevents_second_spawn(owned, monkeypatch):
    monkeypatch.setattr(runner, 'sleep', lambda delay: stop(owned))
    assert run(owned) == 0
    assert len(owned[4]) == 1
    assert read_json(owned[0].home / supervision.RECORD_NAME)['phase'] == 'stopped'


def test_exit_zero_without_stop_latch_is_bounded_failure(owned, monkeypatch):
    original = runner.subprocess.Popen
    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        child.code = 0
        return child
    monkeypatch.setattr(runner.subprocess, 'Popen', spawn)
    assert run(owned) == 3 and len(owned[4]) == 4


def test_stop_latch_after_child_exit_stops_parent_without_retry(owned, monkeypatch):
    original = runner.subprocess.Popen
    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        child.callback = lambda: stop(owned)
        return child
    monkeypatch.setattr(runner.subprocess, 'Popen', spawn)
    assert run(owned) == 0 and len(owned[4]) == 1


def test_spawn_uncertainty_consumes_reservation_and_never_replays(owned, monkeypatch):
    spawn = Mock(side_effect=OSError('ambiguous launch'))
    monkeypatch.setattr(runner.subprocess, 'Popen', spawn)
    assert run(owned) == 2 and spawn.call_count == 1
    value = read_json(owned[0].home / supervision.RECORD_NAME)
    assert value['phase'] == 'unknown' and value['attempts_started'] == 1 and value['child'] is None
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'exited')
    assert supervision.previous_finished(value) is False
    stop(owned)
    with pytest.raises(InstallationError, match='SUPERVISOR_RECOVERY_UNCONFIRMED'):
        owned[0].installation.start()
    assert spawn.call_count == 1


def test_duplicate_entry_does_not_reset_exhausted_cycle(owned, monkeypatch):
    assert run(owned) == 3
    original = (owned[0].home / supervision.RECORD_NAME).read_bytes()
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'exited')
    assert run(owned) == 3 and len(owned[4]) == 4
    assert (owned[0].home / supervision.RECORD_NAME).read_bytes() == original


def test_explicit_start_requires_stop_and_reuses_response_loss_cycle(owned, monkeypatch):
    assert run(owned) == 3
    adapter = owned[0]
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'exited')
    with pytest.raises(InstallationError, match='SUPERVISOR_CYCLE_NOT_STOPPED'):
        adapter.installation.start()
    stop(owned)
    assert adapter.installation.start()
    selected = read_json(adapter.home / CONTROL_NAME)
    assert adapter.installation.start()
    assert read_json(adapter.home / CONTROL_NAME) == selected


def test_native_retry_policy_is_refused_before_child_selection(owned):
    adapter, tasks, receipt, *_ = owned
    current = tasks.tasks[receipt['name']]
    xml = current.xml.replace('</Settings>', '<RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure></Settings>')
    changed = replace(current, xml=xml)
    tasks.tasks[receipt['name']] = changed
    atomic_json(adapter.installation.path, {**receipt, 'native_xml': xml, 'native_digest': changed.digest})
    assert run(owned) == 2 and not owned[4]
    assert not (adapter.home / supervision.RECORD_NAME).exists()


def test_upgrade_old_policy_refused_without_mutation(owned):
    adapter, tasks, receipt, *_ = owned
    task = tasks.tasks[receipt['name']]
    old_xml = task.xml.replace('</Settings>', '<RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure></Settings>')
    before = list(tasks.calls)
    with pytest.raises(UpgradeError) as caught:
        ServerUpgradeHost.propose(old_xml, adapter.installation.definition(adapter.context, receipt['token']))
    assert caught.value.code == supervision.POLICY_ERROR
    assert tasks.calls == before


def test_status_requires_parent_exit_even_after_child_stopped(owned, monkeypatch):
    original = runner.subprocess.Popen
    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        child.callback = lambda: stop(owned)
        return child
    monkeypatch.setattr(runner.subprocess, 'Popen', spawn)
    assert run(owned) == 0
    adapter, _, receipt, *_ = owned
    control = read_json(adapter.home / CONTROL_NAME)
    assert supervision.status(adapter.home, receipt, adapter.installation.instance_id, control)[1:] == ('stopping', 'SUPERVISOR_PENDING')
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'exited')
    assert supervision.status(adapter.home, receipt, adapter.installation.instance_id, control)[1:] == (None, None)


def test_old_installation_token_requires_exact_previous_exit(owned, monkeypatch):
    assert run(owned) == 3
    adapter, _, receipt, *_ = owned
    changed = {**receipt, 'token': 'f' * 32}
    with pytest.raises(InstallationError):
        supervision.read_record(adapter.home, changed, adapter.installation.instance_id)
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'exited')
    assert supervision.read_record(adapter.home, changed, adapter.installation.instance_id) is None


def test_child_bootstrap_is_fenced_by_parent_and_exact_child_birth(owned, monkeypatch):
    adapter, _, receipt, *_ = owned
    original = runner.subprocess.Popen
    observed = []
    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        def callback():
            value = read_json(adapter.home / supervision.RECORD_NAME)
            actual = value['child']
            supervision.validate_child(adapter.home, receipt, adapter.installation.instance_id,
                value['cycle_id'], actual['pid'], actual['birth'], value['attempt_nonce'])
            with pytest.raises(InstallationError):
                supervision.validate_child(adapter.home, receipt, adapter.installation.instance_id,
                    value['cycle_id'], actual['pid'], actual['birth'] + 1, value['attempt_nonce'])
            observed.append(True)
            stop(owned)
        child.callback = callback
        return child
    monkeypatch.setattr(runner.subprocess, 'Popen', spawn)
    assert run(owned) == 0 and observed == [True]


def test_stop_preserves_cycle_but_clears_pending_native_launch(owned):
    adapter = owned[0]
    adapter.installation.start()
    selected = read_json(adapter.home / CONTROL_NAME)
    assert selected['launch_requested'] is True
    adapter.installation.begin_stop(None)
    stopped = read_json(adapter.home / CONTROL_NAME)
    assert stopped['cycle_id'] == selected['cycle_id']
    assert stopped['launch_requested'] is False and stopped['desired'] == 'draining'


def test_new_logon_reconciles_prior_owner_before_new_cycle(owned, monkeypatch):
    assert run(owned) == 3
    old = read_json(owned[0].home / supervision.RECORD_NAME)
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'exited')
    monkeypatch.setattr(runner, 'windows_logon_session', lambda: 'new-logon')
    owned[4].clear()
    assert run(owned) == 3 and len(owned[4]) == 4
    new = read_json(owned[0].home / supervision.RECORD_NAME)
    assert new['cycle_id'] != old['cycle_id'] and new['attempts_started'] == 4


def test_initial_launch_guard_contention_waits_without_consuming_attempt(owned, monkeypatch):
    from contextlib import contextmanager
    original = runner.launch_exclusion
    calls = [0]
    @contextmanager
    def contend(home, database):
        calls[0] += 1
        if calls[0] == 1:
            raise runner.LockBusy()
        with original(home, database):
            yield
    monkeypatch.setattr(runner, 'launch_exclusion', contend)
    assert run(owned) == 3 and len(owned[4]) == 4
    assert read_json(owned[0].home / supervision.RECORD_NAME)['attempts_started'] == 4


def test_current_process_birth_is_exact_and_never_signaled():
    birth = supervision.own_birth()
    assert supervision.process_state(os.getpid(), birth) == 'alive'
    assert supervision.process_state(os.getpid(), birth + 1) == 'exited'
    assert supervision.process_state(None, birth) == 'unknown'


@pytest.mark.parametrize('changes', [
    {'attempts_started': 1}, {'child': None}, {'next_retry_monotonic': 0},
])
def test_exhaustion_receipt_requires_complete_budget_and_child_exit(owned, changes):
    assert run(owned) == 3
    adapter, _, receipt, *_ = owned
    value = read_json(adapter.home / supervision.RECORD_NAME)
    atomic_json(adapter.home / supervision.RECORD_NAME, {**value, **changes})
    with pytest.raises(InstallationError, match='SUPERVISOR_RECEIPT_INVALID'):
        supervision.read_record(adapter.home, receipt, adapter.installation.instance_id)


def test_child_publication_failure_waits_for_owned_child_and_preserves_ambiguity(owned, monkeypatch):
    original = runner.atomic_json
    def fail_publication(path, value):
        if path.name == supervision.RECORD_NAME and value.get('child') is not None:
            raise OSError('publication failed after spawn')
        return original(path, value)
    monkeypatch.setattr(runner, 'atomic_json', fail_publication)
    assert run(owned) == 2
    assert len(owned[4]) == 1 and owned[4][0].exited is True
    value = read_json(owned[0].home / supervision.RECORD_NAME)
    assert value['attempts_started'] == 1 and value['child'] is None
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'exited')
    assert not supervision.previous_finished(value)


def test_runtime_child_checks_cycle_before_bootstrap_and_preserves_control(owned, monkeypatch):
    from okto_nexus.adapters.inbound.cli import supervised_service
    adapter, _, receipt, *_ = owned
    cycle = 'c' * 32
    value = {'revision': 1, 'token': receipt['token'], 'instance_id': adapter.installation.instance_id,
             'cycle_id': cycle, 'logon_session': 'test-logon', 'attempts_started': 1,
             'phase': 'running', 'next_retry_monotonic': None, 'last_exit_code': None,
             'parent': {'pid': 9999, 'birth': 200},
             'launcher': {'pid': 8888, 'birth': 90, 'physical_exit': False},
             'child': {'pid': os.getpid(), 'birth': 100, 'physical_exit': False},
             'attempt_nonce': 'e' * 32, 'child_acknowledged': True}
    atomic_json(adapter.home / supervision.RECORD_NAME, value)
    control = read_json(adapter.home / CONTROL_NAME)
    atomic_json(adapter.home / CONTROL_NAME, {**control, 'cycle_id': cycle})
    monkeypatch.setattr(supervision, 'own_birth', lambda: 100)
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'alive')
    monkeypatch.setattr(supervision, 'join_parent', lambda *args, **kwargs: True)
    serve = Mock(return_value=1)
    monkeypatch.setattr('okto_nexus.adapters.inbound.cli.serve.run_serve', serve)
    assert supervised_service.run(adapter.home, adapter.database, receipt['token'],
        installation=adapter.installation, supervisor_cycle='d' * 32, supervisor_nonce='e' * 32) == 2
    serve.assert_not_called()
    assert supervised_service.run(adapter.home, adapter.database, receipt['token'],
        installation=adapter.installation, supervisor_cycle=cycle, supervisor_nonce='e' * 32) == 1
    serve.assert_called_once()
    assert read_json(adapter.home / CONTROL_NAME)['cycle_id'] == cycle


def test_stop_exhausted_supervisor_does_not_assert_runtime_work_drained(owned, monkeypatch):
    assert run(owned) == 3
    adapter = owned[0]
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'exited')
    result = ServiceLifecycle(adapter, monotonic=time.monotonic, sleep=time.sleep).stop(timeout=2)
    assert result['state'] == 'stopped'
    assert result['shutdown_outcome'] == 'unconfirmed'
    assert result['supervision_scope'] == 'supervisor_only'
    assert result['runtime_work_settlement'] == 'not_asserted'
    assert read_json(adapter.home / CONTROL_NAME)['supervisor_only_stop'] is True


def test_supervisor_only_cleanup_preserves_runtime_data_without_claiming_settlement(owned, monkeypatch):
    assert run(owned) == 3
    adapter, tasks, *_ = owned
    monkeypatch.setattr(supervision, 'process_state', lambda pid, birth: 'exited')
    marker = adapter.home/'retained-user-state.txt'
    marker.write_text('uncertain work remains retained')
    result = ServiceLifecycle(adapter, monotonic=time.monotonic, sleep=time.sleep).uninstall_user_service(timeout=2)
    assert result['installation_state'] == 'absent'
    assert marker.read_text() == 'uncertain work remains retained'
    assert (adapter.home/supervision.RECORD_NAME).exists()
    assert not tasks.tasks


def test_handshake_cannot_change_nonce_or_attempt(owned):
    adapter = owned[0]
    record = {'instance_id':adapter.installation.instance_id,'cycle_id':'a'*32,
              'attempts_started':1,'attempt_nonce':'b'*32}
    path = supervision.handshake_path(adapter.home,record['cycle_id'],1)
    atomic_json(path,{**record,'revision':1,'pid':100,'birth':200,'parent_pid':300,
                      'attempt_nonce':'c'*32})
    with pytest.raises(ValueError,match='reserved attempt'):
        supervision.read_handshake(adapter.home,record)


def test_retained_runtime_rejects_reused_process_birth():
    with pytest.raises(OSError,match='identity changed'):
        supervision.RetainedProcess(os.getpid(),supervision.own_birth()+1)
