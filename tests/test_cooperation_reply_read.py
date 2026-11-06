"""DX-08 observes canonical exchange evidence without consuming the actor inbox.

TCP tests exercise the real auth boundary. Native peers are synthetic and use
only temporary installations; publication and managed authority remain real.
"""
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_pr34_remediation as tcp
from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.domain.coordination_requests import message_request_hash
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError


@pytest.fixture
def runtime(tmp_path):
    with contextmanager(tcp.runtime.__wrapped__)(tmp_path, SimpleNamespace(param=False)) as state:
        yield state


def snapshot(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        tables = [row[0] for row in uow.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: [tuple(row) for row in uow.connection.execute('SELECT * FROM "' + name + '"')]
                for name in tables}


def message(deps, message_id, *, sender='worker', recipient='caller', parent='original',
            workspace='cooperation', lane='unread', confirmed=False, target=None, delivered=True):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=workspace)
        for actor in (sender, recipient):
            if deps.repos.agents.get(uow, actor) is None:
                deps.repos.agents.upsert(uow, agent_id=actor)
        target = target or {'strategy': 'direct', 'agent_id': recipient}
        deps.repos.messages.create(uow, message_id=message_id, workspace_id=workspace,
            from_agent_id=sender, parent_message_id=parent, target=json.dumps(target),
            subject='Not proof', body='NEXUS_CONNECTION_OK PRIVATE CONTENT')
        if delivered:
            deps.repos.deliveries.create(uow, delivery_id='delivery-' + message_id,
                message_id=message_id, recipient_agent_id=recipient, status=lane)
        if confirmed:
            key = deps.repos.coordination_requests.key(uow, actor_agent_id=sender, workspace_id=workspace,
                operation='message_create', client_request_id='request-' + message_id)
            deps.repos.coordination_requests.record(uow, key,
                request_hash=message_request_hash(subject='Not proof', body='NEXUS_CONNECTION_OK PRIVATE CONTENT',
                    target=target, parent_message_id=parent), now=deps.clock.now_iso(), resource_id=message_id)
    return message_id


def original(deps, **kwargs):
    return message(deps, 'original', sender='caller', recipient='worker', parent=None, **kwargs)


def observe(runtime, **changes):
    return tcp.tool(runtime[1], runtime[5], 'message_status',
        dict(message_id='original', include_replies=True) | changes)


@pytest.mark.parametrize('warm', [False, True])
def test_tcp_cold_and_warm_observation_is_fresh_and_preserves_all_rows(runtime, monkeypatch, warm):
    deps = runtime[0]
    original(deps)
    message(deps, 'reply', lane='read', confirmed=True)
    assert deps.config.feature_trace is False
    if warm:
        assert tcp.tool(runtime[1], runtime[5], 'agent_whoami', {})['ok']
    calls = []
    resolve = AgentKeyAuthService.resolve_readonly
    def fresh(self, uow, key):
        assert not uow._write
        before = self.cache_stats()
        actor = resolve(self, uow, key)
        assert self.cache_stats() == before
        calls.append(before['entries'])
        return actor
    monkeypatch.setattr(AgentKeyAuthService, 'resolve_readonly', fresh)
    before = snapshot(deps)
    for _ in range(3):
        result = observe(runtime)
        assert result['ok'], result
        reply, = result['data']['replies']
        assert reply == dict(message_id='reply', parent_message_id='original', workspace_id='cooperation',
            from_agent_id='worker', target={'strategy': 'direct', 'agent_id': 'caller'},
            created_at=reply['created_at'], delivery_status='read', read_at=None,
            authority_kind='coordination_request', runtime_outcome=None)
        assert result['data']['replies_truncated'] is False
        assert 'PRIVATE CONTENT' not in json.dumps(result)
        assert snapshot(deps) == before
    assert calls == [1 if warm else 0] * 3


def test_tcp_real_canonical_reply_remains_observable_after_another_session_ack(runtime):
    deps, client, _, _, _, key = runtime
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id='cooperation')
        peer_key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id='worker')
    sent = tcp.tool(client, key, 'message_create', dict(workspace_id='cooperation', from_agent_id='caller',
        body='Please reply canonically.', target={'strategy': 'direct', 'agent_id': 'worker'},
        client_request_id='smoke-original'))
    assert sent['ok'], sent
    mid = sent['data']['message_id']
    reply = tcp.tool(client, peer_key, 'message_create', dict(workspace_id='cooperation', from_agent_id='worker',
        body='NEXUS_CONNECTION_OK PRIVATE CONTENT', target={'strategy': 'direct', 'agent_id': 'caller'},
        parent_message_id=mid, client_request_id='smoke-reply'))
    assert reply['ok'], reply
    consumer = tcp.tool(client, key, 'session_open', {'agent_id': 'caller', 'workspace_id': 'cooperation'})
    assert consumer['ok'], consumer
    session = {k: consumer['data'][k] for k in ('session_id', 'session_secret')}
    assert tcp.tool(client, key, 'inbox_pull', {'agent_id': 'caller', **session})['ok']
    assert tcp.tool(client, key, 'inbox_ack',
        {'agent_id': 'caller', 'message_ids': [reply['data']['message_id']], **session})['ok']
    before = snapshot(deps)
    result = observe(runtime, message_id=mid)
    assert result['ok'], result
    item, = result['data']['replies']
    assert item['delivery_status'] == 'read' and item['authority_kind'] == 'coordination_request'
    assert item['message_id'] == reply['data']['message_id']
    assert snapshot(deps) == before


def test_reply_query_filters_before_limit_and_prioritizes_confirmed_provenance(runtime):
    deps = runtime[0]
    original(deps)
    message(deps, 'other-parent', parent=None)
    for i in range(65):
        message(deps, 'noise-' + str(i))
    for mid, changes in (
        ('wrong-peer', {'sender': 'stranger'}), ('wrong-parent', {'parent': 'other-parent'}),
        ('wrong-workspace', {'workspace': 'elsewhere'}), ('wrong-recipient', {'recipient': 'stranger'}),
        ('broadcast', {'target': {'strategy': 'broadcast'}}), ('no-delivery', {'delivered': False}),
    ):
        message(deps, mid, confirmed=True, **changes)
    message(deps, 'confirmed-last', confirmed=True, lane='parked')
    before = snapshot(deps)
    result = observe(runtime)
    assert result['ok'], result
    items = result['data']['replies']
    assert len(items) == 50 and result['data']['replies_truncated']
    assert items[0]['message_id'] == 'confirmed-last'
    assert items[0]['delivery_status'] == 'parked'
    assert all(item['authority_kind'] == 'unconfirmed' for item in items[1:])
    assert all(item['message_id'].startswith('noise-') for item in items[1:])
    assert snapshot(deps) == before


@pytest.mark.parametrize('change', ['key', 'inactive', 'method'])
def test_tcp_revocation_cannot_use_a_warm_positive_auth_cache(runtime, change):
    deps = runtime[0]
    original(deps)
    assert tcp.tool(runtime[1], runtime[5], 'agent_whoami', {})['ok']
    with deps.connection_factory.unit_of_work() as uow:
        if change == 'method':
            uow.connection.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES ('caller','mcp',0) "
                "ON CONFLICT(agent_id,method) DO UPDATE SET enabled=0")
        else:
            uow.connection.execute('UPDATE agents SET ' + (
                "api_key_hash='rotated'" if change == 'key' else 'is_active=0') + " WHERE agent_id='caller'")
    before = snapshot(deps)
    response = runtime[1].post('/mcp/', headers={'Authorization': 'Bearer ' + runtime[5],
        'Accept': 'application/json, text/event-stream'}, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'message_status', 'arguments': {'message_id': 'original', 'include_replies': True}}})
    assert response.status_code in (401, 403), response.text
    assert snapshot(deps) == before


@pytest.mark.parametrize('change', ['key', 'inactive', 'method'])
def test_transaction_revalidates_actor_binding_and_connection_method(runtime, change):
    deps = runtime[0]
    original(deps)
    service = build_service(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        actor = deps.repos.agents.get(uow, 'caller')
    service._request_context_provider = lambda: RuntimeRequestContext('caller', 'agent_key',
        credential_binding=actor.api_key_hash)
    with deps.connection_factory.unit_of_work() as uow:
        if change == 'method':
            uow.connection.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES ('caller','mcp',0) "
                "ON CONFLICT(agent_id,method) DO UPDATE SET enabled=0")
        else:
            uow.connection.execute('UPDATE agents SET ' + (
                "api_key_hash='rotated'" if change == 'key' else 'is_active=0') + " WHERE agent_id='caller'")
    before = snapshot(deps)
    with pytest.raises(OktoNexusError) as denied:
        service.message_status(message_id='original', include_replies=True)
    assert denied.value.code == 'PERMISSION_DENIED'
    assert snapshot(deps) == before


def test_legacy_shape_strict_boolean_sender_visibility_and_discovery(runtime):
    deps = runtime[0]
    original(deps)
    message(deps, 'foreign', sender='worker', recipient='caller', parent=None)
    legacy = tcp.tool(runtime[1], runtime[5], 'message_status', {'message_id': 'original'})
    assert legacy['ok'] and set(legacy['data']) == {'message_id', 'deliveries', 'count'}
    for invalid in ('true', 1, None, []):
        result = tcp.mcp_call(runtime[1], runtime[5], 'tools/call', {'name': 'message_status',
            'arguments': {'message_id': 'original', 'include_replies': invalid}})
        assert result['isError'], result
    denied = observe(runtime, message_id='foreign')
    absent = observe(runtime, message_id='missing')
    assert denied['error']['code'] == absent['error']['code'] == 'NOT_FOUND'
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE messages SET target=? WHERE message_id='original'", ('{"strategy":"broadcast"}',))
    assert observe(runtime)['error']['code'] == 'VALIDATION_ERROR'
    info = tcp.tool(runtime[1], runtime[5], 'nexus_info', {})['data']
    assert info['coordination_observation'] == {'revision': 1, 'passive': True, 'workspace_selector': True}
    assert info['coordination_cooperation'] == dict(revision=1, reply_tool='message_status',
        direct_replies=True, authority_provenance=True)


def test_no_context_or_claimed_caller_cannot_observe_replies(runtime):
    deps = runtime[0]
    original(deps)
    service = build_service(deps)
    before = snapshot(deps)
    with pytest.raises(OktoNexusError) as denied:
        service.message_status(message_id='original', caller_agent_id='caller', include_replies=True)
    assert denied.value.code == 'PERMISSION_DENIED'
    assert snapshot(deps) == before


def test_managed_reply_observation_preserves_scope_and_revocation(tmp_path, monkeypatch):
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=()))
    monkeypatch.syspath_prepend(str(Path(__file__).parent / 'execution_r4'))
    from test_mcp_session_capabilities import opening, activate, rpc, envelope
    with contextmanager(opening.__wrapped__)(tmp_path, monkeypatch, SimpleNamespace(param=None)) as state:
        cap = activate(state, actions=['tools/call', 'message_status'])
        deps = state[0]
        message(deps, 'original', sender='subject', recipient='peer', parent=None, workspace='ws')
        message(deps, 'reply', sender='peer', recipient='subject', workspace='ws', confirmed=True)
        message(deps, 'foreign-workspace', sender='subject', recipient='peer', parent=None, workspace='elsewhere')
        before = snapshot(deps)
        result = envelope(rpc(state, cap['capability'], 'message_status',
            {'message_id': 'original', 'include_replies': True}))
        assert result['ok'] and result['data']['replies'][0]['authority_kind'] == 'coordination_request', result
        wrong = envelope(rpc(state, cap['capability'], 'message_status',
            {'message_id': 'foreign-workspace', 'include_replies': True}))
        assert wrong['error']['code'] == 'PERMISSION_DENIED', wrong
        after = snapshot(deps)
        # This managed fixture independently publishes inventory; the observation
        # must leave every other row, including all agents and leases, unchanged.
        assert {k: v for k, v in after.items() if not k.startswith('execution_inventory_')} == {
            k: v for k, v in before.items() if not k.startswith('execution_inventory_')}
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'")
        assert rpc(state, cap['capability'], 'message_status',
            {'message_id': 'original', 'include_replies': True}).status_code == 401


@pytest.mark.parametrize('outcome', ['success', 'failed', 'interrupted'])
def test_native_canonical_publication_reports_outcome_without_model_text_proof(tmp_path, monkeypatch, outcome):
    """Real Core publication with a synthetic native peer, no personal provider."""
    monkeypatch.syspath_prepend(str(Path(__file__).parent / 'execution_r4'))
    from test_local_realization import local_setup
    from test_canonical_delivery import connected_local, enable, send
    from test_canonical_result_publication import current_turn, wait_result
    from test_embedded_dispatch import wait_receipt
    from nexus_connector_core import RuntimeEvent
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, SimpleNamespace()) as setup:
        _, binding, native = connected_local.__wrapped__(setup)
        enable(setup, binding)
        source = send(setup, monkeypatch)
        assert source['ok'], source
        turn = current_turn(setup)
        wait_receipt(setup, turn)
        deps, _, client, headers, *_ = setup
        with deps.connection_factory.unit_of_work(write=False) as uow:
            stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
        client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
            stream['session_id'], stream['stream_epoch'], 0, 'turn_state', 'fixture.cooperation',
            dict(delivery_phase='terminal', delivery_outcome=outcome,
                output_text='NEXUS_CONNECTION_OK PRIVATE CONTENT'), operation_id=turn['operation_id']))
        row = wait_result(setup, 'PUBLISHED')
        key = headers['operator']['Authorization'].removeprefix('Bearer ')
        result = tcp.tool(client, key, 'message_status',
            {'message_id': source['data']['message_id'], 'include_replies': True})
        assert result['ok'], result
        reply, = result['data']['replies']
        assert reply['message_id'] == row['publication_message_id']
        assert reply['authority_kind'] == 'runtime_result'
        assert reply['runtime_outcome'] == ('completed' if outcome == 'success' else outcome)
        assert 'PRIVATE CONTENT' not in json.dumps(result)
        with deps.connection_factory.unit_of_work() as uow:
            # A mismatched terminal source must never acquire confirmed provenance.
            uow.connection.execute('UPDATE execution_results SET output_event_count=output_event_count+1')
        again = tcp.tool(client, key, 'message_status',
            {'message_id': source['data']['message_id'], 'include_replies': True})
        assert again['ok'] and again['data']['replies'][0]['authority_kind'] == 'unconfirmed'
