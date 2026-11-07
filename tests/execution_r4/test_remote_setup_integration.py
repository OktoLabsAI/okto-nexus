"""Operator + Connector CLI over real TCP, with explicit native/provider doubles.

No OS service, personal vault, real harness or provider is exercised here.
The canonical Server, human session, Connector state and protocol are real.
"""
import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
import io
import json
import time

import httpx
import pytest
from nexus_connector_core import InstallationCandidate, calculate_inventory_revision, get_runtime_catalog
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.installation import effective_installation_ref
from nexus_connector_core.inventory_observer import HarnessObservation, InventoryObservationBatch

import test_pr34_remediation as tcp
from test_remote_operator_terminal import MemoryVault, ACCOUNT
from okto_nexus.adapters.inbound.http.operator_auth import OperatorAuth
from okto_nexus.adapters.outbound.operator_client import OperatorProfile
from okto_nexus.adapters.outbound.execution.core_inventory import local_inventory_snapshot
from okto_nexus.application.project_preset import configuration
from okto_nexus.application.remote_terminal_setup import RemoteProjectSetup
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus_connector.cli.commands import connect, configure_local
from okto_nexus_connector.cli.main import build_parser
from okto_nexus_connector.cli.output import Output
from okto_nexus_connector.identity.vault import RestrictedFileVault
from okto_nexus_connector.platform.paths import state_file
from okto_nexus_connector.services import remote_setup
from okto_nexus_connector.services.executor_registration import ExecutorRegistrationService
from okto_nexus_connector.services.executor_onboarding import ExecutorOnboarding
from okto_nexus_connector.storage.state_store import StateStore
from okto_nexus_connector.transport.https_client import NexusHTTPClient, R4BindingProposal
from okto_nexus_connector.transport.wss_r4 import connect_r4_connection

runtime = tcp.runtime


def counts(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return {name: uow.connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
            for name in ('agents', 'workspaces', 'execution_bindings', 'runtime_execution_grants',
                         'execution_proposals', 'approvals', 'connection_setup_commits')}


@pytest.mark.parametrize('loss', ['none', 'decision', 'apply', 'rereview', 'local-rereview', 'finish-race'])
def test_operator_and_connector_cli_complete_same_root_once(runtime, tmp_path, monkeypatch, loss):
    deps, client = runtime[:2]
    origin = str(client.base_url).rstrip('/')
    OperatorAuth(deps.config.home_dir).configure(**ACCOUNT, local=True)
    operator_vault = MemoryVault()
    profile = OperatorProfile(tmp_path / 'human-client', 'remote', backend=operator_vault)
    profile.login(origin, **ACCOUNT)
    operator_call = profile.client()
    calls, saved, material, handoffs = [], [], [], []
    lose_decision = [loss == 'decision']

    def call(method, path, body=None):
        calls.append((method, path))
        result = operator_call(method, path, body)
        if lose_decision[0] and path.endswith('/decision'):
            lose_decision[0] = False
            raise ConnectionError('OUTCOME_UNKNOWN', 'Injected operator response loss', possible_effect=True)
        return result

    flow = RemoteProjectSetup(call, lambda value: saved.append(deepcopy(value)), origin=origin,
        material_sink=lambda key: material.append(key),
        handoff_sink=lambda value: handoffs.append(deepcopy(value)))
    host = tmp_path / 'host'
    host.mkdir()
    project = host / 'project'
    project.mkdir()
    binary = host / 'synthetic-codex.exe'
    binary.write_bytes(b'Synthetic fixture, never execute')
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
    observed = replace(candidate, version='fixture-v1')
    store = StateStore(state_file(host))
    config = configuration(adapter_id=candidate.adapter_id, project=str(project), label='Remote project')
    config['execution_location'] = 'remote'
    local = remote_setup.prepare(store, setup_run_id='integrated-root', server=origin, configuration=config,
        candidate=candidate, candidate_ref=effective_installation_ref(candidate),
        inventory_revision=calculate_inventory_revision([candidate]))
    selection = dict(agent='new-project-assistant', create_agent=True, display_name='Project assistant',
        client=None, project='operator-local-shortcut', label='Remote project', workspace_id=None,
        binding_id=None, candidate_ref=None, provider_home=None, operator_profile='remote', remote_draft=local['draft'])
    before = counts(deps)
    document = flow.review(selection)
    assert counts(deps) == before
    result = flow.apply(document, approval=document['review_revision'], timeout=0)
    assert result['state'] == 'awaiting_host' and len(material) == len(handoffs) == 1
    assert counts(deps)['agents'] == before['agents'] + 1
    assert counts(deps)['runtime_execution_grants'] == before['runtime_execution_grants']
    receipt_path = host / 'handoff.json'
    receipt_path.write_bytes(remote_setup.document_bytes(handoffs[-1]))
    (host / 'vault').mkdir()
    vault = RestrictedFileVault(host / 'vault', approved=True)
    monkeypatch.setattr('okto_nexus_connector.cli.commands.identity._vault', lambda *a: vault)
    monkeypatch.setattr(configure_local, '_vault', lambda *a: vault)
    monkeypatch.setattr(connect, '_read_key', lambda *a: material[0])
    monkeypatch.setattr(connect, 'vault_backend_names', lambda: ('synthetic',))
    monkeypatch.setattr(configure_local.manager, 'start', lambda *a: None)
    probes, host_calls = [], []
    lose_apply = [loss == 'apply']
    original_send = httpx.AsyncClient.send

    async def send(wire, request, *args, **kwargs):
        host_calls.append((request.method, request.url.path))
        assert 'cookie' not in request.headers
        assert request.headers.get('Authorization') != 'Bearer ' + runtime[4]
        response = await original_send(wire, request, *args, **kwargs)
        if lose_apply[0] and request.url.path.endswith('/bindings:apply') and response.status_code == 200:
            lose_apply[0] = False
            raise httpx.ReadError('Injected host response loss', request=request)
        return response

    monkeypatch.setattr(httpx.AsyncClient, 'send', send)

    async def observe(*args, **kwargs):
        probes.append(kwargs)
        store.update(lambda state: state.execution_executors[0].installation_observations.append(
            dict(source=asdict(candidate), version=observed.version)))

    async def candidates(*args, **kwargs):
        return [observed]

    monkeypatch.setattr(configure_local, 'observe_installation', observe)
    monkeypatch.setattr(configure_local, 'configured_candidates', candidates)
    batch = InventoryObservationBatch(1, time.monotonic(), (observed,), (observed,), tuple(
        HarnessObservation(entry.adapter_id, 'PRESENT' if entry.adapter_id == candidate.adapter_id else 'ABSENT', 0, None)
        for entry in get_runtime_catalog().runtimes if entry.discoverable))
    bootstraps, links = [], []

    async def reconcile(frame):
        assert not frame['operation_ids'] and not frame['session_ids']
        return {name: frame[name] for name in ('protocol_major', 'contract_revision', 'server_id', 'executor_id',
            'connection_id', 'connection_generation', 'reconcile_id', 'cursor')} | dict(
                type='reconcile.report', next_cursor=None, complete=True, receipts=[], claims=[],
                stream_watermarks=[], ownership_facts=[])

    async def ipc(root, method, body=None):
        assert root == host
        if method == 'state.reload':
            if not bootstraps:
                server_id = handoffs[-1]['bootstrap']['server_id']
                bootstrap = await ExecutorRegistrationService(store, vault).bootstrap(server_id=server_id)
                bootstraps.append(bootstrap)
                async with NexusHTTPClient(origin) as http:
                    protocol = await http.r4_protocol()
                    link = await connect_r4_connection(http.link_url(bootstrap.executor.executor_id), bootstrap.ticket,
                        server_id=server_id, executor_id=bootstrap.executor.executor_id,
                        management_revision=protocol.management_revision, snapshot_format=protocol.executor_snapshot_format,
                        boot_id='integrated-boot', report_reconciliation=reconcile)
                    links.append(link)
                    snapshot = local_inventory_snapshot([observed], server_id=server_id,
                        executor_id=bootstrap.executor.executor_id, producer_instance_id=link.state.connection_id,
                        publication_sequence=1, observations=batch.coverage())
                    await http.publish_inventory(bootstrap.ticket, executor_id=bootstrap.executor.executor_id, snapshot=snapshot)
            return {}
        assert method == 'executor.realize'
        return await ExecutorOnboarding(store, vault).realize(**body, bootstrap=bootstraps[0], inventory_batch=batch)

    monkeypatch.setattr(configure_local, 'ipc', ipc)
    output = Output(json_mode=False, stream=io.StringIO())

    def host_args():
        return build_parser().parse_args(['connect', '--setup-receipt', str(receipt_path), '--alias', 'project'])

    async def run():
        pending = await connect.run_connect(host_args(), output, host)
        assert pending['status'] == 'awaiting_operator_approval'
        assert pending['operator_review']['command'] == 'okto-nexus connect --profile CONNECT_PROFILE'
        assert counts(deps)['runtime_execution_grants'] == before['runtime_execution_grants']
        if loss == 'finish-race':
            assert (await asyncio.to_thread(flow.apply, saved[-1], timeout=0))['state'] == 'awaiting_finish'
        if loss in ('rereview', 'local-rereview', 'finish-race'):
            from okto_nexus_connector.errors import ConnectorError
            original_bootstrap = deepcopy(handoffs[-1]['bootstrap'])
            original_children = deepcopy(handoffs[-1]['child_requests'])
            revised_selection = deepcopy(selection)
            if loss in ('local-rereview', 'finish-race'):
                from okto_nexus_connector.cli.commands import connect_setup_review
                new_project = host / 'revised-project'
                new_project.mkdir()
                new_draft = host / 'revised-draft.json'
                async def choose(args, output):
                    args.discovery_inventory_revision = calculate_inventory_revision([observed])
                    return observed.adapter_id, observed, None
                monkeypatch.setattr(connect, '_choose_harness', choose)
                monkeypatch.setattr(connect_setup_review, 'choice', lambda *args, **kwargs: True)
                args = build_parser().parse_args(['connect', '--setup-draft', str(new_draft), '--request-id',
                    'integrated-root', '--review-current', '--project', str(new_project)])
                amendment = await connect.run_connect(args, output, host)
                assert amendment['status'] == 'awaiting_operator_review'
                retained = remote_setup.load(store, 'integrated-root')
                assert retained['local']['configuration']['workspace_root'] == str(project)
                assert retained['pending_local_review']['local']['configuration']['workspace_root'] == str(new_project)
                revised_selection['remote_draft'] = remote_setup.read_document(new_draft)
            else:
                with deps.connection_factory.unit_of_work() as uow:
                    uow.connection.execute('UPDATE agents SET role=? WHERE agent_id=?',
                        ('Reviewed project role', selection['agent']))
                changed = await asyncio.to_thread(flow.apply, saved[-1], timeout=0)
                assert changed['state'] == 'review_required'
            if loss == 'finish-race':
                # Model the retained, already approved apply reaching Server
                # after local suspension, with its acknowledgement lost before
                # Connector persistence. The Server and wire are real.
                child = store.load().binding_intents[0]
                async with NexusHTTPClient(origin) as http:
                    await http.apply_r4_binding(material[0], client_intent_id=child.apply_client_intent_id,
                        proposal=R4BindingProposal(**child.proposal), operator_proof_ref=child.operator_proof_ref)
                assert remote_setup.load(store, 'integrated-root').get('pending_local_review')
            else:
                await revise_operator_and_host(revised_selection, original_bootstrap, original_children)

        if loss == 'decision':
            with pytest.raises(ConnectionError) as failed:
                await asyncio.to_thread(flow.apply, saved[-1], timeout=0)
            assert failed.value.possible_effect
        if loss != 'finish-race':
            waiting = await asyncio.to_thread(flow.apply, saved[-1], timeout=0)
            assert waiting['state'] == 'awaiting_finish'
            assert counts(deps)['runtime_execution_grants'] == before['runtime_execution_grants']
        monkeypatch.setattr(connect, '_read_key', lambda *a: pytest.fail('key imported twice'))
        if loss == 'apply':
            from okto_nexus_connector.errors import ConnectorError
            with pytest.raises(ConnectorError):
                await connect.run_connect(host_args(), output, host)
        configured = await connect.run_connect(host_args(), output, host)
        assert configured['saved']
        if loss == 'finish-race':
            retained = remote_setup.load(store, 'integrated-root')
            assert retained.get('pending_local_review') is None
            assert retained['local']['configuration']['workspace_root'] == str(project)
            assert retained['handoff_history'][-1]['outcome'] == 'prior_finish_committed'
        complete = await asyncio.to_thread(flow.apply, saved[-1], timeout=0)
        assert complete['state'] == 'configured'
        assert saved[-1]['final_binding']['finish_id'] == saved[-1]['final_binding']['proposal_id'] + '_setup'
        final_counts = counts(deps)
        assert final_counts['runtime_execution_grants'] == before['runtime_execution_grants'] + 1
        for name in ('execution_bindings', 'execution_proposals', 'approvals', 'connection_setup_commits'):
            extra = 2 if loss in ('rereview', 'local-rereview') and name in ('execution_proposals', 'approvals') else 1
            assert final_counts[name] == before[name] + extra
        previous = len(calls)
        assert (await asyncio.to_thread(flow.apply, saved[-1], timeout=0))['state'] == 'configured'
        assert all(method == 'GET' for method, path in calls[previous:])
        assert counts(deps) == final_counts
        assert len(probes) == 1
        assert sum(path.endswith('/decision') for method, path in calls) == 1
        assert len(store.load().identities) == len(store.load().execution_bindings) == 1
        public = json.dumps(saved) + json.dumps(handoffs) + store.path.read_text() + output.stream.getvalue()
        assert material[0] not in public
        assert all(token not in public for token in operator_vault.values.values())
        assert not runtime[3], 'No provider session may start during setup'

    async def revise_operator_and_host(revised_selection, original_bootstrap, original_children):
        from okto_nexus_connector.errors import ConnectorError
        revised = await asyncio.to_thread(flow.review, revised_selection, previous=saved[-1])
        with pytest.raises(ConnectionError) as unapproved:
            await asyncio.to_thread(flow.apply, revised, timeout=0)
        assert unapproved.value.code == 'REVIEW_REQUIRED'
        await asyncio.to_thread(flow.apply, revised, approval=revised['review_revision'], timeout=0)
        assert handoffs[-1]['bootstrap'] == original_bootstrap
        assert (handoffs[-1]['child_requests']['realize'] == original_children['realize']) is (loss == 'rereview')
        assert handoffs[-1]['child_requests']['prepare'] != original_children['prepare']
        unchanged = store.path.read_bytes()
        with pytest.raises(ConnectorError) as stale:
            await connect.run_connect(host_args(), output, host)
        assert stale.value.code == ('OPERATION_CONFLICT' if loss == 'local-rereview' else 'REMOTE_SETUP_REVIEW_REQUIRED')
        assert store.path.read_bytes() == unchanged
        receipt_path.write_bytes(remote_setup.document_bytes(handoffs[-1]))
        assert (await connect.run_connect(host_args(), output, host))['status'] == 'awaiting_operator_approval'
        retained = remote_setup.load(store, 'integrated-root')
        assert len(retained['handoff_history']) == 1
        assert store.load().binding_intents[0].status == 'REVIEW_REPLACED'
        if loss == 'local-rereview':
            assert retained.get('pending_local_review') is None
            assert retained['local']['configuration']['workspace_root'] == str(host / 'revised-project')

    async def bounded():
        try:
            async with asyncio.timeout(90):
                await run()
        finally:
            for link in links:
                await link.close()

    asyncio.run(bounded())
