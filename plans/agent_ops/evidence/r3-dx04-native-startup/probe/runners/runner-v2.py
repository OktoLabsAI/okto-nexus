"""Disposable DX04 probe. Preparation only until explicitly invoked with --execute-native.

Uses installed Nexus, a real synthetic Server, real own Windows Credential Manager
entry, unmodified ParticipantLaunch, and its exact native Codex argv. No prompt,
login/trust selection, provider key, or productive tool call is sent.
"""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

NATIVE_SHA = 'edfdd48f8b458af0906e507b4cb05217b326c3d6e515e9f024e05e3b8d650f70'
HELPER_SHA = '76d063e78a2543e3e8234e035297539281e73f431578d29b8593740f19f6952a'
CONFIG = ('cli_auth_credentials_store = "file"\n'
          'mcp_oauth_credentials_store = "file"\n'
          'check_for_update_on_startup = false\n')
LABELS = ('Sign in with ChatGPT', 'Sign in with an API key', 'Use an API key',
          'Sign in to Codex', 'Do you trust', 'Trust this folder',
          'Do you trust the contents', 'Choose how you want to sign in',
          'Welcome to Codex', 'Press Enter to continue')
GATE_LABELS = LABELS[:8]


class ProbeRefusal(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise ProbeRefusal(code)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path = Path(path)
    pending = path.with_name(path.name + '.pending')
    pending.write_text(json.dumps(value, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    os.replace(pending, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


def error_code(error):
    # Never serialize a raw exception, potentially credential-bearing output,
    # arbitrary server text, native text, URLs or environment values.
    return error.args[0] if isinstance(error, ProbeRefusal) else type(error).__name__


def environment(root):
    system = Path(os.environ.get('SYSTEMROOT', r'C:\Windows'))
    native = root / 'native'
    mapping = {'HOME': native / 'home', 'USERPROFILE': native / 'home',
               'APPDATA': native / 'appdata', 'LOCALAPPDATA': native / 'localappdata',
               'XDG_CONFIG_HOME': native / 'xdg', 'CODEX_HOME': native / 'codex',
               'CLAUDE_CONFIG_DIR': native / 'claude', 'TEMP': native / 'tmp', 'TMP': native / 'tmp'}
    for path in mapping.values():
        path.mkdir(parents=True, exist_ok=True)
    empty = native / 'empty.gitconfig'
    empty.write_text('', encoding='utf-8')
    paths = [str(system / 'System32')]
    git = Path(r'C:/Program Files/Git/cmd')
    if (git / 'git.exe').is_file():
        paths.append(str(git))
    return {'SYSTEMROOT': str(system), 'WINDIR': str(system),
            'COMSPEC': str(system / 'System32/cmd.exe'), 'PATH': os.pathsep.join(paths),
            **{name: str(path) for name, path in mapping.items()},
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': str(empty),
            'GIT_CONFIG_SYSTEM': str(empty), 'PYTHONNOUSERSITE': '1', 'PYTHONUTF8': '1',
            'PYTHONIOENCODING': 'utf-8', 'OKTO_NEXUS_NO_BANNER': '1'}


class McpObserver:
    """Passive ASGI observer. Forward every original request/response unchanged."""
    def __init__(self, app, path):
        self.app, self.path = app, Path(path)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path', '').rstrip('/') != '/mcp':
            return await self.app(scope, receive, send)
        request_body, response_body = bytearray(), bytearray()
        status, truncated = None, False

        async def observed_receive():
            nonlocal truncated
            message = await receive()
            body = message.get('body', b'')
            if len(request_body) + len(body) <= 16384:
                request_body.extend(body)
            else:
                truncated = True
            return message

        async def observed_send(message):
            nonlocal status, truncated
            if message['type'] == 'http.response.start':
                status = message['status']
            body = message.get('body', b'')
            if len(response_body) + len(body) <= 8 * 1024 * 1024:
                response_body.extend(body)
            else:
                truncated = True
            await send(message)

        try:
            await self.app(scope, observed_receive, observed_send)
        finally:
            row = {'http_method': scope['method'], 'http_status': status, 'truncated': truncated}
            try:
                req = json.loads(request_body)
                method = req.get('method')
                row['method'] = method if method in ('initialize', 'notifications/initialized', 'tools/list', 'tools/call') else 'other'
                responses = []
                try:
                    responses.append(json.loads(response_body))
                except ValueError:
                    for line in response_body.splitlines():
                        if line.startswith(b'data: '):
                            try:
                                responses.append(json.loads(line[6:]))
                            except ValueError:
                                pass
                matched = [r for r in responses if isinstance(r, dict) and r.get('id') == req.get('id')]
                row['protocol_result'] = any(isinstance(r.get('result'), dict) and 'protocolVersion' in r['result'] for r in matched)
                row['tools_count'] = max([len(r['result']['tools']) for r in matched
                    if isinstance(r.get('result'), dict) and isinstance(r['result'].get('tools'), list)] or [0])
            except (ValueError, TypeError, AttributeError):
                row['method'] = 'unparsed'
            # No request/response body, header, key, token hash or session ID retained.
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row) + '\n')


def install_observer(path):
    from okto_nexus.adapters.inbound.http import app as app_module
    original = app_module.build_app

    def observed_build(*args, **kwargs):
        app = original(*args, **kwargs)
        app.add_middleware(McpObserver, path=path)
        return app

    app_module.build_app = observed_build


def observer_rows(path):
    try:
        lines = Path(path).read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return []
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except ValueError:
            pass  # A concurrent final line is incomplete until the next poll.
    return result


def mcp_confirmed(rows):
    good = [r for r in rows if r['http_status'] == 200 and not r['truncated']]
    return (any(r.get('method') == 'initialize' and r.get('protocol_result') for r in good)
            and any(r.get('method') == 'tools/list' and r.get('tools_count', 0) > 0 for r in good))


def console_worker(config_file):
    """Reopen the own hidden console; actual CLI/product launch runs unchanged."""
    import msvcrt
    config = read_json(config_file)
    root = Path(config['root'])
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    kernel.SetStdHandle.restype = wintypes.BOOL
    kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
    streams = []
    for name, device, mode, number in (('stdin', 'CONIN$', 'r', -10),
                                      ('stdout', 'CONOUT$', 'w', -11), ('stderr', 'CONOUT$', 'w', -12)):
        stream = open(device, mode, encoding='utf-8')
        streams.append(stream)
        setattr(sys, name, stream)
        require(kernel.SetStdHandle(number, msvcrt.get_osfhandle(stream.fileno())), 'STD_HANDLE')
    # Normal Python cancellation stops an in-flight CLI before a later spawn.
    # Unlike SetConsoleCtrlHandler(NULL,TRUE), no ignore flag reaches the child.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    facts = {'pid': os.getpid(), 'streams': {n: getattr(sys, n).isatty() for n in ('stdin', 'stdout', 'stderr')}}
    child_file = root / 'tty-child.json'
    child_code = ('import json,os,sys;from pathlib import Path;'
                  'Path(sys.argv[1]).write_text(json.dumps(dict(pid=os.getpid(),'
                  'streams={n:getattr(sys,n).isatty() for n in ("stdin","stdout","stderr")})))')
    subprocess.run([sys.executable, '-I', '-c', child_code, str(child_file)], check=True, timeout=5)
    require(all(facts['streams'].values()) and all(read_json(child_file)['streams'].values()), 'TTY_REQUIRED')
    write_json(root / 'tty-owner.json', facts)
    done = threading.Event()

    class Coord(ctypes.Structure):
        _fields_ = [('X', wintypes.SHORT), ('Y', wintypes.SHORT)]

    class Rect(ctypes.Structure):
        _fields_ = [('Left', wintypes.SHORT), ('Top', wintypes.SHORT), ('Right', wintypes.SHORT), ('Bottom', wintypes.SHORT)]

    class ScreenInfo(ctypes.Structure):
        _fields_ = [('size', Coord), ('cursor', Coord), ('attributes', wintypes.WORD), ('window', Rect), ('maximum', Coord)]

    kernel.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ScreenInfo)]
    kernel.GetConsoleScreenBufferInfo.restype = wintypes.BOOL
    kernel.ReadConsoleOutputCharacterW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, Coord, ctypes.POINTER(wintypes.DWORD)]
    kernel.ReadConsoleOutputCharacterW.restype = wintypes.BOOL

    def watch():
        labels, signalled = set(), False
        try:
            while not done.wait(.1):
                # Reopening CONOUT$ follows the active screen buffer; raw text
                # never leaves memory. Only fixed allowlisted labels are saved.
                with open('CONOUT$', 'w', encoding='utf-8') as output:
                    handle = msvcrt.get_osfhandle(output.fileno())
                    info = ScreenInfo()
                    if kernel.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
                        count = min(65536, info.size.X * (info.window.Bottom - info.window.Top + 1))
                        buffer, received = ctypes.create_unicode_buffer(count + 1), wintypes.DWORD()
                        if kernel.ReadConsoleOutputCharacterW(handle, buffer, count, Coord(0, info.window.Top), ctypes.byref(received)):
                            text = buffer.value.casefold()
                            labels.update(label for label in LABELS if label.casefold() in text)
                write_json(root / 'screen-labels.json', {'labels': sorted(labels),
                    'gate_seen': bool(labels.intersection(GATE_LABELS)), 'raw_text_retained': False})
                if (root / 'cancel.request').exists() and not signalled:
                    signalled = True
                    ok = bool(kernel.GenerateConsoleCtrlEvent(0, 0))  # Own new console only.
                    write_json(root / 'console-cancel.json', {'own_console_ctrl_c_sent': ok})
        except BaseException as exc:
            write_json(root / 'watcher-error.json', {'error_class': error_code(exc)})

    watcher = threading.Thread(target=watch, name='own-console-reader', daemon=False)
    watcher.start()
    result = {'participant_cli_invoked': False}
    try:
        from okto_nexus.adapters.inbound.cli.main import main
        result['participant_cli_invoked'] = True
        write_json(root / 'worker-stage.json', result)
        result['cli_exit'] = main(config['argv'])
        return int(result['cli_exit'])
    except BaseException as exc:
        result['error_class'] = error_code(exc)
        return 3
    finally:
        done.set()
        watcher.join(3)
        result['watcher_joined'] = not watcher.is_alive()
        write_json(root / 'worker-result.json', result)


class OwnedConsole:
    def __init__(self, config, env, cwd):
        import win32api
        import win32con
        import win32job
        import win32process
        self.api, self.job_api, self.process_api = win32api, win32job, win32process
        self.job = win32job.CreateJobObject(None, 'dx04-probe-' + uuid.uuid4().hex)
        self.process = self.thread = None
        self.cleanup_started = None
        self.facts = {'job_assigned_before_resume': False, 'kill_on_job_close': True}
        try:
            limits = win32job.QueryInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation)
            limits['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation, limits)
            startup = win32process.STARTUPINFO()
            startup.dwFlags |= win32con.STARTF_USESHOWWINDOW
            startup.wShowWindow = win32con.SW_HIDE
            argv = [sys.executable, '-I', str(Path(__file__).resolve()), '--console-worker', str(config)]
            self.process, self.thread, pid, tid = win32process.CreateProcess(
                None, subprocess.list2cmdline(argv), None, None, False,
                win32con.CREATE_NEW_CONSOLE | win32con.CREATE_SUSPENDED,
                env, str(cwd), startup)
            self.facts.update(leader_pid=pid, thread_id=tid)
            win32job.AssignProcessToJobObject(self.job, self.process)
            require(win32job.IsProcessInJob(self.process, self.job), 'JOB_MEMBERSHIP_REQUIRED')
            self.facts['job_assigned_before_resume'] = True
            self.started = time.monotonic()
            win32process.ResumeThread(self.thread)
        except BaseException:
            # The only process created here is still suspended unless membership
            # was established. Terminate this exact owned handle on preparation failure.
            if self.process is not None:
                win32api.TerminateProcess(self.process, 3)
                import win32event
                win32event.WaitForSingleObject(self.process, 10000)
            self.close_handles()
            raise

    def active(self):
        return self.job_api.QueryInformationJobObject(self.job,
            self.job_api.JobObjectBasicAccountingInformation)['ActiveProcesses']

    def contain_and_join(self, root):
        facts = dict(self.facts)
        if self.cleanup_started is None:
            self.cleanup_started = time.monotonic()
        (root / 'cancel.request').write_text('cancel owned console\n', encoding='ascii')
        deadline = self.cleanup_started + 10
        while self.active() and time.monotonic() < deadline:
            time.sleep(.05)
        facts['forced_job_termination'] = bool(self.active())
        if facts['forced_job_termination']:
            self.job_api.TerminateJobObject(self.job, 125)
        deadline = self.cleanup_started + 20
        while self.active() and time.monotonic() < deadline:
            time.sleep(.05)
        facts['active_processes_after_join'] = self.active()
        facts['leader_exit_code'] = self.process_api.GetExitCodeProcess(self.process)
        return facts

    def close_handles(self):
        errors = []
        for name in ('thread', 'process', 'job'):
            handle = getattr(self, name, None)
            if handle is not None:
                try:
                    handle.Close()
                    setattr(self, name, None)
                except BaseException as exc:
                    errors.append({'phase': name + '_handle_close', 'error_class': error_code(exc)})
        return errors


def cli(args, env, cwd, key=None):
    # Windows venv python.exe can redirect to another PID. Use the real base
    # Python, with only the already selected installed Q paths added explicitly.
    prefix = Path(sys.prefix).resolve()
    base = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
    paths = [p for p in sys.path if p and Path(p).resolve().is_relative_to(prefix)]
    require(paths, 'INSTALLED_IMPORT_PATHS_REQUIRED')
    launcher = cwd.parent / 'installed-cli.py'
    source = ('import sys,site\nfrom pathlib import Path\n'
              f'site.addsitedir({str(prefix / "Lib/site-packages")!r})\n'
              f'sys.path[:0] = {paths!r}\n'
              'import okto_nexus,nexus_connector_core\n'
              f'assert all(Path(m.__file__).resolve().is_relative_to(Path({str(prefix)!r})) '
              'for m in (okto_nexus,nexus_connector_core))\n'
              'from okto_nexus.adapters.inbound.cli.main import main\n'
              'raise SystemExit(main())\n')
    launcher.write_text(source, encoding='utf-8')
    command = [str(base), '-I', str(launcher), *args]
    # This retained handle now identifies the actual CLI interpreter, not a
    # venv redirector. Preparation has no native client spawn; that is in the Job.
    with subprocess.Popen(command, env=env, cwd=cwd, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          creationflags=subprocess.CREATE_NO_WINDOW) as child:
        try:
            stdout, stderr = child.communicate((key + '\n').encode() if key else b'', timeout=25)
        except BaseException:
            child.kill()
            child.wait(timeout=10)
            raise
    require(not key or key.encode() not in stdout + stderr, 'SECRET_IN_CLI_OUTPUT')
    require(child.returncode == 0, 'CLI_REFUSED')
    return json.loads(stdout)


def canonical_counts(server):
    tables = ('agents', 'sessions', 'messages', 'handoffs', 'execution_bindings',
              'execution_sessions', 'execution_operations')
    with server.deps.connection_factory.unit_of_work(write=False) as uow:
        return {name: uow.connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in tables}


def exact_credential(target):
    import win32cred
    try:
        row = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
    except Exception as exc:
        if getattr(exc, 'winerror', None) == 1168:
            return None
        raise
    value = row['CredentialBlob']
    return value.decode('utf-16-le') if isinstance(value, bytes) else value


def win32_preflight():
    import win32api
    import win32con
    import win32event
    import win32job
    import win32process
    required = {win32api: ('TerminateProcess',),
                win32job: ('CreateJobObject', 'AssignProcessToJobObject', 'IsProcessInJob',
                           'QueryInformationJobObject', 'SetInformationJobObject', 'TerminateJobObject'),
                win32process: ('CreateProcess', 'ResumeThread', 'GetExitCodeProcess', 'STARTUPINFO'),
                win32event: ('WaitForSingleObject',)}
    facts = {m.__name__: {n: callable(getattr(m, n, None)) for n in names} for m, names in required.items()}
    require(all(all(row.values()) for row in facts.values()), 'WIN32_API_UNAVAILABLE')
    require(all(hasattr(win32con, n) for n in ('CREATE_NEW_CONSOLE', 'CREATE_SUSPENDED',
                                              'STARTF_USESHOWWINDOW', 'SW_HIDE')), 'WIN32_CONSTANT_UNAVAILABLE')
    return facts


def run_probe(args):
    require(os.name == 'nt' and sys.flags.isolated, 'WINDOWS_ISOLATED_PYTHON_REQUIRED')
    root = args.output.resolve()
    require(not root.exists(), 'OUTPUT_MUST_BE_NEW')
    root.mkdir(parents=True)
    env = environment(root)
    report = {'status': 'PREPARING', 'native_args': [str(args.native.resolve()), '--no-daemon'],
              'provider_credentials_supplied': False, 'native_inputs_sent': [],
              'scope': 'Windows local synthetic exact ParticipantLaunch startup only'}
    server = console = None
    key = target = None
    vault_apply_started = False
    errors = []
    try:
        report['win32_preflight'] = win32_preflight()  # Before Server/identity/vault effects.
        require(digest(args.native) == NATIVE_SHA, 'NATIVE_BINARY_CHANGED')
        require(digest(args.restart_helper) == HELPER_SHA, 'HELPER_CHANGED')
        import okto_nexus
        import nexus_connector_core
        import site
        prefix = Path(sys.prefix).resolve()
        modules = (okto_nexus, nexus_connector_core)
        require(all(Path(m.__file__).resolve().is_relative_to(prefix) for m in modules), 'INSTALLED_PRODUCTS_REQUIRED')
        report['installed_modules'] = {m.__name__: str(Path(m.__file__).resolve()) for m in modules}
        package = Path(okto_nexus.__file__).resolve().parent
        product_inputs = [package / name for name in (
            'application/participant_launch.py', 'application/terminal_participant.py',
            'adapters/inbound/cli/participant.py', 'adapters/inbound/cli/participant_launch.py',
            'adapters/outbound/participant_process.py', 'adapters/outbound/participant_client.py',
            'adapters/outbound/provider_vault.py')]
        input_hashes = {str(p): digest(p) for p in product_inputs + [args.native, args.restart_helper, Path(__file__)]}
        report['input_hashes_before'] = input_hashes
        report['native_sha256'] = digest(args.native)
        spec = importlib.util.spec_from_file_location('dx04_restart_fixture', args.restart_helper)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        server_root = root / 'server'
        server_root.mkdir()
        server = helper.RestartServer(server_root)
        dependencies = [p for p in site.getsitepackages() if Path(p).resolve().is_relative_to(prefix)]
        products = [str(Path(m.__file__).resolve().parent.parent) for m in modules]
        observed = root / 'mcp-observations.jsonl'
        launcher = helper.LAUNCHER.replace('# dependency_paths', f'sys.path.extend({dependencies!r})').replace(
            '# product_paths', f'sys.path[:0] = {products!r}\nsys.path.insert(0, {str(Path(__file__).parent)!r})\n'
            f'from dx04_probe import install_observer\ninstall_observer({str(observed)!r})')
        server.launcher.write_text(launcher, encoding='utf-8')
        server.env = dict(env)
        from okto_nexus.application.auth import AgentKeyAuthService
        from okto_nexus.adapters.outbound.participant_client import ParticipantVault
        auth = AgentKeyAuthService(server.deps.repos.agents, server.deps.clock)
        suffix = uuid.uuid4().hex
        agent, workspace, profile = 'dx04-' + suffix, 'dx04-workspace', 'dx04-' + suffix
        with server.deps.connection_factory.unit_of_work() as uow:
            server.deps.repos.workspaces.upsert(uow, workspace_id=workspace, display_name='DX04 synthetic workspace')
            server.deps.repos.agents.upsert(uow, agent_id=agent, role='Synthetic native MCP participant')
            key = auth.issue_key(uow, agent_id=agent)
        server.start()
        before = canonical_counts(server)
        # Same real auth middleware must reject missing credentials before native startup.
        negative = server.client.post('/mcp/', json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'dx04-negative-control', 'version': '1'}}},
            headers={'Accept': 'application/json, text/event-stream'})
        require(negative.status_code == 401, 'REAL_MCP_AUTH_NEGATIVE_CONTROL')
        report['missing_bearer_status'] = negative.status_code
        project, home = root / 'project', root / 'participant-home'
        project.mkdir()
        # Empty Git boundary prevents discovery of ancestor project instructions.
        (project / '.git/objects').mkdir(parents=True)
        (project / '.git/refs/heads').mkdir(parents=True)
        (project / '.git/HEAD').write_text('ref: refs/heads/probe\n', encoding='ascii')
        (project / '.git/config').write_text('[core]\nrepositoryformatversion = 0\nbare = false\n', encoding='ascii')
        config_path = Path(env['CODEX_HOME']) / 'config.toml'
        config_path.write_text(CONFIG, encoding='utf-8')
        common = ['--home', str(home), '--profile', profile, '--project', str(project)]
        cli(['init', '--mode', 'participant', *common, '--server', server.origin, '--agent', agent,
             '--workspace-id', workspace, '--client', 'codex', '--client-version', '0.167.0',
             '--config-file', str(config_path), '--entry-name', 'dx04_probe', '--key-stdin', '--plan', '--json'], env, project, key)
        checkpoint = home / 'terminal/participants' / (profile + '.json')
        setup = read_json(checkpoint)
        target = ParticipantVault(home, profile, setup['review']).service + '/agent-key'
        require(exact_credential(target) is None, 'VAULT_TARGET_ALREADY_EXISTS')
        report['vault_target_absent_before'] = True
        vault_apply_started = True  # Cleanup only after verified absence and our write intent.
        cli(['init', '--mode', 'participant', *common, '--key-stdin', '--approve', setup['review_revision'], '--json'], env, project, key)
        require(hmac.compare_digest(exact_credential(target) or '', key), 'VAULT_WRITE_UNCONFIRMED')
        cli(['participant', 'launch', *common, '--executable', str(args.native.resolve()), '--plan', '--json'], env, project)
        launch_path = home / 'terminal/participants' / (profile + '.launch.json')
        launch = read_json(launch_path)
        process = launch['review']['process']
        require(process['arguments'] == ['--no-daemon'], 'EXACT_NATIVE_ARGV_REQUIRED')
        require(Path(process['config_file']) == config_path and Path(process['cwd']) == project, 'CONTEXT_MISMATCH')
        require(key not in checkpoint.read_text() + launch_path.read_text() + config_path.read_text(), 'SECRET_IN_PERSISTENCE')
        require(not any(name.startswith('NEXUS_PARTICIPANT_TOKEN_') for name in env), 'PARENT_MUST_NOT_PRESEED_REFERENCE')
        report['context'] = {'cwd': str(project), 'config_file': str(config_path),
                             'homes': {n: env[n] for n in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'CODEX_HOME')},
                             'credential_stores': {'provider': 'file', 'mcp_oauth': 'file'},
                             'check_for_update_on_startup': False, 'parent_reference_absent': True}
        worker_file = root / 'worker-config.json'
        write_json(worker_file, {'root': str(root), 'argv': ['participant', 'launch', *common,
            '--executable', str(args.native.resolve()), '--approve', launch['review_revision']]})
        console = OwnedConsole(worker_file, env, project)
        report['status'] = 'OBSERVING'
        write_json(root / 'probe-status.json', report)
        deadline = console.started + 60
        while console.active() and time.monotonic() < deadline:
            rows = observer_rows(observed)
            screen = read_json(root / 'screen-labels.json', {})
            if mcp_confirmed(rows) or screen.get('gate_seen') or (root / 'watcher-error.json').exists():
                break
            time.sleep(.1)
        report['observation_seconds'] = round(time.monotonic() - console.started, 3)
        report['console_cleanup'] = console.contain_and_join(root)
        require(report['console_cleanup']['active_processes_after_join'] == 0, 'OWNED_JOB_NOT_EMPTY')
        errors.extend(console.close_handles())
        console = None
        report['native_mcp_confirmed'] = mcp_confirmed(observer_rows(observed))
        report['screen_labels'] = read_json(root / 'screen-labels.json', {})
        report['tty_owner'] = read_json(root / 'tty-owner.json')
        report['tty_child'] = read_json(root / 'tty-child.json')
        report['worker_result'] = read_json(root / 'worker-result.json')
        require(report['tty_owner'] is not None and report['tty_child'] is not None and
                all(report['tty_owner']['streams'].values()) and all(report['tty_child']['streams'].values()),
                'NATIVE_TTY_PRECONDITION_UNCONFIRMED')
        require(not (root / 'watcher-error.json').exists(), 'CONSOLE_WATCHER_FAILED')
        stage = read_json(root / 'worker-stage.json', {})
        require(stage.get('participant_cli_invoked') is True, 'PARTICIPANT_CLI_NOT_INVOKED')
        report['launch_checkpoint_state'] = read_json(launch_path)['state']
        require(report['launch_checkpoint_state'] in ('started', 'exited'), 'NATIVE_SPAWN_UNCONFIRMED')
        require(not any(r.get('method') == 'tools/call' for r in observer_rows(observed)), 'UNEXPECTED_MCP_TOOL_CALL')
        report['canonical_counts_unchanged'] = canonical_counts(server) == before
        require(report['canonical_counts_unchanged'], 'UNEXPECTED_CANONICAL_EFFECT')
        require(digest(args.native) == NATIVE_SHA, 'NATIVE_BINARY_CHANGED_DURING_PROBE')
        report['input_hashes_unchanged'] = all(digest(p) == value for p, value in input_hashes.items())
        require(report['input_hashes_unchanged'], 'INPUT_CHANGED_DURING_PROBE')
        report['status'] = ('MCP_CHAIN_OBSERVED' if report['native_mcp_confirmed'] else
                            'NATIVE_GATE_OBSERVED' if report['screen_labels'].get('gate_seen') else 'MCP_NOT_OBSERVED')
    except BaseException as exc:
        errors.append({'phase': 'probe', 'error_class': error_code(exc)})
        report['status'] = 'UNCONFIRMED'
    finally:
        if console is not None:
            try:
                report['console_cleanup'] = console.contain_and_join(root)
            except BaseException as exc:
                errors.append({'phase': 'console_cleanup', 'error_class': error_code(exc)})
            finally:
                errors.extend(console.close_handles())
        if server is not None:
            try:
                if server.children:
                    server.stop()
                    with socket.socket() as check:
                        check.settimeout(.5)
                        report['server_listener_closed'] = check.connect_ex(('127.0.0.1', server.port)) != 0
                    require(report['server_listener_closed'], 'SERVER_LISTENER_OPEN')
            except BaseException as exc:
                errors.append({'phase': 'canonical_server_stop', 'error_class': error_code(exc)})
            finally:
                try:
                    server.cleanup()
                except BaseException as exc:
                    errors.append({'phase': 'server_cleanup', 'error_class': error_code(exc)})
        if vault_apply_started and report.get('vault_target_absent_before') is True and target is not None and key is not None:
            try:
                current = exact_credential(target)
                if current is not None:
                    require(hmac.compare_digest(current, key), 'VAULT_CLEANUP_VALUE_CHANGED')
                    import win32cred
                    win32cred.CredDelete(target, win32cred.CRED_TYPE_GENERIC, 0)
                report['own_vault_absent_after'] = exact_credential(target) is None
                require(report['own_vault_absent_after'], 'VAULT_CLEANUP_UNCONFIRMED')
            except BaseException as exc:
                errors.append({'phase': 'own_vault_cleanup', 'error_class': error_code(exc)})
        watcher_error = read_json(root / 'watcher-error.json')
        if watcher_error is not None:
            report['console_watcher_error'] = watcher_error
            errors.append({'phase': 'console_watcher', 'error_class': watcher_error.get('error_class', 'UNKNOWN')})
        report['errors'] = errors
        report['cleanup_confirmed'] = not errors
        report['scope_limit'] = 'Startup/credential transport only; no provider, work, tool call, account login or trust approval.'
        write_json(root / 'result.json', report)
        print(json.dumps({'result': str(root / 'result.json'), 'status': report['status'], 'error_count': len(errors)}))
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--console-worker', type=Path)
    parser.add_argument('--execute-native', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--native', type=Path)
    parser.add_argument('--restart-helper', type=Path)
    args = parser.parse_args()
    if args.console_worker:
        return console_worker(args.console_worker)
    if not args.execute_native or any(x is None for x in (args.output, args.native, args.restart_helper)):
        parser.error('Explicit --execute-native and --output/--native/--restart-helper are required; preparation never starts a native client.')
    return run_probe(args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Even a preflight failure never emits a traceback with fixture material.
        print(json.dumps({'probe_error_class': error_code(error)}))
        raise SystemExit(3) from None
