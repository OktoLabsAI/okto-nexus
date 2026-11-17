"""Never turn an incomplete inventory into permission for duplicate setup."""
from urllib.parse import parse_qs, urlsplit

import pytest

from okto_nexus.adapters.inbound.cli import canonical_connections as module
from okto_nexus.adapters.inbound.cli.connection_choices import ConnectionChoiceCatalog, ConnectionChoice
from okto_nexus.application.terminal_connection import ConnectionError


def row(name):
    return dict(server_id='server', executor_id='executor', binding_id='binding-' + name,
        endpoint_id='endpoint-' + name, agent_id='agent-' + name, workspace_id='workspace',
        workspace_binding_id='workspace-binding-' + name, adapter_id='codex_app_server', execution_location='local')


def fixture_call(project, *, fault=None):
    rows, calls = [row('a'), row('b')], []
    def call(method, path):
        calls.append((method, path))
        assert method == 'GET'
        if '/connections/catalog?' in path:
            query = parse_qs(urlsplit(path).query)
            index = 1 if query.get('cursor') else 0
            value = dict(version=1, server_id='server', scope={'execution_location': 'local'},
                revision='a' * 64, total=2, total_is_exact=True, items=[dict(rows[index])],
                has_more=index == 0, next_cursor='page-2' if index == 0 else None)
            if fault is not None:
                fault(value, index)
            return value
        if '/connections/setup/' in path:
            return {'folders': {'workspace_root': str(project)}}
        if '/connections/bindings/' in path:
            return next(item for item in rows if item['binding_id'] == path.rsplit('/', 1)[-1]) | {'state': 'APPROVED'}
        pytest.fail(path)
    return call, calls


def test_all_pages_then_proven_tuple_candidates_and_legacy_dedup(tmp_path):
    call, calls = fixture_call(tmp_path)
    legacy = ConnectionChoice('legacy', 'agent-a', 'codex', 'binding-a', None,
        'done', False, False, False, False, False, False)
    catalog = module.merge_canonical_connections(call, local=ConnectionChoiceCatalog((legacy,), (), True),
        server_id='server', project=str(tmp_path))
    assert catalog.complete and len(catalog.choices) == 2
    assert catalog.choices[0] is legacy
    assert catalog.choices[1].canonical_ref['binding_id'] == 'binding-b'
    assert all('/connections/catalog?' in path for _, path in calls[:2])


@pytest.mark.parametrize('damage', ['version', 'revision', 'scope', 'total', 'duplicate', 'cursor', 'server', 'missing'])
def test_incomplete_changed_or_foreign_pages_never_become_empty_success(tmp_path, damage):
    def fault(value, index):
        if damage == 'version':
            value['version'] = True
        if damage == 'revision' and index:
            value['revision'] = 'b' * 64
        if damage == 'scope':
            value['scope'] = {}
        if damage == 'total' and index:
            value['total'] = 3
        if damage == 'duplicate' and index:
            value['items'] = [row('a')]
        if damage == 'cursor':
            value['next_cursor'] = None
        if damage == 'server':
            value['items'][0]['server_id'] = 'other-server'
        if damage == 'missing':
            value['items'] = []
    call, calls = fixture_call(tmp_path, fault=fault)
    catalog = module.merge_canonical_connections(call, local=ConnectionChoiceCatalog((), (), True),
        server_id='server', project=str(tmp_path))
    assert not catalog.complete and not catalog.choices
    assert not any('/connections/setup/' in path for _, path in calls)


def test_transport_failure_is_not_permission_for_a_new_identity(tmp_path):
    def call(*args):
        raise ConnectionError('SERVER_UNREACHABLE', 'Synthetic unavailable catalog')
    catalog = module.merge_canonical_connections(call, local=ConnectionChoiceCatalog((), (), True),
        server_id='server', project=str(tmp_path))
    assert not catalog.complete and catalog.issues[0].reason == 'canonical_catalog_unconfirmed'


def test_local_shortcut_full_tuple_drift_is_not_merged_by_agent_or_binding_name(tmp_path):
    call, _ = fixture_call(tmp_path)
    stored = row('a') | {'executor_id': 'old-executor'}
    local = ConnectionChoice('local', 'agent-a', 'codex', 'binding-a', 'workspace',
        'done', False, False, False, False, False, False, binding_ref=stored)
    catalog = module.merge_canonical_connections(call, local=ConnectionChoiceCatalog((local,), (), True),
        server_id='server', project=str(tmp_path))
    assert not catalog.complete and catalog.choices == (local,)
