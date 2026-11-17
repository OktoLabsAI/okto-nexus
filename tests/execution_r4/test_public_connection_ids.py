"""QC namespace/Finish contracts using owned SQLite and inert discovery only."""
# ruff: noqa: F811
from copy import deepcopy
import uuid
import json

import pytest

from test_connection_setup import count, finish, local_setup, request_for  # noqa: F401
from okto_nexus.application.connection_project_context import read_project_context
from okto_nexus.application.connection_public_ids import list_public_ids, reserve_public_id
from okto_nexus.application.execution_local_realizations import directory_identity
from okto_nexus.domain.connection_public_ids import connect_id
from okto_nexus.errors import OktoNexusError


def public_request(setup, *, name='reviewer', intent=None, workspace_id=None):
    context, request = request_for(setup)
    request.update(client_intent_id=intent or 'public-' + uuid.uuid4().hex, workspace_id=workspace_id)
    proof = read_project_context(setup[0], context, executor_id=request['executor_id'],
                                 project_root=request['configuration']['workspace_root'], workspace_id=workspace_id)
    request['public_connection'] = dict(version=1, connect_id=name,
        reservation_ref='pcr_' + uuid.uuid4().hex, project_revision=proof['project_revision'])
    return context, request


def test_public_finish_atomic_receipt_and_lost_reply(local_setup):
    context, request = public_request(local_setup)
    reserved = reserve_public_id(local_setup[0], context, request, approved=True)
    assert reserved['state'] == 'reserved' and reserved['workspace_id'] is None
    assert count(local_setup, 'execution_bindings') == count(local_setup, 'runtime_execution_grants') == 0
    assert reserve_public_id(local_setup[0], context, request, approved=True) == reserved
    result = finish(local_setup, context, request, verified={
        'root': directory_identity(request['configuration']['workspace_root']), 'home': None})
    public = result['public_connection']
    assert public['state'] == 'bound' and public['connect_id'] == 'reviewer'
    assert public['canonical_ref']['workspace_id'] == result['binding']['workspace_id']
    assert finish(local_setup, context, request, verified=None) == result
    from okto_nexus.application.connection_setup import read_setup_commit
    assert read_setup_commit(local_setup[0], context, request['client_intent_id'],
                             expected_request=request)['result'] == result
    assert reserve_public_id(local_setup[0], context, request, approved=True)['state'] == 'bound'
    assert count(local_setup, 'connection_setup_commits') == count(local_setup, 'execution_bindings') == 1
    listed = list_public_ids(local_setup[0], context, workspace_id=public['canonical_ref']['workspace_id'])
    assert listed['total'] == 1 and listed['items'][0]['canonical_ref'] == public['canonical_ref']


def test_finish_failure_keeps_reservation_without_canonical_effects(local_setup):
    context, request = public_request(local_setup)
    reserve_public_id(local_setup[0], context, request, approved=True)
    with pytest.raises(OktoNexusError):
        finish(local_setup, context, request, verified=None)
    for table in ('execution_bindings', 'workspaces', 'runtime_execution_grants', 'connection_setup_commits'):
        assert count(local_setup, table) == 0
    assert count(local_setup, 'connection_public_ids') == count(local_setup, 'connection_project_drafts') == 1


def test_second_intent_cannot_split_same_new_project_root(local_setup):
    context, first = public_request(local_setup)
    reserve_public_id(local_setup[0], context, first, approved=True)
    _, second = public_request(local_setup, name='worker')
    with pytest.raises(OktoNexusError, match='already reserved'):
        reserve_public_id(local_setup[0], context, second, approved=True)
    assert count(local_setup, 'connection_public_ids') == count(local_setup, 'connection_project_drafts') == 1
    changed = deepcopy(first)
    changed['public_connection']['connect_id'] = 'other'
    with pytest.raises(OktoNexusError, match='different approved intent'):
        reserve_public_id(local_setup[0], context, changed, approved=True)


def test_http_project_namespace_capability_and_legacy_hash_omission(local_setup):
    context, request = request_for(local_setup)
    client, headers = local_setup[2:4]
    base = '/api/v1/runtime-management/connections'
    capability = client.get(base + '/public-ids', headers=headers['operator'])
    assert capability.status_code == 200, capability.text
    assert capability.json()['status'] == 'namespace_required'
    proof = client.get(base + '/project-context', params=dict(executor_id=request['executor_id'],
                       project_root=request['configuration']['workspace_root']), headers=headers['operator'])
    assert proof.status_code == 200, proof.text
    assert proof.json()['workspace_id'] is None and proof.json()['mapped_workspace_ids'] == []
    assert client.get(base + '/project-context', params=dict(executor_id=request['executor_id'],
                      project_root=request['configuration']['workspace_root']), headers=headers['subject']).status_code == 403
    # Explicit null and omission must normalize to the same legacy receipt hash.
    request['configuration']['execution_location'] = 'remote'
    request['configuration']['runtime_enabled'] = False
    result = client.post(base + '/setup:finish', json=request, headers=headers['operator'])
    assert result.status_code == 200, result.text
    replay = client.post(base + '/setup:finish', json=dict(request, public_connection=None), headers=headers['operator'])
    assert replay.status_code == 200 and replay.json() == result.json()


@pytest.mark.parametrize('value', ['', '1worker', 'a/b', 'a:b', 'éclair', 'a' * 65])
def test_public_id_grammar(value):
    with pytest.raises(OktoNexusError):
        connect_id(value)


def test_existing_projects_same_label_namespace_and_revision_cursors(local_setup):
    from okto_nexus.application.connection_workspaces import list_connection_workspaces
    deps = local_setup[0]
    context, _ = request_for(local_setup)
    with deps.connection_factory.unit_of_work() as uow:
        for workspace in ('project-a', 'project-b'):
            uow.connection.execute('INSERT INTO workspaces(workspace_id,display_name,created_at) VALUES(?,?,?)',
                                   (workspace, 'Same label', deps.clock.now_iso()))
    first_page = list_connection_workspaces(deps, context, limit=1)
    assert first_page['total'] == 2 and first_page['has_more']
    second_page = list_connection_workspaces(deps, context, limit=1, cursor=first_page['next_cursor'])
    assert second_page['items'][0]['workspace_id'] != first_page['items'][0]['workspace_id']
    assert second_page['revision'] == first_page['revision']
    for workspace in ('project-a', 'project-b'):
        context, request = public_request(local_setup, workspace_id=workspace)
        reserve_public_id(deps, context, request, approved=True)
    assert count(local_setup, 'connection_public_ids') == 2
    _, occupied = public_request(local_setup, workspace_id='project-a')
    with pytest.raises(OktoNexusError, match='already reserved'):
        reserve_public_id(deps, context, occupied, approved=True)
    _, extra = public_request(local_setup, workspace_id='project-a', name='second')
    reserve_public_id(deps, context, extra, approved=True)
    page = list_public_ids(deps, context, workspace_id='project-a', limit=1)
    assert page['total'] == 2 and page['has_more']
    assert list_public_ids(deps, context, workspace_id='project-a', limit=1,
                           cursor=page['next_cursor'])['items'][0]['connect_id'] != page['items'][0]['connect_id']
    with pytest.raises(OktoNexusError):
        list_public_ids(deps, context, workspace_id='project-b', limit=1, cursor=page['next_cursor'])
    _, third = public_request(local_setup, workspace_id='project-a', name='third')
    reserve_public_id(deps, context, third, approved=True)
    with pytest.raises(OktoNexusError, match='changed'):
        list_public_ids(deps, context, workspace_id='project-a', limit=1, cursor=page['next_cursor'])


def test_concurrent_same_id_and_same_new_root_are_serialized(local_setup):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    deps = local_setup[0]
    context, first = public_request(local_setup)
    _, second = public_request(local_setup, name='different')
    barrier = Barrier(2)

    def attempt(request):
        barrier.wait(timeout=5)
        try:
            return reserve_public_id(deps, context, request, approved=True)['state']
        except OktoNexusError:
            return 'conflict'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (first, second)))
    assert sorted(results) == ['conflict', 'reserved']
    assert count(local_setup, 'connection_project_drafts') == count(local_setup, 'connection_public_ids') == 1


def test_legacy_association_metadata_only_and_projection(local_setup):
    from okto_nexus.application.connection_public_ids import associate_existing
    from okto_nexus.bootstrap.connection_catalog import build_connection_catalog
    context, request = request_for(local_setup)
    legacy = finish(local_setup, context, request, verified={
        'root': directory_identity(request['configuration']['workspace_root']), 'home': None})
    catalog = build_connection_catalog(local_setup[0])
    row = catalog.read(context=context)['items'][0]
    assert row['connect_id'] is None
    ref = {key: row[key] for key in ('server_id', 'executor_id', 'binding_id', 'endpoint_id',
                                    'agent_id', 'workspace_id', 'workspace_binding_id')}
    tables = ('execution_bindings', 'agents', 'runtime_execution_grants', 'connection_setup_commits',
              'execution_operations', 'execution_sessions')
    def rows():
        with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
            return {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                    for table in tables}
    before = rows()
    body = dict(approved=True, client_intent_id='adopt-existing', connect_id='legacy',
                expected_binding_ref=ref, expected_binding_revision=row['binding_revision'])
    result = associate_existing(local_setup[0], context, body)
    assert result == associate_existing(local_setup[0], context, body)
    assert result['canonical_ref']['binding_id'] == legacy['binding']['binding_id']
    assert rows() == before
    assert catalog.read(context=context)['items'][0]['connect_id'] == 'legacy'
    proof = read_project_context(local_setup[0], context, executor_id=request['executor_id'],
                                 project_root=request['configuration']['workspace_root'])
    assert proof['mapped_workspace_ids'] == [ref['workspace_id']]
    assert proof['mappings'][0]['workspace_root'] == str(local_setup[6].resolve())
    from okto_nexus.adapters.outbound.sqlite.home_entries import CONNECTIONS
    with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
        projected = uow.connection.execute(CONNECTIONS, dict(server_id=ref['server_id'], workspace_id=None)).fetchall()
        assert len(projected) == 1 and projected[0]['connect_id'] == 'legacy'
        plan = [row['detail'] for row in uow.connection.execute('EXPLAIN QUERY PLAN ' + CONNECTIONS,
                dict(server_id=ref['server_id'], workspace_id=None))]
        assert any('connection_public_id_binding' in detail for detail in plan), plan


def test_stale_directory_proof_and_foreign_executor_rejected_before_stat(local_setup, monkeypatch):
    from okto_nexus.application import connection_project_context as projects
    context, request = public_request(local_setup)
    original = projects.directory_identity
    current = original(request['configuration']['workspace_root'])
    monkeypatch.setattr(projects, 'directory_identity', lambda value: dict(current, inode='different-directory'))
    with pytest.raises(OktoNexusError, match='changed'):
        reserve_public_id(local_setup[0], context, request, approved=True)
    assert count(local_setup, 'connection_public_ids') == 0
    monkeypatch.setattr(projects, 'directory_identity', lambda value: pytest.fail('must reject foreign scope before stat'))
    with pytest.raises(OktoNexusError):
        read_project_context(local_setup[0], context, executor_id='another-server-executor',
                             project_root=request['configuration']['workspace_root'])


def test_two_servers_same_workspace_ids_do_not_share_namespace(local_setup, tmp_path):
    from test_embedded_inventory import app_for
    from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
    deps_a = local_setup[0]
    deps_b, _ = app_for(tmp_path / 'second-server')
    installation = ensure_execution_installation(deps_b.connection_factory)
    context, first = request_for(local_setup)
    for deps in (deps_a, deps_b):
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('INSERT INTO workspaces(workspace_id,display_name,created_at) VALUES(?,?,?)',
                                   ('same-workspace-id', 'Same name', deps.clock.now_iso()))
    context, request = public_request(local_setup, workspace_id='same-workspace-id')
    reserve_public_id(deps_a, context, request, approved=True)
    foreign = deepcopy(request)
    foreign['executor_id'] = installation.embedded_executor_id
    foreign['public_connection']['project_revision'] = read_project_context(deps_b, context,
        executor_id=foreign['executor_id'], project_root=first['configuration']['workspace_root'],
        workspace_id='same-workspace-id')['project_revision']
    reserve_public_id(deps_b, context, foreign, approved=True)
    a = list_public_ids(deps_a, context, workspace_id='same-workspace-id')
    b = list_public_ids(deps_b, context, workspace_id='same-workspace-id')
    assert a['total'] == b['total'] == 1 and a['server_id'] != b['server_id']
    assert a['items'][0]['connect_id'] == b['items'][0]['connect_id']


def test_finish_public_binding_failure_rolls_back_canonical_authority(local_setup, monkeypatch):
    from okto_nexus.application import connection_public_ids as ids
    context, request = public_request(local_setup)
    reserve_public_id(local_setup[0], context, request, approved=True)

    def reject(*args, **kwargs):
        assert count(local_setup, 'runtime_execution_grants') == 0  # other connection sees only committed state
        raise OktoNexusError('CONFLICT', 'Injected public association conflict.', {})

    monkeypatch.setattr(ids, 'bind_public_id', reject)
    with pytest.raises(OktoNexusError, match='association conflict'):
        finish(local_setup, context, request, verified={
            'root': directory_identity(request['configuration']['workspace_root']), 'home': None})
    for table in ('execution_bindings', 'workspaces', 'runtime_execution_grants', 'connection_setup_commits'):
        assert count(local_setup, table) == 0
    assert list_public_ids(local_setup[0], context)['status'] == 'namespace_required'


def test_http_reserve_validation_and_principal_cursor_fences(local_setup):
    from dataclasses import replace
    from okto_nexus.application.connection_workspaces import list_connection_workspaces
    deps, _, client, headers, *_ = local_setup
    context, request = public_request(local_setup)
    path = '/api/v1/runtime-management/connections/public-ids/reserve'
    assert client.post(path, json=dict(approved=True, request={}), headers=headers['operator']).status_code == 422
    assert client.post(path, json=dict(approved=False, request=request), headers=headers['operator']).status_code == 422
    assert client.post(path, json=dict(approved=True, request=request), headers=headers['subject']).status_code == 403
    assert count(local_setup, 'connection_public_ids') == 0
    reserved = client.post(path, json=dict(approved=True, request=request), headers=headers['operator'])
    assert reserved.status_code == 200, reserved.text
    assert client.post(path, json=dict(approved=True, request=request), headers=headers['operator']).json() == reserved.json()
    assert client.get(path.rsplit('/', 1)[0], params={'unknown': 'x'}, headers=headers['operator']).status_code == 422
    with deps.connection_factory.unit_of_work() as uow:
        for workspace in ('one', 'two'):
            uow.connection.execute('INSERT INTO workspaces(workspace_id,created_at) VALUES(?,?)',
                                   (workspace, deps.clock.now_iso()))
    page = list_connection_workspaces(deps, context, limit=1, principal='human-a')
    with pytest.raises(OktoNexusError):
        list_connection_workspaces(deps, context, limit=1, principal='human-b', cursor=page['next_cursor'])
    with pytest.raises(OktoNexusError, match='human identity'):
        list_public_ids(deps, replace(context, authentication_source='operator_session'), workspace_id='one')


def test_legacy_request_hash_matches_frozen_installed_pr27():
    """Golden captured from installed PR27, before this optional member existed."""
    import inspect
    from okto_nexus.adapters.inbound.http.runtime_v1 import ConnectionSetupRequest, build_router
    from okto_nexus.application.execution_local_realizations import _digest
    body = dict(client_intent_id='legacy-golden', agent_id='subject',
        baseline=dict(execution_revision=0, runtime_revision=0, defaults_revision=1,
                      binding_revision=None, endpoint_revision=None),
        configuration=dict(format='okto-nexus-connection', version=1, adapter_id='codex_app_server',
            execution_location='remote', runtime_enabled=False, session_policy='per_sender',
            workspace_root='C:/golden-project', workspace_label='Golden', provider_home=None,
            secret_bindings={}, alias='golden', harness_settings={}, automatic_reply=True,
            tool_access='always_allow', authorization=dict(minutes=60, actions=20)))
    endpoint = next(route.endpoint for route in build_router().routes if route.name == 'connection_setup_finish')
    normalize = inspect.getclosurevars(endpoint).nonlocals['setup_request']
    expected = 'sha256:b9624d2d24ae9ef11fdd8160d6faa67675c74fb392ea0d181d44d152d8af35b9'
    assert _digest(normalize(ConnectionSetupRequest.model_validate(body))) == expected
    assert _digest(normalize(ConnectionSetupRequest.model_validate(dict(body, public_connection=None)))) == expected


@pytest.mark.parametrize('malformed', ['not-json', '{}', '{"root":{"path":"relative","device":"1","inode":"2"}}',
                                    '{"root":{"path":"C:/project","device":null,"inode":"2"}}'])
def test_malformed_approved_local_mapping_is_incomplete_not_new_project(local_setup, malformed):
    context, request = request_for(local_setup)
    finish(local_setup, context, request, verified={
        'root': directory_identity(request['configuration']['workspace_root']), 'home': None})
    with local_setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_local_realizations SET local_record_json=?', (malformed,))
    with pytest.raises(OktoNexusError) as failure:
        read_project_context(local_setup[0], context, executor_id=request['executor_id'],
                             project_root=request['configuration']['workspace_root'])
    assert failure.value.details['reason'] == 'PROJECT_INVENTORY_INCOMPLETE'
    assert count(local_setup, 'connection_public_ids') == 0


def test_remote_logical_proof_never_reads_private_local_mapping(local_setup, monkeypatch):
    from okto_nexus.application import connection_project_context as projects
    context, request = request_for(local_setup)
    result = finish(local_setup, context, request, verified={
        'root': directory_identity(request['configuration']['workspace_root']), 'home': None})
    deps = local_setup[0]
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        installation = conn.execute('SELECT server_id FROM execution_installation').fetchone()[0]
        conn.execute('INSERT INTO execution_executors '
            '(server_id,executor_id,connector_id,registered_by_agent_id,kind,control_state,generation) '
            "VALUES(?,'remote-test','connector-test','operator','remote','DISCONNECTED',1)", (installation,))

        def clone(table, changes):
            value = dict(conn.execute('SELECT * FROM ' + table + ' LIMIT 1').fetchone())
            value.update(changes)
            conn.execute('INSERT INTO ' + table + '(' + ','.join(value) + ') VALUES('
                         + ','.join('?' for _ in value) + ')', tuple(value.values()))

        # Deliberately adversarial but FK-valid legacy metadata on a remote host.
        clone('execution_workspace_bindings', dict(executor_id='remote-test', workspace_binding_id='remote-wxb'))
        clone('execution_realizations', dict(executor_id='remote-test', workspace_binding_id='remote-wxb'))
        clone('execution_local_realizations', dict(executor_id='remote-test', local_record_json='not-json'))
    monkeypatch.setattr(projects, 'directory_identity', lambda _: pytest.fail('remote proof must never stat a Server directory'))
    proof = read_project_context(deps, context, executor_id='remote-test',
                                 workspace_id=result['binding']['workspace_id'])
    assert proof['project_root'] is None and proof['mappings'] == [] and proof['mapped_workspace_ids'] == []
    assert str(local_setup[6]) not in json.dumps(proof)


def test_http_bound_and_pending_collision_codes_are_distinct(local_setup):
    context, request = public_request(local_setup)
    reserve_public_id(local_setup[0], context, request, approved=True)
    client, headers = local_setup[2:4]
    path = '/api/v1/runtime-management/connections/public-ids/reserve'
    _, other = public_request(local_setup, name='another')
    pending = client.post(path, json=dict(approved=True, request=other), headers=headers['operator'])
    assert pending.status_code == 409 and pending.json()['error']['code'] == 'CONNECT_ID_PENDING'
    result = finish(local_setup, context, request, verified={
        'root': directory_identity(request['configuration']['workspace_root']), 'home': None})
    _, occupied = public_request(local_setup, workspace_id=result['binding']['workspace_id'])
    bound = client.post(path, json=dict(approved=True, request=occupied), headers=headers['operator'])
    assert bound.status_code == 409 and bound.json()['error']['code'] == 'HARNESS_ID_ALREADY_EXISTS'


def test_committed_legacy_intent_cannot_acquire_different_public_content(local_setup):
    context, legacy = request_for(local_setup)
    result = finish(local_setup, context, legacy, verified={
        'root': directory_identity(legacy['configuration']['workspace_root']), 'home': None})
    _, changed = public_request(local_setup, intent=legacy['client_intent_id'],
                                 workspace_id=result['binding']['workspace_id'])
    with pytest.raises(OktoNexusError, match='committed setup receipt'):
        reserve_public_id(local_setup[0], context, changed, approved=True)
    assert count(local_setup, 'connection_public_ids') == count(local_setup, 'connection_project_drafts') == 0
