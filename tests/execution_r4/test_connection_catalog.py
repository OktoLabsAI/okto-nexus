"""Operator catalog is read-only; canonical setup revalidation stays separate."""
from contextlib import contextmanager
import base64
import json
import sqlite3
from types import SimpleNamespace

import pytest

import test_terminal_connect
from okto_nexus.bootstrap.connection_catalog import build_connection_catalog
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

terminal = test_terminal_connect.terminal
checking = test_terminal_connect.checking
local_setup = test_terminal_connect.local_setup
ROUTE = '/api/v1/runtime-management/connections/catalog'


@pytest.fixture
def catalog(terminal, local_setup):
    t = terminal
    first = t.flow.review(t.selection)
    a = t.flow.apply(first, approval=first['review_revision'])
    second = t.flow.review(dict(t.selection, agent='catalog-second', create_agent=True, workspace_id=a['workspace_id']))
    b = t.flow.apply(second, approval=second['review_revision'])
    t.catalog_client = local_setup[2]
    t.catalog_headers = local_setup[3]
    t.catalog_a, t.catalog_b = a, b
    return t


def test_http_catalog_authorization_projection_filters_and_no_sensitive_fields(catalog):
    t = catalog
    response = t.catalog_client.get(ROUTE, headers={'X-Nexus-UI': '1'})
    assert response.status_code == 200, response.text
    value = response.json()
    assert 'data' not in value and value['total'] == len(value['items']) == 2
    assert response.headers['cache-control'] == 'no-store'
    assert value['requires_canonical_revalidation'] and value['cursor_integrity'] == 'unsigned_scope_checked'
    for row in value['items']:
        assert row['needs_revalidation']
        assert row['server_id'] == value['server_id']
        assert not set(row) & {'provider_home', 'workspace_root', 'secret_bindings', 'configuration', 'keys', 'grants'}
    assert t.selection['project'] not in response.text
    filtered = t.catalog_client.get(ROUTE, params={'agent_id': 'catalog-second'}, headers={'X-Nexus-UI': '1'})
    assert filtered.status_code == 200 and filtered.json()['total'] == 1
    denied = t.catalog_client.get(ROUTE, headers=t.catalog_headers['subject'])
    assert denied.status_code == 403 and 'items' not in denied.json()
    assert denied.headers['cache-control'] == 'no-store'
    projects = t.catalog_client.get('/api/v1/runtime-management/connections/workspaces', headers={'X-Nexus-UI': '1'})
    assert projects.status_code == 200 and projects.headers['cache-control'] == 'no-store'
    assert t.catalog_a['workspace_id'] in {item['workspace_id'] for item in projects.json()['items']}
    assert all(set(item) == {'workspace_id', 'display_name'} for item in projects.json()['items'])


def test_catalog_public_labels_never_serialize_arbitrary_metadata(catalog):
    t = catalog
    t.call('PATCH', '/api/v1/agents/catalog-second', {'metadata': {'display_name': {'private': 'not-a-public-label'}}})
    value = t.catalog_client.get(ROUTE, headers={'X-Nexus-UI': '1'}).json()
    row = next(item for item in value['items'] if item['agent_id'] == 'catalog-second')
    assert row['agent_label'] == 'catalog-second'
    assert 'not-a-public-label' not in json.dumps(value)


def test_cursor_scope_limit_revision_and_unknown_parameters(catalog):
    t = catalog
    client, headers = t.catalog_client, {'X-Nexus-UI': '1'}
    first = client.get(ROUTE, params={'limit': 1}, headers=headers).json()
    assert first['has_more'] and first['next_cursor']
    second = client.get(ROUTE, params={'limit': 1, 'cursor': first['next_cursor']}, headers=headers)
    assert second.status_code == 200 and not second.json()['has_more']
    assert first['items'][0]['binding_id'] != second.json()['items'][0]['binding_id']
    for changes in ({'workspace_id': 'other'}, {'limit': 2}, {'cursor': 'bad'}, {'unknown': 'yes'}):
        response = client.get(ROUTE, params={'limit': 1, 'cursor': first['next_cursor']} | changes, headers=headers)
        assert response.status_code in (400, 422) and 'items' not in response.json()
    repeated = client.get(ROUTE + '?limit=1&limit=2', headers=headers)
    assert repeated.status_code in (400, 422)
    changed = t.call('PATCH', '/api/v1/agents/catalog-second', {'metadata': {'display_name': 'Changed public label'}})
    assert changed['data']['metadata']['display_name'] == 'Changed public label'
    stale = client.get(ROUTE, params={'limit': 1, 'cursor': first['next_cursor']}, headers=headers)
    assert stale.status_code == 409 and stale.json()['error']['details']['reason'] == 'CATALOG_CHANGED'


def test_catalog_one_read_uow_write_barrier_and_human_cursor_fence(catalog):
    t = catalog
    service = build_connection_catalog(t.deps)
    calls, statements = [], []
    factory = service.factory
    class TracedFactory:
        @contextmanager
        def unit_of_work(self, **kwargs):
            calls.append(kwargs)
            with factory.unit_of_work(**kwargs) as uow:
                uow.connection.set_trace_callback(statements.append)
                forbidden = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                    sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE}
                uow.connection.set_authorizer(lambda action, *rest: sqlite3.SQLITE_DENY if action in forbidden else sqlite3.SQLITE_OK)
                try:
                    yield uow
                finally:
                    uow.connection.set_authorizer(None)
                    uow.connection.set_trace_callback(None)
    service.factory = TracedFactory()
    context = RuntimeRequestContext(None, 'operator_session', trusted_local_operator=True)
    first = service.read(context=context, principal='human-a', limit=1)
    assert calls == [{'write': False}]
    assert len([sql for sql in statements if sql.lstrip().upper().startswith('SELECT')]) == 3
    cursor = first['next_cursor']
    decoded = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
    assert 'human-a' not in str(decoded) and 'credential' not in str(decoded)
    with pytest.raises(OktoNexusError):
        service.read(context=context, principal='human-b', limit=1, cursor=cursor)
    with pytest.raises(OktoNexusError):
        service.read(context=context, principal=None, limit=1)


def test_cli_existing_canonical_without_profile_creates_only_shortcut(catalog, tmp_path, monkeypatch):
    from okto_nexus.adapters.inbound.cli import connect
    from okto_nexus.adapters.outbound.service_manager.context import read_json
    t = catalog
    home = tmp_path / 'new-operator-shortcuts'
    tables = ('agents', 'workspaces', 'execution_bindings', 'runtime_execution_grants', 'execution_operations')
    def counts():
        with t.deps.connection_factory.unit_of_work(write=False) as uow:
            return {name: uow.connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in tables}
    before, tests = counts(), tuple(t.turns)
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=1),
        inspect=lambda: dict(state='ready', instance_id='fixture-instance'),
        ensure_running=lambda **kwargs: pytest.fail('plan cannot start service'))
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts = []
    def choose(prompt):
        prompts.append(prompt)
        return '1'
    monkeypatch.setattr('builtins.input', choose)
    t.calls.clear()
    assert connect.run_connect(['--home', str(home), '--project', t.selection['project'], '--plan', '--no-chat']) == 0
    profile_path, = (home / 'terminal/profiles').glob('*.json')
    profile = read_json(profile_path)
    assert profile['format'] == 1 and profile['state'] == 'done'
    assert profile['selection']['create_agent'] is False and 'request' not in profile
    assert profile['result']['binding']['binding_id'] in {t.catalog_a['binding_id'], t.catalog_b['binding_id']}
    assert len(prompts) == 1 and prompts[0] == 'Connection: '
    assert counts() == before and tuple(t.turns) == tests
    assert t.calls and all(method == 'GET' for method, _ in t.calls)
    assert not (home / 'terminal/connection-intents').exists()
    stored = profile_path.read_bytes()
    assert connect.run_connect(['--home', str(home), '--profile', profile_path.stem, '--plan', '--json']) == 0
    assert profile_path.read_bytes() == stored and counts() == before and tuple(t.turns) == tests
