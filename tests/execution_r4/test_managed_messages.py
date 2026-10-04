"""Managed senders use public MCP without borrowing an agent API key."""
from pathlib import Path

import pytest

from test_mcp_session_capabilities import opening, activate, rpc, envelope
from test_session_capabilities import service
from okto_nexus.application.runtime_actor_authority import MANAGED_MESSAGE_PREFIX, valid_actor_binding


def message(**changes):
    return dict(workspace_id='ws', from_agent_id='subject', subject='Runtime sender',
                body='A message from the managed session.', target={'strategy':'direct', 'agent_id':'other'}) | changes


@pytest.mark.parametrize('opening', ['strict'], indirect=True)
def test_managed_message_uses_session_identity_and_records_causal_sender(opening):
    cap = activate(opening, actions=['tools/call', 'message_create'])
    result = envelope(rpc(opening, cap['capability'], 'message_create', message()))
    assert result['ok'], result
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT * FROM messages').fetchone()
        assert row['from_agent_id'] == 'subject' and row['workspace_id'] == 'ws'
        assert row['from_session_id'] is None
        from okto_nexus.application.message_session_origin import for_message, runtime_key
        assert for_message(uow.connection, row['message_id']) == runtime_key(cap['scope'])
        assert uow.connection.execute('SELECT count(*) FROM sessions').fetchone()[0] == 0
        assert uow.connection.execute('SELECT actor_agent_id FROM runtime_causal_roots').fetchone()[0] == 'subject'
        assert uow.connection.execute('SELECT recipient_agent_id FROM message_deliveries').fetchone()[0] == 'other'


@pytest.mark.parametrize('changes', [
    {'from_agent_id':'operator'}, {'workspace_id':'other'}, {'project_root':'C:/outside'},
    {'from_session_id':'legacy'}, {'session_secret':'legacy'},
])
def test_managed_message_rejects_identity_or_workspace_escape(opening, changes):
    cap = activate(opening, actions=['tools/call', 'message_create'])
    result = envelope(rpc(opening, cap['capability'], 'message_create', message(**changes)))
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM messages').fetchone()[0] == 0


def test_recorded_message_sender_is_scoped_and_revocable(opening):
    from okto_nexus.domain.execution_principal import current_execution_principal, current_execution_tool
    from okto_nexus.application.runtime_actor_authority import managed_message_binding
    cap = activate(opening, actions=['tools/call', 'message_create'])
    authority = service(opening)
    principal = authority.authenticate_transport(token=cap['capability'], audience='nexus-mcp-session')
    pt, tt = current_execution_principal.set(principal), current_execution_tool.set('message_create')
    try:
        with opening[0].connection_factory.unit_of_work() as uow:
            binding = managed_message_binding(uow, capabilities=authority, actor_id='subject', workspace_id='ws')
    finally:
        current_execution_principal.reset(pt)
        current_execution_tool.reset(tt)
    assert binding.startswith(MANAGED_MESSAGE_PREFIX)
    assert cap['capability'] not in binding and principal.secret_hash not in binding
    with opening[0].connection_factory.unit_of_work() as uow:
        actor = opening[0].repos.agents.get(uow, 'subject')
        assert valid_actor_binding(uow, actor, binding, capabilities=authority, workspace_id='ws')
        assert not valid_actor_binding(uow, actor, binding, capabilities=authority, workspace_id='different')
        assert not valid_actor_binding(uow, actor, binding)
        uow.connection.execute('UPDATE execution_session_capabilities SET revoked_at=?', (opening[0].clock.now_iso(),))
        assert not valid_actor_binding(uow, actor, binding, capabilities=authority, workspace_id='ws')


@pytest.mark.parametrize('revoke', [False, True])
def test_managed_send_approval_keeps_sender_authority(opening, monkeypatch, revoke):
    from fastapi.testclient import TestClient
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_hitl import _attach, _rule
    deps, app = opening[:2]
    deps.config.feature_hitl = True
    _attach(deps, 'subject', governance=[_rule('message_create', 'require_approval')])
    cap = activate(opening, actions=['tools/call', 'message_create'])
    pending = envelope(rpc(opening, cap['capability'], 'message_create', message()))
    assert pending['ok'] and pending['data']['status'] == 'pending_approval', pending
    approval_id = pending['data']['approval_id']
    recorded = deps.approvals.get_approval(approval_id=approval_id)['request_payload']['kwargs']
    assert recorded['_managed_message_binding'].startswith(MANAGED_MESSAGE_PREFIX)
    assert cap['capability'] not in str(recorded)
    if revoke:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE execution_session_capabilities SET revoked_at=?', (deps.clock.now_iso(),))
    response = TestClient(app, base_url='https://127.0.0.1:8202').post(
        f'/api/v1/approvals/{approval_id}/decision', json={'decision':'approve'},
        headers={'Authorization':'Bearer '+app.state.test_agent_keys['operator']})
    assert response.status_code == (403 if revoke else 200), response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM messages').fetchone()[0] == (0 if revoke else 1)
        if not revoke:
            assert uow.connection.execute('SELECT actor_agent_id FROM runtime_causal_roots').fetchone()[0] == 'subject'
            from okto_nexus.application.message_session_origin import runtime_key
            assert uow.connection.execute('SELECT source_session_key FROM execution_message_origins').fetchone()[0] == runtime_key(cap['scope'])
