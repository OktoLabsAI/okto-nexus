"""Single-server lock (spec S1, C3 / D4 / TS7-adjacent unit coverage)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

from okto_nexus.adapters.inbound.http.lock import ServeLock
from okto_nexus.errors import ErrorCode, OktoNexusError


def test_acquire_writes_pid_and_release_removes(tmp_path):
    lock = ServeLock(tmp_path)
    lock.acquire(pid=4242)
    payload = json.loads(lock.path.read_text(encoding="utf-8"))
    assert payload["pid"] == 4242
    lock.release()
    assert not lock.path.exists()
    lock.release()  # idempotent


def test_second_acquire_fails_citing_active_pid(tmp_path):
    first = ServeLock(tmp_path)
    first.acquire(pid=os.getpid())
    second = ServeLock(tmp_path)
    with pytest.raises(OktoNexusError) as excinfo:
        second.acquire(pid=2222)
    assert excinfo.value.code == ErrorCode.CONFIG_ERROR
    assert str(os.getpid()) in excinfo.value.message  # PID is surfaced to the operator
    assert first.path.exists()  # loser never clobbers a fresh lock
    first.release()


def test_stale_heartbeat_never_steals_live_os_lock(tmp_path):
    owner = ServeLock(tmp_path)
    owner.acquire()
    old = time.time() - 3600
    os.utime(owner.path, (old, old))
    successor = ServeLock(tmp_path)
    try:
        with pytest.raises(OktoNexusError):
            successor.acquire()
        assert owner._payload()['generation'] == owner.generation
    finally:
        owner.release()


def test_heartbeat_refreshes_mtime(tmp_path):
    lock = ServeLock(tmp_path)
    lock.acquire()
    old = time.time() - 120
    os.utime(lock.path, (old, old))
    lock.heartbeat()
    assert time.time() - lock.path.stat().st_mtime < 5
    lock.release()


def test_context_manager_releases_on_exit(tmp_path):
    with ServeLock(tmp_path) as lock:
        assert lock.path.exists()
    assert not lock.path.exists()


def test_canonical_home_alias_and_shared_database_are_exclusive(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    db = tmp_path / 'shared' / 'nexus.db'
    with ServeLock(home, db_path=db):
        with pytest.raises(OktoNexusError):
            ServeLock(home / '..' / 'home', db_path=tmp_path / 'other.db').acquire()
        with pytest.raises(OktoNexusError):
            ServeLock(tmp_path / 'second', db_path=db).acquire()
        # A failed second-lock acquire must release its first lock.
        with ServeLock(tmp_path / 'second', db_path=tmp_path / 'independent.db'):
            pass
    with ServeLock(tmp_path / 'second', db_path=db):
        pass


@pytest.mark.parametrize('observed', [False, None])
def test_legacy_stale_or_reused_pid_is_not_dead_proof(tmp_path, monkeypatch, observed):
    from okto_nexus.adapters.inbound.http import lock as module
    legacy = tmp_path / 'nexus.serve.lock'
    original = json.dumps({'pid': 4242, 'host': socket.gethostname()})
    legacy.write_text(original)
    os.utime(legacy, (1, 1))
    monkeypatch.setattr(module, 'process_exited', lambda pid: observed)
    monkeypatch.setattr(os, 'kill', lambda *_: pytest.fail('Do not signal historical PIDs'))
    with pytest.raises(OktoNexusError) as refusal:
        ServeLock(tmp_path).acquire()
    assert refusal.value.details['reason'] == 'legacy_owner_unconfirmed'
    assert legacy.read_text() == original


def test_confirmed_dead_legacy_owner_can_upgrade(tmp_path, monkeypatch):
    from okto_nexus.adapters.inbound.http import lock as module
    (tmp_path / 'nexus.serve.lock').write_text(json.dumps({'pid': 4242, 'host': socket.gethostname()}))
    monkeypatch.setattr(module, 'process_exited', lambda pid: True)
    with ServeLock(tmp_path) as lock:
        assert lock._payload()['lock_version'] == 2


def test_old_owner_release_cannot_remove_changed_generation(tmp_path):
    lock = ServeLock(tmp_path)
    lock.acquire()
    value = {**lock._payload(), 'generation': 'external-change'}
    lock.path.write_text(json.dumps(value))
    lock.release()
    assert json.loads(lock.path.read_text()) == value
    with ServeLock(tmp_path):
        pass


_CHILD = '''
from pathlib import Path
import os, sys, threading
from okto_nexus.adapters.inbound.http.lock import ServeLock
from okto_nexus.errors import OktoNexusError
threading.Timer(20, lambda: os._exit(9)).start()
lock = ServeLock(Path(sys.argv[1]))
try:
    lock.acquire()
except OktoNexusError:
    print('busy', flush=True)
    os._exit(0)
print('owned', flush=True)
sys.stdin.readline()
os._exit(0)  # abrupt process death: deliberately no release or Python cleanup
'''


def test_two_real_processes_one_owner_and_crash_releases_os_lock(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    children = [subprocess.Popen([sys.executable, '-u', '-c', _CHILD, str(tmp_path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env) for _ in range(2)]
    try:
        reports = [child.stdout.readline().strip() for child in children]
        assert sorted(reports) == ['busy', 'owned']
        with pytest.raises(OktoNexusError):
            ServeLock(tmp_path).acquire()
        for child, report in zip(children, reports):
            if report == 'owned':
                child.communicate('crash\n', timeout=15)
            else:
                child.communicate(timeout=15)
            assert child.returncode == 0
        # A stale v2 PID record remains, but the OS lock was released by exit.
        assert (tmp_path / 'nexus.serve.lock').exists()
        with ServeLock(tmp_path):
            pass
    finally:
        for child in children:
            if child.poll() is None:
                child.communicate('stop\n', timeout=25)


def test_serve_loser_does_not_bootstrap_or_migrate(tmp_path, monkeypatch):
    from okto_nexus.adapters.inbound.cli.serve import run_serve
    from okto_nexus.bootstrap import dependencies
    monkeypatch.setattr(dependencies, 'bootstrap', lambda *_: pytest.fail('bootstrap before exclusion'))
    with ServeLock(tmp_path):
        assert run_serve(['--home', str(tmp_path)], env={'OKTO_NEXUS_NO_BANNER': '1'}) == 1
    assert not (tmp_path / 'nexus.db').exists()


def test_failed_bootstrap_releases_both_locks(tmp_path, monkeypatch):
    from okto_nexus.adapters.inbound.cli.serve import run_serve
    from okto_nexus.bootstrap import dependencies
    def fail(*_):
        raise OktoNexusError(ErrorCode.CONFIG_ERROR, 'synthetic bootstrap failure', {})
    monkeypatch.setattr(dependencies, 'bootstrap', fail)
    assert run_serve(['--home', str(tmp_path)]) == 1
    with ServeLock(tmp_path):
        pass


def test_unavailable_lock_storage_reports_failure_without_bootstrap(tmp_path, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli.serve import run_serve
    from okto_nexus.bootstrap import dependencies
    def fail(*_):
        raise PermissionError('synthetic lock storage denial')
    monkeypatch.setattr(ServeLock, 'acquire', fail)
    monkeypatch.setattr(dependencies, 'bootstrap', lambda *_: pytest.fail('bootstrap after lock failure'))
    assert run_serve(['--home', str(tmp_path)]) == 1
    assert 'Cannot acquire Server instance exclusion' in capsys.readouterr().err
