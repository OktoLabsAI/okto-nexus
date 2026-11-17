"""Canonical service controls on one retained own fixture, no SQL repairs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import zipfile

import psutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FIXTURE = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-git-cli-complete-3hnalsq1/git-cli-composed/tmp/pytest-of-unknown/pytest-0/test_origin_first_connect_and_0')
PACKAGE = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc')
PYTHON = PACKAGE / 'venv/Scripts/python.exe'
TABLES = ('execution_bindings', 'agent_endpoints', 'runtime_execution_grants', 'connection_setup_commits',
          'connection_public_ids', 'connection_project_drafts', 'execution_sessions', 'execution_operations')


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def snapshot():
    with sqlite3.connect((FIXTURE / 'home/nexus.db').as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        result = {}
        for name in TABLES:
            rows = sorted([dict(r) for r in conn.execute('SELECT * FROM ' + name)], key=repr)
            result[name] = dict(count=len(rows), sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest())
        reference = dict(conn.execute('SELECT canonical_ref_json,connect_id FROM connection_public_ids WHERE state=\'bound\'').fetchone())
        result['reference'] = json.loads(reference['canonical_ref_json'])
        result['connect_id'] = reference['connect_id']
        result['workspaces'] = [dict(r) for r in conn.execute('SELECT workspace_id,display_name,root_realpath FROM workspaces')]
    return result


def payload():
    result = {}
    for module, wheel in [('okto_nexus', PACKAGE / 'artifacts/okto_nexus-0.3.6-py3-none-any.whl'),
                         ('nexus_connector_core', REPO / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
                         ('okto_nexus_connector', REPO / 'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl')]:
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.startswith(module + '/') and not name.endswith('/'):
                    raw = (PACKAGE / 'venv/Lib/site-packages' / name).read_bytes()
                    assert raw == archive.read(name), name
                    result[name] = hashlib.sha256(raw).hexdigest()
    assert len(result) == 1027
    return result


def environment(root):
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT'}}
    for name in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP'):
        target = root / name.lower()
        target.mkdir(exist_ok=True)
        env[name] = str(target)
    env.update(PATH='', PYTHONUTF8='1', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_CONFIG_SYSTEM=os.devnull, GIT_TERMINAL_PROMPT='0')
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'start', 'status', 'stop', 'after'])
    action = parser.parse_args().action
    if action == 'prepare':
        assert not (HERE / 'allocation.json').exists()
        root = Path(tempfile.mkdtemp(prefix='nexus-qc25-continuity-'))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        profiles = list((FIXTURE / 'quick-cli-home/terminal/profiles').glob('*.json'))
        assert len(profiles) == 1
        saved = json.loads(profiles[0].read_text())
        assert saved['state'] == 'done' and saved['selection']['label'] == 'logical-origin'
        assert saved['selection']['project'] == str(FIXTURE / 'workspace')
        config = (FIXTURE / 'workspace/.git/config').read_text()
        assert 'https://changed.invalid/different-name.git' in config
        me = psutil.Process()
        excluded = {me.pid, *(p.pid for p in me.parents())}
        live = []
        for p in psutil.process_iter(['pid', 'cmdline', 'create_time']):
            if p.pid not in excluded and str(FIXTURE.parent.parent.parent.parent) in ' '.join(p.info['cmdline'] or []):
                live.append(dict(pid=p.pid, created=p.info['create_time']))
        assert not live, live
        before = snapshot()
        assert before['execution_sessions']['count'] == before['execution_operations']['count'] == 0
        write(HERE / 'allocation.json', dict(root=str(root), fixture=str(FIXTURE), home=str(FIXTURE / 'home'), port=port,
            url='http://127.0.0.1:' + str(port), project_root=str(FIXTURE / 'workspace'),
            logical_name='logical-origin', reference=before['reference'], connect_id=before['connect_id'],
            profile_sha256=hashlib.sha256(profiles[0].read_bytes()).hexdigest(),
            original_process_marker_matches=live, observed_at=datetime.now(timezone.utc).isoformat()))
        write(root / 'before.json', before)
        write(root / 'payload-before.json', payload())
        print(json.dumps(dict(status='SAFETY_READY', root=str(root), sessions=0, operations=0, old_processes=live)))
        return
    allocation = json.loads((HERE / 'allocation.json').read_text())
    root = Path(allocation['root'])
    if action == 'after':
        after = snapshot()
        before = json.loads((root / 'before.json').read_text())
        write(root / 'after.json', after)
        write(root / 'payload-after.json', payload())
        changed = [k for k in before if before[k] != after[k]]
        write(root / 'comparison.json', dict(changed=changed, sessions_before=before['execution_sessions']['count'],
            sessions_after=after['execution_sessions']['count'], payload_unchanged=json.loads((root / 'payload-before.json').read_text()) == payload()))
        print(json.dumps(dict(changed=changed)))
        return
    argv = [str(PYTHON), '-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main', 'service', action, '--json', '--timeout', '30',
            '--home', str(FIXTURE / 'home'), '--db-path', str(FIXTURE / 'home/nexus.db'),
            '--host', '127.0.0.1', '--port', str(allocation['port']), '--embedding-mode', 'off',
            '--metrics-mode', 'disabled', '--metrics-dir', str(root / 'metrics'), '--feature-harness-integrations', 'true']
    result = subprocess.run(argv, cwd=root, env=environment(root), stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=50)
    (root / (action + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    write(root / (action + '-command.json'), dict(argv=argv, exit_code=result.returncode))
    value = json.loads(result.stdout)
    write(root / (action + '.json'), value)
    print(json.dumps(dict(exit_code=result.returncode, result=value)))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
