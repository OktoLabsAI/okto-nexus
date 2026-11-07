"""Finite authorized native lifecycle campaign. No force/kill/retry mutations."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parent
PROPOSAL = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-campaign-proposals/native-service-campaign-proposal.json')
PLAN_BYTES = PROPOSAL.read_bytes()
PLAN = json.loads(PLAN_BYTES)
ENV = PLAN['environment']
os.environ.clear()
os.environ.update(ENV)
OUT = ROOT / 'execution-001-resume'
OUT.mkdir(exist_ok=True)
os.chdir(PLAN['project_root'])
HANDLES = []
CHILDREN = []
OWNERSHIP = {}
INSTANCE = {}
RECORD = None


class StopProgression(Exception):
    pass


def require(condition, code):
    if not condition:
        raise StopProgression(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(name, value):
    path = OUT / name
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def services():
    from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
    from okto_nexus_connector.platform.user_service import UserService
    selected = {'nexus': ServerInstallation(Path(PLAN['server_home']), Path(PLAN['server_database'])),
                'connector': UserService(Path(PLAN['connector_state']))}
    for name, service in selected.items():
        require(service.name == PLAN['task_names'][name], 'TASK_NAME_MISMATCH')
        INSTANCE[name] = service.instance_id
    return selected


def package_proof():
    packages = {}
    for dist, package in PLAN['packages'].items():
        wheel = Path(package['wheel'])
        require(sha(wheel.read_bytes()) == package['wheel_sha256'], 'WHEEL_HASH_MISMATCH')
        installed = Path(package['import_path'])
        module = importlib.import_module(installed.name)
        require(Path(module.__file__).resolve().parent == installed.resolve(), 'IMPORT_PATH_MISMATCH')
        require(importlib.metadata.version(dist) == package['version'], 'PACKAGE_VERSION_MISMATCH')
        with zipfile.ZipFile(wheel) as archive:
            prefix = installed.name + '/'
            expected = {name[len(prefix):]: sha(archive.read(name)) for name in archive.namelist()
                        if name.startswith(prefix) and not name.endswith('/')}
        actual = {p.relative_to(installed).as_posix(): sha(p.read_bytes()) for p in installed.rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
        require(actual == expected and len(actual) == package['file_count'], 'INSTALLED_PAYLOAD_MISMATCH')
        packages[dist] = {'wheel_sha256': package['wheel_sha256'], 'version': package['version'],
                          'import_path': str(installed), 'files': actual, 'file_count': len(actual)}
    return packages


def port_free():
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((PLAN['host'], PLAN['port']))


def preflight():
    require(PLAN['revision'] == 4 and PLAN['port'] == 52106 and len(PLAN['steps']) == 24, 'PROPOSAL_MISMATCH')
    require(Path(PLAN['root']).resolve() == ROOT and sys.flags.isolated, 'RUNTIME_CONTEXT_MISMATCH')
    require(Path(sys.executable).absolute() == Path(PLAN['python']), 'PYTHON_MISMATCH')
    require(json.loads((ROOT / 'environment.json').read_text()) == ENV, 'ENVIRONMENT_MISMATCH')
    for filename, key in [('installed-proof.json', 'installed_proof_sha256'),
                          ('pythonw-import-proof.json', 'pythonw_proof_sha256'),
                          ('environment-preparation.json', 'dependency_preparation_sha256')]:
        require(sha((ROOT / filename).read_bytes()) == PLAN[key], 'PREPARATION_HASH_MISMATCH')
    packages = package_proof()
    emptiness = {key: Path(PLAN[key]).is_dir() and not any(Path(PLAN[key]).iterdir())
                 for key in ('server_home', 'connector_state', 'project_root')}
    require(all(emptiness.values()), 'HOME_NOT_EMPTY')
    port_free()
    observations = {}
    for name, selected in services().items():
        task = selected.tasks.read(selected.name)
        observations[name] = {'name': selected.name, 'instance_id': selected.instance_id, 'absent': task is None}
        require(task is None, 'TARGET_TASK_ALREADY_EXISTS')
    result = {'status': 'PASS', 'at': now(), 'proposal_sha256': sha(PLAN_BYTES), 'revision': PLAN['revision'],
              'runner_sha256': sha(Path(__file__).read_bytes()), 'environment': ENV,
              'environment_exact': dict(os.environ) == {k.upper(): v for k, v in ENV.items()},
              'homes_empty': emptiness, 'port': PLAN['port'], 'port_free': True,
              'tasks': observations, 'packages': packages, 'native_mutations': 0,
              'user_authorization': 'sim pode executar',
              'authorization_context': 'User authorized proposal v7 and native proposal revision4; historical authorization fields remain immutable.'}
    require(result['environment_exact'], 'EFFECTIVE_ENVIRONMENT_MISMATCH')
    save('preflight.json', result)
    return result


SAFE = set('state reason component instance_id generation active_version installed_version pid supervisor ready_for_queries storage_initialized admission protocol_revision shutdown_outcome wait_timed_out installed already_installed uninstalled data_preserved started stopped reused enabled changed installation_state installation_prepared enablement_confirmed process_action running ipc_ok draining version result code stage possible_effect name definition_digest native_state last_result start_at_login available_before_login available_after_logout shutdown drain user_service error phase force_requested force_available deadline_exceeded resources cleanup_pending recovery_required status outcome'.split())


def public(value):
    if isinstance(value, dict):
        return {key: public(item) for key, item in value.items() if key in SAFE}
    if isinstance(value, list):
        return [public(item) for item in value[:100]]
    return value if value is None or type(value) in (str, int, bool, float) else type(value).__name__


def command(argv, label):
    require(argv in [s[k] for s in PLAN['steps'] for k in ('argv', 'followup_status_argv', 'followup_service_status_argv') if k in s], 'COMMAND_NOT_IN_PROPOSAL')
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=PLAN['project_root'], env=ENV, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    CHILDREN.append(proc)
    buffers = [bytearray(), bytearray()]
    digests = [hashlib.sha256(), hashlib.sha256()]
    sizes = [0, 0]

    def reader(stream, index):
        while data := stream.read(8192):
            digests[index].update(data)
            sizes[index] += len(data)
            if len(buffers[index]) < 1048576:
                buffers[index].extend(data[:1048576 - len(buffers[index])])
        stream.close()

    readers = [threading.Thread(target=reader, args=(stream, index), daemon=True)
               for index, stream in enumerate((proc.stdout, proc.stderr))]
    for thread in readers:
        thread.start()
    save('active-command.json', {'label': label, 'pid': proc.pid, 'started_at': now(),
                                'argv_sha256': sha(json.dumps(argv).encode()), 'handle_owner_pid': os.getpid()})
    # Restart has sequential canonical stop/start timeouts of 45 seconds each.
    bound = 105 if 'restart' in argv else 60
    while proc.poll() is None and time.monotonic() - started < bound:
        time.sleep(.05)
    require(proc.poll() is not None, 'COMMAND_TIMEOUT_HANDLE_RETAINED')
    for thread in readers:
        thread.join(5)
    require(not any(thread.is_alive() for thread in readers), 'OUTPUT_PIPE_STILL_OPEN_HANDLE_RETAINED')
    require(sizes[0] <= 1048576, 'COMMAND_OUTPUT_LIMIT')
    try:
        payload = json.loads(buffers[0].decode('utf-8-sig'))
    except (ValueError, UnicodeError):
        payload = None
    report = {'label': label, 'returncode': proc.returncode, 'elapsed_seconds': time.monotonic() - started,
              'pid': proc.pid, 'stdout_bytes': sizes[0], 'stderr_bytes': sizes[1],
              'stdout_sha256': digests[0].hexdigest(), 'stderr_sha256': digests[1].hexdigest(),
              'result': public(payload), 'raw_output_retained': False}
    save(label + '.json', report)
    require(type(payload) is dict, 'COMMAND_JSON_INVALID')
    return proc.returncode, payload, report


KERNEL = ctypes.WinDLL('kernel32', use_last_error=True)
KERNEL.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
KERNEL.OpenProcess.restype = wintypes.HANDLE
KERNEL.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
KERNEL.WaitForSingleObject.restype = wintypes.DWORD
KERNEL.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
KERNEL.GetProcessTimes.restype = wintypes.BOOL
KERNEL.CloseHandle.argtypes = (wintypes.HANDLE,)
KERNEL.CloseHandle.restype = wintypes.BOOL


def process_times(handle):
    values = [wintypes.FILETIME() for _ in range(4)]
    require(bool(KERNEL.GetProcessTimes(handle, *(ctypes.byref(v) for v in values))), 'PROCESS_TIMES_UNCONFIRMED')
    return {'birth_100ns': (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime,
            'exit_100ns': (values[1].dwHighDateTime << 32) | values[1].dwLowDateTime,
            'exited': KERNEL.WaitForSingleObject(handle, 0) == 0}


def capture_owner(status):
    pid = status.get('pid')
    require(type(pid) is int and pid > 0 and status.get('generation'), 'READY_OWNER_MISSING')
    handle = KERNEL.OpenProcess(0x1000 | 0x100000, False, pid)
    require(bool(handle), 'OWNER_HANDLE_UNAVAILABLE')
    HANDLES.append(handle)
    times = process_times(handle)
    require(not times['exited'], 'OWNER_ALREADY_EXITED')
    return {'handle': handle, 'pid': pid, 'generation': status['generation'],
            'instance_id': status['instance_id'], **times}


def native_observation(name, selected):
    task = selected.tasks.read(selected.name)
    if task is None:
        return {'name': selected.name, 'exists': False}
    receipt, verified = selected.observe()
    require(receipt is not None and verified.digest == task.digest, 'OWNERSHIP_UNCONFIRMED')
    token = receipt['token']
    if name in OWNERSHIP:
        require(token == OWNERSHIP[name], 'INSTALLATION_OWNER_CHANGED')
    else:
        OWNERSHIP[name] = token
    context_path = Path(PLAN['server_home'] if name == 'nexus' else PLAN['connector_state']) / 'service-context.json'
    context = json.loads(context_path.read_text(encoding='utf-8'))
    expected_extra = {'OKTO_NEXUS_CONNECTOR_STATE': PLAN['connector_state']} if name == 'connector' else {}
    approved = {k.upper(): v for k, v in (ENV | expected_extra).items()}
    approved['PATH'] = os.pathsep.join(dict.fromkeys(str(Path(item).resolve()) for item in ENV['PATH'].split(os.pathsep) if item and Path(item).is_absolute()))
    require(all(approved.get(k.upper()) == v for k, v in context['environment'].items()), 'RECORDED_ENVIRONMENT_MISMATCH')
    require(context['executable'] == PLAN['python'] and context['cwd'] == (PLAN['project_root'] if name == 'nexus' else PLAN['connector_state']), 'RECORDED_CONTEXT_MISMATCH')
    if name == 'nexus':
        args = context['arguments']
        for flag, value in [('--embedding-mode', 'off'), ('--feature-harness-integrations', 'false'), ('--metrics-mode', 'disabled'), ('--port', '52106')]:
            require(flag in args and args[args.index(flag) + 1] == value, 'RECORDED_FLAGS_MISMATCH')
    return {'name': selected.name, 'exists': True, 'state': task.state, 'enabled': task.enabled,
            'last_result': task.last_result, 'digest': task.digest, 'ownership_confirmed': True,
            'owner_token_unchanged': True, 'context_digest': receipt['context_digest'],
            'recorded_environment_is_approved_subset': True,
            'action_shape': {'executable': PLAN['pythonw'], 'component': name,
                             'installation_token': 'PRESENT_REDACTED', 'supervised_foreground': True}}


def status(name, step):
    _, value, report = command(step['followup_status_argv'], step['id'] + '-status')
    require(value.get('instance_id') == INSTANCE[name], 'STATUS_INSTANCE_MISMATCH')
    require(value.get('state') in ('ready', 'stopped'), 'STATUS_UNCONFIRMED')
    return value, report


def resume_preflight():
    prior = ROOT / 'execution-001'
    initial = json.loads((prior / 'preflight.json').read_text())
    first = json.loads((prior / 'nexus-01-install.json').read_text())
    observed = json.loads((prior / 'nexus-01-install-status.json').read_text())
    failure = json.loads((prior / 'failure.json').read_text())
    record = json.loads((prior / 'execution-record.json').read_text())
    require(sha((ROOT / 'execute_campaign.py').read_bytes()) == '3b4e00cb501c715e53da34f72b32e81727cbe92dd04229fd241b74aa81a5d014', 'INITIAL_RUNNER_CHANGED')
    require(initial['proposal_sha256'] == sha(PLAN_BYTES) and PLAN['revision'] == 4 and PLAN['port'] == 52106, 'PROPOSAL_CHANGED')
    require(record['attempted'] == [{'id': 'nexus-01-install', 'at': record['attempted'][0]['at']}] and not record['passed'], 'PRIOR_PROGRESSION_MISMATCH')
    require(failure['reason'] == 'RECORDED_ENVIRONMENT_MISMATCH' and not failure['live_cli_handles'], 'PRIOR_FAILURE_MISMATCH')
    require(first['returncode'] == 0 and first['result']['state'] == 'stopped', 'PRIOR_INSTALL_UNCONFIRMED')
    require(observed['returncode'] == 0 and observed['result']['state'] == 'stopped', 'PRIOR_STATUS_UNCONFIRMED')
    require(Path(sys.executable).absolute() == Path(PLAN['python']) and sys.flags.isolated, 'PYTHON_MISMATCH')
    require(dict(os.environ) == {k.upper(): v for k, v in ENV.items()}, 'ENVIRONMENT_MISMATCH')
    packages = package_proof()
    require(packages == initial['packages'], 'PRE_RESUME_PACKAGE_CHANGED')
    for key in ('connector_state', 'project_root'):
        require(not any(Path(PLAN[key]).iterdir()), 'UNSTARTED_HOME_CHANGED')
    port_free()
    selected = services()
    require(selected['connector'].tasks.read(selected['connector'].name) is None, 'UNSTARTED_TASK_EXISTS')
    task = selected['nexus'].tasks.read(selected['nexus'].name)
    expected = observed['result']['user_service']['definition_digest']
    require(task is not None and task.digest == expected and task.enabled and task.state == 3, 'INSTALLED_TASK_CHANGED')
    native = native_observation('nexus', selected['nexus'])
    require(native['digest'] == expected, 'OWN_RECEIPT_NOT_CONFIRMED')
    result = {'status': 'PASS', 'at': now(), 'proposal_sha256': sha(PLAN_BYTES), 'revision': PLAN['revision'],
              'runner_sha256': sha(Path(__file__).read_bytes()), 'packages': packages,
              'port_free': True, 'port': 52106, 'native_mutations_during_resume_preflight': 0,
              'nexus_owned_stopped_task': native, 'connector_task_absent': True,
              'original_failure_preserved': str(prior / 'failure.json'),
              'completed_install_will_not_repeat': True,
              'normalization': 'Expected PATH canonicalized using the existing context Path.resolve contract; child environment unchanged.',
              'user_authorization': 'sim pode executar'}
    save('preflight.json', result)
    return result


def execute():
    global RECORD
    require(not (OUT / 'execution-record.json').exists(), 'CAMPAIGN_ALREADY_ATTEMPTED')
    before = resume_preflight()  # Reconcile completed install; never repeat its effect.
    selected = services()
    RECORD = {'status': 'RUNNING', 'started_at': now(), 'user_authorization': 'sim pode executar',
              'proposal_sha256': sha(PLAN_BYTES), 'runner_sha256': sha(Path(__file__).read_bytes()),
              'planned_actions': 24, 'attempted': [], 'passed': [], 'owners': {},
              'limits': ['empty Windows runtimes only', 'no logout/reboot', 'no providers/credentials/turns',
                         'no force/kill', 'no M1/M2 completion claim']}
    save('execution-record.json', RECORD)
    owners = {}
    first_digests = {}
    for step in PLAN['steps']:
        name, phase = step['component'], int(step['id'].split('-')[1])
        previous_owner = owners.get(name)
        if phase > 1:
            native_observation(name, selected[name])
        RECORD['attempted'].append({'id': step['id'], 'at': now()})
        save('execution-record.json', RECORD)
        if step['id'] == 'nexus-01-install':
            command_report = json.loads((ROOT / 'execution-001/nexus-01-install.json').read_text())
            code, result = command_report['returncode'], command_report['result']
            command_report = {**command_report, 'effect_replayed': False, 'observation_resumed': True}
        else:
            code, result, command_report = command(step['argv'], step['id'])
        expected = step['expect_returncode']
        require((code != 0 if expected == 'nonzero' else code == expected), 'ACTION_EXIT_MISMATCH')
        current, status_report = status(name, step)
        native = native_observation(name, selected[name])
        if phase == 12:
            require(not native['exists'] and current['state'] == 'stopped', 'UNINSTALL_NOT_CONFIRMED')
        else:
            require(native['exists'], 'INSTALLED_TASK_MISSING')
            require(native['enabled'] is (phase not in (5, 6, 7)), 'ENABLEMENT_MISMATCH')
        if phase == 1:
            first_digests[name] = native['digest']
        if phase == 2:
            require(native['digest'] == first_digests[name], 'REPEATED_INSTALL_CHANGED_DEFINITION')
        if phase in (3, 4, 5, 9, 10):
            require(current['state'] == 'ready' and current.get('ready_for_queries') is True, 'READINESS_NOT_CONFIRMED')
            require(current.get('supervisor') == 'windows-task-scheduler', 'SUPERVISOR_MISMATCH')
            version = PLAN['packages']['okto-nexus' if name == 'nexus' else 'okto-nexus-connector']['version']
            require(current.get('active_version') == version, 'ACTIVE_VERSION_MISMATCH')
            fresh = capture_owner(current)
            if phase in (4, 5):
                require(all(fresh[k] == previous_owner[k] for k in ('pid', 'generation', 'birth_100ns', 'instance_id')), 'REUSE_OWNER_CHANGED')
            if phase in (9, 10):
                old = process_times(previous_owner['handle'])
                require(old['exited'] and fresh['generation'] != previous_owner['generation'], 'RESTART_OWNER_NOT_REPLACED')
                require(old['exit_100ns'] <= fresh['birth_100ns'], 'RESTART_PROCESS_OVERLAP')
            owners[name] = fresh
        else:
            require(current['state'] == 'stopped', 'PROCESS_NOT_STOPPED')
            if native['exists']:
                require(native['state'] not in (0, 2, 4), 'NATIVE_TASK_STILL_ACTIVE')
        if phase in (6, 11):
            require(result.get('shutdown_outcome') == 'drained', 'DRAIN_NOT_CONFIRMED')
            require(previous_owner is not None and process_times(previous_owner['handle'])['exited'], 'PRIOR_OWNER_STILL_ALIVE')
        if phase == 7:
            require('DISABLED' in str(result.get('reason') or result.get('error', {}).get('code', '')), 'DISABLED_REFUSAL_NOT_CONFIRMED')
        if phase == 12 and 'followup_service_status_argv' in step:
            _, service_status, _ = command(step['followup_service_status_argv'], step['id'] + '-service-status')
            require(service_status.get('installed') is False, 'SERVICE_UNINSTALL_STATUS_MISMATCH')
        evidence = {'id': step['id'], 'action': command_report, 'status': status_report,
                    'native': native, 'assertions': 'PASS'}
        if name in owners:
            owner = owners[name]
            evidence['owner'] = {k: owner[k] for k in ('pid', 'generation', 'instance_id', 'birth_100ns')}
            evidence['owner'].update(process_times(owner['handle']))
        RECORD['passed'].append(evidence)
        RECORD['owners'][name] = evidence.get('owner')
        save('execution-record.json', RECORD)
        print(json.dumps({'checkpoint': step['id'], 'status': 'PASS'}), flush=True)
    port_free()
    require(all(selected[n].tasks.read(selected[n].name) is None for n in selected), 'FINAL_TASK_REMAINS')
    require(all(process_times(owner['handle'])['exited'] for owner in owners.values()), 'FINAL_OWNER_REMAINS')
    require(package_proof() == before['packages'], 'POST_PACKAGE_CHANGED')
    RECORD.update(status='PASS', completed_at=now(), cleanup_confirmed=True,
                  tasks_absent=True, owners_exited=True, listener_closed=True, packages_unchanged=True)
    save('execution-record.json', RECORD)
    print(json.dumps({'status': 'PASS', 'actions': 24, 'cleanup_confirmed': True}), flush=True)


if __name__ == '__main__':
    try:
        require(sys.argv[1:] in (['preflight'], ['execute']), 'MODE_INVALID')
        if sys.argv[1] == 'preflight':
            report = resume_preflight()
            print(json.dumps({'status': report['status'], 'path': str(OUT / 'preflight.json'),
                              'resumption_fenced': True, 'port_free': True}), flush=True)
        else:
            execute()
    except Exception as error:
        failure = {'status': 'STOPPED_PROGRESSION', 'at': now(),
                   'reason': str(error) if isinstance(error, StopProgression) else type(error).__name__,
                   'runner_pid': os.getpid(), 'cleanup_confirmed': False,
                   'live_cli_handles': [p.pid for p in CHILDREN if p.poll() is None]}
        save('failure.json', failure)
        if RECORD is not None:
            RECORD.update(failure)
            save('execution-record.json', RECORD)
        print(json.dumps(failure), flush=True)
        # Keep ownership handles while a CLI or known service owner is alive.
        # Progression and mutations remain stopped. No timeout kills a process.
        while any(p.poll() is None for p in CHILDREN) or any(KERNEL.WaitForSingleObject(h, 0) != 0 for h in HANDLES):
            time.sleep(1)
        raise SystemExit(1)
    finally:
        for handle in HANDLES:
            KERNEL.CloseHandle(handle)
