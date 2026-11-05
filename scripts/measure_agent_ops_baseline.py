"""Measure nonproductive foreground startup in a disposable, loopback-only home.

This is not a service, provider, or complete onboarding acceptance campaign.
Only the child created here is stopped; no process is found or killed by PID file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener


def measure() -> dict:
    with tempfile.TemporaryDirectory(prefix='nexus-agent-ops-baseline-') as directory:
        root = Path(directory)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        env = {key: value for key, value in os.environ.items() if key.upper() in {
            'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE',
            'LOCALAPPDATA', 'APPDATA', 'PATH', 'LANG', 'LC_ALL',
        }}
        env['OKTO_NEXUS_NO_BANNER'] = '1'
        env['PYTHONUTF8'] = '1'
        command = [sys.executable, '-m', 'okto_nexus.adapters.inbound.cli.main',
                   'serve', '--home', str(root / 'home'), '--project-root', str(root),
                   '--host', '127.0.0.1', '--port', str(port), '--embedding-mode', 'off']
        started = time.monotonic()
        opener = build_opener(ProxyHandler({}))
        base_url = f'http://127.0.0.1:{port}'
        with (root / 'server.log').open('wb') as log:
            child = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=log)
            try:
                while time.monotonic() - started < 60:
                    if child.poll() is not None:
                        raise RuntimeError(f'Foreground startup failed: exit {child.returncode}')
                    try:
                        with opener.open(base_url + '/healthz', timeout=.5) as response:
                            if response.status == 200:
                                break
                    except (URLError, TimeoutError):
                        time.sleep(.1)
                else:
                    raise TimeoutError('Foreground HTTP liveness not reached in 60 seconds')
                result = {
                    'platform': platform.platform(), 'python': platform.python_version(),
                    'installation': 'editable candidate in repository venv',
                    'component': 'server', 'topology': 'local', 'supervisor': 'foreground',
                    'cold_empty_home_http_liveness_seconds': round(time.monotonic() - started, 3),
                    'provider_invocations': 0,
                    'credential_use': 'synthetic operator key in disposable home; memory only',
                    'baseline_dashboard_setup_steps_from_source': 7,
                    'complete_terminal_work_cycle': 'NOT_AVAILABLE_AT_BASELINE',
                    'terminal_survival': 'NOT_TESTED', 'login': 'NOT_TESTED',
                    'logout': 'NOT_TESTED', 'boot': 'NOT_TESTED',
                    'cleanup': 'canonical shutdown with synthetic disposable operator; child exit awaited',
                    'limitations': ['HTTP liveness is not instance readiness or harness readiness.',
                                    'No clean installed Nexus wheel or paid provider timing measured.'],
                }
                # This home was created above and never contains a personal identity.
                # Use the real shutdown contract rather than a PID-based termination.
                with opener.open(Request(base_url + '/api/v1/agents/operator/regenerate-key',
                                         data=b'', method='POST'), timeout=10) as response:
                    key = json.load(response)['data']['api_key']
                with opener.open(Request(base_url + '/v1/runtime/shutdown',
                                         data=b'{"timeout_seconds":30}', method='POST',
                                         headers={'Content-Type': 'application/json',
                                                  'Authorization': 'Bearer ' + key}), timeout=40) as response:
                    result['shutdown_state'] = json.load(response)['state']
                child.wait(timeout=15)
                assert result['shutdown_state'] == 'DRAINED'
                return result
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=15)


if __name__ == '__main__':
    result = measure()
    target = Path(__file__).resolve().parents[1] / 'plans/agent_ops/evidence/baseline-startup.json'
    target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
