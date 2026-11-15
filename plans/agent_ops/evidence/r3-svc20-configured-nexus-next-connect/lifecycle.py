"""One selected configured connect; installed lifecycle plus retained W16 cohort helpers."""
from pathlib import Path
from types import SimpleNamespace
import argparse
import importlib.util
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
CHILDREN = []
HANDLES = {}


def require(ok, code):
    if not ok:
        raise ValueError(code)


def save(name, value):
    with (ROOT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def operation_count(home):
    # Count only; no action payloads, authentication material or journal mutation.
    with sqlite3.connect((Path(home) / 'nexus.db').as_uri() + '?mode=ro', uri=True, timeout=1) as db:
        db.execute('PRAGMA query_only=ON')
        deadline = time.monotonic() + 2
        db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        return db.execute('SELECT count(*) FROM execution_operations').fetchone()[0]


def protect_private(path):
    import ntsecuritycon
    import win32api
    import win32con
    import win32security
    path.mkdir()
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        owner = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    acl = win32security.ACL()
    for sid in (owner, win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)):
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, 3, ntsecuritycon.FILE_ALL_ACCESS, sid)
    win32security.SetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None)


def cli(plan, label, argv, digest):
    require(argv[0] == plan['python'] and '--force' not in argv, 'COMMAND_SCOPE_CHANGED')
    save(label + '-reserved.json', {'argv': argv, 'selected_at': time.time(), 'repeat_allowed': False})
    out = ROOT / 'private' / (label + '.stdout')
    err = ROOT / 'private' / (label + '.stderr')
    with out.open('xb') as stdout, err.open('xb') as stderr:
        child = subprocess.Popen(argv, cwd=plan['cwd'], env=plan['environment'], stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        CHILDREN.append(child)
        try:
            code = child.wait(timeout=180)
        except subprocess.TimeoutExpired:
            save(label + '-timeout.json', {'status': 'CLI_TIMEOUT_UNCONFIRMED', 'pid': child.pid,
                'retained_handle': True, 'no_kill': True, 'no_replay': True})
            raise ValueError('CLI_TIMEOUT_UNCONFIRMED') from None
    try:
        value = json.loads(out.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            value = {}
    except (ValueError, UnicodeError):
        value = {}
    save(label + '-returned.json', {'returncode': code, 'wrapper_exit_confirmed': True,
        'stdout_sha256': digest(out), 'stderr_sha256': digest(err),
        'reported': {k: value.get(k) for k in ('state', 'code', 'reason', 'shutdown_outcome')}})
    return code, value


def snapshot_data(plan, digest):
    result = {}
    for item in plan['retained_data']:
        path = Path(item)
        require(path.is_file() and not path.is_symlink(), 'RETAINED_DATA_MISSING')
        result[item] = {'sha256': digest(path), 'bytes': path.stat().st_size}
    return result


def handoff(context, cohort, connect_selected):
    """Failure remains failure; keep CLI/cohort handles while root chooses normal cleanup."""
    save('failure-handoff.json', {'cohort_captured': bool(HANDLES),
        'connect_selected': connect_selected, 'root_owns_normal_cleanup': True,
        'seconds': 7200, 'force': False, 'empty_handle_set_is_not_exit_proof': True})
    deadline = time.monotonic() + 7200
    while time.monotonic() < deadline:
        if connect_selected and not HANDLES and all(p.poll() is not None for p in CHILDREN):
            try:
                selected, captured = cohort.capture(context)
                HANDLES.update(captured)
                save('late-cohort-selection.json', selected)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                pass
        try:
            exited = bool(HANDLES) and all(h.exited() for h in HANDLES.values())
        except (OSError, ValueError, RuntimeError):
            exited = False
        if all(p.poll() is not None for p in CHILDREN) and (exited or not connect_selected):
            save('handoff-finished.json', {'cli_exits_confirmed': True,
                'captured_cohort_exits_confirmed': exited, 'acceptance_promoted': False})
            return
        time.sleep(2)
    save('handoff-timeout.json', {'status': 'UNKNOWN', 'retry_allowed': False,
                                 'acceptance_promoted': False})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = json.loads((ROOT / 'lifecycle-plan.json').read_bytes())
    if not args.execute:
        print(json.dumps({'status': plan['status'], 'commands': plan['commands'], 'effects': 0}, indent=2))
        return 0
    require(Path(sys.prefix).resolve() == Path(plan['python_prefix']).resolve(), 'INSTALLED_PREFIX_REQUIRED')
    connect = load_module('svc20_connect', ROOT / 'run.py')
    connect_plan = json.loads((ROOT / 'plan.json').read_bytes())
    connect.validate(connect_plan)
    for pin in plan['pins']:
        require(connect.digest(pin['path']) == pin['sha256'], 'LIFECYCLE_PIN_CHANGED')
    save('execution-selected.json', {'plan_sha256': connect.digest(ROOT / 'lifecycle-plan.json'),
        'single_invocation': True, 'provider_turns_selected': 0})
    protect_private(ROOT / 'private')
    sys.path.insert(0, plan['cohort_directory'])
    import cohort
    from okto_nexus.adapters.outbound.service_manager.local import LocalServerLifecycle
    from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
    home = Path(plan['home'])
    context = SimpleNamespace(P={'paths': {'server_home': str(home)}, 'topology': {'origin': plan['origin']}},
        C={'tasks': {'nexus': plan['task']}}, installed={'python_images': plan['python_images']})
    service = cohort.installation(context)
    local = LocalServerLifecycle(home=home, database=home / 'nexus.db', host='127.0.0.1', port=plan['port'])
    connect_selected = False
    try:
        require(service.tasks.read(service.name) is None, 'EXACT_TASK_MUST_BE_ABSENT')
        absent = inspect_local_server(home=home, database=home / 'nexus.db', host='127.0.0.1', port=plan['port'], timeout=2)
        require(absent.get('state') == 'stopped' and absent.get('pid') is None and
                absent.get('reason') == 'NO_SERVICE_OWNER' and
                absent.get('instance_id') == plan['task']['instance_id'], 'CANONICAL_ABSENCE_REQUIRED')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(('127.0.0.1', plan['port']))
        operations_before = operation_count(home)
        require(cli(plan, 'install', plan['commands']['install'], connect.digest)[0] == 0, 'INSTALL_FAILED')
        _, task = service.observe()
        require(task is not None and not task.active and task.state == 3 and task.enabled, 'INSTALLED_STOPPED_REQUIRED')
        installed_digest = task.digest
        connect_selected = True
        code, _ = cli(plan, 'connect', plan['commands']['connect'], connect.digest)
        # Even a nonzero connect may have started the service. Capture before any stop.
        deadline = time.monotonic() + 180
        while True:
            value = cohort.readiness_probe(context)
            if value is not None:
                selected, handles = cohort.capture(context)
                HANDLES.update(handles)
                require(selected['task']['digest'] == installed_digest, 'INSTALLED_TASK_DEFINITION_CHANGED')
                save('cohort-selection.json', selected)
                break
            require(time.monotonic() < deadline, 'COHORT_CAPTURE_UNCONFIRMED')
            time.sleep(1)
        observation_path = ROOT / 'nexus-observation.json'
        observed = json.loads(observation_path.read_bytes()) if observation_path.exists() else {}
        connect_ok = code == 0 and observed.get('status') == 'CONFIGURED_NEXT_CONNECT_OBSERVED'
        cohort.same_cycle(selected['cohort'], cohort.cycle(context))
        cohort.same_owner(selected, cohort.status(context, 'nexus'))
        require(service.observe()[1].digest == installed_digest, 'TASK_DEFINITION_CHANGED_BEFORE_STOP')
        stopped, value = cli(plan, 'normal-stop', plan['commands']['stop'], connect.digest)
        require(stopped == 0 and value.get('shutdown_outcome') == 'drained', 'NORMAL_STOP_UNCONFIRMED')
        deadline = time.monotonic() + 30
        while not all(h.exited() for h in HANDLES.values()):
            require(time.monotonic() < deadline, 'COHORT_EXIT_UNCONFIRMED')
            time.sleep(.1)
        cohort.same_cycle(selected['cohort'], cohort.cycle(context))
        save('cohort-exit-proof.json', {'retained_handle': True, 'force': False,
            'processes': {role: {'pid': h.pid, 'birth': h.birth, 'exit_code': h.exit_code(),
                'physical_exit_confirmed': True} for role, h in HANDLES.items()}})
        deadline = time.monotonic() + 30
        while True:
            _, task = service.observe()
            if task is not None and task.state == 3 and not task.active:
                require(task.digest == installed_digest, 'TASK_DEFINITION_CHANGED_BEFORE_UNINSTALL')
                break
            require(time.monotonic() < deadline, 'NATIVE_INACTIVE_UNCONFIRMED')
            time.sleep(.1)
        require(local.inspect().get('state') == 'stopped', 'CANONICAL_STOP_REQUIRED')
        require(operation_count(home) == operations_before, 'NEW_EXECUTION_OPERATION_OBSERVED')
        before = snapshot_data(plan, connect.digest)
        save('data-before-uninstall.json', before)
        require(cli(plan, 'uninstall', plan['commands']['uninstall'], connect.digest)[0] == 0, 'UNINSTALL_FAILED')
        require(service.tasks.read(service.name) is None, 'TASK_REMAINS')
        after = snapshot_data(plan, connect.digest)
        require(before == after, 'UNINSTALL_CHANGED_RETAINED_DATA')
        save('result.json', {'status': 'PASS_SCOPED' if connect_ok else 'CONNECT_FAILED_CLEANUP_CONFIRMED',
            'configured_next_connect': connect_ok, 'new_execution_operations': 0,
            'cohort_exit_confirmed': True, 'task_absent': True, 'selected_data_retained': after,
            'scope': 'Nexus configured next-connect only; original both-host stop/190s proof reused; Connector remains pending.',
            'force_used': False, 'acceptance_promoted': False})
        return 0 if connect_ok else 3
    except BaseException as error:
        save('failure.json', {'status': 'UNCONFIRMED', 'error_type': type(error).__name__,
            'code': str(error) if isinstance(error, ValueError) and str(error).replace('_', '').isalnum() else None,
            'no_replay': True, 'cleanup_confirmed': False})
        handoff(context, cohort, connect_selected)
        return 3
    finally:
        for handle in HANDLES.values():
            handle.close()


if __name__ == '__main__':
    raise SystemExit(main())
