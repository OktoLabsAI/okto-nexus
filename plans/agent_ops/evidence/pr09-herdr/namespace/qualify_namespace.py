"""Two real Herdr namespaces, real Windows identity, no Nexus publication.

Only the secondary disposable session is mutated/stopped. The observer subprocess
allowlist is independently checked; setup/teardown commands are separate records.
"""
from contextlib import ExitStack
import ctypes
from ctypes import wintypes
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

from okto_nexus.adapters.outbound.observation import herdr
from okto_nexus.adapters.outbound.observation.windows_identity import open_process_identity
from okto_nexus.application.herdr_observer import sample_source
from okto_nexus.domain.herdr_observations import HerdrObservationError, preview_hash

ROOT = Path(__file__).resolve().parent
PRIMARY = Path('C:/Users/jpamb/AppData/Local/Temp/pr09-herdr-0.9.5-_n3kwt9i')
PRIMARY_SESSION = 'nexus-pr09-6fcb0c9a'
SESSION = 'nexus-pr09-namespace-cvxe4ar4'
SITE = Path('C:/Users/jpamb/AppData/Local/Temp/pr09-installed-_p9t3pls/qualified-v2/venv/Lib/site-packages')
assert Path(herdr.__file__).resolve().is_relative_to(SITE)
EXE = ROOT / 'distribution/herdr.exe'
EVIDENCE = ROOT / 'evidence'
proof = {'revision': 1, 'case': 'OBS-12 distinct explicit namespaces with identical pane IDs',
    'result': 'incomplete', 'observer_python': sys.executable, 'observer_module': str(Path(herdr.__file__)),
    'real_herdr': True, 'real_os_identity': True, 'observed_executables_synthetic': True,
    'provider_inference': False, 'nexus_publish': False, 'observer_commands': [], 'driver_commands': []}


def environment(root):
    env = {name: value for name, value in os.environ.items() if name.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS'}}
    env.update(PATH='C:\\Windows\\System32;C:\\Windows;C:\\Python313', HOME=str(root / 'profile'),
        USERPROFILE=str(root / 'profile'), APPDATA=str(root / 'appdata'),
        LOCALAPPDATA=str(root / 'localappdata'), TEMP=str(root / 'temp'), TMP=str(root / 'temp'),
        HERDR_CONFIG_PATH=str(root / 'config.toml'), NO_COLOR='1')
    return env


ENV = environment(ROOT)


def call(label, args):
    result = subprocess.run([str(EXE), '--session', SESSION, *args], cwd=ROOT / 'work',
        env=ENV, capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    for stream in ('stdout', 'stderr'):
        with (EVIDENCE / (label + '.' + stream + '.txt')).open('xb') as target:
            target.write(getattr(result, stream))
    proof['driver_commands'].append({'label': label, 'session': SESSION, 'arguments': args,
        'exit_code': result.returncode})
    if result.returncode != 0:
        raise AssertionError('Secondary fixture command failed: ' + label)
    return result


def json_call(label, args):
    value = json.loads(call(label, args).stdout)
    if 'error' in value:
        raise AssertionError('Secondary fixture returned an error: ' + label)
    return value


def descendants(pid):
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entry))
    kernel.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entry))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise AssertionError('Process snapshot unavailable')
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(entry)
        parents = {}
        exists = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while exists:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            exists = kernel.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    owned = {pid}
    while True:
        found = {child for child, parent in parents.items() if parent in owned}
        if found <= owned:
            return owned
        owned |= found


ALLOWED = {('--version',), ('api', 'schema', '--json'), ('status', 'server', '--json'),
           ('api', 'snapshot'), ('pane', 'process-info', '--pane', 'w2:p2')}
real_popen = subprocess.Popen


def observer_popen(argv, *args, **kwargs):
    assert type(argv) is list and len(argv) >= 4
    assert (argv[0], argv[1], argv[2]) in {
        (str(EXE), '--session', SESSION),
        (str(PRIMARY / 'distribution/herdr.exe'), '--session', PRIMARY_SESSION)}
    assert tuple(argv[3:]) in ALLOWED
    assert kwargs.get('shell') is False
    proof['observer_commands'].append({'session': argv[2], 'arguments': argv[3:],
        'shell': False, 'environment_keys': sorted(kwargs['env'])})
    return real_popen(argv, *args, **kwargs)


primary = herdr.HerdrCLI(PRIMARY / 'distribution/herdr.exe', PRIMARY_SESSION, environment=environment(PRIMARY))
secondary = herdr.HerdrCLI(EXE, SESSION, environment=ENV)
process = None
held = {}
stack = ExitStack()
try:
    with patch.object(herdr.subprocess, 'Popen', observer_popen):
        primary_contract = primary.contract()
        binding1, observation1, time1 = sample_source(primary, open_process_identity,
            pane='w2:p2', namespace='pr09-qualified-primary-installation', session=PRIMARY_SESSION)
    assert binding1.pid == 52216, 'Primary occupant changed before the namespace proof'
    before = json_call('before-start', ['status', 'server', '--json'])
    assert before.get('running') is False
    with (EVIDENCE / 'server.stdout.txt').open('xb') as out, (EVIDENCE / 'server.stderr.txt').open('xb') as err:
        process = subprocess.Popen([str(EXE), '--session', SESSION, 'server'], cwd=ROOT / 'work',
            env=ENV, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    proof['secondary_launcher_pid'] = process.pid
    print(json.dumps({'phase': 'secondary-started', 'session': SESSION, 'pid': process.pid}), flush=True)
    for index in range(40):
        status = json_call('startup-' + str(index), ['status', 'server', '--json'])
        if status.get('running') is True:
            break
        assert process.poll() is None
        time.sleep(.25)
    else:
        raise AssertionError('Secondary server did not become ready')
    for number in (1, 2):
        value = json_call('create-workspace-' + str(number), ['workspace', 'create',
            '--cwd', str(ROOT / 'work'), '--label', 'pr09-secondary-' + str(number)])
        assert value['result']['root_pane']['pane_id'] == 'w' + str(number) + ':p1'
    json_call('split-w2', ['pane', 'split', '--pane', 'w2:p1', '--direction', 'right', '--focus'])
    stopfile = ROOT / 'work/stop-secondary-fixture'
    command = 'import subprocess; subprocess.run(' + repr([str(ROOT / 'work/codex.exe'), str(stopfile)]) + ')'
    call('start-synthetic-fixture', ['pane', 'run', 'w2:p2', command])
    for index in range(40):
        snapshot = json_call('detect-fixture-' + str(index), ['api', 'snapshot'])['result']['snapshot']
        if any(row['pane_id'] == 'w2:p2' for row in snapshot['agents']):
            break
        time.sleep(.25)
    else:
        raise AssertionError('Secondary synthetic occupant was not detected')
    with patch.object(herdr.subprocess, 'Popen', observer_popen):
        secondary_contract = secondary.contract()
        binding2, observation2, time2 = sample_source(secondary, open_process_identity,
            pane='w2:p2', namespace='pr09-qualified-secondary-installation', session=SESSION)
        assert binding1.pane_id == binding2.pane_id == 'w2:p2'
        assert binding1.namespace != binding2.namespace and binding1.session != binding2.session
        assert binding1.terminal_id != binding2.terminal_id
        assert binding1.pid != binding2.pid and binding1.creation_filetime != binding2.creation_filetime
        assert binding1.host_id == binding2.host_id
        assert preview_hash(binding1) != preview_hash(binding2)
        try:
            sample_source(secondary, open_process_identity, pane='w2:p2', binding=binding1)
        except HerdrObservationError as exc:
            proof['cross_namespace_reuse_refused'] = exc.code
        else:
            raise AssertionError('A primary binding was accepted for the secondary occupant')
        stable, _, _ = sample_source(primary, open_process_identity,
            pane='w2:p2', binding=binding1)
        assert stable == binding1
    proof.update(primary={'contract': primary_contract, 'binding': asdict(binding1),
            'binding_hash': preview_hash(binding1), 'observation': observation1.to_dict(), 'observed_at': time1},
        secondary={'contract': secondary_contract, 'binding': asdict(binding2),
            'binding_hash': preview_hash(binding2), 'observation': observation2.to_dict(), 'observed_at': time2},
        same_pane_id=True, distinct_bindings=True, primary_unchanged_during_comparison=True,
        observer_allowlist_enforced=True)
    owned = descendants(process.pid)
    for pane in ('w1:p1', 'w2:p1', 'w2:p2'):
        info = json_call('teardown-process-' + pane.replace(':', '-'),
            ['pane', 'process-info', '--pane', pane])['result']['process_info']
        owned.add(info['shell_pid'])
        owned.update(item['pid'] for item in info['foreground_processes'])
    owned.discard(None)
    assert binding1.pid not in owned and binding2.pid in owned
    for pid in sorted(owned):
        held[pid] = stack.enter_context(open_process_identity(pid))
    proof['secondary_owned_processes'] = [asdict(guard.identity) for guard in held.values()]
    proof['result'] = 'passed'
except Exception as exc:
    proof.update(result='failed', error_type=type(exc).__name__, error_code=getattr(exc, 'code', None))
    raise
finally:
    try:
        if process is not None:
            call('stop-secondary', ['server', 'stop'])
            process.wait(timeout=15)
            remaining = set(held)
            deadline = time.monotonic() + 15
            while remaining and time.monotonic() < deadline:
                remaining = {pid for pid in remaining
                    if held[pid]._kernel.WaitForSingleObject(held[pid]._handle, 0) != 0}
                if remaining:
                    time.sleep(.1)
            proof['secondary_stop'] = {'canonical_server_stop': True, 'launcher_exit_code': process.returncode,
                'held_processes': len(held), 'all_owned_processes_exited': not remaining,
                'remaining_owned_pids': sorted(remaining)}
            assert not remaining, 'A secondary-owned process survived canonical stop'
            stopped = json_call('after-stop', ['status', 'server', '--json'])
            assert stopped.get('running') is False
            with patch.object(herdr.subprocess, 'Popen', observer_popen):
                final_primary, _, _ = sample_source(primary, open_process_identity, pane='w2:p2', binding=binding1)
            assert final_primary == binding1
            proof['primary_alive_and_binding_unchanged_after_secondary_stop'] = True
    except Exception as cleanup:
        proof.update(result='failed', cleanup_error_type=type(cleanup).__name__,
            cleanup_error_code=getattr(cleanup, 'code', None))
        raise
    finally:
        stack.close()
        proof['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (EVIDENCE / 'namespace-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({key: proof[key] for key in ('result', 'same_pane_id', 'distinct_bindings',
    'observer_allowlist_enforced', 'cross_namespace_reuse_refused', 'secondary_stop',
    'primary_alive_and_binding_unchanged_after_secondary_stop')}, indent=2))
