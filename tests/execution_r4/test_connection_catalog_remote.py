"""Explicit workspace permits remote association without interpreting host paths."""
import json
from types import SimpleNamespace

import pytest

import test_binding_operator
from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.inbound.http.connection_catalog import build_router
from okto_nexus.adapters.outbound.service_manager.context import read_json
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.application.terminal_work import TerminalWork

onboarding = test_binding_operator.onboarding


def test_remote_canonical_alias_requires_workspace_and_preserves_remote_scope(onboarding, tmp_path, monkeypatch):
    deps, client, headers, prepare = onboarding
    _, apply, approval_id = test_binding_operator.prepare_delegated(client, headers, prepare)
    assert test_binding_operator.decide_binding(client, headers, approval_id).status_code == 200
    result = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert result.status_code == 200, result.text
    binding = result.json()
    app = client.app
    route = '/api/v1/runtime-management/connections/catalog'
    if not any(getattr(item, 'path', None) == route for item in app.routes):
        app.include_router(build_router(), prefix='/api/v1/runtime-management')
    home, project = tmp_path / 'operator-shortcuts', tmp_path / 'operator-own-folder'
    project.mkdir()
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=1),
        inspect=lambda: dict(state='ready', instance_id='fixture-local-server'),
        ensure_running=lambda **kwargs: pytest.fail('plan must not start any service'))
    calls, changed = [], [False]
    def call(method, path, body=None):
        calls.append((method, path))
        response = client.request(method, path, json=body, headers=headers['operator'])
        value = response.json()
        if response.status_code >= 400:
            error = value['error']
            raise ConnectionError(error['code'], error['message'])
        if changed[0] and '/connections/bindings/' in path:
            value['executor_id'] = 'another-executor'
        return value
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: call)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr('builtins.input', lambda prompt: '1')
    tables = ('agents', 'execution_bindings', 'runtime_execution_grants', 'execution_operations')
    def counts():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return {name: uow.connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in tables}
    before = counts()
    assert connect.run_connect(['--home', str(home), '--project', str(project),
        '--workspace-id', binding['workspace_id'], '--plan', '--no-chat']) == 0
    profile_path, = (home / 'terminal/profiles').glob('*.json')
    profile = read_json(profile_path)
    assert profile['remote_scope']['executor_id'] == binding['executor_id']
    assert profile['remote_scope']['workspace_id'] == binding['workspace_id']
    assert profile['selection']['project'] == str(project)
    assert profile['selection']['provider_home'] is None
    assert not profile['selection'].get('operator_profile')
    assert profile['result']['binding']['binding_id'] == binding['binding_id']
    flow = TerminalWork(call, lambda value: pytest.fail('observation must not save work'), profile)
    assert flow.binding()['binding_id'] == binding['binding_id']
    assert flow.sessions()['sessions'] == []
    assert connect.run_connect(['--home', str(home), '--profile', profile_path.stem, '--plan', '--json']) == 0
    assert counts() == before and all(method == 'GET' for method, _ in calls)
    assert 'workspace_root' not in json.dumps(profile)
    changed[0] = True
    with pytest.raises(ConnectionError) as error:
        flow.binding()
    assert error.value.code == 'PROFILE_DRIFT'
    assert counts() == before
