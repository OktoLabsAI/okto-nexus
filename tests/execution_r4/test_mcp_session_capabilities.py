"""Real HTTP MCP handlers over canonical capability/lease authority.

Selection/qualification and READY state are fixture preconditions, not provider
acceptance. Handoffs are existing domain work; claim/complete use public MCP.
"""

import json

from fastapi.testclient import TestClient
import pytest

from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo
from test_session_capabilities import opening, issue, begin, apply_lease


def activate(state, *, actions=None, audience='nexus-mcp-session'):
    response = issue(state, audience=audience, actions=actions or [
        'tools/call', 'agent_whoami', 'handoff_list_available', 'handoff_get',
        'handoff_claim', 'handoff_complete', 'event_cursor', 'event_get', 'event_wait'])
    assert response.status_code == 200, response.text
    begin(state)
    leases, _, _, ack = apply_lease(state)
    leases.applied(ack, channel=state[5])
    with state[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
    return response.json()


def rpc(state, secret, name='agent_whoami', arguments=None, **headers):
    return TestClient(state[1], base_url="https://127.0.0.1:8202").post('/mcp/', headers={
        'Authorization': 'Bearer ' + secret,
        'Accept': 'application/json, text/event-stream', **headers}, json={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': name, 'arguments': arguments or {}}})


def envelope(response):
    assert response.status_code == 200, response.text
    payload = (json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')))
        if 'text/event-stream' in response.headers.get('content-type', '') else response.json())
    assert 'result' in payload, payload
    result = payload['result']
    return result.get('structuredContent') or json.loads(result['content'][0]['text'])


def seed_work(state, *, handoff_id='work', target='subject', workspace='ws'):
    deps = state[0]
    with deps.connection_factory.unit_of_work() as uow:
        if workspace != 'ws':
            uow.connection.execute('INSERT OR IGNORE INTO workspaces(workspace_id,created_at) VALUES (?,?)',
                (workspace, deps.clock.now_iso()))
        SqliteHandoffRepo(deps.clock).create(uow, handoff_id=handoff_id, workspace_id=workspace,
            status='OPEN', from_agent_id='other', target=json.dumps({'strategy': 'direct', 'agent_id': target}),
            visibility='public', payload=json.dumps({'task': 'Review this change.'}))


def args(**changes):
    return dict(project_root='ws', agent_id='subject', handoff_id='work') | changes


@pytest.mark.parametrize("opening", ["strict"], indirect=True)
def test_managed_mcp_claim_and_complete_share_canonical_domain_and_strict_auth(opening):
    assert opening[0].config.trust_mode == "strict"
    cap = activate(opening)
    seed_work(opening)
    who = envelope(rpc(opening, cap['capability']))
    assert who['ok'] is True and who['data']['agent_id'] == 'subject'
    assert who['data']['session_scope'] == cap['scope']
    claimed = envelope(rpc(opening, cap['capability'], 'handoff_claim', args()))
    assert claimed['ok'] is True, claimed
    epoch = claimed['data']['claim_epoch']
    complete = envelope(rpc(opening, cap['capability'], 'handoff_complete', args(claim_epoch=epoch, result='Reviewed.')))
    assert complete['ok'] is True, complete
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='work'").fetchone()[0] == 'COMPLETED'
        claim = uow.connection.execute('SELECT * FROM execution_tool_claims').fetchone()
        assert claim['session_id'] == cap['scope']['session_id']
        assert json.loads(claim['scope_json']) == cap['scope']
        assert uow.connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0


@pytest.mark.parametrize('actions', [['tools/call'], ['agent_whoami']])
def test_protocol_ceiling_is_not_tool_permission(opening, actions):
    cap = activate(opening, actions=actions)
    result = envelope(rpc(opening, cap['capability']))
    assert result['ok'] is False and result['error']['code'] == 'PERMISSION_DENIED'


@pytest.mark.parametrize('name,arguments', [
    ('handoff_claim', args(project_root='other-workspace')),
    ('handoff_claim', args(agent_id='other')),
    ('handoff_claim', args(session_id='other-session')),
    ('handoff_claim', args(session_secret='legacy-secret')),
    ('handoff_claim', args(runtime_endpoint_id='ep')),
    ('inbox_pull', {'agent_id': 'subject'}),
    ('session_open', {'agent_id': 'subject', 'workspace_id': 'ws'}),
    ('workspace_list', {}),
    ('nexus_info', {}),
])
def test_managed_mcp_cannot_escape_to_other_scope_or_unadapted_surface(opening, name, arguments):
    cap = activate(opening, actions=['tools/call', name])
    seed_work(opening)
    result = envelope(rpc(opening, cap['capability'], name, arguments))
    assert result['ok'] is False and result['error']['code'] == 'PERMISSION_DENIED', result
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_tool_claims').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0


def test_mcp_capability_keeps_canonical_handoff_eligibility(opening):
    cap = activate(opening)
    seed_work(opening, target='other')
    result = envelope(rpc(opening, cap['capability'], 'handoff_claim', args()))
    assert result['ok'] is False and result['error']['code'] == 'NOT_ELIGIBLE_TO_CLAIM', result


def test_mcp_capability_cannot_complete_an_unowned_claim(opening):
    cap = activate(opening)
    seed_work(opening)
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET status='CLAIMED',claimed_by='subject',claim_epoch=1 WHERE handoff_id='work'")
    result = envelope(rpc(opening, cap['capability'], 'handoff_complete', args(claim_epoch=1)))
    assert result['ok'] is False and result['error']['code'] == 'PERMISSION_DENIED', result


def test_mcp_revocation_and_audience_do_not_change_tools_only_identity(opening):
    cap = activate(opening)
    assert envelope(rpc(opening, cap['capability']))['ok']
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'")
    assert rpc(opening, cap['capability']).status_code == 401
    assert envelope(rpc(opening, opening[1].state.test_agent_keys['subject']))['ok']
    assert TestClient(opening[1]).get('/api/v1/agents', headers={'Authorization': 'Bearer ' + cap['capability']}).status_code == 401


def test_native_capability_is_not_mcp_or_a_legacy_key(opening):
    cap = activate(opening, audience='nexus-native-session')
    assert rpc(opening, cap['capability']).status_code == 401


def test_mcp_reserved_capability_cannot_initialize_active_identity(opening):
    cap = issue(opening).json()
    assert rpc(opening, cap['capability']).status_code == 401


def test_mcp_revalidates_after_transport_authentication_before_domain_effect(opening, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.connection_gate import ConnectionGateServer
    cap = activate(opening)
    seed_work(opening)
    original = ConnectionGateServer.check
    def revoke_after_check(self):
        original(self)
        with opening[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'")
    monkeypatch.setattr(ConnectionGateServer, 'check', revoke_after_check)
    result = envelope(rpc(opening, cap['capability'], 'handoff_claim', args()))
    assert result['ok'] is False, result
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='work'").fetchone()[0] == 'OPEN'
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_tool_claims').fetchone()[0] == 0


def test_mcp_claim_scope_record_and_domain_mutation_commit_together(opening):
    cap = activate(opening)
    seed_work(opening)
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_claim_scope BEFORE INSERT ON execution_tool_claims "
                               "BEGIN SELECT RAISE(ABORT,'injected claim storage failure'); END")
    result = envelope(rpc(opening, cap['capability'], 'handoff_claim', args()))
    assert result['ok'] is False
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status,claim_epoch FROM handoffs WHERE handoff_id='work'").fetchone()[:] == ('OPEN', 0)
        assert uow.connection.execute("SELECT COUNT(*) FROM events WHERE type='handoff.claimed'").fetchone()[0] == 0


def test_mcp_session_cannot_complete_a_claim_from_another_scope(opening):
    cap = activate(opening)
    seed_work(opening)
    claimed = envelope(rpc(opening, cap['capability'], 'handoff_claim', args()))
    assert claimed['ok'], claimed
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_tool_claims SET scope_json=?',
            (json.dumps(cap['scope'] | {'session_owner_generation': 999}),))
    result = envelope(rpc(opening, cap['capability'], 'handoff_complete', args(claim_epoch=claimed['data']['claim_epoch'])))
    assert result['ok'] is False and result['error']['code'] == 'PERMISSION_DENIED'


def test_mcp_event_and_handoff_context_use_canonical_workspace_handles(opening):
    cap = activate(opening)
    seed_work(opening)
    seed_work(opening, handoff_id='hidden-work', workspace='other-ws')
    context = envelope(rpc(opening, cap['capability'], 'handoff_get', args()))
    assert context['ok'] and context['data']['handoff_id'] == 'work', context
    other = envelope(rpc(opening, cap['capability'], 'handoff_get', args(handoff_id='hidden-work')))
    assert other['ok'] is False, other
    cursor = envelope(rpc(opening, cap['capability'], 'event_cursor',
        {'project_root': 'ws', 'agent_id': 'subject', 'stream': 'workspace'}))
    assert cursor['ok'], cursor


def test_mcp_authority_is_independent_of_control_socket_but_bounded_by_lease(opening):
    cap = activate(opening)
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='OFFLINE'")
    assert envelope(rpc(opening, cap['capability']))['ok']
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z'")
    assert rpc(opening, cap['capability']).status_code == 401
    assert envelope(rpc(opening, opening[1].state.test_agent_keys['subject']))['ok']


def test_mcp_managed_and_key_requests_keep_separate_concurrent_identities(opening):
    from concurrent.futures import ThreadPoolExecutor
    cap = activate(opening)
    def request(secret):
        return envelope(rpc(opening, secret))['data']
    with ThreadPoolExecutor(max_workers=2) as pool:
        managed = pool.submit(request, cap['capability'])
        other = pool.submit(request, opening[1].state.test_agent_keys['other'])
        assert managed.result()['session_scope'] == cap['scope']
        key_identity = other.result()
        assert key_identity['agent_id'] == 'other' and 'session_scope' not in key_identity
