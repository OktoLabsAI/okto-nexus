"""Attach retirement removes entry points while keeping historical records."""
from pathlib import Path
import importlib.util
import pytest

import okto_nexus
from test_local_realization import local_setup
from test_connection_setup import request_for, finish
from okto_nexus.application.execution_local_realizations import directory_identity


@pytest.mark.parametrize('platform', ['win32', 'linux', 'darwin'])
def test_installed_core_cannot_load_external_attach(platform):
    from nexus_connector_core import CoreError
    from nexus_connector_core.native.registry import load_adapter
    assert importlib.util.find_spec('nexus_connector_core.native.adapters.claude_code_attach') is None
    with pytest.raises(CoreError, match='CAPABILITY_UNSUPPORTED'):
        load_adapter('claude_attach', platform=platform)


def test_attach_removed_from_dashboard_and_catalog(local_setup):
    from okto_nexus.adapters.outbound.execution.core_inventory import local_catalog
    assert 'claude_attach' not in {r['adapter_id'] for r in local_catalog()['runtimes']}
    _, _, client, headers, *_ = local_setup
    base = '/api/v1/runtime-management/connections/subject/claude-attach/'
    assert client.get(base + 'targets', headers=headers['operator']).status_code == 404
    for action in ('probe', 'test'):
        assert client.post(base + action, headers=headers['operator'], json={}).status_code == 404


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_removed_attach_cannot_open_through_legacy_public_routes(local_setup, monkeypatch, surface):
    deps, _, client, headers, *_, root = local_setup
    request = dict(agent_id='subject', kind='claude_code', substrate='attach',
                   target_pid=12345, project_root=str(root))
    if surface == 'rest':
        response = client.post('/api/v1/harness/sessions', headers=headers['operator'], json=request)
        assert response.status_code == 403, response.text
        assert response.json()['error']['code'] == 'PERMISSION_DENIED'
    else:
        monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
        from test_pr34_remediation import tool
        client.headers['host'] = '127.0.0.1:8000'
        response = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '), 'harness_open', request)
        assert not response['ok'] and response['error']['code'] == 'PERMISSION_DENIED', response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM harness_sessions').fetchone()[0] == 0


def test_attach_retirement_disables_only_old_endpoints_and_preserves_records(local_setup):
    context, request = request_for(local_setup)
    result = finish(local_setup, context, request, verified={
        'root': directory_identity(request['configuration']['workspace_root']), 'home': None})
    endpoint = result['binding']['endpoint_id']
    sql = (Path(okto_nexus.__file__).parent / 'migrations/119_retire_claude_attach.sql').read_text(encoding='utf-8')
    with local_setup[0].connection_factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("UPDATE agent_endpoints SET adapter_id='claude_attach',enabled=1 WHERE endpoint_id=?", (endpoint,))
        before = dict(conn.execute('SELECT * FROM agent_endpoints WHERE endpoint_id=?', (endpoint,)).fetchone())
        bindings = [tuple(r) for r in conn.execute('SELECT * FROM execution_bindings')]
        conn.execute(sql)
        after = dict(conn.execute('SELECT * FROM agent_endpoints WHERE endpoint_id=?', (endpoint,)).fetchone())
        assert after == {**before, 'enabled': 0, 'revision': before['revision'] + 1}
        assert [tuple(r) for r in conn.execute('SELECT * FROM execution_bindings')] == bindings
        conn.execute(sql)
        assert conn.execute('SELECT revision FROM agent_endpoints WHERE endpoint_id=?', (endpoint,)).fetchone()[0] == after['revision']
