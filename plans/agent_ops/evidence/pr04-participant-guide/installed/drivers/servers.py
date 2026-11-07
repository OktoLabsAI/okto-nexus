"""Own two isolated installed servers and retain secret-free canonical hashes."""
import hashlib
import json
import os
from pathlib import Path
import re
import site
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parent
TABLES = ('agents', 'workspaces', 'sessions', 'agent_connection_policies', 'agent_connection_methods',
    'agent_connection_keys', 'execution_agent_revisions', 'execution_link_tickets', 'ephemeral_poll_tokens',
    'execution_local_tool_credentials', 'runtime_execution_grants', 'connection_authorization_receipts',
    'connection_setup_commits', 'remote_setup_runs', 'remote_setup_reviews', 'execution_proposals',
    'execution_bindings', 'execution_workspace_bindings', 'execution_realizations', 'execution_local_realizations',
    'execution_executors', 'agent_execution_policies', 'agent_endpoints', 'runtime_profiles',
    'agent_policy_bindings', 'agent_comm_binding', 'execution_operations', 'execution_sessions', 'execution_leases',
    'execution_receipts', 'approvals', 'messages', 'handoffs')


def write_json(path, value):
    with path.open('x', encoding='utf-8') as output:
        json.dump(value, output, indent=2)


def digest(rows):
    strings = [json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        default=lambda value: {'blob_sha256': hashlib.sha256(value).hexdigest()}) for row in rows]
    return hashlib.sha256(json.dumps(sorted(strings), separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def snapshot(metadata):
    path = Path(metadata['home']) / 'nexus.db'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        result = {}
        for table in TABLES:
            rows = [dict(row) for row in conn.execute('SELECT * FROM "' + table + '"')]
            result[table] = dict(rows=len(rows), sha256=digest(rows))
            if table == 'agents':
                # Keep a raw fingerprint too, but isolate the known audit-only
                # last_seen write for the reserved operator from authority data.
                result['agents_raw'] = result[table]
                stable = [dict(row, last_seen_at=None) if row['agent_id'] == 'operator' else row for row in rows]
                result[table] = dict(rows=len(rows), sha256=digest(stable))
                credentials = [{key: row[key] for key in ('agent_id', 'api_key_hash', 'is_active', 'deleted_at')}
                    for row in rows]
                result['agent_credentials'] = dict(rows=len(rows), sha256=digest(credentials))
    return dict(revision=1, home=metadata['home'], tables=result,
        excluded_from_stable_hash=['agents.operator.last_seen_at only; raw hash retained separately'],
        raw_rows_or_secrets_written=False)


def request(metadata, method, path, body=None):
    origin = metadata['url']
    headers = {'Origin': origin, 'X-Nexus-UI': '1'}
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(origin + path, data=data, headers=headers, method=method)
    with build_opener(ProxyHandler({})).open(req, timeout=40) as response:
        value = json.load(response)
    assert value.get('ok') is True, 'Canonical API refused request.'
    return value['data']


def current_owner(metadata):
    owner = request(metadata, 'GET', '/api/v1/service')
    # Windows venv launcher PID can differ from the interpreter's actual PID.
    expected_pid = metadata.get('pid') or json.loads(Path(metadata['entry_proof']).read_text())['pid']
    assert owner['pid'] == expected_pid, 'Port no longer belongs to this isolated interpreter.'
    if 'generation' in metadata:
        assert (owner['instance_id'], owner['generation']) == (metadata['instance_id'], metadata['generation'])
    return owner


def start(candidate, scenario):
    proof = json.loads((candidate / 'package-proof.json').read_text())
    folder = candidate / 'servers' / scenario
    folder.mkdir(parents=True, exist_ok=False)
    task_home = folder / 'home'
    task_home.mkdir()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {key: value for key, value in os.environ.items()
        if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PATH', 'TEMP', 'TMP'}}
    env.update(USERPROFILE=str(task_home), APPDATA=str(task_home / 'appdata'),
        LOCALAPPDATA=str(task_home / 'localappdata'), PYTHONDONTWRITEBYTECODE='1',
        OKTO_NEXUS_NO_BANNER='1', OKTO_NEXUS_LOG_LEVEL='warning')
    log = folder / 'server.log'
    with log.open('x', encoding='utf-8') as output:
        process = subprocess.Popen([proof['python'], '-I', '-B', '-X', 'utf8', str(ROOT / 'server_entry.py'),
            str(candidate), scenario, str(port), site.getusersitepackages()], cwd=task_home, env=env,
            stdout=output, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    metadata = dict(url=f'http://127.0.0.1:{port}', launcher_pid=process.pid, home=str(task_home), log=str(log),
        entry_proof=str(folder / 'import-proof.json'),
        python=proof['python'], scenario=scenario, wheel_sha256=proof['wheel_sha256'],
        shutdown=f'python {ROOT / "servers.py"} stop {candidate.name} {scenario}')
    write_json(folder / 'launch.json', metadata)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'Isolated Server exited {process.returncode}; inspect its retained log.')
        try:
            owner = current_owner(metadata)
            if owner.get('ready') or str(owner.get('state', '')).lower() == 'ready':
                break
        except (OSError, ValueError):
            pass
        time.sleep(.25)
    else:
        raise RuntimeError('Readiness timeout; own process metadata retained for explicit shutdown.')
    metadata.update(pid=owner['pid'], generation=owner['generation'], instance_id=owner['instance_id'])
    write_json(folder / 'server.json', metadata)
    write_json(folder / 'owner.json', owner)
    served = {}
    for relative in (proof['dashboard_bundle'], 'adapters/inbound/http/static/assets/index-CbeM8Lpf.css'):
        asset_path = relative.removeprefix('adapters/inbound/http/static/')
        with build_opener(ProxyHandler({})).open(metadata['url'] + '/' + asset_path, timeout=10) as response:
            asset_digest = hashlib.sha256(response.read()).hexdigest()
        assert asset_digest == proof['files'][relative], 'HTTP served a different packaged asset.'
        served[asset_path] = asset_digest
    write_json(folder / 'static-http-proof.json', dict(exact_packaged_bytes=True, assets=served))
    write_json(folder / 'baseline.json', snapshot(metadata))
    print(json.dumps(metadata, indent=2))


def capture(candidate, scenario, label):
    folder = candidate / 'servers' / scenario
    metadata = json.loads((folder / 'server.json').read_text())
    current_owner(metadata)
    before = json.loads((folder / 'baseline.json').read_text())
    after = snapshot(metadata)
    changes = [key for key in before['tables'] if key != 'agents_raw' and
        before['tables'][key] != after['tables'][key]]
    write_json(folder / (label + '-snapshot.json'), after)
    result = dict(unchanged=not changes, changed_tables=changes,
        operator_audit_or_other_raw_agent_change=before['tables']['agents_raw'] != after['tables']['agents_raw'],
        checked_tables=len(TABLES), snapshot=str(folder / (label + '-snapshot.json')))
    write_json(folder / (label + '-proof.json'), result)
    print(json.dumps(result, indent=2))
    assert not changes, 'Canonical state changed; inspect the hashes without exporting rows.'


def stop(candidate, scenario):
    folder = candidate / 'servers' / scenario
    metadata = json.loads((folder / 'server.json').read_text())
    recorded = json.loads((folder / 'owner.json').read_text())
    current = current_owner(metadata)
    assert (current['instance_id'], current['generation']) == (recorded['instance_id'], recorded['generation'])
    result = request(metadata, 'POST', '/api/v1/service/stop', dict(instance_id=current['instance_id'],
        generation=current['generation'], timeout_seconds=30.0))
    exited = None
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x00100000, False, metadata['pid'])
        if handle:
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            try:
                exited = kernel.WaitForSingleObject(handle, 40000) == 0
            finally:
                kernel.CloseHandle(handle)
        else:
            exited = ctypes.get_last_error() == 87
    retained = dict(pid=metadata['pid'], canonical_result=result, process_exited=exited)
    write_json(folder / 'shutdown.json', retained)
    print(json.dumps(retained, indent=2))


if __name__ == '__main__':
    action, candidate_name, scenario = sys.argv[1:4]
    assert re.fullmatch(r'[a-zA-Z0-9_-]+', candidate_name)
    assert scenario in ('onboarding', 'agents')
    candidate = ROOT / candidate_name
    if action == 'start':
        start(candidate, scenario)
    elif action == 'snapshot':
        label = sys.argv[4]
        assert re.fullmatch(r'[a-zA-Z0-9_-]+', label)
        capture(candidate, scenario, label)
    elif action == 'stop':
        stop(candidate, scenario)
    else:
        raise ValueError('Unknown lifecycle command.')
