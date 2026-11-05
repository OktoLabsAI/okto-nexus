"""Explicit pre-bootstrap fencing; never a runtime cancellation or PID takeover."""
import json
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest

from okto_nexus.adapters.inbound.cli.service import run_service
from okto_nexus.adapters.outbound.service_manager.context import atomic_json, document_revision, read_json
from okto_nexus.adapters.outbound.service_manager.local import LAUNCH_NAME, LocalServerLifecycle, launch_exclusion
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock


@pytest.fixture
def selected(tmp_path):
    home = tmp_path / 'nexus'
    home.mkdir()
    database = home / 'nexus.db'
    adapter = LocalServerLifecycle(home=home, database=database, host='127.0.0.1', port=1)
    # A live/unrelated PID is deliberately not evidence for or against recovery.
    receipt = {'revision': 1, 'instance_id': server_instance_id(home, database),
               'state': 'pending', 'token': 'pending-token', 'pid': os.getpid()}
    atomic_json(home / LAUNCH_NAME, receipt)
    return adapter, receipt, document_revision(receipt)


def test_recovery_fences_late_child_and_is_idempotent(selected, monkeypatch):
    from okto_nexus.adapters.inbound.cli import service_process
    adapter, receipt, revision = selected
    assert adapter.inspect()['launch_recovery']['receipt_revision'] == revision
    spawn = Mock(side_effect=AssertionError('Recovery must not start a process'))
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    result = adapter.recover_start(expected_revision=revision)
    assert result['recovered'] and result['changed'] and result['state'] == 'stopped'
    assert adapter.recover_start(expected_revision=revision)['changed'] is False
    assert service_process.run(adapter.home, adapter.database, receipt['token']) == 2
    assert not adapter.database.exists()
    assert not (adapter.home / 'nexus.serve.lock').exists()
    assert adapter.inspect()['reason'] == 'STARTUP_ABORTED'
    assert read_json(adapter.home / LAUNCH_NAME)['recovered_from'] == revision


@pytest.mark.parametrize('guard', ['launch', 'home', 'database'])
def test_recovery_refuses_launch_or_owner_exclusion(selected, guard):
    adapter, _, revision = selected
    before = (adapter.home / LAUNCH_NAME).read_bytes()
    if guard == 'launch':
        with launch_exclusion(adapter.home, adapter.database):
            result = adapter.recover_start(expected_revision=revision)
    else:
        lock = ExclusiveFileLock(adapter.home / 'nexus.serve.guard' if guard == 'home'
            else adapter.database.with_name(adapter.database.name + '.serve.guard'))
        lock.acquire()
        try:
            result = adapter.recover_start(expected_revision=revision)
        finally:
            lock.release()
    assert not result['recovered'] and result['reason'] == 'RECOVERY_OWNER_UNCONFIRMED'
    assert result['state'] != 'stopped'
    assert (adapter.home / LAUNCH_NAME).read_bytes() == before


@pytest.mark.parametrize('change,reason', [
    ({'token': 'new-token'}, 'LAUNCH_REVISION_CONFLICT'),
    ({'state': 'owned'}, 'RECOVERY_REQUIRES_PENDING'),
    ({'instance_id': 'foreign'}, 'INVALID_LAUNCH_RECEIPT'),
    ({'revision': 99}, 'INVALID_LAUNCH_RECEIPT'),
])
def test_changed_or_ineligible_receipt_is_preserved(selected, change, reason):
    adapter, receipt, revision = selected
    atomic_json(adapter.home / LAUNCH_NAME, {**receipt, **change})
    before = (adapter.home / LAUNCH_NAME).read_bytes()
    result = adapter.recover_start(expected_revision=revision)
    assert not result['recovered'] and result['reason'] == reason
    if reason == 'LAUNCH_REVISION_CONFLICT':
        assert result['state'] == 'unknown'
    assert (adapter.home / LAUNCH_NAME).read_bytes() == before


def test_installed_supervisor_is_not_modified(selected):
    adapter, _, revision = selected
    path = adapter.home / 'service-installation.json'
    path.write_text('{"preserve":true}', encoding='utf-8')
    assert adapter.recover_start(expected_revision=revision)['reason'] == 'RECOVERY_REQUIRES_DETACHED'
    assert path.read_text(encoding='utf-8') == '{"preserve":true}'


def test_response_loss_confirms_same_recovery_without_rewriting(selected, monkeypatch):
    from okto_nexus.adapters.outbound.service_manager import local
    adapter, _, revision = selected
    def lose(path, receipt):
        atomic_json(path, receipt)
        raise OSError('response lost')
    monkeypatch.setattr(local, 'atomic_json', lose)
    assert adapter.recover_start(expected_revision=revision)['reason'] == 'RECOVERY_UNCONFIRMED'
    result = adapter.recover_start(expected_revision=revision)
    assert result['recovered'] and not result['changed']


def test_status_and_recovery_survive_missing_saved_interpreter(selected, capsys):
    adapter, _, revision = selected
    path = adapter.home / 'service-context.json'
    atomic_json(path, {'revision': 1, 'component': 'server',
        'executable': str(adapter.home / 'removed-venv' / 'python.exe'),
        'environment_prefix': str(adapter.home / 'removed-venv'), 'cwd': str(adapter.home),
        'arguments': ['--home', str(adapter.home), '--embedding-mode', 'off'], 'environment': {}})
    before = path.read_bytes()
    assert run_service(['status', '--home', str(adapter.home), '--json']) == 3
    assert json.loads(capsys.readouterr().out)['launch_recovery']['receipt_revision'] == revision
    assert run_service(['recover-start', '--home', str(adapter.home), '--expected-revision', revision, '--json']) == 0
    assert json.loads(capsys.readouterr().out)['recovered']
    assert path.read_bytes() == before


def test_absent_recovery_and_cli_validation_do_not_initialize(tmp_path, capsys):
    home = tmp_path / 'absent'
    args = ['recover-start', '--home', str(home), '--json']
    with pytest.raises(SystemExit):
        run_service(args)
    assert run_service([*args, '--expected-revision', '0' * 64]) == 3
    assert not home.exists()
    assert json.loads(capsys.readouterr().out)['reason'] == 'NO_PENDING_LAUNCH'


def test_actual_cli_recovery_and_late_child_are_fenced(selected, tmp_path):
    adapter, receipt, revision = selected
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE',
        'LOCALAPPDATA', 'APPDATA', 'PATH', 'LANG', 'LC_ALL', 'HOME'}}
    result = subprocess.run([sys.executable, '-I', '-m', 'okto_nexus.adapters.inbound.cli.main', 'service', 'recover-start',
        '--home', str(adapter.home), '--expected-revision', revision, '--json'],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert json.loads(result.stdout)['recovered']
    late = subprocess.run([sys.executable, '-I', '-m',
        'okto_nexus.adapters.inbound.cli.service_process', str(adapter.home), str(adapter.database), receipt['token']],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert late.returncode == 2, (late.stdout, late.stderr)
    assert not adapter.database.exists()
