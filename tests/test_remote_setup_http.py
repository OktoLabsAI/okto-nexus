"""Real TCP Connections bootstrap and canonical Finish; inventory is synthetic."""
from copy import deepcopy
import json

import pytest
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.discovery import fingerprint

import test_pr34_remediation as tcp
from test_remote_setup_server import request as draft_request
from okto_nexus.adapters.outbound.execution.core_inventory import local_inventory_snapshot
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.project_preset import ORIGIN


runtime = tcp.runtime
BASE = '/v1/connections/remote-setup:'


def headers(key):
    return {'Authorization': 'Bearer ' + key}


def post(env, action, body, *, key=None, status=200):
    response = env[1].post(BASE + action, json=body, headers=headers(key or env[4]))
    assert response.status_code == status, response.text
    return response


def setup(runtime, tmp_path):
    deps = runtime[0]
    binary = tmp_path / 'synthetic-codex.exe'
    binary.write_bytes(b'Synthetic inventory only; never execute')
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        installation = dict(uow.connection.execute('SELECT * FROM execution_installation').fetchone())
    snapshot = local_inventory_snapshot([candidate], server_id=installation['server_id'],
        executor_id=installation['embedded_executor_id'], producer_instance_id='synthetic', publication_sequence=1)
    body = draft_request()
    body['draft']['installation']['candidate_ref'] = snapshot['evidence'][0]['candidate_ref']
    review = post(runtime, 'review', body).json()['review']
    ref = dict(setup_run_id=review['draft']['setup_run_id'], review_revision=review['review_revision'])
    bootstrap = post(runtime, 'bootstrap', ref).json()
    return body, review, ref, bootstrap, candidate


def materialize(runtime, review, bootstrap, candidate):
    deps, client = runtime[:2]
    key = bootstrap['material']['api_key']
    children, boot = review['child_requests'], bootstrap['bootstrap']
    registered = client.post('/v1/connections/executors:register', headers=headers(key), json=dict(
        client_intent_id=children['register'], connector_id=review['draft']['connector_id'],
        label='Synthetic remote host', control_capabilities=[]))
    assert registered.status_code in (200, 201), registered.text
    registration = registered.json()
    executor = registration['executor_id']
    ticket = headers(registration['bootstrap_ticket']['ticket'])
    snapshot = local_inventory_snapshot([candidate], server_id=boot['server_id'], executor_id=executor,
        producer_instance_id='synthetic', publication_sequence=1)
    response = client.put('/v1/runtime/executors/' + executor + '/inventory', json=snapshot, headers=ticket)
    assert response.status_code == 200, response.text
    realization = client.post('/v1/runtime/executors/' + executor + '/realizations', headers=ticket, json=dict(
        client_intent_id=children['realize'], agent_id=boot['agent_id'], local_realization_ref='root_1234567890123456',
        realization_revision=1, workspace_id=boot['workspace_id'], workspace_label='Project',
        adapter_id='codex_app_server', candidate_ref=review['draft']['installation']['candidate_ref'],
        inventory_revision=snapshot['inventory_revision'], local_root_proof_digest='sha256:' + 'b' * 64,
        configuration_digest='sha256:' + 'c' * 64, local_consent_id=review['draft']['local_consent']['local_consent_id']))
    assert realization.status_code in (200, 201), realization.text
    prepare = dict(client_intent_id=children['prepare'], agent_id_hint=boot['agent_id'],
        executor_id=executor, adapter_id='codex_app_server', candidate_ref=review['draft']['installation']['candidate_ref'],
        inventory_revision=snapshot['inventory_revision'], realization_ref=realization.json()['realization_ref'],
        workspace_id=boot['workspace_id'], alias=review['draft']['configuration']['alias'],
        connection_configuration=review['draft']['configuration'], project_preset=dict(ORIGIN),
        remote_setup=dict(setup_run_id=boot['setup_run_id'], review_revision=review['review_revision']))
    return prepare, key


def policies(runtime, agent):
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        return {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)]
            for table in ('agent_execution_policies', 'agent_runtime_overrides', 'runtime_execution_grants',
                'agent_endpoints', 'execution_bindings', 'runtime_profiles', 'connection_setup_commits')}


def prepare(runtime, request, key):
    response = runtime[1].post('/v1/connections/bindings:prepare', headers=headers(key), json=request)
    assert response.status_code == 200, response.text
    proposal = response.json()
    approval = next(value for value in proposal['required_approvals'] if value.startswith('apr_'))
    return proposal, approval


def apply_request(review, proposal, approval):
    return dict(client_intent_id=review['child_requests']['apply'], proposal_id=proposal['proposal_id'],
        proposal_revision=proposal['proposal_revision'], approved_diff_hash=proposal['diff']['approved_diff_hash'],
        operator_proof_ref=approval)


def test_tcp_new_identity_metadata_pending_matches_and_one_canonical_finish(runtime, tmp_path):
    body, review, ref, bootstrap, candidate = setup(runtime, tmp_path)
    before = policies(runtime, bootstrap['bootstrap']['agent_id'])
    request, key = materialize(runtime, review, bootstrap, candidate)
    assert policies(runtime, bootstrap['bootstrap']['agent_id']) == before
    me = runtime[1].get('/v1/connections/me', headers=headers(key))
    assert me.json()['capabilities']['remote_setup'] == {'revision': 1, 'draft_version': 1, 'handoff_version': 1}
    # Own metadata is readable; possession of this root never authorizes bootstrap or review.
    host = post(runtime, 'recover', {'setup_run_id': ref['setup_run_id']}, key=key).json()
    assert host['handoff'] == bootstrap['handoff'] and host['material'] is None
    post(runtime, 'bootstrap', ref, key=key, status=403)
    post(runtime, 'review', body, key=key, status=403)
    proposal, approval = prepare(runtime, request, key)
    compared = post(runtime, 'materialization', ref).json()
    assert compared['state'] == 'review_matches', compared
    assert compared['proposal'] == proposal and compared['approval_id'] == approval
    assert compared['canonical_fields']['remote_setup'] == ref
    assert 'operator_guard_digest' not in json.dumps(compared)
    assert 'credential_binding' not in json.dumps(compared)
    assert policies(runtime, bootstrap['bootstrap']['agent_id']) == before
    apply = apply_request(review, proposal, approval)
    denied = runtime[1].post('/v1/connections/bindings:apply', headers=headers(key), json=apply)
    assert denied.status_code == 403
    decision = runtime[1].post('/api/v1/approvals/' + approval + '/decision', headers=headers(runtime[4]), json={'decision': 'approve'})
    assert decision.status_code == 200, decision.text
    assert policies(runtime, bootstrap['bootstrap']['agent_id']) == before
    applied = runtime[1].post('/v1/connections/bindings:apply', headers=headers(key), json=apply)
    assert applied.status_code == 200, applied.text
    recovered = post(runtime, 'recover', ref).json()
    assert recovered['state'] == 'committed'
    assert recovered['final_binding']['proposal_id'] == proposal['proposal_id']
    assert recovered['final_binding']['finish_id'] == proposal['proposal_id'] + '_setup'
    assert recovered['bootstrap'] == bootstrap['bootstrap'] and recovered['material'] is None
    body['expected_review_revision'] = ref['review_revision']
    body['draft']['configuration']['alias'] = 'Another'
    post(runtime, 'review', body, status=409)


@pytest.mark.parametrize('decided', [False, True])
def test_tcp_new_review_fences_old_child_without_erasing_partial_receipts(runtime, tmp_path, decided):
    body, review, ref, bootstrap, candidate = setup(runtime, tmp_path)
    request, key = materialize(runtime, review, bootstrap, candidate)
    proposal, approval = prepare(runtime, request, key)
    if decided:
        assert runtime[1].post('/api/v1/approvals/' + approval + '/decision',
            headers=headers(runtime[4]), json={'decision': 'approve'}).status_code == 200
    before = policies(runtime, bootstrap['bootstrap']['agent_id'])
    # A permission/policy review may change while realization's body stays exact.
    body['expected_review_revision'] = ref['review_revision']
    body['draft']['start_at_login'] = True
    updated = post(runtime, 'review', body).json()['review']
    assert updated['child_requests']['realize'] == review['child_requests']['realize']
    assert updated['child_requests']['prepare'] != review['child_requests']['prepare']
    current = post(runtime, 'recover', {'setup_run_id': ref['setup_run_id']}, key=key).json()
    assert current['bootstrap'] == bootstrap['bootstrap']
    assert current['handoff']['review_revision'] == updated['review_revision']
    if decided:
        response = runtime[1].post('/v1/connections/bindings:apply', headers=headers(key),
            json=apply_request(review, proposal, approval))
    else:
        response = runtime[1].post('/api/v1/approvals/' + approval + '/decision',
            headers=headers(runtime[4]), json={'decision': 'approve'})
    assert response.status_code == 409, response.text
    assert policies(runtime, bootstrap['bootstrap']['agent_id']) == before
    changed = deepcopy(request)
    changed['client_intent_id'] = updated['child_requests']['prepare']
    changed['remote_setup']['review_revision'] = updated['review_revision']
    new_proposal, _ = prepare(runtime, changed, key)
    assert new_proposal['proposal_id'] != proposal['proposal_id']
    current_ref = dict(ref, review_revision=updated['review_revision'])
    assert post(runtime, 'materialization', current_ref).json()['state'] == 'review_matches'


def test_tcp_recovery_is_passive_and_revocation_bypasses_warm_cache(runtime, tmp_path):
    _, _, ref, bootstrap, _ = setup(runtime, tmp_path)
    key = bootstrap['material']['api_key']
    for credential in (runtime[4], key):
        assert runtime[1].get('/v1/connections/me', headers=headers(credential)).status_code == 200
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        before = [tuple(row) for row in uow.connection.execute('SELECT * FROM agents ORDER BY agent_id')]
    for credential in (runtime[4], key):
        for _ in range(2):
            response = post(runtime, 'recover', ref, key=credential)
            assert response.headers['cache-control'] == 'no-store'
            assert response.json()['material'] is None
    with runtime[0].connection_factory.unit_of_work() as uow:
        assert [tuple(row) for row in uow.connection.execute('SELECT * FROM agents ORDER BY agent_id')] == before
        AgentKeyAuthService(runtime[0].repos.agents, runtime[0].clock).issue_key(uow,
            agent_id=bootstrap['bootstrap']['agent_id'])
    post(runtime, 'recover', ref, key=key, status=401)


@pytest.mark.parametrize('malformed', ['duplicate', 'oversize', 'unknown'])
def test_tcp_strict_boundary_never_echoes_untrusted_payload(runtime, malformed):
    value = draft_request()
    if malformed == 'unknown':
        value['private'] = 'do-not-echo'
    raw = json.dumps(value)
    if malformed == 'duplicate':
        raw = raw[:-1] + ',"identity":"do-not-echo"}'
    if malformed == 'oversize':
        raw += ' ' * 65536
    response = runtime[1].post(BASE + 'review', headers=headers(runtime[4]), content=raw)
    assert response.status_code == 422, response.text
    assert 'do-not-echo' not in response.text
