"""A rotated canonical identity never reuses an old bootstrap's authority fence."""
import pytest

import test_pr34_remediation as tcp
from test_remote_setup_http import headers, post, setup, materialize, prepare, apply_request, policies
from okto_nexus.application.auth import AgentKeyAuthService


runtime = tcp.runtime


@pytest.mark.parametrize('stage', ['prepare', 'manual_decision', 'manual_apply'])
def test_rotated_subject_key_cannot_promote_old_root(runtime, tmp_path, stage):
    _, review, ref, bootstrap, candidate = setup(runtime, tmp_path)
    request, key = materialize(runtime, review, bootstrap, candidate)
    proposal = approval = None
    if stage != 'prepare':
        proposal, approval = prepare(runtime, request, key)
    if stage == 'manual_apply':
        decision = runtime[1].post('/api/v1/approvals/' + approval + '/decision',
            headers=headers(runtime[4]), json={'decision': 'approve'})
        assert decision.status_code == 200, decision.text
    with runtime[0].connection_factory.unit_of_work() as uow:
        new_key = AgentKeyAuthService(runtime[0].repos.agents, runtime[0].clock).issue_key(uow,
            agent_id=bootstrap['bootstrap']['agent_id'])
    before = policies(runtime, bootstrap['bootstrap']['agent_id'])
    if stage == 'prepare':
        response = runtime[1].post('/v1/connections/bindings:prepare', json=request, headers=headers(new_key))
    elif stage == 'manual_decision':
        response = runtime[1].post('/api/v1/approvals/' + approval + '/decision',
            headers=headers(runtime[4]), json={'decision': 'approve'})
    else:
        response = runtime[1].post('/v1/connections/bindings:apply',
            json=apply_request(review, proposal, approval), headers=headers(new_key))
    assert response.status_code == 409, response.text
    assert policies(runtime, bootstrap['bootstrap']['agent_id']) == before
    recovered = post(runtime, 'recover', ref, key=new_key).json()
    assert recovered['current_references'] == 'changed'
    assert recovered['bootstrap'] == bootstrap['bootstrap'] and recovered['material'] is None
    post(runtime, 'recover', ref, key=key, status=401)
