"""Canonical endpoint disable preserves durable namespace occupancy.

Finish installation proof is synthetic; no harness process/provider is started.
Old timestamp rows below are explicitly SQL fixture facts, not a cleanup run.
"""
# Pytest injected fixture arguments intentionally share re-export names.
# ruff: noqa: F811
from test_public_connection_ids import public_request, local_setup  # noqa: F401
from test_connection_setup import count, finish
from okto_nexus.application.connection_public_ids import list_public_ids, reserve_public_id
from okto_nexus.application.execution_local_realizations import directory_identity


def authority_rows(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        # Authenticated HTTP legitimately touches operator last_seen_at. It is
        # liveness telemetry, not identity creation or execution authority.
        return {table: [{key: value for key, value in dict(row).items()
                        if not (table == 'agents' and key == 'last_seen_at')}
                       for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
            for table in ('agents', 'execution_bindings', 'runtime_execution_grants', 'connection_setup_commits',
                          'execution_operations', 'execution_sessions', 'agent_endpoints', 'connection_public_ids')}


def test_disabled_canonical_endpoint_keeps_bound_public_id_occupied_without_reactivation(local_setup):
    deps, _, client, headers, *_ = local_setup
    context, request = public_request(local_setup)
    reserve_public_id(deps, context, request, approved=True)
    result = finish(local_setup, context, request, verified={
        'root': directory_identity(request['configuration']['workspace_root']), 'home': None})
    binding = result['binding']
    endpoint_id, workspace_id = binding['endpoint_id'], binding['workspace_id']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        revision = uow.connection.execute('SELECT revision FROM agent_endpoints WHERE endpoint_id=?',
                                          (endpoint_id,)).fetchone()[0]
        grants_before = [dict(row) for row in uow.connection.execute('SELECT * FROM runtime_execution_grants')]
    assert grants_before and any(row['revoked_at'] is None for row in grants_before)
    disabled = client.patch('/api/v1/harness/endpoints/' + endpoint_id, headers=headers['operator'],
                            json=dict(expected_revision=revision, enabled=False))
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()['data']['enabled'] is False
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after_grants = [dict(row) for row in uow.connection.execute('SELECT * FROM runtime_execution_grants')]
    assert len(after_grants) == len(grants_before) and all(row['revoked_at'] for row in after_grants)
    before_retry = authority_rows(local_setup)
    public = list_public_ids(deps, context, workspace_id=workspace_id)['items']
    assert len(public) == 1 and public[0]['connect_id'] == 'reviewer'
    assert public[0]['state'] == 'bound' and public[0]['canonical_ref'] == result['public_connection']['canonical_ref']
    _, replacement = public_request(local_setup, workspace_id=workspace_id)
    path = '/api/v1/runtime-management/connections/public-ids/reserve'
    refused = client.post(path, headers=headers['operator'], json=dict(approved=True, request=replacement))
    assert refused.status_code == 409, refused.text
    assert refused.json()['error']['code'] == 'HARNESS_ID_ALREADY_EXISTS'
    assert authority_rows(local_setup) == before_retry
    assert count(local_setup, 'connection_public_ids') == count(local_setup, 'execution_bindings') == 1


def test_old_uncertain_reservation_timestamps_do_not_make_new_intent_available(local_setup):
    deps = local_setup[0]
    context, request = public_request(local_setup)
    reserved = reserve_public_id(deps, context, request, approved=True)
    # Deliberate fixture aging, not a canonical expiry mutation or execution of a cleanup job.
    with deps.connection_factory.unit_of_work() as uow:
        for table in ('connection_public_ids', 'connection_project_drafts'):
            uow.connection.execute('UPDATE ' + table + ' SET created_at=?,updated_at=?',
                                   ('1900-01-01T00:00:00Z', '1900-01-01T00:00:00Z'))
    before = authority_rows(local_setup)
    _, other = public_request(local_setup)
    client, headers = local_setup[2:4]
    refused = client.post('/api/v1/runtime-management/connections/public-ids/reserve',
        headers=headers['operator'], json=dict(approved=True, request=other))
    assert refused.status_code == 409, refused.text
    assert refused.json()['error']['code'] == 'CONNECT_ID_PENDING'
    assert authority_rows(local_setup) == before
    recovered = reserve_public_id(deps, context, request, approved=True)
    assert recovered == reserved and recovered['state'] == 'reserved'
    assert count(local_setup, 'connection_public_ids') == count(local_setup, 'connection_project_drafts') == 1
    for table in ('execution_bindings', 'workspaces', 'runtime_execution_grants', 'connection_setup_commits'):
        assert count(local_setup, table) == 0
