"""Real detached local processes, disposable data and no provider/credential use."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener


def test_concurrent_detached_start_survives_cli_exit_reuses_and_drains(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE',
        'LOCALAPPDATA', 'APPDATA', 'PATH', 'LANG', 'LC_ALL', 'HOME'}}
    home = tmp_path / 'isolated home'
    base = [sys.executable, '-m', 'okto_nexus.adapters.inbound.cli.main', 'service']
    selection = ['--home', str(home), '--host', '127.0.0.1', '--port', str(port),
                 '--project-root', str(tmp_path), '--embedding-mode', 'off']
    def invoke(action, *extra):
        completed = subprocess.run([*base, action, '--home', str(home), '--json', *extra],
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=65)
        assert completed.returncode == 0, (completed.stdout, completed.stderr)
        return json.loads(completed.stdout)
    parents = []
    stopped = False
    try:
        for _ in range(3):
            parents.append(subprocess.Popen([*base, 'start', *selection, '--timeout', '40', '--json'],
                cwd=tmp_path, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        observations = []
        for parent in parents:
            out, err = parent.communicate(timeout=55)
            assert parent.returncode == 0, (out, err)
            observations.append(json.loads(out))
        assert all(view['state'] == 'ready' for view in observations)
        generations = {view['generation'] for view in observations}
        pids = {view['pid'] for view in observations}
        assert len(generations) == len(pids) == 1
        assert all(view['supervisor'] == 'detached' for view in observations)
        # Every launcher has exited, and selection is restored without the old
        # port, cwd, environment configuration flags or terminal handles.
        time.sleep(.3)
        original = invoke('status')
        assert original['generation'] in generations and original['pid'] in pids
        assert invoke('start')['generation'] == original['generation']
        reopened = invoke('restart', '--timeout', '40')
        assert reopened['generation'] != original['generation']
        opener = build_opener(ProxyHandler({}))
        stale = Request(f'http://127.0.0.1:{port}/api/v1/service/stop', method='POST',
            data=json.dumps({'instance_id': original['instance_id'],
                             'generation': original['generation']}).encode(),
            headers={'Content-Type': 'application/json'})
        try:
            opener.open(stale, timeout=5)
        except HTTPError as error:
            assert error.code == 409
        else:
            raise AssertionError('A stale generation stopped a new instance')
        assert invoke('status')['generation'] == reopened['generation']
        result = invoke('stop', '--timeout', '40')
        assert result['state'] == 'stopped' and result['shutdown_outcome'] == 'drained'
        stopped = True
        assert invoke('status')['state'] == 'stopped'
        assert home.joinpath('nexus.db').is_file()
    finally:
        for parent in parents:
            if parent.poll() is None:
                parent.communicate(timeout=55)
        if not stopped and home.exists():
            # Only the configured disposable instance; never signal a PID from
            # metadata or touch an existing personal service.
            subprocess.run([*base, 'stop', *selection, '--timeout', '40', '--json'],
                cwd=tmp_path, env=env, capture_output=True, timeout=55)
