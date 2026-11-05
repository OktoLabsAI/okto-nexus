"""Durable Finish recovery is a read, including after the test cache is gone."""
from copy import deepcopy

import pytest

from test_connection_setup import request_for
import test_local_realization
from okto_nexus.application.connection_setup import read_setup_commit
from okto_nexus.application.execution_local_realizations import directory_identity
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

local_setup = test_local_realization.local_setup


def snapshot(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)]
                for table in ('connection_setup_commits', 'execution_bindings', 'agent_endpoints',
                              'runtime_execution_grants', 'agent_execution_policies', 'agent_runtime_overrides')}


@pytest.mark.parametrize('prefix', ['/v1', '/api/v1/runtime-management'])
@pytest.mark.parametrize('actor', ['operator', None])
def test_recovery_matches_durable_receipt_without_reapplying(local_setup, monkeypatch, prefix, actor):
    from okto_nexus.adapters.inbound.http import runtime_v1

    deps, app, client, headers, *_ = local_setup
    context, request = request_for(local_setup)
    verified = {'root': directory_identity(request['configuration']['workspace_root']), 'home': None}
    monkeypatch.setattr(app.state.connection_tests, 'verified', lambda *args: verified)
    response = client.post(prefix + '/connections/setup:finish', headers=headers['operator'], json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    before = snapshot(deps)
    if actor is None:
        # Receipt recovery accepts an authorized human without an agent identity.
        # This does not claim that every binding-creation path accepts that context.
        context = RuntimeRequestContext(None, 'operator_session', trusted_local_operator=True)
        monkeypatch.setattr(runtime_v1, 'runtime_request_context', lambda: context)

    def must_not_test(*args):
        pytest.fail('A committed setup must not consult or repeat the test')

    app.state.connection_tests.tests.clear()
    monkeypatch.setattr(app.state.connection_tests, 'verified', must_not_test)
    monkeypatch.setattr(app.state.connection_tests, 'start', must_not_test)
    receipt = client.post(prefix + '/connections/setup:recover', headers=headers['operator'], json=request)
    assert receipt.status_code == 200, receipt.text
    assert receipt.headers['cache-control'] == 'no-store'
    assert receipt.json()['result'] == result
    assert receipt.json()['state'] == 'committed'
    assert receipt.json()['setup_run_id'] == request['client_intent_id']
    assert receipt.json()['request_hash'].startswith('sha256:')
    observed = client.get(prefix + '/connections/setup-commits/' + request['client_intent_id'],
                          headers=headers['operator'])
    assert observed.json() == receipt.json()
    assert observed.headers['cache-control'] == 'no-store'
    repeated = client.post(prefix + '/connections/setup:finish', headers=headers['operator'], json=request)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == result

    changed = deepcopy(request)
    changed['configuration']['alias'] = 'another-name'
    for operation in ('recover', 'finish'):
        conflict = client.post(prefix + '/connections/setup:' + operation, headers=headers['operator'], json=changed)
        assert conflict.status_code == 409, conflict.text
    assert snapshot(deps) == before


def test_missing_or_unauthorized_receipt_is_not_success(local_setup):
    deps, _, client, headers, *_ = local_setup
    _, request = request_for(local_setup)
    before = snapshot(deps)
    path = '/v1/connections/setup-commits/' + request['client_intent_id']
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers['subject']).status_code == 403
    assert client.post('/v1/connections/setup:recover', headers=headers['subject'], json=request).status_code == 403
    missing = client.get(path, headers=headers['operator'])
    assert missing.status_code == 404
    assert missing.json()['error']['stage'] == 'connection.setup_commit'
    assert 'may still be pending' in missing.json()['error']['message']
    response = client.post('/v1/connections/setup:recover', headers=headers['operator'], json=request)
    assert response.status_code == 404
    assert snapshot(deps) == before


def test_receipts_are_scoped_to_authorized_audit_actor(local_setup):
    deps = local_setup[0]
    operator = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    other = RuntimeRequestContext('other-operator', 'http_loopback', trusted_local_operator=True)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('INSERT INTO connection_setup_commits VALUES(?,?,?,?,?)',
            ('operator', 'same-id', 'sha256:original', '{"saved":true}', deps.clock.now_iso()))
    assert read_setup_commit(deps, operator, 'same-id')['result'] == {'saved': True}
    with pytest.raises(OktoNexusError) as missing:
        read_setup_commit(deps, other, 'same-id')
    assert missing.value.code == 'NOT_FOUND'
    for invalid in ('', 'a' * 101, None):
        with pytest.raises(OktoNexusError) as bad:
            read_setup_commit(deps, operator, invalid)
        assert bad.value.code == 'VALIDATION_ERROR'


@pytest.mark.parametrize('lost_at,lose_test_cache', [('finish', True), ('test', False), ('test', True)])
@pytest.mark.asyncio
async def test_connector_recovers_through_real_http_handlers(local_setup, tmp_path, monkeypatch, lost_at, lose_test_cache):
    import httpx
    from types import SimpleNamespace
    from okto_nexus_connector.cli.commands import connection_config as command
    from okto_nexus_connector.errors import ConnectorError
    from okto_nexus_connector.storage.state_store import IdentityRecord, ServerProfileRecord
    from okto_nexus_connector.transport.https_client import NexusHTTPClient

    deps, app, client, headers, *_ = local_setup
    _, request = request_for(local_setup)
    root = tmp_path / 'connector'
    store = command.StateStore(command.paths.state_file(root))
    server_id = app.state.embedded_inventory_owner.key.server_id
    key = headers['operator']['Authorization'].removeprefix('Bearer ')
    base = 'http://127.0.0.1:8202'
    def seed(state):
        state.servers[server_id] = ServerProfileRecord(server_id, base, base, 'now')
        state.identities.append(IdentityRecord('operator', server_id, 'operator', 'vault:operator', 1, 'now'))
    store.update(seed)
    monkeypatch.setattr(command, '_vault', lambda *args: SimpleNamespace(resolve=lambda _: key))
    probes = []
    async def simulated_harness(entry, value, candidate):
        probes.append(value['client_intent_id'])
        entry.update(status='succeeded', stage='Connection verified')
    monkeypatch.setattr(app.state.connection_tests, 'run', simulated_harness)
    calls = []
    lost = False
    def exchange(wire):
        nonlocal lost
        path = wire.url.path
        calls.append((wire.method, path))
        response = client.request(wire.method, path, headers=wire.headers, content=wire.content)
        if not lost and path.endswith('setup:' + lost_at):
            assert response.status_code == 200, response.text
            lost = True
            raise httpx.ReadError('Injected lost response', request=wire)
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)
    args = SimpleNamespace(identity='operator', agent='subject', request_id=request['client_intent_id'],
                           **{name: request[name] for name in ('executor_id', 'candidate_ref', 'inventory_revision',
                                                             'workspace_id', 'binding_id')})
    output = SimpleNamespace(line=lambda _: None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(exchange)) as wire_client:
        monkeypatch.setattr(command, 'NexusHTTPClient', lambda url: NexusHTTPClient(url, client=wire_client))
        with pytest.raises(ConnectorError) as unavailable:
            await command.apply_configuration(args, output, root, request['configuration'])
        assert unavailable.value.code == 'OUTCOME_UNKNOWN'
        assert unavailable.value.possible_effect and not unavailable.value.retry_safe
        before = snapshot(deps)
        if lose_test_cache:
            app.state.connection_tests.tests.clear()
        if lost_at == 'test' and lose_test_cache:
            with pytest.raises(ConnectorError) as unknown:
                await command.apply_configuration(args, output, root, request['configuration'])
            assert unknown.value.code == 'SETUP_TEST_UNCONFIRMED'
            assert snapshot(deps) == before
        else:
            recovered = await command.apply_configuration(args, output, root, request['configuration'])
            assert recovered['saved'] and recovered['agent_id'] == 'subject'
            assert len(snapshot(deps)['execution_bindings']) == 1
            assert len(snapshot(deps)['runtime_execution_grants']) == 1
            if lost_at == 'finish':
                assert snapshot(deps) == before
    assert calls.count(('POST', '/v1/connections/setup:test')) == 1
    assert calls.count(('POST', '/v1/connections/setup:finish')) == (0 if lost_at == 'test' and lose_test_cache else 1)
    assert probes == [request['client_intent_id']]
    assert key not in store.path.read_text(encoding='utf-8')
