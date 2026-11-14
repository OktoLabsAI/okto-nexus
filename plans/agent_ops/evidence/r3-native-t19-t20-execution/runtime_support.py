"""Inert adapted T14 lifecycle helpers; only own plan paths. No launch at import."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent
PUBLIC,PRIVATE=ROOT/'public',ROOT/'private'
HANDLES,CHILDREN=[],[]


def require(value, code):
    if not value:
        raise ValueError(code)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_bytes())

def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as out:
        json.dump(value, out, indent=2); out.write('\n'); out.flush(); os.fsync(out.fileno())

def secure(path):
    import ntsecuritycon, win32api, win32con, win32security
    require(path.resolve().is_relative_to(ROOT), 'OUTSIDE_TEST_ROOT')
    path.mkdir(exist_ok=True)
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try: user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally: token.Close()
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    acl = win32security.ACL()
    for sid in (user, system):
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, 3, ntsecuritycon.FILE_ALL_ACCESS, sid)
    win32security.SetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION, None, None, acl, None)

def fingerprint(home, excluded):
    """Stopped runtime only; no data content is exported, only paths/hash/size."""
    result = {}
    for path in sorted(home.rglob('*')):
        require(not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400, 'REPARSE_FILE_REFUSED')
        if path.is_file():
            name = path.relative_to(home).as_posix()
            if name not in excluded:
                result[name] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    require(bool(result), 'NO_RUNTIME_DATA')
    return result

def validate_preservation(before, after):
    require(before == after, 'UNINSTALL_CHANGED_RETAINED_DATA')

def public_status(value):
    keys = ('state', 'reason', 'pid', 'generation', 'instance_id', 'supervisor', 'ready_for_queries',
            'running', 'ipc_ok', 'storage_initialized', 'shutdown_outcome', 'stopped', 'installed', 'installation_state', 'next_action')
    return {k: value[k] for k in keys if k in value}

def cli(plan, name, phase, *, foreground=False):
    step = plan['commands'][name][phase]
    argv, cwd = step['argv'], step['cwd']
    env = plan['environments'][step['environment']]
    require('--force' not in argv and argv[0] == plan['python'], 'COMMAND_SCOPE_CHANGED')
    label = name + '-' + phase
    save(PRIVATE / (label + '.reserved.json'), {'argv': argv, 'cwd': cwd,
        'environment_sha256': hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest(), 'at': time.time()})
    out, err = (PRIVATE / (label + '.stdout')).open('xb'), (PRIVATE / (label + '.stderr')).open('xb')
    try:
        child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
        CHILDREN.append(child)
        save(PRIVATE / (label + '.process.json'), {'pid': child.pid})
        if foreground:
            return child
        code = child.wait()
    finally:
        out.close(); err.close()
    try:
        value = read(PRIVATE / (label + '.stdout'))
        require(isinstance(value, dict), 'JSON_OBJECT_REQUIRED')
    except (ValueError, UnicodeError):
        value = {'state': 'unknown', 'reason': 'CLI_OUTPUT_UNCONFIRMED'}
    save(PUBLIC / (label + '.json'), {'returncode': code, 'wrapper_exit_confirmed': True,
        'stdout_sha256': sha(PRIVATE / (label + '.stdout')), 'stderr_sha256': sha(PRIVATE / (label + '.stderr')),
        'result': public_status(value)})
    return code, value

class Owner:
    def __init__(self, status):
        self.identity = {k: status[k] for k in ('pid', 'generation', 'instance_id')}
        self.kernel = k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD); k.OpenProcess.restype = wintypes.HANDLE
        k.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        k.GetProcessTimes.restype = wintypes.BOOL
        k.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD); k.WaitForSingleObject.restype = wintypes.DWORD
        k.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = (wintypes.HANDLE,); k.CloseHandle.restype = wintypes.BOOL
        self.handle = k.OpenProcess(0x1000 | 0x100000 | 0x0001, False, status['pid'])
        require(bool(self.handle), 'OWNER_HANDLE_UNAVAILABLE')
        HANDLES.append(self)
        fields = [wintypes.FILETIME() for _ in range(4)]
        require(k.GetProcessTimes(self.handle, *[ctypes.byref(v) for v in fields]), 'OWNER_BIRTH_UNAVAILABLE')
        self.birth = (fields[0].dwHighDateTime << 32) | fields[0].dwLowDateTime
        buf, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        require(k.QueryFullProcessImageNameW(self.handle, 0, buf, ctypes.byref(size)), 'OWNER_IMAGE_UNAVAILABLE')
        self.image = str(Path(buf.value).resolve())
        require(not self.exited(), 'OWNER_ALREADY_EXITED')

    def exited(self):
        result = self.kernel.WaitForSingleObject(self.handle, 0)
        require(result in (0, 258), 'OWNER_WAIT_UNCONFIRMED')
        return result == 0

    def close(self):
        self.kernel.CloseHandle(self.handle)

def inspect(plan, name):
    if name == 'nexus':
        from okto_nexus.adapters.outbound.service_manager.local import LocalServerLifecycle
        return LocalServerLifecycle(home=plan['homes'][name], database=Path(plan['homes'][name]) / 'nexus.db',
            host='127.0.0.1', port=plan['port']).inspect(timeout=1)
    from okto_nexus_connector.daemon import manager
    return manager.status(Path(plan['homes'][name]), timeout=1).to_json()

def wait_ready(plan, name, supervisor):
    deadline = time.monotonic() + plan['observation_timeout_seconds']
    last = None
    while time.monotonic() < deadline:
        last = inspect(plan, name)
        if last.get('state') == 'ready' and last.get('supervisor') == supervisor:
            require(last.get('instance_id') == plan['instance_ids'][name] and type(last.get('pid')) is int
                and bool(last.get('generation')), 'READY_IDENTITY_INVALID')
            require(last.get('ready_for_queries') is True if name == 'nexus' else last.get('running') is True and last.get('ipc_ok') is True,
                    'READINESS_UNCONFIRMED')
            return last
        time.sleep(.25)
    save(PUBLIC / (name + '-' + supervisor + '-readiness-timeout.json'), {'last': public_status(last or {}), 'no_restart': True})
    raise ValueError('READINESS_TIMEOUT_NO_RETRY')

def own_ready(plan, name, supervisor):
    ready = wait_ready(plan, name, supervisor)
    owner = Owner(ready)
    again = inspect(plan, name)
    require(all(again.get(k) == v for k, v in owner.identity.items()), 'OWNER_CHANGED_DURING_CAPTURE')
    allowed_images = {str(Path(p).resolve()) for p in plan['python_images'] if Path(p).name.lower() == ('pythonw.exe' if supervisor != 'foreground' else 'python.exe')}
    require(owner.image in allowed_images, 'NATIVE_PROCESS_IMAGE_CHANGED')
    return owner, ready

def stop_owner(plan, name, phase, owner, service, *, task_present):
    code, result = cli(plan, name, phase)
    require(code == 0 and result.get('shutdown_outcome') == 'drained', 'NORMAL_STOP_NOT_DRAINED')
    deadline = time.monotonic() + 30
    while not owner.exited() and time.monotonic() < deadline:
        time.sleep(.1)
    require(owner.exited(), 'PHYSICAL_EXIT_UNCONFIRMED')
    deadline = time.monotonic() + 30
    while True:
        task = service.tasks.read(service.name)
        inactive = (task is not None and not task.active and task.state not in (0, 2, 4)) if task_present else task is None
        if inactive:
            break
        require(time.monotonic() < deadline, 'NATIVE_TASK_EXIT_UNCONFIRMED')
        time.sleep(.1)
    current = inspect(plan, name)
    require(current['state'] == 'stopped', 'CANONICAL_STOP_UNCONFIRMED')
    save(PUBLIC / (name + '-' + phase + '-physical-exit.json'), {**owner.identity, 'birth_filetime': owner.birth,
        'retained_handle': True, 'physical_exit_confirmed': True, 'force_used': False, 'canonical': public_status(current)})

def port_available(plan):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind(('127.0.0.1', plan['port']))
