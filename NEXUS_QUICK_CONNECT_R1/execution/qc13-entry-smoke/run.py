"""Actual installed console entry, cold plan and old-Server capability refusal."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx

from okto_nexus.adapters.inbound.cli.quick_connect_ids import require_public_ids
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
from okto_nexus.application.terminal_connection import ConnectionError

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PREFIX = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/venv')
OLD = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1/venv/Scripts/python.exe')


def main():
    assert sys.flags.isolated and Path(sys.prefix).resolve() == PREFIX.resolve()
    assert not (OUT / 'qualification.json').exists(), 'Preserve completed cuts'
    own = Path(tempfile.mkdtemp(prefix='nexus-qc13-entry-smoke-')).resolve()
    project, empty = own / 'project', own / 'empty-path'
    project.mkdir()
    empty.mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in (
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PROCESSOR_ARCHITECTURE',
        'NUMBER_OF_PROCESSORS', 'PATHEXT')}
    for name in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP'):
        path = own / ('env-' + name.lower())
        path.mkdir()
        env[name] = str(path)
    env.update(PATH=str(empty), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
        OKTO_NEXUS_NO_BANNER='1', OKTO_NEXUS_LOG_LEVEL='warning')
    commands = []
    for name, argv, expected in (
        ('cold-plan', ['connect', 'codex', '--plan', '--json', '--home', str(own / 'new-home')], 3),
        ('new-add-requires-profile', ['connect', 'codex', '--new-connection', '--id', 'worker', '--json',
            '--home', str(own / 'other-home')], 3),
    ):
        command = [str(PREFIX / 'Scripts/okto-nexus.exe'), *argv]
        result = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=30, check=False)
        value = json.loads(result.stdout)
        assert result.returncode == expected, (name, result.returncode)
        assert '\x1b' not in result.stdout
        if name == 'cold-plan':
            assert value['state'] == 'service_not_ready'
            assert not (own / 'new-home/nexus.db').exists()
        else:
            assert value['state'] == 'selection_required'
            assert value['reason'] == 'new_connection_requires_profile'
            assert value['effects_started'] is False and value['lifecycle_requested'] is False
        commands.append(dict(name=name, command=command, exit_code=result.returncode, result=value))
        (OUT / (name + '.stdout.json')).write_text(result.stdout, encoding='utf-8')
        (OUT / (name + '.stderr.txt')).write_text(result.stderr, encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    home = own / 'old-server-home'
    serve = [str(OLD), '-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main', 'serve',
        '--home', str(home), '--project-root', str(project), '--host', '127.0.0.1',
        '--port', str(port), '--embedding-mode', 'off']
    process = None
    cleanup = None
    try:
        with (own / 'old-server.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(serve, cwd=own, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            deadline = time.monotonic() + 30
            with httpx.Client(trust_env=False, timeout=1) as client:
                while True:
                    assert process.poll() is None, 'Owned old Server exited before readiness'
                    try:
                        if client.get(f'http://127.0.0.1:{port}/healthz').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    assert time.monotonic() < deadline, 'Owned Server readiness timed out'
                    time.sleep(0.1)
            call = LocalOperatorHTTP(host='127.0.0.1', port=port)
            me = call('GET', '/api/v1/runtime-management/connections/me')
            try:
                require_public_ids(call, me['server_id'])
            except ConnectionError as error:
                assert error.code == 'CONNECT_ID_UNSUPPORTED_SERVER', error.code
                refusal = dict(code=error.code, message=error.message)
            else:
                raise AssertionError('Old installed Server unexpectedly supports new public IDs')
            commands.append(dict(name='old-server-capability', old_server_command=serve,
                new_client_module='site-packages CLI adapter, exact capability check', result=refusal))
    finally:
        if process is not None:
            stop = [str(OLD), '-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main', 'service', 'stop',
                '--home', str(home), '--host', '127.0.0.1', '--port', str(port), '--timeout', '15', '--json']
            result = subprocess.run(stop, cwd=own, env=env, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=25, check=False)
            code = process.wait(timeout=15)
            cleanup = dict(command=stop, canonical_exit=result.returncode, physical_exit=code,
                pid=process.pid, forced=False)
            (OUT / 'stop.stdout.json').write_text(result.stdout, encoding='utf-8')
            (OUT / 'stop.stderr.txt').write_text(result.stderr, encoding='utf-8')
            assert result.returncode == code == 0
    report = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS_SCOPED_INSTALLED_ENTRY',
        own_root=str(own), cwd=str(project), python=sys.executable, prefix=sys.prefix,
        commands=commands, cleanup=cleanup, provider_calls=0,
        limitations=['Cold plan is not a configured connection or real provider journey.',
            'Old Server test uses the installed new capability adapter, not the whole service upgrade command.',
            'Temporary state retained after normal stop; no personal installation or earlier artifact changed.'])
    (OUT / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'], commands=len(commands), cleanup=cleanup)), flush=True)


if __name__ == '__main__':
    main()
