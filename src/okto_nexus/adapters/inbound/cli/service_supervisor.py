"""One persistent foreground supervisor for the installed Windows user task.

Task Scheduler only launches this process. The owned runtime child remains
foreground and is waited for; it is never detached and abandoned. Public
``serve`` and external/container supervision do not enter this module.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import secrets
import subprocess
import sys
from time import monotonic, sleep, time as wall_time

from nexus_connector_core.user_service_supervision import RetryState, reserve_attempt, record_exit

from ...outbound.service_manager.context import CONTEXT_NAME, atomic_json, read_json, validate_context
from ...outbound.service_manager.installation import CONTROL_NAME, InstallationError, ServerInstallation
from ...outbound.service_manager.identity import windows_logon_session
from ...outbound.service_manager.local import launch_exclusion
from ...outbound.service_manager.locking import ExclusiveFileLock, LockBusy
from ...outbound.service_manager.supervision import (
    RECORD_NAME, GUARD_NAME, handle_birth, own_birth, previous_finished,
    read_record, read_handshake, retain_runtime, require_single_supervisor)


def _authorized(installation, token):
    receipt, task = installation.observe()
    if not receipt or receipt['token'] != token:
        raise InstallationError('SUPERVISOR_INSTALLATION_CHANGED', 'The installed supervisor identity changed.')
    require_single_supervisor(task.xml)
    return receipt, task, installation.control(receipt)


@contextmanager
def _initial_exclusion(home, database):
    # The caller selecting native Run may still own launch exclusion when the
    # task begins. Contention is bounded waiting, not a failed child attempt.
    deadline = monotonic() + 30
    with ExitStack() as held:
        while True:
            try:
                held.enter_context(launch_exclusion(home, database))
                break
            except LockBusy:
                if monotonic() >= deadline:
                    raise
                sleep(.05)
        yield


def _await_runtime(home, database, installation, token, record, launcher):
    deadline = monotonic() + 60
    while monotonic() < deadline:
        try:
            with launch_exclusion(home, database):
                receipt = installation.receipt()
                if not receipt or receipt['token'] != token:
                    raise ValueError('Installation changed during handshake')
                current = read_record(home, receipt, installation.instance_id)
                if not current or any(current.get(key) != record.get(key) for key in
                        ('cycle_id', 'attempts_started', 'attempt_nonce', 'parent', 'launcher')):
                    raise ValueError('Attempt changed during handshake')
                try:
                    handshake = read_handshake(home, current)
                except FileNotFoundError:
                    handshake = None
                if handshake is not None:
                    return retain_runtime(launcher, current['launcher']['birth'], handshake), handshake
        except LockBusy:
            pass
        if launcher.poll() is not None:
            raise ValueError('Launcher exited without an acknowledged runtime identity')
        sleep(.05)
    raise InstallationError('SUPERVISOR_HANDSHAKE_TIMEOUT',
        'The runtime identity was not confirmed within the technical 60-second handshake window.')


def run(home: Path, database: Path, token: str, *, installation=None) -> int:
    installation = installation or ServerInstallation(home, database)
    guard = ExclusiveFileLock(home / GUARD_NAME)
    record = None
    child = None
    runtime = None
    state = RetryState()

    def publish():
        record.update(asdict(state))
        # The serialized monotonic value is diagnostic; another parent must
        # reconcile identities instead of resuming this clock or its budget.
        atomic_json(home / RECORD_NAME, record)

    def desired():
        receipt = installation.receipt()
        if not receipt or receipt['token'] != token:
            raise InstallationError('SUPERVISOR_INSTALLATION_CHANGED', 'The selected installation changed.')
        control = installation.control(receipt)
        if control.get('cycle_id') != record['cycle_id']:
            raise InstallationError('SUPERVISOR_CYCLE_UNCONFIRMED', 'The selected supervisor cycle changed.')
        return control['desired'] == 'running'

    try:
        guard.acquire()
        with _initial_exclusion(home, database):
            receipt, task, control = _authorized(installation, token)
            logon = windows_logon_session()
            if not task.enabled or (control['desired'] == 'draining' and control.get('logon_session') == logon):
                return 0
            previous = read_record(home, receipt, installation.instance_id)
            if not previous_finished(previous):
                raise InstallationError('SUPERVISOR_RECOVERY_UNCONFIRMED',
                    'Reconcile the prior parent and child; no process death or work release was inferred.')
            selected = (control.get('launch_requested') is True
                        and type(control.get('cycle_id')) is str and len(control['cycle_id']) == 32)
            if previous and previous.get('logon_session') == logon and not selected:
                return 3  # no new explicit cycle; a queued duplicate cannot reset it
            cycle = control['cycle_id'] if selected else secrets.token_hex(16)
            context = validate_context(read_json(home / CONTEXT_NAME))
            record = {'revision': 1, 'token': token, 'instance_id': installation.instance_id,
                      'cycle_id': cycle, 'logon_session': logon,
                      'parent': {'pid': os.getpid(), 'birth': own_birth()},
                      'launcher': None, 'child': None, 'child_acknowledged': False,
                      'next_retry_at_epoch': None}
            publish()
            atomic_json(home / CONTROL_NAME, {'revision': 1, 'token': token,
                'desired': 'running', 'launch_requested': False,
                'logon_session': logon, 'cycle_id': cycle})
        while True:
            # A stop during backoff never waits for the full minute to latch.
            if not desired():
                state = reserve_attempt(state, monotonic(), False)
                publish()
                return 0
            if state.phase == 'backoff' and monotonic() < state.next_retry_monotonic:
                sleep(max(0, min(.2, state.next_retry_monotonic - monotonic())))
                continue
            try:
                with launch_exclusion(home, database):
                    _, task, _ = _authorized(installation, token)
                    state = reserve_attempt(state, monotonic(), desired() and task.enabled)
                    record['next_retry_at_epoch'] = None
                    if state.phase != 'running':
                        publish()
                        return 0 if state.phase == 'stopped' else 3
                    # Persist the reservation before spawning. If publication
                    # of its identity is lost, no later parent may replay it.
                    record['child'] = None
                    record['launcher'] = None
                    record['child_acknowledged'] = False
                    record['attempt_nonce'] = secrets.token_hex(16)
                    publish()
                    executable = Path(context['executable'])
                    if executable.name.lower() == 'python.exe':
                        executable = executable.with_name('pythonw.exe')
                    command = [str(executable), '-I', '-B', '-X', 'utf8', '-m',
                        'okto_nexus.adapters.inbound.cli.supervised_service',
                        str(home), str(database), token, '--supervisor-cycle', cycle,
                        '--supervisor-nonce', record['attempt_nonce']]
                    child = subprocess.Popen(command, cwd=context['cwd'], env=context['environment'],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, close_fds=True)
                    record['launcher'] = {'pid': child.pid, 'birth': handle_birth(child._handle),
                                          'physical_exit': False}
                    publish()
            except LockBusy:
                sleep(.05)
                continue
            # Windows venv pythonw is a redirector. Retain and verify the actual
            # runtime handle as well, before acknowledging any bootstrap.
            runtime, handshake = _await_runtime(home, database, installation, token, record, child)
            with _initial_exclusion(home, database):
                receipt = installation.receipt()
                current = read_record(home, receipt, installation.instance_id)
                if (current.get('attempt_nonce') != record['attempt_nonce'] or current['phase'] != 'running'
                        or installation.control(receipt).get('cycle_id') != cycle
                        or runtime.poll() is not None or child.poll() is not None):
                    raise ValueError('Runtime identity changed before acknowledgment')
                record['child'] = {'pid': runtime.pid, 'birth': runtime.birth, 'physical_exit': False}
                record['child_acknowledged'] = True
                publish()  # identity ACK only; the child rechecks stop before bootstrap
            launcher_code = child.wait()
            code = runtime.wait()
            record['launcher'].update(physical_exit=True, exit_code=launcher_code)
            record['child']['physical_exit'] = True
            record['child']['exit_code'] = code
            state = record_exit(state, monotonic(), code, desired())
            runtime.close()
            runtime = None
            child = None
            if state.phase == 'backoff':
                record['next_retry_at_epoch'] = wall_time() + 60
            publish()
            if state.phase in {'stopped', 'exhausted'}:
                return 0 if state.phase == 'stopped' else 3
    except LockBusy:
        return 3
    except (Exception, SystemExit, KeyboardInterrupt) as error:
        if record is not None:
            state = replace(state, phase='unknown', next_retry_monotonic=None)
            record['reason'] = error.code if isinstance(error, InstallationError) else 'SUPERVISOR_RECOVERY_UNCONFIRMED'
            try:
                publish()
            except OSError:
                pass
        return 2
    finally:
        if child is not None:
            # Publication or observer failure is not authorization to abandon
            # or kill a foreground runtime. A canonical stop can still drain it.
            while child.poll() is None:
                try:
                    child.wait()
                except (KeyboardInterrupt, SystemExit):
                    continue
        if runtime is not None:
            try:
                runtime.wait()
            finally:
                runtime.close()
        guard.release()


if __name__ == '__main__':
    raise SystemExit(run(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]))
