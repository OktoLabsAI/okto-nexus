"""Real CLI/service/local HTTP integration without harness/provider activity."""
import json
import os
import socket
import subprocess
import sys
from urllib.request import ProxyHandler, Request, build_opener
import pytest


@pytest.mark.parametrize('legacy_context', [False, True])
def test_connect_starts_reuses_and_leaves_service_owned_until_explicit_stop(tmp_path, legacy_context):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE',
        'LOCALAPPDATA', 'APPDATA', 'PATH', 'LANG', 'LC_ALL', 'HOME'}}
    home = tmp_path / 'home'
    base = [sys.executable, '-m', 'okto_nexus.adapters.inbound.cli.main']
    selection = ['--home', str(home), '--host', '127.0.0.1', '--port', str(port),
                 '--embedding-mode', 'off', '--feature-harness-integrations', 'false']
    def invoke(arguments):
        result = subprocess.run([*base, *arguments, '--json'], cwd=tmp_path, env=env,
                                capture_output=True, text=True, timeout=70)
        return result, json.loads(result.stdout)
    # A plan on an absent home must not bootstrap a Server or create state.
    process, planned = invoke(['connect', '--plan', '--agent', 'missing', *selection])
    assert process.returncode == 3 and planned['state'] == 'service_not_ready'
    assert not home.exists()
    process, absent_work = invoke(['work', 'status', *selection])
    assert process.returncode == 3 and absent_work['code'] == 'CONNECTION_REQUIRED'
    assert not home.exists()
    if legacy_context:
        from okto_nexus.adapters.inbound.cli.service import resolve_local_service
        from okto_nexus.adapters.outbound.service_manager.context import atomic_json
        context = resolve_local_service(selection).adapter.context
        context.pop('settings_pinned_fields')
        home.mkdir()
        atomic_json(home / 'service-context.json', context)
    try:
        process, result = invoke(['connect', '--agent', 'missing', *selection])
        assert process.returncode == 3 and result['code'] == 'NOT_FOUND', (result, process.stderr)
        process, first = invoke(['service', 'status', '--home', str(home)])
        assert process.returncode == 0 and first['state'] == 'ready'
        # The launcher has exited. The next connect uses the saved service context.
        process, result = invoke(['connect', '--agent', 'missing', '--home', str(home)])
        assert process.returncode == 3 and result['code'] == 'NOT_FOUND'
        _, second = invoke(['service', 'status', '--home', str(home)])
        assert (second['generation'], second['pid']) == (first['generation'], first['pid'])
        opener = build_opener(ProxyHandler({}))
        def settings(changes=None):
            request = Request(f'http://127.0.0.1:{port}/api/v1/settings',
                data=json.dumps(changes).encode() if changes is not None else None,
                method='PATCH' if changes is not None else 'GET',
                headers={'X-Nexus-UI': '1', 'Content-Type': 'application/json'})
            with opener.open(request, timeout=10) as response:
                return json.load(response)['data']
        current = {item['key']: item for item in settings()['items']}
        assert current['feature_hitl']['source'] == 'default' and current['feature_hitl']['editable']
        assert current['feature_harness_integrations']['source'] == 'cli/env'
        assert settings({'feature_hitl': True})['applied'] == {'feature_hitl': True}
        process, restarted = invoke(['service', 'restart', '--home', str(home), '--timeout', '40'])
        assert process.returncode == 0 and restarted['state'] == 'ready', restarted
        assert restarted['generation'] != first['generation']
        current = {item['key']: item for item in settings()['items']}
        assert current['feature_hitl']['value'] is True and current['feature_hitl']['source'] == 'stored'
    finally:
        process, stopped = invoke(['service', 'stop', '--home', str(home), '--timeout', '40'])
        assert process.returncode == 0 and stopped['state'] == 'stopped', stopped
        assert stopped.get('shutdown_outcome') == 'drained'
