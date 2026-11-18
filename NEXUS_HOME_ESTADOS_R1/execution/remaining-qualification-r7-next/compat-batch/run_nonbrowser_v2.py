"""PREPARED separate Root gates for S4 old-state reading or candidate CLI-only K05.

No browser helper is imported or started. No app import occurs in this host.
"""
import argparse
import hashlib
import importlib.util
import json
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

import psutil

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--journey', choices=['S4', 'K05'], required=True)
    parser.add_argument('--gate', choices=['ROOT_APPROVED_COMPAT_S4', 'ROOT_APPROVED_COMPAT_K05_CANDIDATE'], required=True)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    expected_gate = 'ROOT_APPROVED_COMPAT_S4' if args.journey == 'S4' else 'ROOT_APPROVED_COMPAT_K05_CANDIDATE'
    assert args.gate == expected_gate
    manifest_path = HERE / ('PREPARED-S4-R9.json' if args.journey == 'S4' else 'PREPARED-K05-R9-v2.json')
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest(manifest_path) == args.manifest_sha256
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['journey'] == args.journey and manifest['status'] == 'PREPARED_BOUND_NOT_EXECUTED'
    assert digest(HERE / 'run_s3_v2.py') == manifest['helper_sha256'][str(HERE / 'run_s3_v2.py')]
    # Load only the hash-verified host guard functions; never call its S3 main.
    spec = importlib.util.spec_from_file_location('compat_s3_host_guard', HERE / 'run_s3_v2.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    before = helper.guards(manifest)  # Read-only all payload/source/helper pins before allocation.
    root = Path(tempfile.mkdtemp(prefix='nexus-hst-compat-' + args.journey.lower() + '-')).resolve()
    for name in ('control', 'cwd', 'peer-root', 'peer-home', 'project', 'provider-home', 'candidate'):
        (root / name).mkdir()
    (root / 'candidate/codex.exe').write_bytes(manifest['synthetic_candidate_text'].encode())
    assert helper.sha(root / 'candidate/codex.exe') == manifest['synthetic_candidate_sha256']
    manager = helper.load('compat_nonbrowser_commands', Path(manifest['command_helper']))
    lifecycle = helper.load('compat_nonbrowser_environment', Path(manifest['environment_helper']))
    history = helper.load('compat_nonbrowser_history', Path(manifest['history_helper']))
    password = secrets.token_urlsafe(32)
    username = 'compat-human'
    phases, failures, containment = [], [], []
    active = None
    copied = None

    def run_phase(phase, home, *, create_account, cycle):
        nonlocal active
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        deadline = time.monotonic() + 180
        commands = manager.Commands(root, lifecycle.environment(root), deadline)
        python = manifest['phases'][phase]['python']
        origin = f'http://127.0.0.1:{port}'
        common = ['--gate', 'ROOT_APPROVED_COMPAT_BATCH', '--manifest', str(manifest_path),
            '--manifest-sha256', args.manifest_sha256, '--phase', phase, '--root', str(root),
            '--home', str(home), '--port', str(port)]
        log = (root / (phase + '-server.private.log')).open('wb')
        process = subprocess.Popen([python, '-I', '-B', '-X', 'utf8', str(HERE / 'foreground_owner_v4.py'), *common],
            cwd=root / 'cwd', env=commands.env, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        process.stdin.close()
        commands.sample(process.pid)
        active = {'phase': phase, 'home': home, 'port': port, 'python': python, 'process': process,
            'commands': commands, 'log': log, 'stopped': False}
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor())

        def request(method, path, body=None, *, authenticated=False):
            headers = {'X-Nexus-UI': '1'}
            if authenticated:
                headers['X-Nexus-Operator-Session-Required'] = '1'
            data = json.dumps(body).encode() if body is not None else None
            if data is not None:
                headers['Content-Type'] = 'application/json'
            with opener.open(Request(origin + path, method=method, data=data, headers=headers), timeout=10) as response:
                value = json.load(response)
            return value.get('data', value)

        ready = None
        end = min(deadline, time.monotonic() + 40)
        while time.monotonic() < end:
            commands.sample(process.pid)
            assert process.poll() is None, 'Foreground owner exited; retain old metadata, no repair'
            try:
                value = request('GET', '/api/v1/service')
                if value.get('state') == 'ready':
                    ready = value
                    break
            except OSError:
                pass
            time.sleep(.1)
        assert ready is not None, 'Foreground ready deadline'
        commands.sample(process.pid)
        assert ready['pid'] in commands.known and manager.Commands.alive(commands.known[ready['pid']])
        owner = {key: ready[key] for key in ('pid', 'instance_id', 'generation')}
        birth = commands.known[ready['pid']]['birth']
        if create_account:
            request('POST', '/api/v1/operator-auth/account', {'username': username, 'password': password})
        # On a copied home authenticate the SAME own account; never replace it.
        request('POST', '/api/v1/operator-auth/login', {'username': username, 'password': password})
        jar = next(h.cookiejar for h in opener.handlers if isinstance(h, HTTPCookieProcessor))
        cookie = next(c.value for c in jar if c.name == 'nexus_operator_session')
        private_cookie = root / 'control' / (phase + '-cookie.private.json')
        helper.save(private_cookie, {'cookie': cookie})
        info = request('GET', '/api/v1/info', authenticated=True)
        helper.save(root / 'control' / ('info-' + phase + '.json'), info)
        if phase == 's4-old':
            assert 2 not in info.get('home_presentation_versions', [])
        else:
            assert 2 in info.get('home_presentation_versions', [])
        if cycle:
            commands.run(phase + '-cli-cycle', [python, '-I', '-B', '-X', 'utf8', str(HERE / 'cli_cycle_v3.py'),
                *common, '--operator-cookie-file', str(private_cookie)], timeout=120)
            cycle_data = json.loads((root / 'control' / ('cli-cycle-' + phase + '.json')).read_text(encoding='utf-8'))
            assert cycle_data['no_web_step_required'] is True
            workspace = cycle_data['binding']['workspace_id']
        else:
            old = json.loads((root / 'control/cli-cycle-s4-old.json').read_text(encoding='utf-8'))
            workspace = old['binding']['workspace_id']
        if args.journey == 'S4':
            commands.run(phase + '-projection', [python, '-I', '-B', '-X', 'utf8', str(HERE / 'projection_reader_v3.py'),
                '--gate', 'ROOT_APPROVED_COMPAT_BATCH', '--manifest', str(manifest_path),
                '--manifest-sha256', args.manifest_sha256, '--phase', phase, '--root', str(root),
                '--home', str(home), '--origin', origin, '--workspace-id', workspace,
                '--operator-cookie-file', str(private_cookie)], timeout=30)
        observed = request('GET', '/api/v1/service', authenticated=True)
        assert {key: observed[key] for key in owner} == owner
        assert manager.Commands.alive(commands.known[owner['pid']])
        record = {'phase': phase, 'port': port, 'owner_before': owner, 'owner_after': {key: observed[key] for key in owner},
            'birth': birth, 'python': python, 'workspace_id': workspace, 'dashboard_opened': False,
            'protected_before_stop': history.snapshot(home)}
        stop_phase(active)
        record.update(stop=active['stop'], exit_code=process.returncode,
            known_births=list(commands.known.values()), commands=commands.commands,
            protected_after_stop=history.snapshot(home))
        trace = [json.loads(line) for line in (root / 'control' / ('http-' + phase + '.jsonl')).read_text(encoding='utf-8').splitlines()]
        dashboard_requests = [row for row in trace if row['path'] == '/' or row['path'].startswith('/assets/')]
        browser_births = [row for row in commands.known.values() if Path(row['exe']).name.lower() in ('chrome.exe', 'node.exe')]
        assert not dashboard_requests and not browser_births
        assert not (root / 'control/browser-s3.done').exists()
        record.update(http_request_count=len(trace), dashboard_requests=dashboard_requests,
            browser_births=browser_births, browser_marker_written=False)
        # The authoritative old compatibility baseline is AFTER drained stop.
        # A late canonical receipt during shutdown must not be blamed on a GET.
        assert not commands.remaining()
        phases.append(record)
        helper.save(root / 'control' / ('phase-' + phase + '.json'), record)
        active = None
        return record

    def stop_phase(value):
        if value['stopped']:
            return
        commands = value['commands']
        text = commands.run(value['phase'] + '-canonical-stop', [value['python'], '-I', '-B', '-X', 'utf8',
            '-m', 'okto_nexus.adapters.inbound.cli.main', 'service', 'stop', '--home', str(value['home']),
            '--host', '127.0.0.1', '--port', str(value['port']), '--timeout', '30', '--json'], timeout=40, cleanup=True)
        stop = json.loads(text)
        assert stop['state'] == 'stopped' and stop.get('shutdown_outcome') == 'drained'
        end = time.monotonic() + 10
        while time.monotonic() < end and commands.remaining():
            time.sleep(.1)
        assert value['process'].poll() == 0 and not commands.remaining(), 'Canonical stop is not physical absence'
        value['stopped'], value['stop'] = True, stop
        value['log'].close()

    try:
        if args.journey == 'K05':
            run_phase('current-cli', root / 'home', create_account=True, cycle=True)
        else:
            old_home, new_home = root / 'old-home', root / 'current-home'
            old = run_phase('s4-old', old_home, create_account=True, cycle=True)
            old_info = root / 'control/info-s4-old.json'
            stop_proof = root / 'control/old-stop-proof.json'
            helper.save(stop_proof, {'canonical_stop_state': old['stop']['state'],
                'shutdown_outcome': old['stop']['shutdown_outcome'], 'physical_same_birth_remaining': 0,
                'old_info_sha256': helper.sha(old_info), 'old_offered_v2': False})
            copy_commands = manager.Commands(root, lifecycle.environment(root), time.monotonic() + 180)
            copy_commands.run('single-copy', [manifest['phases']['s4-old']['python'], '-I', '-B', '-X', 'utf8',
                str(HERE / 'history_copy_v2.py'), '--gate', 'ROOT_APPROVED_COMPAT_BATCH',
                '--root', str(root), '--old-home', str(old_home), '--new-home', str(new_home),
                '--old-stop-proof', str(stop_proof)], timeout=30)
            copied = json.loads((root / 'control/history-copy.json').read_text(encoding='utf-8'))
            assert copied['copy_count'] == 1
            run_phase('s4-current', new_home, create_account=False, cycle=False)
            assert history.snapshot(new_home) == copied['old']
            assert all(helper.sha(new_home / name) == digest for name, digest in copied['profile_checkpoint_files_at_copy'].items())
    except BaseException as error:  # noqa: BLE001 -- retain failed phase before own cleanup, never auto-retry.
        failures.append({'type': type(error).__name__, 'message': str(error)})
    finally:
        if active is not None:
            try:
                if active['process'].poll() is None:
                    stop_phase(active)
            except BaseException as error:  # noqa: BLE001 -- record canonical failure separately from physical containment.
                failures.append({'type': type(error).__name__, 'message': 'Canonical stop: ' + str(error)})
            if active['commands'].remaining():
                containment = active['commands'].contain()['forced_births']
            if containment:
                failures.append({'type': 'OwnContainmentRequired', 'message': 'Not canonical stop success'})
            active['log'].close()
        after = None
        try:
            after = helper.guards(manifest)
            assert before == after and helper.sha(manifest_path) == args.manifest_sha256
        except BaseException as error:  # noqa: BLE001 -- preserve failed immutable guard, no PASS.
            failures.append({'type': type(error).__name__, 'message': 'End guard: ' + str(error)})
        known = [item for record in phases for item in record['known_births']]
        if active is not None:
            known.extend(active['commands'].known.values())
        remaining = [item for item in known if manager.Commands.alive(item)]
        ports = sorted({record['port'] for record in phases} | ({active['port']} if active is not None else set()))
        listeners = [row.pid for row in psutil.net_connections(kind='tcp') if row.status == 'LISTEN' and row.laddr.port in ports]
        helper.save(root / 'control/nonbrowser-final.json', {'journey': args.journey, 'failures': failures,
            'root': str(root), 'phases': phases, 'before': before, 'after': after, 'copy_count': copied['copy_count'] if copied else 0,
            'remaining': remaining, 'listeners': listeners, 'audited_ports': ports, 'forced_containment': containment,
            'browser_started': False, 'browser_markers_written': False, 'provider_invocations': 0,
            'phase_deadline_seconds': 180, 'K05_inferred_from_old_producer': False,
            'limits': 'Canonical installed CLI/HTTP/SQLite with inert version/Test/native peers; no provider, human acceptance, Windows daemon/session event or performance claim.'})
        print(json.dumps({'root': str(root), 'journey': args.journey, 'failures': failures,
            'remaining': len(remaining), 'listeners': listeners}), flush=True)
    return 0 if not failures and not remaining and not listeners else 1


if __name__ == '__main__':
    raise SystemExit(main())
