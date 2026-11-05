"""Real installed-environment replacement, disposable data and canonical drain."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest


def test_reviewed_upgrade_between_installed_environments_preserves_database(tmp_path):
    target = os.environ.get('R3_UPGRADE_TARGET_PYTHON')
    if not target:
        pytest.skip('Requires a separately installed candidate Python environment')
    assert Path(target).absolute() != Path(sys.executable).absolute()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    home = tmp_path / 'server'
    base = [sys.executable, '-I', '-m', 'okto_nexus.adapters.inbound.cli.main', 'service']
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE', 'HOME',
        'LOCALAPPDATA', 'APPDATA', 'PATH', 'LANG', 'LC_ALL'}}
    def invoke(action, *args, expected=0):
        result = subprocess.run([*base, action, '--home', str(home), '--json', *args],
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=75)
        assert result.returncode == expected, (result.stdout, result.stderr)
        return json.loads(result.stdout)
    stopped = False
    try:
        initial = invoke('start', '--port', str(port), '--project-root', str(tmp_path),
            '--embedding-mode', 'off', '--timeout', '40')
        original_context = json.loads((home / 'service-context.json').read_text(encoding='utf-8'))
        plan = tmp_path / 'plan.json'
        document = invoke('upgrade-plan', '--python', target, '--output', str(plan))
        assert json.loads(plan.read_text(encoding='utf-8')) == document
        assert document['plan']['source_generation'] == initial['generation']
        apply_args = ('--plan-file', str(plan), '--expected-revision', document['plan_revision'])
        refusal = invoke('upgrade-apply', *apply_args, expected=2)
        assert refusal['reason'] == 'UPGRADE_OWNER_UNCONFIRMED'
        assert invoke('status')['generation'] == initial['generation']
        assert invoke('stop', '--timeout', '40')['shutdown_outcome'] == 'drained'
        database = home / 'nexus.db'
        before = hashlib.sha256(database.read_bytes()).hexdigest()
        assert invoke('upgrade-apply', *apply_args)['applied']
        assert hashlib.sha256(database.read_bytes()).hexdigest() == before
        assert invoke('status')['state'] == 'stopped'
        assert not invoke('upgrade-apply', *apply_args)['changed']
        context = json.loads((home / 'service-context.json').read_text(encoding='utf-8'))
        assert context['executable'] == target and context['revision'] == 2
        assert context['arguments'] == original_context['arguments']
        restarted = invoke('start', '--timeout', '40')
        assert restarted['generation'] != initial['generation']
        assert restarted['state'] == 'ready'
        assert json.loads((home / 'service-context.json').read_text(encoding='utf-8')) == context
        assert invoke('stop', '--timeout', '40')['shutdown_outcome'] == 'drained'
        stopped = True
    finally:
        if not stopped and home.exists():
            subprocess.run([*base, 'stop', '--home', str(home), '--timeout', '40', '--json'],
                cwd=tmp_path, env=env, capture_output=True, timeout=65)
