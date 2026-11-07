"""Existing machine authority remains unchanged until reviewed canonical Finish."""
from copy import deepcopy

import pytest

import test_pr34_remediation as tcp
from test_remote_setup_server import request as draft_request
from test_remote_setup_http import headers, post, setup, materialize, prepare, apply_request, policies


runtime = tcp.runtime


def old_machine(runtime, tmp_path):
    _, review, _, bootstrap, candidate = setup(runtime, tmp_path)
    request, key = materialize(runtime, review, bootstrap, candidate)
    proposal, approval = prepare(runtime, request, key)
    decision = runtime[1].post('/api/v1/approvals/' + approval + '/decision',
        headers=headers(runtime[4]), json={'decision': 'approve'})
    assert decision.status_code == 200, decision.text
    result = runtime[1].post('/v1/connections/bindings:apply', headers=headers(key),
        json=apply_request(review, proposal, approval))
    assert result.status_code == 200, result.text
    agent = bootstrap['bootstrap']['agent_id']
    current = runtime[1].get('/api/v1/agents/' + agent + '/execution-policy', headers=headers(runtime[4]))
    assert current.status_code == 200, current.text
    changed = runtime[1].put('/api/v1/agents/' + agent + '/execution-policy', headers=headers(runtime[4]),
        json=dict(expected_revision=current.json()['data']['revision'], execution_location='local',
            local_adapter_id='codex_app_server'))
    assert changed.status_code == 200, changed.text
    return agent, key, proposal, candidate


def next_request(agent, candidate_ref):
    value = draft_request(root='remote-next', agent=agent)
    value['identity']['mode'] = 'select'
    value['draft']['connector_id'] = 'second-connector'
    value['draft']['installation']['candidate_ref'] = candidate_ref
    return value


def test_existing_old_grant_is_only_revoked_by_explicitly_reviewed_finish(runtime, tmp_path):
    agent, key, old, candidate = old_machine(runtime, tmp_path)
    before = policies(runtime, agent)
    body = next_request(agent, old['candidate_ref'])
    review = post(runtime, 'review', body).json()['review']
    machines = review['selection']['previous_machines']
    assert len(machines) == 1 and machines[0]['binding_id'] == old['binding_id']
    assert review['effects']['revoke_previous_machine_authority'] is True
    assert review['effects']['previous_machines'] == machines
    assert 'label' not in machines[0]
    ref = dict(setup_run_id='remote-next', review_revision=review['review_revision'])
    bootstrap = post(runtime, 'bootstrap', ref).json()
    assert bootstrap['material'] is None and bootstrap['material_status'] == 'reuse_existing'
    assert policies(runtime, agent) == before
    # Only a test helper receives the already-owned key; no Server response or
    # checkpoint ever returns selected-identity credential material.
    host = deepcopy(bootstrap)
    host['material'] = {'api_key': key}
    request, _ = materialize(runtime, review, host, candidate)
    proposal, approval = prepare(runtime, request, key)
    compared = post(runtime, 'materialization', ref).json()
    assert compared['state'] == 'review_matches', compared
    assert compared['canonical_fields']['previous_machines'] == machines
    assert policies(runtime, agent) == before
    assert runtime[1].post('/api/v1/approvals/' + approval + '/decision',
        headers=headers(runtime[4]), json={'decision': 'approve'}).status_code == 200
    assert policies(runtime, agent) == before
    applied = runtime[1].post('/v1/connections/bindings:apply', headers=headers(key),
        json=apply_request(review, proposal, approval))
    assert applied.status_code == 200, applied.text
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        old_endpoint = uow.connection.execute('SELECT enabled,activation_state FROM agent_endpoints WHERE endpoint_id=?',
            (old['endpoint_id'],)).fetchone()
        assert tuple(old_endpoint) == (0, 'revoked')
        assert uow.connection.execute('SELECT revoked_at FROM runtime_execution_grants WHERE endpoint_id=?',
            (old['endpoint_id'],)).fetchone()[0] is not None
    assert post(runtime, 'recover', ref).json()['state'] == 'committed'


@pytest.mark.parametrize('stage', ['bootstrap', 'comparison'])
def test_prior_machine_drift_never_borrows_operator_confirmation(runtime, tmp_path, stage):
    agent, key, old, candidate = old_machine(runtime, tmp_path)
    body = next_request(agent, old['candidate_ref'])
    review = post(runtime, 'review', body).json()['review']
    ref = dict(setup_run_id='remote-next', review_revision=review['review_revision'])
    if stage == 'comparison':
        bootstrap = post(runtime, 'bootstrap', ref).json()
    # A concurrent canonical revision differs even if display/config are equal.
    with runtime[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_bindings SET binding_revision=binding_revision+1 WHERE binding_id=?', (old['binding_id'],))
    before = policies(runtime, agent)
    if stage == 'bootstrap':
        post(runtime, 'bootstrap', ref, status=409)
    else:
        host = deepcopy(bootstrap)
        host['material'] = {'api_key': key}
        request, _ = materialize(runtime, review, host, candidate)
        prepare(runtime, request, key)
        compared = post(runtime, 'materialization', ref).json()
        assert compared['state'] == 'requires_review'
        assert 'previous_machines' in compared['changed_fields']
    assert policies(runtime, agent) == before
