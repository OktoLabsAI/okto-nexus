"""Actual concurrent CLI starts, disposable state, no Server or provider work."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def test_concurrent_cli_start_reuse_restart_and_drain_keep_one_owner(tmp_path):
    root = tmp_path / 'isolated connector'
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE',
        'LOCALAPPDATA', 'APPDATA', 'PATH', 'LANG', 'LC_ALL', 'HOME'}}
    env['API_KEY_SENTINEL'] = 'must-not-be-copied'
    base = [sys.executable, '-I', '-m', 'okto_nexus_connector.cli.main', '--state-dir', str(root), 'daemon']
    def invoke(action, *extra):
        result = subprocess.run([*base, action, '--json', *extra], cwd=tmp_path, env=env,
            capture_output=True, text=True, timeout=70)
        assert result.returncode == 0, (result.stdout, result.stderr)
        return json.loads(result.stdout)
    assert invoke('status')['state'] == 'stopped'
    assert not root.exists()
    from okto_nexus_connector.platform.service_context import LAUNCH, digest, write_document
    from okto_nexus_connector.platform.service_identity import service_instance_id
    (root / 'run').mkdir(parents=True)
    interrupted = {'revision': 1, 'instance_id': service_instance_id(root),
        'token': 'interrupted-token', 'state': 'pending', 'pid': None}
    write_document(root / 'run' / LAUNCH, interrupted)
    recovered = invoke('recover-start', '--expected-revision', digest(interrupted))
    assert recovered['recovered'] and not (root / 'state.json').exists()
    launchers, stopped = [], False
    try:
        for _ in range(3):
            launchers.append(subprocess.Popen([*base, 'start', '--json'], cwd=tmp_path, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        results = []
        for launcher in launchers:
            out, err = launcher.communicate(timeout=60)
            assert launcher.returncode == 0, (out, err)
            results.append(json.loads(out))
        assert len({value['generation'] for value in results}) == 1
        assert len({value['pid'] for value in results}) == 1
        assert sum(value['started'] for value in results) == 1
        assert all(value['supervisor'] == 'detached' and value['state'] == 'ready' for value in results)
        initial = results[0]
        assert invoke('status')['generation'] == initial['generation']
        assert invoke('start')['generation'] == initial['generation']
        late = subprocess.run([sys.executable, '-I', '-m', 'okto_nexus_connector.daemon.service_process',
            '--state-dir', str(root), '--token', interrupted['token']], cwd=tmp_path, env=env,
            capture_output=True, text=True, timeout=20)
        assert late.returncode == 2, (late.stdout, late.stderr)
        assert invoke('status')['generation'] == initial['generation']
        assert 'must-not-be-copied' not in (root / 'service-context.json').read_text(encoding='utf-8')
        restarted = invoke('restart')
        assert restarted['generation'] != initial['generation']
        shutdown = invoke('stop')
        assert shutdown['shutdown_outcome'] == 'drained'
        receipt = json.loads((root / 'run' / 'shutdown.json').read_text(encoding='utf-8'))
        assert receipt['generation'] == restarted['generation']
        run_marker = json.loads((root / 'service-run.json').read_text(encoding='utf-8'))
        assert run_marker['state'] == 'drained' and run_marker['generation'] == restarted['generation']
        assert run_marker['instance_id'] == restarted['instance_id']
        stopped = True
        assert invoke('status')['state'] == 'stopped'
        assert (root / 'state.json').exists()
        assert (root / 'logs' / 'daemon.log').exists()
    finally:
        for launcher in launchers:
            if launcher.poll() is None:
                launcher.communicate(timeout=60)
        if not stopped:
            subprocess.run([*base, 'stop', '--json'], cwd=tmp_path, env=env,
                capture_output=True, text=True, timeout=70)
