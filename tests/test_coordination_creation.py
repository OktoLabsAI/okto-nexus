"""Canonical coordination over real HTTP/MCP, SQLite and approval executors."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest
import okto_nexus

import test_pr34_remediation as fixtures
from test_pr34_remediation import tool, mcp_call
from test_hitl import _attach, _rule
from okto_nexus.application.coordination_requests import CoordinationRequestService
from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.keys import hash_api_key
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import ErrorCode, OktoNexusError


runtime = fixtures.runtime
pytestmark = pytest.mark.parametrize('runtime', [False], indirect=True)


def prepare(runtime, operation, **changes):
    deps, client, root, _, operator, caller = runtime
    workspace = tool(client, caller, 'workspace_resolve', dict(project_root=root))['data']['workspace_id']
    arguments = dict(workspace_id=workspace, from_agent_id='caller',
        target=dict(strategy='direct', agent_id='worker'), client_request_id='durable-request')
    arguments.update(dict(subject='Design question', body='Please discuss this design') if operation == 'message_create'
                     else dict(visibility='eligible', payload=dict(objective='Review the design')))
    arguments.update(changes)
    return arguments


def create(runtime, operation, arguments):
    return tool(runtime[1], runtime[5], operation, arguments)


def recover(runtime, operation, arguments, key=None):
    return tool(runtime[1], key or runtime[5], 'coordination_request_get', dict(
        workspace_id=arguments['workspace_id'], operation=operation, client_request_id=arguments['client_request_id']))


def decide(runtime, approval_id, decision='approve'):
    return runtime[1].post(f'/api/v1/approvals/{approval_id}/decision', headers={'x-api-key': runtime[4]},
                          json=dict(decision=decision))


def snapshot(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        values = {name: uow.connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in (
            'messages', 'message_deliveries', 'handoffs', 'approvals', 'coordination_requests',
            'delivery_outbox', 'execution_operations')}
        values['events'] = [tuple(row) for row in uow.connection.execute(
            "SELECT event_id,type FROM events WHERE type IN ('message.created','handoff.created','approval.requested','approval.granted','approval.denied') ORDER BY event_id")]
        return values


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_same_request_concurrent_retry_recovers_one_canonical_object(runtime, operation):
    args = prepare(runtime, operation)
    # A second actual send would exceed the canonical quota.
    _attach(runtime[0], 'caller', governance=[_rule(operation, 'max_count', limit_value=1, window='1h')])
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: create(runtime, operation, args), range(6)))
    assert all(result['ok'] for result in results), results
    id_field = 'message_id' if operation == 'message_create' else 'handoff_id'
    assert len({result['data'][id_field] for result in results}) == 1
    assert sum(not result['data']['reused'] for result in results) == 1
    first = results[0]['data']
    assert first['status'] == 'created' and 'body' not in first and 'payload' not in first
    before = snapshot(runtime[0])
    assert recover(runtime, operation, args)['data'][id_field] == first[id_field]
    assert snapshot(runtime[0]) == before
    changed = {**args, ('body' if operation == 'message_create' else 'payload'): 'Changed intent'}
    conflict = create(runtime, operation, changed)
    assert conflict['error']['code'] == 'CONFLICT', conflict
    assert conflict['error']['details']['reason'] == 'CLIENT_REQUEST_CONTENT_CONFLICT'
    assert snapshot(runtime[0]) == before
    unknown = recover(runtime, operation, args, key=runtime[4])
    assert unknown['error']['code'] == 'NOT_FOUND', unknown


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_pending_approval_reuses_original_and_commits_result_atomically(runtime, operation):
    deps = runtime[0]
    deps.config.feature_hitl = True
    deps.config.feature_trace = True
    args = prepare(runtime, operation)
    opened = tool(runtime[1], runtime[5], 'session_open', dict(agent_id='caller', workspace_id=args['workspace_id']))['data']
    session_field = 'from_session_id' if operation == 'message_create' else 'session_id'
    args.update({session_field: opened['session_id'], 'session_secret': opened['session_secret']})
    _attach(deps, 'caller', governance=[_rule(operation, 'require_approval')])
    first = create(runtime, operation, args)
    assert first['ok'] and first['data']['status'] == 'pending_approval', first
    before = snapshot(deps)
    again = create(runtime, operation, args)
    assert again['ok'] and again['data']['approval_id'] == first['data']['approval_id'], again
    assert snapshot(deps) == before
    approval_id = first['data']['approval_id']
    stored = deps.approvals.get_approval(approval_id=approval_id)
    assert opened['session_secret'] not in json.dumps(stored)
    assert runtime[5] not in json.dumps(stored)
    result = decide(runtime, approval_id)
    assert result.status_code == 200, result.text
    result = result.json()['data']['executed_result']
    assert result['status'] == 'created'
    assert result['approval_id'] == approval_id
    assert result['request_receipt']['expires_at'] == first['data']['request_receipt']['expires_at']
    resource_id = result['request_receipt']['resource_id']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        table, column = ('messages', 'message_id') if operation == 'message_create' else ('handoffs', 'handoff_id')
        row = uow.connection.execute(f'SELECT trace_id FROM {table} WHERE {column}=?', (resource_id,)).fetchone()
        assert row['trace_id'] == stored['trace_id']
        origins = 'execution_message_origins' if operation == 'message_create' else 'execution_handoff_origins'
        origin = uow.connection.execute(f'SELECT source_session_key FROM {origins} WHERE {column}=?', (resource_id,)).fetchone()
        assert json.loads(origin[0]) == ['mcp', opened['session_id']]
        assert json.loads(uow.connection.execute('SELECT executed_result FROM approvals WHERE approval_id=?', (approval_id,)).fetchone()[0]) == result
    after = snapshot(deps)
    assert create(runtime, operation, args)['data']['request_receipt']['resource_id'] == resource_id
    assert decide(runtime, approval_id).json()['data']['reused'] is True
    assert snapshot(deps) == after


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
@pytest.mark.parametrize('cut', ['event', 'receipt', 'approval_result'])
def test_commit_cuts_leave_no_partial_creation(runtime, operation, cut):
    deps = runtime[0]
    args = prepare(runtime, operation)
    if cut == 'approval_result':
        deps.config.feature_hitl = True
        _attach(deps, 'caller', governance=[_rule(operation, 'require_approval')])
        pending = create(runtime, operation, args)['data']
    before = snapshot(deps)
    statement = ("BEFORE INSERT ON events WHEN NEW.type='" + operation.replace('_create', '.created') + "'" if cut == 'event'
                 else 'BEFORE INSERT ON coordination_requests' if cut == 'receipt'
                 else 'BEFORE UPDATE OF executed_result ON approvals')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('CREATE TRIGGER injected_cut ' + statement + " BEGIN SELECT RAISE(ABORT,'injected coordination cut'); END")
    if cut == 'approval_result':
        failed = decide(runtime, pending['approval_id'])
        assert failed.status_code >= 400
    else:
        assert create(runtime, operation, args)['ok'] is False
    assert snapshot(deps) == before
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER injected_cut')
    recovered = decide(runtime, pending['approval_id']) if cut == 'approval_result' else create(runtime, operation, args)
    assert recovered.status_code == 200 if cut == 'approval_result' else recovered['ok'], recovered
    assert snapshot(deps)['coordination_requests'] == 1


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_actor_forgery_permission_revocation_and_metadata_only_lookup(runtime, operation):
    deps = runtime[0]
    args = prepare(runtime, operation)
    forged = create(runtime, operation, {**args, 'from_agent_id': 'worker'})
    assert forged['error']['code'] == 'PERMISSION_DENIED', forged
    assert snapshot(deps)['coordination_requests'] == 0
    original = create(runtime, operation, args)
    assert original['ok'], original
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.set_permissions(uow, agent_id='caller', preset_id=None,
            permissions={'messages': {'send_direct': False}} if operation == 'message_create' else {'handoffs': {'create': False}})
    assert create(runtime, operation, args)['error']['code'] == 'PERMISSION_DENIED'
    # Own metadata remains readable, just like a creator's canonical handoff ID.
    assert recover(runtime, operation, args)['ok']
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET api_key_hash='revoked' WHERE agent_id='caller'")
    # Passive HTTP authentication bypasses the positive cache and refuses the
    # revoked key before MCP dispatch, without disclosing the receipt.
    lookup = dict(workspace_id=args['workspace_id'], operation=operation,
                  client_request_id=args['client_request_id'])
    before = snapshot(deps)
    response = runtime[1].post('/mcp/', headers={'x-api-key': runtime[5],
        'Accept': 'application/json, text/event-stream'}, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': 'coordination_request_get', 'arguments': lookup}})
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'AUTH_FAILED'
    assert original['data']['request_receipt']['resource_id'] not in response.text
    # A context authenticated before rotation is independently rejected inside
    # the receipt read transaction as well.
    stale = RuntimeRequestContext('caller', 'agent_key', credential_binding=hash_api_key(runtime[5]))
    service = CoordinationRequestService(factory=deps.connection_factory,
        repo=deps.repos.coordination_requests, agents=deps.repos.agents,
        workspaces=deps.repos.workspaces, clock=deps.clock, context_provider=lambda: stale)
    with pytest.raises(OktoNexusError) as denied:
        service.get(**lookup)
    assert denied.value.code == ErrorCode.PERMISSION_DENIED
    assert snapshot(deps) == before


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_approval_rechecks_original_key_and_rejects_revocation(runtime, operation):
    deps = runtime[0]
    args = prepare(runtime, operation)
    deps.config.feature_hitl = True
    _attach(deps, 'caller', governance=[_rule(operation, 'require_approval')])
    pending = create(runtime, operation, args)['data']
    before = snapshot(deps)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET api_key_hash='rotated' WHERE agent_id='caller'")
    refused = decide(runtime, pending['approval_id'])
    assert refused.status_code == 403, refused.text
    assert snapshot(deps) == before


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
@pytest.mark.parametrize('cut', ['before_execution', 'after_creation'])
def test_real_process_exit_during_approval_resumes_original_request(runtime, operation, cut):
    deps = runtime[0]
    args = prepare(runtime, operation)
    deps.config.feature_hitl = True
    _attach(deps, 'caller', governance=[_rule(operation, 'require_approval')])
    pending = create(runtime, operation, args)['data']
    worker = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.messages import build_service as messages
from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service as handoffs
deps = bootstrap({}, ['--home', sys.argv[2]])
messages(deps)
handoffs(deps)
original = deps.approvals._executors[sys.argv[4]]
def crash(kwargs):
    if sys.argv[5] == 'before_execution':
        os._exit(73)
    original(kwargs)
    os._exit(74)
deps.approvals._executors[sys.argv[4]] = crash
deps.approvals.decide(approval_id=sys.argv[3], decision='approve', decided_by='operator')
'''
    run = subprocess.run([sys.executable, '-I', '-c', worker, str(Path(okto_nexus.__file__).parents[1]),
        str(deps.config.home_dir), pending['approval_id'], operation, cut], capture_output=True, text=True, timeout=40)
    assert run.returncode == (73 if cut == 'before_execution' else 74), run.stderr
    view = recover(runtime, operation, args)['data']
    assert view['status'] == ('approved_awaiting_execution' if cut == 'before_execution' else 'created'), view
    result = decide(runtime, pending['approval_id'])
    assert result.status_code == 200, result.text
    final = result.json()['data']['executed_result']
    assert final['status'] == 'created'
    assert final['approval_id'] == pending['approval_id']
    before = snapshot(deps)
    assert create(runtime, operation, args)['data']['request_receipt']['resource_id'] == final['request_receipt']['resource_id']
    assert decide(runtime, pending['approval_id']).status_code == 200
    assert snapshot(deps) == before
    assert sum(kind == 'approval.granted' for _, kind in before['events']) == 1


def test_receipt_tombstone_expiry_and_capability_discovery(runtime):
    deps = runtime[0]
    args = prepare(runtime, 'message_create')
    first = create(runtime, 'message_create', args)['data']
    info = tool(runtime[1], runtime[5], 'nexus_info', {})['data']
    assert info['coordination_requests']['retention_days'] == 30
    schema = mcp_call(runtime[1], runtime[5], 'tools/list', {})['tools']
    for item in schema:
        if item['name'] in ('message_create', 'handoff_create'):
            fields = item['inputSchema']['properties']
            assert 'client_request_id' in fields
            assert not any(key.startswith('_') for key in fields)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('DELETE FROM message_deliveries WHERE message_id=?', (first['message_id'],))
        uow.connection.execute('DELETE FROM messages WHERE message_id=?', (first['message_id'],))
    assert recover(runtime, 'message_create', args)['data']['status'] == 'resource_removed'
    assert create(runtime, 'message_create', args)['data']['status'] == 'resource_removed'
    before = snapshot(deps)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE coordination_requests SET created_at=?,expires_at=?',
            (iso_plus(deps.clock.now_iso(), -32 * 86400), iso_plus(deps.clock.now_iso(), -86400)))
    assert recover(runtime, 'message_create', args)['data']['status'] == 'expired'
    refused = create(runtime, 'message_create', args)
    assert refused['error']['details']['reason'] == 'CLIENT_REQUEST_WINDOW_EXPIRED'
    assert snapshot(deps) == before


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_pending_receipt_failure_rolls_back_approval_and_event(runtime, operation):
    deps = runtime[0]
    args = prepare(runtime, operation)
    deps.config.feature_hitl = True
    _attach(deps, 'caller', governance=[_rule(operation, 'require_approval')])
    before = snapshot(deps)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_pending BEFORE INSERT ON coordination_requests BEGIN SELECT RAISE(ABORT,'pending cut'); END")
    assert create(runtime, operation, args)['ok'] is False
    assert snapshot(deps) == before
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER fail_pending')
    assert create(runtime, operation, args)['data']['status'] == 'pending_approval'


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_concurrent_approval_and_lost_postcommit_result_preserve_one_effect(runtime, monkeypatch, operation):
    deps = runtime[0]
    args = prepare(runtime, operation)
    deps.config.feature_hitl = True
    _attach(deps, 'caller', governance=[_rule(operation, 'require_approval')])
    pending = create(runtime, operation, args)['data']
    original = deps.approvals._executors[operation]
    def lose_result(kwargs):
        original(kwargs)
        raise RuntimeError('injected lost postcommit result')
    monkeypatch.setitem(deps.approvals._executors, operation, lose_result)
    # An unhandled ASGI failure closes its TCP connection after the 500. Model
    # recovery with a fresh transport, not a race against that closing socket
    # in the same keepalive pool (which Windows may reset after the response).
    with httpx.Client(base_url=runtime[1].base_url, timeout=10) as failed_client:
        try:
            failed = failed_client.post(f'/api/v1/approvals/{pending["approval_id"]}/decision',
                headers={'x-api-key': runtime[4]}, json=dict(decision='approve'))
        except httpx.TransportError:
            pass  # The injected post-commit failure may lose the response too.
        else:
            assert failed.status_code >= 400
    assert recover(runtime, operation, args)['data']['status'] == 'created'
    before = snapshot(deps)
    monkeypatch.setitem(deps.approvals._executors, operation, original)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: decide(runtime, pending['approval_id']), range(4)))
    assert all(result.status_code == 200 for result in results), [result.text for result in results]
    assert len({result.json()['data']['executed_result']['request_receipt']['resource_id'] for result in results}) == 1
    assert snapshot(deps) == before
    assert sum(kind == 'approval.granted' for _, kind in before['events']) == 1


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
@pytest.mark.parametrize('change', ['rejected', 'expired', 'removed', 'tampered_payload'])
def test_pending_request_cannot_be_recreated_after_decision_or_window_change(runtime, operation, change):
    deps = runtime[0]
    args = prepare(runtime, operation)
    deps.config.feature_hitl = True
    _attach(deps, 'caller', governance=[_rule(operation, 'require_approval')])
    pending = create(runtime, operation, args)['data']
    if change == 'rejected':
        assert decide(runtime, pending['approval_id'], 'reject').status_code == 200
        before = snapshot(deps)
        assert create(runtime, operation, args)['data']['status'] == 'rejected'
        assert decide(runtime, pending['approval_id'], 'reject').status_code == 200
        assert snapshot(deps) == before
        return
    with deps.connection_factory.unit_of_work() as uow:
        if change == 'expired':
            uow.connection.execute('UPDATE coordination_requests SET created_at=?,expires_at=?',
                (iso_plus(deps.clock.now_iso(), -32 * 86400), iso_plus(deps.clock.now_iso(), -86400)))
        elif change == 'removed':
            uow.connection.execute('DELETE FROM coordination_requests')
        else:
            payload = json.loads(uow.connection.execute('SELECT request_payload FROM approvals').fetchone()[0])
            payload['kwargs']['body' if operation == 'message_create' else 'payload'] = 'Modified stored intent'
            uow.connection.execute('UPDATE approvals SET request_payload=?', (json.dumps(payload),))
    before = snapshot(deps)
    refused = decide(runtime, pending['approval_id'])
    assert refused.status_code == 409, refused.text
    assert snapshot(deps) == before


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_verified_session_provenance_is_scoped_and_recovery_does_not_heartbeat(runtime, operation, tmp_path):
    deps = runtime[0]
    args = prepare(runtime, operation)
    other = tmp_path / 'other-project'
    other.mkdir()
    wrong_workspace = tool(runtime[1], runtime[5], 'workspace_resolve', dict(project_root=str(other)))['data']['workspace_id']
    opened = tool(runtime[1], runtime[5], 'session_open', dict(agent_id='caller', workspace_id=wrong_workspace))['data']
    session_field = 'from_session_id' if operation == 'message_create' else 'session_id'
    args.update({session_field: opened['session_id'], 'session_secret': opened['session_secret']})
    refused = create(runtime, operation, args)
    assert refused['error']['code'] == 'PERMISSION_DENIED', refused
    args['workspace_id'] = wrong_workspace
    first = create(runtime, operation, args)
    assert first['ok'], first
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE sessions SET last_heartbeat_at=?', ('2026-01-01T00:00:00.000000Z',))
    assert recover(runtime, operation, args)['ok']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT last_heartbeat_at FROM sessions').fetchone()[0] == '2026-01-01T00:00:00.000000Z'
    # A changed proof is validated, never hashed or accepted because the ID exists.
    assert create(runtime, operation, {**args, 'session_secret': 'wrong-proof'})['error']['code'] == 'NOT_OWNER'
