"""Finite DX-T34 case. Import is inert; execution requires the reviewed proposal hash."""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import queue
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile

BASE = Path(__file__).resolve().parent
CONFIG = 'cli_auth_credentials_store = "file"\nmodel_provider = "openai"\n'
PROFILE = 'dx-t34-empty-login'


class Refused(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_once(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def load(reviewed_sha):
    path = BASE / 'proposal.json'
    require(sha(path) == reviewed_sha, 'PROPOSAL_REVIEW_MISMATCH')
    proposal = json.loads(path.read_bytes())
    require(Path(proposal['root']) == BASE and proposal['model_turn_limit'] == 0, 'SCOPE_MISMATCH')
    require(proposal['status'] == 'OFFLINE_QUALIFIED_PENDING_ROOT_EXECUTION', 'PROPOSAL_NOT_FROZEN')
    require(proposal['native_version'] == '0.157.0'
        and proposal['pins']['native']['sha256'] == 'ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f'
        and Path(proposal['pins']['driver']['path']).resolve() == Path(__file__).resolve(), 'EXECUTOR_SELECTION_CHANGED')
    for pin in proposal['pins'].values():
        p = Path(pin['path'])
        require(p.is_absolute() and p.is_file() and not p.is_symlink() and sha(p) == pin['sha256'], 'PIN_MISMATCH')
    return proposal


def environment(root, prefix, native, inherited):
    # No ambient provider API keys, proxy, login or personal configuration paths.
    env = {key: inherited[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in inherited}
    require('SYSTEMROOT' in env, 'WINDOWS_ENVIRONMENT_REQUIRED')
    env.update(HOME=str(root / 'profile'), USERPROFILE=str(root / 'profile'),
        CODEX_HOME=str(root / 'profile/.codex'), APPDATA=str(root / 'appdata'),
        LOCALAPPDATA=str(root / 'localappdata'), TEMP=str(root / 'tmp'), TMP=str(root / 'tmp'),
        PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PIP_CONFIG_FILE=os.devnull)
    env['PATH'] = os.pathsep.join((str(prefix / 'Scripts'), str(native.parent),
                                  str(Path(env['SYSTEMROOT']) / 'System32')))
    return env


def validate_config(value):
    config = value.get('config') if isinstance(value, dict) else None
    require(isinstance(config, dict) and config.get('cli_auth_credentials_store') == 'file', 'FILE_CREDENTIAL_STORE_NOT_OBSERVED')
    require(config.get('model_provider') in (None, 'openai'), 'PROVIDER_CONTEXT_CHANGED')
    return {'credential_store': 'file', 'provider': config.get('model_provider')}


def validate_account(value):
    require(isinstance(value, dict) and 'account' in value and value['account'] is None
            and value.get('requiresOpenaiAuth') is True, 'MISSING_LOGIN_NOT_PROVED')
    return {'account_present': False, 'requires_openai_auth': True, 'refresh_token': False}


def preflight(native, root, env, *, popen=subprocess.Popen):
    """Only initialize/config/account; no thread/start, turn/start or login RPC."""
    # Read the same own-home configuration that the later service child sees;
    # an argv override here could conceal a wrong CODEX_HOME/config selection.
    argv = [str(native), 'app-server']
    child = popen(argv, cwd=root / 'project', env=env, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    incoming = queue.Queue(maxsize=128)
    invalid = threading.Event()
    def read():
        while True:
            line = child.stdout.readline(1048577)
            if not line:
                return
            if len(line) > 1048576:
                invalid.set()
                continue
            try:
                value = json.loads(line)
                incoming.put_nowait(value)
            except (ValueError, queue.Full):
                invalid.set()
    def discard_stderr():
        while child.stderr.read(4096):
            pass  # Never persist potential account/provider diagnostics.
    readers = [threading.Thread(target=read, daemon=True), threading.Thread(target=discard_stderr, daemon=True)]
    for reader in readers:
        reader.start()
    methods = []
    def send(value):
        child.stdin.write((json.dumps(value) + '\n').encode('utf8'))
        child.stdin.flush()
    def rpc(method, params):
        require(method in {'initialize', 'config/read', 'account/read'}, 'RPC_OUTSIDE_SCOPE')
        request_id = len(methods) + 1
        methods.append(method)
        send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + 30
        while True:
            require(not invalid.is_set(), 'NATIVE_PROTOCOL_UNCONFIRMED')
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'NATIVE_READ_TIMEOUT')
            try:
                message = incoming.get(timeout=remaining)
            except queue.Empty:
                raise Refused('NATIVE_READ_TIMEOUT') from None
            require(isinstance(message, dict), 'NATIVE_PROTOCOL_UNCONFIRMED')
            require(not ('method' in message and 'id' in message), 'UNEXPECTED_NATIVE_REQUEST')
            if message.get('id') == request_id:
                require('result' in message and 'error' not in message, 'NATIVE_RPC_REFUSED')
                return message['result']
    report = None
    try:
        rpc('initialize', {'clientInfo': {'name': 'nexus-dx34-audit', 'version': '1'},
                           'capabilities': {'experimentalApi': True}})
        send({'method': 'initialized', 'params': {}})
        config = validate_config(rpc('config/read', {'includeLayers': False, 'cwd': str(root / 'project')}))
        account = validate_account(rpc('account/read', {'refreshToken': False}))
        report = dict(config=config, account=account, methods=methods, model_turns=0, pid=child.pid)
    finally:
        child.stdin.close()  # Normal protocol EOF only; never terminate/kill.
        try:
            exit_code = child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise Refused('NATIVE_EOF_EXIT_UNCONFIRMED_PID_' + str(child.pid)) from None
        for reader in readers:
            reader.join(timeout=1)
        child.stdout.close()
        child.stderr.close()
    require(exit_code == 0, 'NATIVE_PREFLIGHT_EXIT_NONZERO')
    return {**report, 'exit_code': exit_code, 'physical_exit_observed': True}


class ProcessProof:
    """Retain the actual owner process handle; PID absence is not an exit proof."""
    def __init__(self, pid):
        require(type(pid) is int and pid > 0 and os.name == 'nt', 'OWNER_PID_INVALID')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.OpenProcess(0x100000 | 0x1000, False, pid)
        require(bool(self.handle), 'OWNER_HANDLE_UNAVAILABLE')
        created, ended, kernel, user = (wintypes.FILETIME() for _ in range(4))
        require(bool(self.kernel.GetProcessTimes(self.handle, ctypes.byref(created), ctypes.byref(ended),
                    ctypes.byref(kernel), ctypes.byref(user))), 'OWNER_BIRTH_UNAVAILABLE')
        self.birth = (created.dwHighDateTime << 32) | created.dwLowDateTime
        self.pid = pid
        require(self.kernel.WaitForSingleObject(self.handle, 0) == 258, 'OWNER_ALREADY_EXITED')

    def wait(self, timeout):
        return self.kernel.WaitForSingleObject(self.handle, int(timeout * 1000)) == 0

    def close(self):
        self.kernel.CloseHandle(self.handle)


def journal_proof(root):
    journals = list((root / 'nexus-home/connection-tests').glob('*/journal.db'))
    require(len(journals) == 1, 'SETUP_JOURNAL_COUNT_UNEXPECTED')
    path = journals[0]
    require(path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(), 'JOURNAL_PATH_CHANGED')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.25) as db:
        db.execute('PRAGMA query_only=ON')
        opens = db.execute("SELECT stage,error_code,possible_effect,retry_safe FROM operations_v2 WHERE operation_id='open'").fetchall()
        turns = db.execute("SELECT COUNT(*) FROM operation_actions WHERE action IN ('turn.submit','turn.steer')").fetchone()[0]
        turn_receipts = db.execute("SELECT COUNT(*) FROM operations_v2 WHERE operation_id='turn'").fetchone()[0]
    require(opens == [('FAILED', 'PROVIDER_AUTH_REQUIRED', 1, 0)] and turns == turn_receipts == 0, 'AUTH_FAILURE_OR_ZERO_TURN_UNCONFIRMED')
    return dict(journal_relative=str(path.relative_to(root)), open_stage='FAILED', error_code='PROVIDER_AUTH_REQUIRED',
                possible_effect=True, retry_safe=False, turn_actions=turns, turn_receipts=turn_receipts,
                read_after_owner_exit=True, sha256=sha(path))


def validate_review(review, proposal, root):
    require(review.get('state') == 'review', 'SETUP_REVIEW_UNAVAILABLE')
    selected = review['selection']
    config = review['request']['configuration']
    require(selected['candidate_ref'] == proposal['candidate_ref'] and selected['agent'] == PROFILE,
            'SETUP_SELECTION_CHANGED')
    require(Path(config['provider_home']) == root / 'profile/.codex'
            and Path(config['workspace_root']) == root / 'project', 'SETUP_PATH_CHANGED')
    require(config['adapter_id'] == 'codex_app_server' and config['harness_settings'] == {}
            and config['secret_bindings'] == {}, 'SETUP_AUTH_CONTEXT_CHANGED')
    require(config['authorization'] == {'minutes': 60, 'no_expiry': False, 'actions': 20, 'unlimited_actions': False},
            'SETUP_GRANT_CHANGED')
    require(not review['request']['broadcast_handoff_auto_claim'], 'SETUP_AUTOMATION_CHANGED')
    return review['review_revision']


def validate_failure(value, root):
    require(value.get('state') == 'test_failed' and value.get('error_code') == 'PROVIDER_AUTH_REQUIRED', 'CLI_AUTH_FAILURE_UNCONFIRMED')
    # Public retryable_failure is true only after the task and cleanup finish;
    # the internal cleanup_confirmed boolean is deliberately not exposed.
    require(value.get('work_state') == 'not_submitted' and value.get('test', {}).get('retryable_failure') is True,
            'SETUP_CLEANUP_UNCONFIRMED')
    guidance = value.get('next_action', '')
    require('codex login' in guidance and str(root / 'profile/.codex') in guidance, 'CLI_GUIDANCE_UNCONFIRMED')
    return {key: value[key] for key in ('state', 'error_code', 'work_state', 'next_action', 'setup_run_id')}


def verify_installed(proposal, prefix):
    count = 0
    site = prefix / 'Lib/site-packages'
    for key in ('nexus_wheel', 'core_wheel'):
        with zipfile.ZipFile(proposal['pins'][key]['path']) as wheel:
            for item in wheel.infolist():
                if item.is_dir() or not item.filename.startswith(('okto_nexus/', 'nexus_connector_core/')):
                    continue
                path = site / item.filename
                require(path.resolve().is_relative_to(site.resolve()) and path.is_file() and not path.is_symlink()
                    and hashlib.sha256(wheel.read(item)).hexdigest() == sha(path), 'INSTALLED_PAYLOAD_MISMATCH')
                count += 1
    require(count > 0, 'INSTALLED_PAYLOAD_EMPTY')
    return {'files_equal_to_pinned_wheels': count}


def install(proposal):
    require(not (BASE / 'installation/venv').exists(), 'INSTALLATION_ALREADY_EXISTS')
    write_once(BASE / 'installation-reserved.json', {'mode': 'dependencies_and_two_products', 'proposal_sha256': sha(BASE / 'proposal.json')})
    subprocess.run([sys.executable, '-I', '-B', str(BASE / 'installation/prepare_dependencies.py')], check=True)
    python = BASE / 'installation/venv/Scripts/python.exe'
    env = json.loads((BASE / 'installation/environment.json').read_bytes())
    subprocess.run([str(python), '-I', '-B', '-m', 'pip', 'install', '--no-index', '--no-deps',
        proposal['pins']['core_wheel']['path'], proposal['pins']['nexus_wheel']['path']], env=env, check=True)
    write_once(BASE / 'installation-complete.json', {'status': 'TWO_PRODUCTS_INSTALLED', 'python': str(python),
        'payload': verify_installed(proposal, BASE / 'installation/venv')})


def run(proposal):
    prefix = BASE / 'installation/venv'
    require(Path(sys.executable).resolve() == (prefix / 'Scripts/python.exe').resolve(), 'USE_OWN_INSTALLED_PYTHON')
    installed = verify_installed(proposal, prefix)
    import okto_nexus
    import nexus_connector_core
    require(all(Path(module.__file__).resolve().is_relative_to(prefix) for module in (okto_nexus, nexus_connector_core)),
            'SOURCE_IMPORT_NOT_ALLOWED')
    root = BASE / 'campaign'
    root.mkdir(exist_ok=False)  # One execution only, including failed attempts.
    # Protect this exact new tree before the product can create private state.
    sid = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True).strip().split(',')[-1].strip('"')
    require(sid.startswith('S-1-5-'), 'USER_SID_UNAVAILABLE')
    subprocess.run(['icacls', str(root), '/inheritance:r', '/grant:r', '*'+sid+':(OI)(CI)F',
                    '*S-1-5-18:(OI)(CI)F'], stdout=subprocess.DEVNULL, check=True)
    for name in ('public', 'private', 'project', 'profile/.codex', 'appdata', 'localappdata', 'tmp', 'nexus-home'):
        (root / name).mkdir(parents=True, exist_ok=True)
    config = root / 'profile/.codex/config.toml'
    config.write_text(CONFIG, encoding='utf8')
    native = Path(proposal['pins']['native']['path'])
    env = environment(root, prefix, native, os.environ)
    selection = ['--home', str(root / 'nexus-home'), '--host', '127.0.0.1', '--port', str(proposal['port']),
        '--project-root', str(root / 'project'), '--embedding-mode', 'off', '--feature-harness-integrations', 'true',
        '--metrics-mode', 'disabled', '--harness-root', str(native.parent)]
    base = [str(prefix / 'Scripts/python.exe'), '-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main']
    children = []
    def cli(label, args, timeout=90):
        write_once(root / 'public' / (label + '-reserved.json'), {'argv': base + args + selection, 'time': time.time()})
        with (root / 'private' / (label + '.stdout')).open('xb') as out, (root / 'private' / (label + '.stderr')).open('xb') as err:
            child = subprocess.Popen(base + args + selection, cwd=root, env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
            children.append(child)
            try:
                code = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                write_once(root / 'public' / (label + '-uncertain.json'), {'pid': child.pid, 'code': 'CLI_TIMEOUT_NO_KILL'})
                raise Refused('CLI_TIMEOUT_' + label) from None
        raw = (root / 'private' / (label + '.stdout')).read_bytes()
        require(len(raw) <= 8 * 1048576, 'CLI_OUTPUT_TOO_LARGE')
        try:
            value = json.loads(raw)
        except ValueError:
            raise Refused('CLI_JSON_UNCONFIRMED_' + label) from None
        return code, value
    proof = None
    started = False
    failure = None
    result = {'status': 'UNCONFIRMED', 'proposal_sha256': sha(BASE / 'proposal.json'), 'model_turn_limit': 0,
              'installed_payload': installed}
    try:
        write_once(root / 'public/preflight-reserved.json', {'scope': 'initialize/config/read/account/read, no login/refresh/thread/turn'})
        result['preflight'] = preflight(native, root, env)
        write_once(root / 'public/preflight.json', result['preflight'])
        require(not (root / 'profile/.codex/auth.json').exists() and config.read_text(encoding='utf8') == CONFIG,
                'PREFLIGHT_AUTH_OR_CONFIG_CHANGED')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', proposal['port']))
        started = True
        code, owner = cli('start', ['service', 'start', '--timeout', '120', '--json'], timeout=150)
        require(code == 0 and owner['state'] == 'ready' and owner['ready_for_queries'] is True, 'SERVICE_NOT_READY')
        proof = ProcessProof(owner['pid'])
        result['owner'] = {key: owner[key] for key in ('pid', 'generation', 'instance_id', 'active_version')}
        result['owner']['birth_100ns'] = proof.birth
        code, confirmed = cli('owner-confirmed', ['service', 'status', '--json'])
        require(code == 0 and confirmed['state'] == 'ready' and confirmed['ready_for_queries'] is True
            and all(confirmed[k] == owner[k] for k in ('pid', 'generation', 'instance_id')) and not proof.wait(0),
            'OWNER_CHANGED_DURING_HANDLE_CAPTURE')
        code, reviewed = cli('plan', ['connect', '--plan', '--client', 'codex', '--project', str(root / 'project'),
            '--profile', PROFILE, '--new-agent', PROFILE, '--provider-home', str(root / 'profile/.codex'),
            '--candidate-ref', proposal['candidate_ref'], '--no-start-at-login', '--no-chat', '--json'])
        require(code == 0, 'PLAN_FAILED')
        # Use the durable reviewed request, not presentation fields as authority.
        review = json.loads((root / 'nexus-home/terminal/profiles' / (PROFILE + '.json')).read_bytes())
        revision = validate_review(review, proposal, root)
        require(config.read_text(encoding='utf8') == CONFIG and not (root / 'profile/.codex/auth.json').exists(),
                'AUTH_CONTEXT_CHANGED_BEFORE_TEST')
        code, value = cli('apply', ['connect', '--profile', PROFILE, '--approve', revision,
            '--no-chat', '--timeout', '120', '--json'], timeout=270)
        require(code == 3, 'EXPECTED_AUTH_REFUSAL_EXIT')
        result['cli'] = validate_failure(value, root)
        code, after = cli('after', ['service', 'status', '--json'])
        require(code == 0 and after['state'] == 'ready' and after['ready_for_queries'] is True
                and all(after[k] == owner[k] for k in ('pid', 'generation', 'instance_id')) and not proof.wait(0),
                'OWNER_NOT_RESPONSIVE_AFTER_AUTH_FAILURE')
        result['owner_still_ready_after_failure'] = True
    except Exception as error:
        failure = str(error) if isinstance(error, Refused) else type(error).__name__
    finally:
        if started:
            try:
                stop_code, stop = cli('stop', ['service', 'stop', '--timeout', '45', '--json'])
                result['stop'] = {'cli_exit': stop_code, 'state': stop.get('state'), 'reason': stop.get('reason')}
                result['physical_owner_exit'] = proof is not None and proof.wait(15)
            except Exception as error:
                result['stop_error'] = str(error) if isinstance(error, Refused) else type(error).__name__
        if proof is not None:
            proof.close()
    result['wrapper_processes_exited'] = all(child.poll() is not None for child in children)
    if (failure is None and result.get('physical_owner_exit') is True and result['wrapper_processes_exited']
            and result.get('stop', {}).get('cli_exit') == 0 and result['stop'].get('state') == 'stopped'):
        try:
            result['journal'] = journal_proof(root)
            result['status'] = 'DX_T34_AUTH_ABSENT_DIAGNOSED_ZERO_TURN'
        except Exception as error:
            failure = str(error) if isinstance(error, Refused) else type(error).__name__
    result['failure'] = failure
    write_once(root / 'public/result.json', result)
    print(json.dumps(result), flush=True)
    return 0 if result['status'] == 'DX_T34_AUTH_ABSENT_DIAGNOSED_ZERO_TURN' else 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['install', 'run'])
    parser.add_argument('--reviewed-proposal-sha', required=True)
    args = parser.parse_args()
    proposal = load(args.reviewed_proposal_sha)
    if args.mode == 'install':
        install(proposal)
        return 0
    return run(proposal)


if __name__ == '__main__':
    raise SystemExit(main())
