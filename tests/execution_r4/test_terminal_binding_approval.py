"""Real approval/Connector persistence with separate human and participant clients."""
import asyncio
from dataclasses import asdict
import json
from types import SimpleNamespace as NS

import httpx
import pytest

from okto_nexus.adapters.inbound.cli.operator import run_operator
from okto_nexus.adapters.outbound import operator_client
from okto_nexus.adapters.outbound.operator_client import OperatorProfile
from okto_nexus.application.terminal_binding_approval import TerminalBindingApproval
from okto_nexus.application.terminal_connection import ConnectionError
import test_binding_operator as binding_fixtures
from test_binding_operator import prepare_delegated, connection_preferences, assert_no_binding
from test_remote_operator_terminal import MemoryVault, HTTPBridge, ACCOUNT, ORIGIN

onboarding = binding_fixtures.onboarding


@pytest.fixture
def operator(onboarding, monkeypatch, tmp_path):
    deps, client, headers, prepare = onboarding
    client.app.state.operator_auth.configure(**ACCOUNT, local=True)
    vault, bridge = MemoryVault(), HTTPBridge(client)
    monkeypatch.setattr(operator_client, 'open_backend', lambda: vault)
    monkeypatch.setattr(operator_client, 'build_opener', lambda *args: bridge)
    profile = OperatorProfile(tmp_path / 'operator-client', 'remote')
    profile.login(ORIGIN, **ACCOUNT)
    return NS(deps=deps, client=client, headers=headers, prepare=prepare, profile=profile,
        vault=vault, bridge=bridge, flow=TerminalBindingApproval(profile.client()))


def pending(operator):
    r = operator
    r.client.cookies.clear()
    r.prepare['connection_configuration'] = connection_preferences(r.prepare)
    return prepare_delegated(r.client, r.headers, r.prepare)


def command(r, approval_id, *options):
    return run_operator(['approval', approval_id, '--profile', r.profile.name,
        '--home', str(r.profile.home), '--json', *options])


def test_review_is_passive_and_lost_decision_recovers_same_receipt(operator, capsys):
    r = operator
    proposal, apply, approval_id = pending(r)
    assert command(r, approval_id) == 0
    review = json.loads(capsys.readouterr().out)
    assert review['proposal'] == proposal
    assert review['status'] == 'pending' and not review['expired']
    assert_no_binding(r.deps)
    options = ('--decision', 'approve', '--confirm', review['review_revision'])
    r.bridge.after = '/decision'
    assert command(r, approval_id, *options) == 3
    lost = json.loads(capsys.readouterr().out)
    assert lost['possible_effect'] and lost['approval_id'] == approval_id
    writes = sum(call.method == 'POST' and call.full_url.endswith('/decision') for call in r.bridge.calls)
    assert command(r, approval_id, *options) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['recovered'] and receipt['decided_by'] == 'operator'
    assert receipt['executed_result']['proposal_id'] == proposal['proposal_id']
    assert sum(call.method == 'POST' and call.full_url.endswith('/decision') for call in r.bridge.calls) == writes
    # Decision commits proof only. The original participant still applies it.
    assert_no_binding(r.deps)
    r.client.cookies.clear()
    applied = r.client.post('/v1/connections/bindings:apply', json=apply, headers=r.headers['subject'])
    assert applied.status_code == 200, applied.text
    with r.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_execution_grants').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM approvals').fetchone()[0] == 1
    token = next(iter(r.vault.values.values()))
    assert token not in json.dumps(review) + json.dumps(receipt)


@pytest.mark.parametrize('change', ['reject', 'expire', 'policy', 'concurrent_reject'])
def test_refusal_expiry_and_policy_change_do_not_authorize(operator, change):
    r = operator
    _, apply, approval_id = pending(r)
    review = r.flow.review(approval_id)
    if change == 'reject':
        result = r.flow.decide(approval_id, 'reject', review['review_revision'])
        assert result['status'] == 'rejected' and result['executed_result']['operator_proof_ref'] is None
        assert r.flow.decide(approval_id, 'reject', review['review_revision'])['recovered']
    else:
        if change == 'concurrent_reject':
            r.profile.client()('POST', '/api/v1/approvals/' + approval_id + '/decision', {'decision': 'reject'})
        else:
            with r.deps.connection_factory.unit_of_work() as uow:
                if change == 'expire':
                    uow.connection.execute("UPDATE execution_proposals SET expires_at='2000-01-01T00:00:00+00:00'")
                else:
                    uow.connection.execute("UPDATE agents SET role='changed' WHERE agent_id='subject'")
        with pytest.raises(ConnectionError) as denied:
            r.flow.decide(approval_id, 'approve', review['review_revision'])
        assert denied.value.code in ('PROPOSAL_UNAVAILABLE', 'CONFLICT', 'DECISION_CONFLICT')
    r.client.cookies.clear()
    assert r.client.post('/v1/connections/bindings:apply', json=apply, headers=r.headers['subject']).status_code in (403, 409)
    assert_no_binding(r.deps)


def test_review_confirmation_and_participant_authority_are_not_substitutable(operator, capsys):
    r = operator
    _, _, approval_id = pending(r)
    assert command(r, approval_id, '--decision', 'approve') == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'REVIEW_REQUIRED'
    assert command(r, approval_id, '--decision', 'approve', '--confirm', 'wrong') == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'REVIEW_CHANGED'
    r.client.cookies.clear()
    route = '/api/v1/approvals/' + approval_id
    assert r.client.get(route, headers=r.headers['subject']).status_code == 403
    assert r.client.post(route + '/decision', headers=r.headers['subject'], json={'decision': 'approve'}).status_code == 403
    assert r.flow.review(approval_id)['status'] == 'pending'
    assert_no_binding(r.deps)


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
@pytest.mark.parametrize('project', [False, True])
def test_connector_resumes_original_intent_after_human_terminal_decision(operator, tmp_path, capsys, project, monkeypatch):
    from okto_nexus_connector.storage.state_store import StateStore, IdentityRecord, ServerProfileRecord, ExecutionExecutorRecord
    from okto_nexus_connector.services.binding_onboarding import BindingOnboarding
    from okto_nexus_connector.services.background_onboarding import continue_pending_bindings
    from okto_nexus_connector.transport.https_client import NexusHTTPClient
    from okto_nexus_connector.errors import ConnectorError

    r = operator
    store = StateStore(tmp_path / 'connector-state.json')
    local = store.load().realizations[0]
    key = r.headers['subject']['Authorization'].removeprefix('Bearer ')
    def register(state):
        state.connector_id = 'connector'
        state.identities.append(IdentityRecord('subject', local.server_id, 'subject', 'participant-key', 1, 'now'))
        state.servers[local.server_id] = ServerProfileRecord(local.server_id, ORIGIN, ORIGIN, 'now')
        state.execution_executors.append(ExecutionExecutorRecord(local.server_id, 'connector', 'subject',
            'register', 'Remote host', executor_id=local.executor_id, state='REGISTERED'))
    store.update(register)
    vault = NS(resolve=lambda handle: key if handle == 'participant-key' else pytest.fail('unexpected credential'))
    requests = []
    async def run():
        async def check(request):
            requests.append(request)
            assert request.headers.get('Authorization') == 'Bearer ' + key
            assert 'cookie' not in request.headers
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=r.client.app),
                event_hooks={'request': [check]}) as wire:
            factory = lambda origin: NexusHTTPClient(origin, client=wire)
            bindings = BindingOnboarding(store, vault, http_factory=factory)
            prepared = await bindings.prepare(identity_alias='subject', realization_ref=local.realization_ref,
                alias='assistant', client_intent_id='terminal_prepare',
                connection_configuration=connection_preferences(r.prepare),
                **({'project_preset': {'id': 'project-generalist', 'revision': 1}} if project else {}))
            proposal = prepared['proposal']
            approval_id = next(a for a in proposal['required_approvals'] if a.startswith('apr_'))
            with pytest.raises(ConnectorError) as waiting:
                await bindings.apply(identity_alias='subject', prepare_intent_id='terminal_prepare',
                    client_intent_id='terminal_apply', approved_diff_hash=proposal['approved_diff_hash'], operator_proof_ref=approval_id)
            assert waiting.value.code == 'APPROVAL_REQUIRED'
            assert command(r, approval_id) == 0
            review = json.loads(capsys.readouterr().out)
            if project:
                assert 'Enable Server-wide human review' in review['proposal']['diff']['summary']
            assert command(r, approval_id, '--decision', 'approve', '--confirm', review['review_revision']) == 0
            capsys.readouterr()
            # Reopen persisted Connector state, as after CLI exit/daemon restart.
            reopened = StateStore(tmp_path / 'connector-state.json')
            if project:
                service = r.client.app.state.settings_service
                refresh = service.refresh_native_decisions
                def unavailable(factory):
                    raise OSError('injected postcommit cache failure')
                monkeypatch.setattr(service, 'refresh_native_decisions', unavailable)
                await continue_pending_bindings(reopened, vault, server_id=local.server_id,
                    executor_id=local.executor_id, http_factory=factory)
                assert reopened.load().binding_intents[0].status == 'APPLY_PENDING'
                assert r.deps.config.feature_hitl is False
                monkeypatch.setattr(service, 'refresh_native_decisions', refresh)
            await continue_pending_bindings(reopened, vault, server_id=local.server_id,
                executor_id=local.executor_id, http_factory=factory)
            state = reopened.load()
            assert state.binding_intents[0].project_preset == ({'id': 'project-generalist', 'revision': 1} if project else None)
            assert r.deps.config.feature_hitl is project
            assert state.binding_intents[0].status == 'APPLIED'
            assert state.binding_intents[0].apply_client_intent_id == 'terminal_apply'
            assert state.execution_bindings[0].binding_id == proposal['binding_id']
            count = len(requests)
            await continue_pending_bindings(reopened, vault, server_id=local.server_id,
                executor_id=local.executor_id, http_factory=factory)
            assert len(requests) == count
            token = next(iter(r.vault.values.values()))
            assert token not in json.dumps(asdict(state)) and token not in repr(requests)
    asyncio.run(run())
    with r.deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('execution_proposals', 'approvals', 'execution_bindings', 'runtime_execution_grants'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 1
