"""PREPARED Root-gated S3 supervisor; no product imports in this host process."""
import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

import psutil

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    assert not path.exists(), 'Preserve each antecedent'
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def guards(manifest):
    for path, expected in manifest['helper_sha256'].items():
        assert sha(Path(path)) == expected, path
    for phase in manifest['runtime_payloads'].values():
        assert sha(Path(phase['wheel'])) == phase['wheel_sha256']
        prefix = Path(phase['prefix']) / 'Lib/site-packages'
        assert len(phase['files']) == phase['expected_count']
        for name, expected in phase['files'].items():
            assert sha(prefix / name) == expected, name
    for path, expected in manifest['source_pins'].items():
        assert sha(Path(path)) == expected, path
    tool = manifest['tooling']
    for name, expected in tool['cli_payload_pins'].items():
        assert sha(Path(tool['node_modules']) / name) == expected
    assert len(tool['cli_payload_pins']) == 192
    assert sha(Path(tool['node'])) == tool['node_sha256']
    assert sha(Path(tool['chrome'])) == tool['chrome_sha256']
    return {'source_count': len(manifest['source_pins']),
        'runtime_payloads': {k: len(v['files']) for k, v in manifest['runtime_payloads'].items()},
        'cli_payload_count': 192, 'drift': []}


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--gate', choices=['ROOT_APPROVED_COMPAT_BATCH_S3'], required=True)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    manifest_path = HERE / 'PREPARED-S3-R9.json'
    assert sha(manifest_path) == args.manifest_sha256
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['status'] == 'PREPARED_BOUND_NOT_EXECUTED'
    assert manifest['current_source'] == 'f07163ab7fd618b2ff4247ba6cdb2547b5d4e038'
    script = (HERE / 'browser-s3-reviewed.js').read_text(encoding='utf-8')
    assert script.count('__CONFIG__') == 1, 'Count effective placeholders before allocation'
    before = guards(manifest)  # No allocation or app/browser process before gates.
    root = Path(tempfile.mkdtemp(prefix='nexus-hst-compat-s3-')).resolve()
    for name in ('control', 'cwd', 'peer-root', 'peer-home', 'project', 'provider-home', 'candidate'):
        (root / name).mkdir()
    browser_root = root / 'nexus-hst-browser-s3'
    browser_root.mkdir()
    (browser_root / 'cwd').mkdir()
    (root / 'candidate/codex.exe').write_bytes(manifest['synthetic_candidate_text'].encode())
    assert sha(root / 'candidate/codex.exe') == manifest['synthetic_candidate_sha256']
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    home = root / 'home'
    python = manifest['phases']['s3-current']['python']
    deadline = time.monotonic() + 180
    manager = load('compat_command_lifecycle', Path(manifest['command_helper']))
    lifecycle = load('compat_app_environment', Path(manifest['environment_helper']))
    browser_driver = load('compat_browser_environment', Path(manifest['browser_environment_helper']))
    core = manager.Commands(root, lifecycle.environment(root), deadline)
    browser = manager.Commands(browser_root, browser_driver.environment(browser_root), deadline)
    tooling = manifest['tooling']
    rtk = shutil.which('rtk')
    assert rtk
    session = 'hst-compat-s3-' + secrets.token_hex(8)
    config = browser_root / 'playwright-cli.json'
    shutil.copyfile(Path(manifest['browser_config']), config)
    rendered_pins = {str(config): sha(config)}
    opened = False
    server = cycle = None
    failures = []
    browser_result = None
    logs = []
    opener = build_opener(ProxyHandler({}), HTTPCookieProcessor())

    def request(method, path, body=None, *, authenticated=False):
        headers = {'X-Nexus-UI': '1'}
        if authenticated:
            headers['X-Nexus-Operator-Session-Required'] = '1'
        data = json.dumps(body).encode() if body is not None else None
        if data is not None:
            headers['Content-Type'] = 'application/json'
        with opener.open(Request(origin + path, data=data, headers=headers, method=method), timeout=10) as response:
            value = json.load(response)
        return value.get('data', value)

    def start(name, command):
        log = (root / (name + '.private.log')).open('wb')
        logs.append(log)
        child = subprocess.Popen(command, cwd=root / 'cwd', env=core.env, stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        child.stdin.close()
        core.sample(child.pid)
        return child

    def cli(name, *argv, cleanup=False):
        return browser.run(name, [rtk, 'proxy', tooling['node'], tooling['entry'], '--session=' + session, *argv], cleanup=cleanup)

    def until(predicate, message, seconds=30):
        end = min(deadline, time.monotonic() + seconds)
        while time.monotonic() < end:
            core.sample(server.pid if server else None)
            browser.sample()
            value = predicate()
            if value:
                return value
            assert server is None or server.poll() is None, 'Foreground owner exited'
            time.sleep(.1)
        raise TimeoutError(message)

    common = ['--gate', 'ROOT_APPROVED_COMPAT_BATCH', '--manifest', str(manifest_path),
        '--manifest-sha256', args.manifest_sha256, '--phase', 's3-current',
        '--root', str(root), '--home', str(home), '--port', str(port)]
    try:
        server = start('server', [python, '-I', '-B', '-X', 'utf8', str(HERE / 'foreground_owner_v2.py'), *common])

        def ready():
            try:
                value = request('GET', '/api/v1/service')
                return value if value.get('state') == 'ready' else None
            except OSError:
                return None

        owner = until(ready, 'Foreground ready deadline', 40)
        core.sample(server.pid)
        assert owner['pid'] in core.known
        actual = core.known[owner['pid']]
        assert manager.Commands.alive(actual)
        save(root / 'control/owner-before.json', {'service': owner, 'birth': actual['birth'], 'exe': actual['exe']})
        # Canonical own human account, login and Chrome warmup BEFORE any CLI
        # setup Test/grant/admission/input. Never use an agent bearer as operator.
        password = secrets.token_urlsafe(32)
        request('POST', '/api/v1/operator-auth/account', {'username': 'compat-human', 'password': password})
        request('POST', '/api/v1/operator-auth/login', {'username': 'compat-human', 'password': password})
        jar = next(handler.cookiejar for handler in opener.handlers if isinstance(handler, HTTPCookieProcessor))
        cookie = next(item.value for item in jar if item.name == 'nexus_operator_session')
        private_cookie = root / 'control/operator-cookie.private.json'
        save(private_cookie, {'cookie': cookie})
        os.chmod(private_cookie, 0o600)
        storage = root / 'control/browser-storage.private.json'
        save(storage, {'cookies': [{'name': 'nexus_operator_session', 'value': cookie, 'domain': '127.0.0.1',
            'path': '/api/v1', 'httpOnly': True, 'secure': False, 'sameSite': 'Strict'}], 'origins': []})
        os.chmod(storage, 0o600)
        cli('browser-open', 'open', 'about:blank', '--browser=chrome', '--profile=' + str(browser_root / 'browser-profile'), '--config=' + str(config))
        opened = True
        browser.sample()
        save(root / 'control/browser-own-profile-before-home.json', browser_driver.capture(browser_root, browser.known, tooling))
        cli('browser-load-state', 'state-load', str(storage))
        warmup = browser_root / 'warmup.js'
        warmup.write_text('async page=>{await page.context().setExtraHTTPHeaders({"X-Nexus-UI":"1","X-Nexus-Operator-Session-Required":"1"});'
            'await page.addInitScript(()=>localStorage.setItem("okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0",new Date().toISOString()));'
            'await page.goto(' + json.dumps(origin) + ');await page.getByTestId("navigation-sidebar").waitFor();'
            'return {status:"PASS_WARMUP_BEFORE_ADMISSIONS",homePreference:await page.evaluate(()=>localStorage.getItem("okto-nexus-home-operational"))};}', encoding='utf-8')
        rendered_pins[str(warmup)] = sha(warmup)
        warm = manager.cli_result(cli('browser-warmup', 'run-code', '--filename=' + str(warmup)))
        assert warm['status'] == 'PASS_WARMUP_BEFORE_ADMISSIONS' and warm['homePreference'] != 'enabled'
        save(root / 'control/warmup-before-admissions.json', warm)
        cycle = start('cycle', [python, '-I', '-B', '-X', 'utf8', str(HERE / 'cli_cycle_v2.py'),
            *common, '--operator-cookie-file', str(private_cookie)])
        active_path = root / 'control/cli-active-s3-current.json'
        active = until(lambda: json.loads(active_path.read_text()) if active_path.exists() else None, 'CLI active marker deadline', 40)
        assert cycle.poll() is None
        assert {k: owner[k] for k in ('pid', 'instance_id', 'generation')} == active['owner']
        board = request('GET', '/api/v1/home/harness-board?presentation_version=2&workspace_id=' + active['binding']['workspace_id'], authenticated=True)
        refs = []
        for column in board['columns'].values():
            for item in column['items']:
                refs.extend([item] if item['kind'] == 'request' else item.get('requests_preview', []))
        attention_ids = {item['request']['attention_id'] for item in refs if item['request'].get('operation_id') == active['operation_id']}
        assert len(attention_ids) == 1
        body = browser_root / 's3-reviewed.js'
        public = {'origin': origin, 'workspace_id': active['binding']['workspace_id'],
            'binding_id': active['binding']['binding_id'], 'attention_id': next(iter(attention_ids))}
        body.write_text(script.replace('__CONFIG__', json.dumps(public)), encoding='utf-8')
        rendered_pins[str(body)] = sha(body)
        browser_result = manager.cli_result(cli('browser-settings-rollback', 'run-code', '--filename=' + str(body)))
        save(root / 'control/browser-result.json', browser_result)
        assert browser_result['status'] == 'PASS_BROWSER_S3_SUBSET'
        assert all(check['pass'] for check in browser_result['checks'])
        cli('browser-after-rollback-snapshot', 'snapshot')
        cli('browser-after-rollback-screenshot', 'screenshot', '--filename=' + str(browser_root / 's3-rollback.png'))
        # This marker says only the reviewed UI assertions completed; the CLI
        # independently enforces exact file/config/grant/owner invariants.
        (root / 'control/browser-s3.done').touch()
        until(lambda: cycle.poll() is not None, 'CLI cycle did not settle', 40)
        assert cycle.returncode == 0
        settled = request('GET', '/api/v1/service', authenticated=True)
        assert {k: settled[k] for k in ('pid', 'instance_id', 'generation')} == active['owner']
        assert manager.Commands.alive(actual)
        save(root / 'control/owner-after.json', {'service': settled, 'birth': actual['birth'], 'exe': actual['exe']})
    except BaseException as error:  # noqa: BLE001 -- retain interrupt/failure before mandatory own cleanup.
        failures.append({'type': type(error).__name__, 'message': str(error)})
    finally:
        if opened:
            try:
                cli('browser-final-close', 'close', cleanup=True)
            except BaseException as error:  # noqa: BLE001 -- finish the independent canonical stop below.
                failures.append({'type': type(error).__name__, 'message': 'Browser close: ' + str(error)})
        if server is not None and server.poll() is None:
            try:
                text = core.run('service-final-stop', [python, '-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main',
                    'service', 'stop', '--home', str(home), '--host', '127.0.0.1', '--port', str(port), '--timeout', '30', '--json'], timeout=40, cleanup=True)
                stopped = json.loads(text)
                assert stopped['state'] == 'stopped' and stopped.get('shutdown_outcome') == 'drained'
                save(root / 'control/canonical-stop.json', stopped)
            except BaseException as error:  # noqa: BLE001 -- physical containment is recorded separately.
                failures.append({'type': type(error).__name__, 'message': 'Canonical stop: ' + str(error)})
        end = time.monotonic() + 5
        while time.monotonic() < end and (core.remaining() or browser.remaining()):
            time.sleep(.1)
        contained = []
        for group in (core, browser):
            if group.remaining():
                result = group.contain()
                contained.extend(result['forced_births'])
        if contained:
            failures.append({'type': 'OwnContainmentRequired', 'message': 'Physical containment is not canonical shutdown success'})
        after = None
        try:
            after = guards(manifest)
            assert before == after
            assert sha(manifest_path) == args.manifest_sha256
            assert sha(root / 'candidate/codex.exe') == manifest['synthetic_candidate_sha256']
            assert all(sha(Path(path)) == expected for path, expected in rendered_pins.items())
        except BaseException as error:  # noqa: BLE001 -- preserve failed immutable guard, never return PASS.
            failures.append({'type': type(error).__name__, 'message': 'End guard: ' + str(error)})
        remaining = {item['pid']: item for group in (core, browser) for item in group.remaining()}
        listeners = [row.pid for row in psutil.net_connections(kind='tcp') if row.status == 'LISTEN' and row.laddr.port == port]
        for log in logs:
            log.close()
        save(root / 'control/final.json', {'failures': failures, 'root': str(root), 'before': before, 'after': after,
            'browser_result': browser_result, 'commands': core.commands + browser.commands,
            'known_births': list({item['pid']: item for group in (core, browser) for item in group.known.values()}.values()),
            'remaining': list(remaining.values()), 'listeners': listeners, 'containment': contained,
            'provider_invocations': 0, 'phase_deadline_seconds': 180, 'npx_or_npm_used': False,
            'rendered_script_and_config_pins': rendered_pins,
            'limits': 'Selected config/root/grant/checkpoint invariants, not wholeDB readonly; inert provider peer; no Windows service integration or human acceptance.'})
        print(json.dumps({'root': str(root), 'failures': failures, 'remaining': len(remaining), 'listeners': listeners}), flush=True)
    return 0 if not failures and not remaining and not listeners else 1


if __name__ == '__main__':
    raise SystemExit(main())
