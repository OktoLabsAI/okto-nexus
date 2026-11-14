"""Finite Windows T14/T27 lifecycle qualification. Import is inert."""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
PUBLIC, PRIVATE = ROOT / 'public', ROOT / 'private'
BUNDLE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
PACKAGE_REFERENCE = BUNDLE / 'draft/m1-codex-campaign-proposal-v12.json'
PACKAGE_REFERENCE_SHA = 'd6b1340956fe5ed83cb16f56dd8af13c16c65341d9d517280ac2f6109d561040'
HANDLES, CHILDREN = [], []


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


def package_proof(plan):
    require(sha(PACKAGE_REFERENCE) == PACKAGE_REFERENCE_SHA, 'PACKAGE_REFERENCE_CHANGED')
    package = read(PACKAGE_REFERENCE)['package_pins']
    require(Path(sys.executable).resolve() == Path(package['python']).resolve() and sys.flags.isolated, 'RUNTIME_CHANGED')
    for entry in package['files']:
        require(sha(entry['path']) == entry['sha256'], 'PRODUCT_PAYLOAD_CHANGED')
    for path, digest in plan['python_images'].items():
        require(sha(path) == digest, 'PYTHON_IMAGE_CHANGED')
    return {'proposal_sha256': PACKAGE_REFERENCE_SHA, 'verified_payloads': len(package['files']),
            'python': sys.executable, 'python_images': plan['python_images']}


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
            'running', 'ipc_ok', 'storage_initialized', 'shutdown_outcome', 'stopped', 'installed', 'installation_state')
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
        self.handle = k.OpenProcess(0x1000 | 0x100000, False, status['pid'])
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
    return manager._process_status(Path(plan['homes'][name]), timeout=1).to_json()


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


def native_context(plan, name, service):
    receipt, task = service.observe()
    require(receipt is not None and task is not None and task.active, 'NATIVE_ACTIVE_TASK_UNCONFIRMED')
    context_path = Path(plan['homes'][name]) / 'service-context.json'
    context = read(context_path)
    expected_cwd = plan['project_a'] if name == 'nexus' else plan['homes'][name]
    require(Path(context['executable']).resolve() == Path(plan['python']).resolve()
        and Path(context['cwd']).resolve() == Path(expected_cwd).resolve(), 'SAVED_CONTEXT_CHANGED')
    normal_path = os.pathsep.join(dict.fromkeys(str(Path(x).resolve()) for x in plan['environments']['A']['PATH'].split(os.pathsep)))
    require(context['environment']['PATH'] == normal_path, 'SAVED_PATH_NOT_CONTEXT_A')
    if name == 'nexus':
        for flag, value in [('--project-root', plan['project_a']), ('--port', str(plan['port'])),
                            ('--embedding-mode', 'off'), ('--feature-harness-integrations', 'false')]:
            require(flag in context['arguments'] and context['arguments'][context['arguments'].index(flag) + 1] == value,
                    'PROJECT_OR_CONFIGURATION_CHANGED')
    else:
        require(context['root'] == plan['homes'][name]
            and context['environment']['OKTO_NEXUS_CONNECTOR_STATE'] == plan['homes'][name], 'CONNECTOR_STATE_CONTEXT_CHANGED')
    tree = ET.fromstring(task.xml)
    ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    command = tree.findtext('t:Actions/t:Exec/t:Command', namespaces=ns)
    working = tree.findtext('t:Actions/t:Exec/t:WorkingDirectory', namespaces=ns)
    require(Path(command).resolve() == Path(plan['python']).with_name('pythonw.exe').resolve()
        and Path(working).resolve() == Path(expected_cwd).resolve(), 'NATIVE_ACTION_CONTEXT_CHANGED')
    return {'task_name': service.name, 'task_digest': task.digest, 'active': True, 'enabled': task.enabled,
        'context_sha256': sha(context_path), 'recorded_executable': context['executable'], 'recorded_cwd': context['cwd'],
        'native_action_executable': command, 'native_working_directory': working,
        'recorded_path_matches_A_not_caller_B': True,
        'project_scope': 'Nexus project-root A' if name == 'nexus' else 'Connector canonical state root; no project binding/work claimed'}


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
    task = service.tasks.read(service.name)
    require(task is not None and not task.active and task.state not in (0, 2, 4) if task_present else task is None,
            'NATIVE_TASK_EXIT_UNCONFIRMED')
    current = inspect(plan, name)
    require(current['state'] == 'stopped', 'CANONICAL_STOP_UNCONFIRMED')
    save(PUBLIC / (name + '-' + phase + '-physical-exit.json'), {**owner.identity, 'birth_filetime': owner.birth,
        'retained_handle': True, 'physical_exit_confirmed': True, 'force_used': False, 'canonical': public_status(current)})


def port_available(plan):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind(('127.0.0.1', plan['port']))


def execute(plan):
    package = package_proof(plan)
    require(str(ROOT) == plan['root'], 'ROOT_CHANGED')
    for name in ('private', 'nexus', 'connector', 'project-a', 'caller-b', 'profile'):
        secure(ROOT / name)
    PUBLIC.mkdir(exist_ok=True)
    for name in ('appdata', 'localappdata', 'tmp'):
        (ROOT / 'profile' / name).mkdir(exist_ok=True)
    require(not (PUBLIC / 'started.json').exists(), 'ALREADY_SELECTED')
    require(all(not any(Path(p).iterdir()) for p in (*plan['homes'].values(), plan['project_a'], plan['caller_b'])), 'RUNTIME_ROOT_NOT_EMPTY')
    port_available(plan)
    os.environ.clear(); os.environ.update(plan['environments']['A'])
    from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
    from okto_nexus_connector.platform.user_service import UserService
    services = {'nexus': ServerInstallation(Path(plan['homes']['nexus']), Path(plan['homes']['nexus']) / 'nexus.db'),
                'connector': UserService(Path(plan['homes']['connector']))}
    require(all(v.tasks.read(v.name) is None and v.name == plan['tasks'][k] for k, v in services.items()), 'TASK_ALREADY_PRESENT_OR_WRONG')
    save(PUBLIC / 'started.json', {'package_proof': package, 'plan_sha256': sha(ROOT / 'plan.json'),
        'runner_sha256': sha(__file__), 'at': time.time(), 'provider_calls': 0, 'login_attempts': 0})
    results = {}
    for name, service in services.items():
        code, _ = cli(plan, name, 'install-A'); require(code == 0, 'INSTALL_FAILED')
        code, _ = cli(plan, name, 'start-B'); require(code in (0, 3), 'START_REFUSED')
        installed_owner, ready = own_ready(plan, name, 'windows-task-scheduler')
        context = native_context(plan, name, service)
        save(PUBLIC / (name + '-T14.json'), {'status': 'PASS_SCOPED', 'caller_cwd': plan['caller_b'],
            'caller_path': plan['environments']['B']['PATH'], 'start_cli_exit': code, 'context': context,
            'readiness': public_status(ready), 'process_image': installed_owner.image,
            'birth_filetime': installed_owner.birth, 'provider_calls': 0})
        stop_owner(plan, name, 'stop-installed', installed_owner, service, task_present=True)
        home = Path(plan['homes'][name])
        before = fingerprint(home, plan['uninstall_removes'][name])
        required_data = 'nexus.db' if name == 'nexus' else 'owned-slots.db'
        require(required_data in before and before[required_data]['bytes'] > 0, 'RUNTIME_CREATED_STORE_MISSING')
        code, _ = cli(plan, name, 'uninstall'); require(code == 0, 'UNINSTALL_FAILED')
        require(service.tasks.read(service.name) is None, 'TASK_NOT_REMOVED')
        after = fingerprint(home, plan['uninstall_removes'][name])
        validate_preservation(before, after)
        require(all(not (home / n).exists() for n in plan['uninstall_removes'][name]), 'INTEGRATION_RECEIPT_REMAINS')
        save(PUBLIC / (name + '-uninstall-data.json'), {'before': before, 'after': after,
            'identical': True, 'excluded_only_integration_receipts': plan['uninstall_removes'][name], 'task_absent': True})
        foreground = cli(plan, name, 'foreground', foreground=True)
        foreground_owner, foreground_ready = own_ready(plan, name, 'foreground')
        require(service.tasks.read(service.name) is None and foreground_owner.identity['instance_id'] == installed_owner.identity['instance_id']
            and foreground_owner.identity['generation'] != installed_owner.identity['generation'], 'FOREGROUND_INSTANCE_NOT_REUSED')
        require((home / required_data).is_file() and (home / required_data).stat().st_size > 0, 'RETAINED_STORE_NOT_AVAILABLE')
        if name == 'nexus': require(foreground_ready.get('storage_initialized') is True, 'FOREGROUND_STORAGE_NOT_INITIALIZED')
        # Connector READY is published after DaemonApp awaits ensure_ledger().
        save(PUBLIC / (name + '-foreground-ready.json'), {'readiness': public_status(foreground_ready),
            'process_image': foreground_owner.image, 'birth_filetime': foreground_owner.birth,
            'same_retained_home': str(home), 'required_store': required_data, 'task_absent': True,
            'data_bytes_not_compared_after_startup': True})
        stop_owner(plan, name, 'stop-foreground', foreground_owner, service, task_present=False)
        require(foreground.wait(timeout=30) == 0, 'FOREGROUND_CLI_EXIT_UNCONFIRMED')
        save(PUBLIC / (name + '-foreground-exit.json'), {'returncode': foreground.returncode, 'wrapper_exit_confirmed': True,
            'stdout_sha256': sha(PRIVATE / (name + '-foreground.stdout')), 'stderr_sha256': sha(PRIVATE / (name + '-foreground.stderr'))})
        results[name] = {'T14': 'PASS_SCOPED', 'T27': 'PASS', 'data_preserved_across_uninstall': True,
                         'foreground_same_instance_ready': True, 'all_selected_owners_exited': True, 'task_absent': True}
    port_available(plan)
    require(package_proof(plan) == package, 'PACKAGES_CHANGED')
    save(PUBLIC / 'qualification.json', {'status': 'PASS_SCOPED', 'scenarios': ['SVC-T14', 'SVC-T27'], 'hosts': results,
        'package_proof': package, 'provider_calls': 0, 'login_attempts': 0, 'force_used': False,
        'limits': ['Connector T14 proves canonical state root/cwd, not project binding or remote project work.',
                   'T27 reopens runtime-created empty data stores; no productive turn or authenticated account.',
                   'No M1 acceptance inferred.'], 'completed_at': time.time()})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('operation', choices=('execute',))
    p.add_argument('--expected-plan-sha256', required=True)
    p.add_argument('--expected-runner-sha256', required=True)
    args = p.parse_args()
    try:
        require(sha(ROOT / 'plan.json') == args.expected_plan_sha256 and sha(__file__) == args.expected_runner_sha256, 'FROZEN_SOURCE_CHANGED')
        execute(read(ROOT / 'plan.json'))
        print(json.dumps({'status': 'PASS_SCOPED', 'scenarios': ['SVC-T14', 'SVC-T27']}), flush=True)
    except Exception as error:
        report = {'status': 'STOPPED_PROGRESSION', 'reason': str(error) if isinstance(error, ValueError) else type(error).__name__,
                  'runner_pid': os.getpid(), 'cleanup_confirmed': False, 'automatic_retry': False,
                  'live_cli_pids': [p.pid for p in CHILDREN if p.poll() is None]}
        if PUBLIC.exists(): save(PUBLIC / 'failure.json', report)
        print(json.dumps(report), flush=True)
        # Preserve live owner handles, without another mutation, for root reconciliation.
        while any(p.poll() is None for p in CHILDREN) or any(not h.exited() for h in HANDLES):
            time.sleep(1)
        raise SystemExit(1)
    finally:
        for handle in HANDLES: handle.close()
