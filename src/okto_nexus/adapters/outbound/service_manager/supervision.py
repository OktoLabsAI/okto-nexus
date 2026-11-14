"""Host-owned supervisor receipts and exact Windows process observations."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET

from nexus_connector_core.user_service_supervision import RetryState

from .context import read_json
from .installation import InstallationError

RECORD_NAME = 'service-supervisor.json'
GUARD_NAME = 'service-supervisor.guard'
POLICY_ERROR = 'SERVICE_SUPERVISION_POLICY_CHANGED'


def require_single_supervisor(xml):
    root = ET.fromstring(xml)
    if root.find('{http://schemas.microsoft.com/windows/2004/02/mit/task}Settings/'
                 '{http://schemas.microsoft.com/windows/2004/02/mit/task}RestartOnFailure') is not None:
        raise InstallationError(POLICY_ERROR,
            'The old task has a separate native retry policy. Explicitly stop, uninstall and install '
            'the selected user service to adopt the single foreground supervisor; retain all data.')


def _kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel


class RetainedProcess:
    """Query/synchronize only; this observer cannot terminate a process."""
    def __init__(self, pid, birth):
        self.kernel = _kernel()
        self.handle = self.kernel.OpenProcess(0x100000 | 0x1000, False, pid)
        if not self.handle:
            raise OSError('Runtime handle could not be retained')
        try:
            if handle_birth(self.handle) != birth:
                raise OSError('Runtime process identity changed')
        except BaseException:
            self.close()
            raise
        self.pid, self.birth = pid, birth

    def poll(self):
        state = self.kernel.WaitForSingleObject(self.handle, 0)
        if state == 258:
            return None
        if state != 0:
            raise OSError('Runtime exit is unconfirmed')
        code = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise OSError('Runtime exit code is unconfirmed')
        return code.value

    def wait(self):
        while True:
            code = self.poll()
            if code is not None:
                return code
            time.sleep(.05)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def process_parent(pid):
    """OS ancestry only; never read process argv, environment or credentials."""
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    kernel = _kernel()
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError('Runtime ancestry could not be observed')
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.th32ProcessID == pid:
                return entry.th32ParentProcessID
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        raise OSError('Runtime ancestry was not present')
    finally:
        kernel.CloseHandle(snapshot)


def retain_runtime(launcher, launcher_birth, handshake):
    if (handle_birth(launcher._handle) != launcher_birth
            or launcher.poll() is not None):
        raise OSError('Selected launcher is no longer alive')
    runtime = RetainedProcess(handshake['pid'], handshake['birth'])
    try:
        direct = runtime.pid == launcher.pid and runtime.birth == launcher_birth
        redirected = (runtime.pid != launcher.pid and runtime.birth >= launcher_birth
                      and process_parent(runtime.pid) == launcher.pid
                      and handshake['parent_pid'] == launcher.pid)
        if not (direct or redirected) or runtime.poll() is not None or launcher.poll() is not None:
            raise OSError('Runtime ancestry or lifetime is unconfirmed')
        return runtime
    except BaseException:
        runtime.close()
        raise


def handshake_path(home, cycle_id, attempt):
    if not re.fullmatch(r'[a-f0-9]{32}', str(cycle_id)) or type(attempt) is not int or not 1 <= attempt <= 4:
        raise ValueError('Invalid handshake selection')
    return Path(home) / f'service-supervisor-handshake-{cycle_id}-{attempt}.json'


def read_handshake(home, record):
    value = read_json(handshake_path(home, record['cycle_id'], record['attempts_started']))
    if any(value.get(key) != record.get(key) for key in
           ('instance_id', 'cycle_id', 'attempts_started', 'attempt_nonce')):
        raise ValueError('Handshake does not match the reserved attempt')
    if value.get('revision') != 1 or any(type(value.get(k)) is not int or value[k] <= 0 for k in ('pid', 'birth', 'parent_pid')):
        raise ValueError('Handshake process identity is incomplete')
    return value


def handle_birth(handle):
    kernel = _kernel()
    stamps = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in stamps]):
        raise OSError('Process birth could not be observed')
    return (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime


def own_birth():
    return handle_birth(_kernel().GetCurrentProcess())


def process_state(pid, birth):
    """Return alive/exited/unknown for this exact identity; never signal it."""
    if type(pid) is not int or pid <= 0 or type(birth) is not int or birth <= 0:
        return 'unknown'
    kernel = _kernel()
    handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
    if not handle:
        return 'exited' if ctypes.get_last_error() == 87 else 'unknown'
    try:
        if handle_birth(handle) != birth:
            return 'exited'  # PID reused: the retained older identity is gone.
        wait = kernel.WaitForSingleObject(handle, 0)
        return 'exited' if wait == 0 else 'alive' if wait == 258 else 'unknown'
    except OSError:
        return 'unknown'
    finally:
        kernel.CloseHandle(handle)


def read_record(home, receipt, instance_id):
    try:
        value = read_json(Path(home) / RECORD_NAME)
    except FileNotFoundError:
        return None
    if (value.get('revision') != 1 or type(value.get('token')) is not str or len(value['token']) != 32
            or value.get('instance_id') != instance_id
            or type(value.get('cycle_id')) is not str or len(value['cycle_id']) != 32
            or type(value.get('attempts_started')) is not int
            or not 0 <= value['attempts_started'] <= 4
            or value.get('phase') not in {'initial', 'running', 'backoff', 'exhausted', 'stopped', 'unknown'}):
        raise InstallationError('SUPERVISOR_RECEIPT_INVALID',
            'Reconcile the retained supervisor owner and child before another launch.')
    for owner in [value.get('parent'), value.get('launcher'), value.get('child')]:
        if owner is None:
            continue
        if (not isinstance(owner, dict) or type(owner.get('pid')) is not int or owner['pid'] <= 0
                or type(owner.get('birth')) is not int or owner['birth'] <= 0):
            raise InstallationError('SUPERVISOR_RECEIPT_INVALID', 'The retained process identity is incomplete.')
    if value.get('parent') is None:
        raise InstallationError('SUPERVISOR_RECEIPT_INVALID', 'The supervisor owner is unconfirmed.')
    try:
        RetryState(**{key: value.get(key) for key in (
            'attempts_started', 'phase', 'next_retry_monotonic', 'last_exit_code')})
    except ValueError as error:
        raise InstallationError('SUPERVISOR_RECEIPT_INVALID', 'The retained restart state is invalid.') from error
    if (value['phase'] == 'exhausted' and value['attempts_started'] != 4
            or value['phase'] in {'backoff', 'exhausted', 'stopped'} and value['attempts_started'] > 0
            and (not value.get('child') or value['child'].get('physical_exit') is not True
                 or not value.get('launcher') or value['launcher'].get('physical_exit') is not True)):
        raise InstallationError('SUPERVISOR_RECEIPT_INVALID', 'The retained child exit or attempt budget is incomplete.')
    if value['token'] != receipt['token']:
        # Explicit reinstall/upgrade changes the installation token. Retain the
        # old bytes until a new selection, and require exact old-process exit;
        # a token change itself is never evidence that the old child died.
        if value['phase'] in {'stopped', 'exhausted'} and previous_finished(value):
            return None
        raise InstallationError('SUPERVISOR_RECOVERY_UNCONFIRMED',
            'The prior installation still has an unconfirmed supervisor or child.')
    return value


def previous_finished(value):
    """Unknown spawn/parent loss is not permission to reset a retry cycle."""
    if value is None:
        return True
    parent = value['parent']
    if process_state(parent['pid'], parent['birth']) != 'exited':
        return False
    if value['phase'] == 'unknown':
        return False
    child = value.get('child')
    if child is None:
        return value['attempts_started'] == 0
    launcher = value.get('launcher')
    return (launcher is not None
            and (launcher.get('physical_exit') is True or process_state(launcher['pid'], launcher['birth']) == 'exited')
            and (child.get('physical_exit') is True or process_state(child['pid'], child['birth']) == 'exited'))


def validate_child(home, receipt, instance_id, cycle_id, pid, birth, nonce=None):
    value = read_record(home, receipt, instance_id)
    if (not value or value['cycle_id'] != cycle_id or value['phase'] != 'running'
            or value.get('child_acknowledged') is not True or value.get('attempt_nonce') != nonce):
        raise InstallationError('SUPERVISOR_CHILD_UNCONFIRMED', 'The foreground child has no matching launch reservation.')
    child, parent = value.get('child'), value['parent']
    if (not child or child.get('pid') != pid or child.get('birth') != birth
            or process_state(parent['pid'], parent['birth']) != 'alive'):
        raise InstallationError('SUPERVISOR_CHILD_UNCONFIRMED', 'The parent/child identity changed before runtime admission.')


def join_parent(home, database, installation, token, cycle_id, nonce, *, timeout=60):
    """Publish one exclusive identity handshake, then await parent acknowledgment.

    Stop still completes the identity handshake so both process exits can be
    proved, but acknowledgment never overrides the canonical stop latch.
    """
    from .local import launch_exclusion
    from .locking import LockBusy
    if not re.fullmatch(r'[a-f0-9]{32}', str(nonce)):
        raise InstallationError('SUPERVISOR_CHILD_UNCONFIRMED', 'An exact attempt nonce is required.')
    deadline = time.monotonic() + timeout
    identity = {'pid': os.getpid(), 'birth': own_birth(), 'parent_pid': os.getppid()}
    while time.monotonic() < deadline:
        try:
            with launch_exclusion(home, database):
                receipt = installation.receipt()
                if not receipt or receipt['token'] != token:
                    raise InstallationError('SUPERVISOR_CHILD_UNCONFIRMED', 'Installation changed before handshake.')
                value = read_record(home, receipt, installation.instance_id)
                if (not value or value['cycle_id'] != cycle_id or value['phase'] != 'running'
                        or value.get('attempt_nonce') != nonce):
                    raise InstallationError('SUPERVISOR_CHILD_UNCONFIRMED', 'The attempt reservation changed.')
                parent, launcher = value['parent'], value.get('launcher')
                if (not launcher or process_state(parent['pid'], parent['birth']) != 'alive'
                        or process_state(launcher['pid'], launcher['birth']) != 'alive'
                        or not (identity['pid'] == launcher['pid'] and identity['birth'] == launcher['birth']
                                or identity['parent_pid'] == launcher['pid'])):
                    raise InstallationError('SUPERVISOR_CHILD_UNCONFIRMED', 'The selected parent or launcher is not alive.')
                handshake = {key: value[key] for key in ('instance_id', 'cycle_id', 'attempts_started', 'attempt_nonce')}
                handshake.update(revision=1, **identity)
                path = handshake_path(home, cycle_id, value['attempts_started'])
                try:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    if read_json(path) != handshake:
                        raise InstallationError('SUPERVISOR_CHILD_UNCONFIRMED', 'The attempt already has another child handshake.')
                else:
                    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                        json.dump(handshake, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                if value.get('child_acknowledged'):
                    validate_child(home, receipt, installation.instance_id, cycle_id,
                                   identity['pid'], identity['birth'], nonce)
                    control = installation.control(receipt)
                    if control.get('cycle_id') != cycle_id:
                        raise InstallationError('SUPERVISOR_CHILD_UNCONFIRMED', 'Control changed before bootstrap.')
                    return control['desired'] == 'running'
        except LockBusy:
            pass
        time.sleep(.05)
    raise InstallationError('SUPERVISOR_HANDSHAKE_TIMEOUT', 'The parent did not acknowledge the exact runtime identity within 60 seconds.')


def status(home, receipt, instance_id, control):
    value = read_record(home, receipt, instance_id)
    if value is None:
        return None
    if value['cycle_id'] != control.get('cycle_id'):
        # A selected explicit start has a new control generation; it must not
        # use the previous receipt as proof that the new parent has started.
        if control.get('launch_requested') and previous_finished(value):
            return None
        raise InstallationError('SUPERVISOR_CYCLE_UNCONFIRMED', 'Reconcile the selected cycle before retrying.')
    phase = value['phase']
    parent = value['parent']
    parent_state = process_state(parent['pid'], parent['birth'])
    summary = {'cycle_id': value['cycle_id'], 'attempts_started': value['attempts_started'],
               'max_restarts': 3, 'backoff_seconds': 60, 'phase': phase,
               'last_exit_code': value.get('last_exit_code'),
               'next_retry_at_epoch': value.get('next_retry_at_epoch'), 'parent_state': parent_state}
    if control['desired'] == 'draining' and phase != 'unknown':
        if parent_state == 'alive':
            return summary, 'stopping', 'SUPERVISOR_PENDING'
        if parent_state == 'exited' and previous_finished(value):
            return summary, None, None
        return summary, 'unknown', 'SUPERVISOR_RECOVERY_UNCONFIRMED'
    if phase == 'unknown' or (parent_state != 'alive' and phase in {'initial', 'running', 'backoff'}):
        return summary, 'unknown', 'SUPERVISOR_RECOVERY_UNCONFIRMED'
    if phase == 'exhausted':
        return summary, 'failed', 'SUPERVISOR_RETRY_EXHAUSTED'
    if phase == 'backoff':
        return summary, 'starting', 'SUPERVISOR_BACKOFF'
    if phase == 'stopped' and parent_state != 'exited':
        return summary, 'stopping' if parent_state == 'alive' else 'unknown', 'SUPERVISOR_PENDING'
    return summary, None, None
