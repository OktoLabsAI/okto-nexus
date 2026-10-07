"""Attach retirement removes entry points while keeping historical records."""
from pathlib import Path

import okto_nexus
from test_local_realization import local_setup
from test_connection_setup import request_for, finish
from okto_nexus.application.execution_local_realizations import directory_identity


def test_attach_removed_from_dashboard_and_catalog(local_setup):
    from okto_nexus.adapters.outbound.execution.core_inventory import local_catalog
    assert 'claude_attach' not in {r['adapter_id'] for r in local_catalog()['runtimes']}
    _, _, client, headers, *_ = local_setup
    base = '/api/v1/runtime-management/connections/subject/claude-attach/'
    assert client.get(base + 'targets', headers=headers['operator']).status_code == 404
    for action in ('probe', 'test'):
        assert client.post(base + action, headers=headers['operator'], json={}).status_code == 404


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
