"""Profile requirements restrict current REST, MCP and automatic delivery."""
import asyncio
import json
import sys

import pytest
from okto_nexus.domain.base import iso_plus
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_grant_regressions import mcp_helpers
from test_canonical_native_protocol_regressions import install_native, events
from test_canonical_session_close import terminal_events
from test_agent_recovery_isolation import eventually
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


def profile(setup, binding):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return dict(uow.connection.execute('SELECT p.* FROM runtime_profiles p JOIN agent_endpoints e '
            'ON e.profile_id=p.profile_id WHERE e.endpoint_id=?', (binding['endpoint_id'],)).fetchone())


def configure(setup, binding, config):
    current = profile(setup, binding)
    response = setup[2].patch('/api/v1/harness/profiles/' + current['profile_id'],
        headers=setup[3]['operator'], json=dict(expected_revision=current['revision'], config=config))
    assert response.status_code == 200, response.text
    grant = setup[2].post('/api/v1/harness/grants', headers=setup[3]['operator'], json=dict(
        actor_agent_id='subject', endpoint_id=binding['endpoint_id'],
        actions=['open', 'send', 'steer', 'interrupt', 'close'], max_executions=20,
        expires_at=iso_plus(setup[0].clock.now_iso(), 600)))
    assert grant.status_code == 200, grant.text


def test_required_hitl_rechecked_before_open_work_and_automatic_delivery(connected_local, monkeypatch):
    from test_canonical_handoff import prepare
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    deps.config.feature_hitl = True
    configure(setup, binding, {'required_native_requests': ['item/commandExecution/requestApproval']})
    hid, grant, claim, _ = prepare(setup, binding, monkeypatch)
    enable(setup, binding)
    first = admit(setup, binding, 'required-hitl-open', 'runtime.start', new_session=True)
    wait_receipt(setup, first)
    deps.config.feature_hitl = False
    rejected = client.post('/api/v1/harness/sessions', headers=headers['subject'], json=dict(
        agent_id='subject', kind='codex', endpoint_id=binding['endpoint_id'], project_root=str(root),
        idempotency_key='hitl-disabled-open'))
    assert rejected.status_code == 403, rejected.text
    denied = claim()
    assert denied.get('error', {}).get('code') == 'PERMISSION_DENIED', denied
    message = send(setup, monkeypatch)
    assert message['ok'], message
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == 'OPEN'
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (grant,)).fetchone()[0] == 0
        assert uow.connection.execute('SELECT count(*) FROM delivery_outbox').fetchone()[0] == 0
        assert uow.connection.execute('SELECT consumer_kind FROM message_deliveries WHERE message_id=?', (message['data']['message_id'],)).fetchone()[0] is None
    assert native.opens == 1 and not native.native.sent
    from test_canonical_consumption import pull
    assert message['data']['message_id'] in {item['message_id'] for item in pull(setup, monkeypatch)}
    deps.config.feature_hitl = True
    allowed = claim()
    assert allowed['ok'], allowed
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
    wait_receipt(setup, turn)
    assert len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'hitl-work-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))
    if first['scope']['session_id'] != turn['session_id']:
        wait_receipt(setup, admit(setup, binding, 'hitl-initial-close', 'runtime.close', session_id=first['scope']['session_id']), stages=('SUCCEEDED',))


def test_restricted_work_profile_preserves_real_conversation(connected_local, monkeypatch):
    from test_canonical_handoff import prepare
    setup, binding, _ = connected_local
    setup[0].config.feature_hitl = True
    configure(setup, binding, {'disabled_capabilities': ['managed_work', 'approvals', 'steer_timing']})
    hid, grant, claim, _ = prepare(setup, binding, monkeypatch)
    peers, log = install_native(connected_local, _FAKE_SERVER_SOURCE)
    opened = admit(setup, binding, 'restricted-conversation-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    denied = claim()
    assert denied.get('error', {}).get('code') == 'PERMISSION_DENIED', denied
    before = profile(setup, binding)
    conflict = setup[2].patch('/api/v1/harness/profiles/' + before['profile_id'], headers=setup[3]['operator'],
        json=dict(expected_revision=before['revision'], config=dict(disabled_capabilities=['approvals', 'managed_work'],
            required_native_requests=['item/commandExecution/requestApproval'])))
    assert conflict.status_code == 422, conflict.text
    assert profile(setup, binding) == before
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == 'OPEN'
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (grant,)).fetchone()[0] == 0
        assert uow.connection.execute('SELECT count(*) FROM delivery_outbox').fetchone()[0] == 0
        lease_actions = json.loads(uow.connection.execute('SELECT allowed_actions_json FROM execution_leases '
            'WHERE session_id=? ORDER BY lease_serial DESC LIMIT 1', (opened['scope']['session_id'],)).fetchone()[0])
        assert 'turn.submit' in lease_actions
        assert not {'approval.decide', 'input.provide', 'turn.steer'} & set(lease_actions)
    for index in range(2):
        sent = admit(setup, binding, f'restricted-turn-{index}', 'turn.submit',
            session_id=opened['scope']['session_id'], text=f'Safe conversation {index}')
        wait_receipt(setup, sent, stages=('SUCCEEDED',))
        eventually(lambda: terminal_events(setup, sent['operation_id']))
        eventually(lambda: f'Safe conversation {index}' in setup[2].get(
            '/api/v1/harness/operations/' + sent['operation_id'], headers=setup[3]['subject']).text)
    assert len(peers) == 1
    assert sum(json.loads(line).get('method') == 'turn/start' for line in log.read_text(encoding='utf-8').splitlines()) == 2
    wait_receipt(setup, admit(setup, binding, 'restricted-close', 'runtime.close', session_id=opened['scope']['session_id']), stages=('SUCCEEDED',))


def test_disabled_profile_approvals_cannot_dispatch_native_decision(connected_local):
    from test_canonical_native_approvals import approval_peer
    setup, binding, _ = connected_local
    configure(setup, binding, {'disabled_capabilities': ['approvals']})
    setup, binding, turn, body, peer, log = approval_peer(connected_local)
    response = setup[2].post('/v1/runtime/approval-decisions', headers=setup[3]['operator'], json=body)
    assert response.status_code == 403, response.text
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM execution_decisions').fetchone()[0] == 0
        assert uow.connection.execute("SELECT count(*) FROM execution_operations WHERE action='approval.decide'").fetchone()[0] == 0
    assert not [row for row in map(json.loads, log.read_text(encoding='utf-8').splitlines()) if 'response_to_server_request' in row]
    interrupted = admit(setup, binding, 'profile-denied-interrupt', 'turn.interrupt', session_id=turn['scope']['session_id'],
        target={'kind': 'current_run', 'expected_turn_id': None})
    wait_receipt(setup, interrupted)
    wait_receipt(setup, turn, stages=('CANCELLED',))
    wait_receipt(setup, admit(setup, binding, 'profile-denied-close', 'runtime.close', session_id=turn['scope']['session_id']), stages=('SUCCEEDED',))


@pytest.mark.parametrize('local_setup', ['claude_stream'], indirect=True)
@pytest.mark.parametrize('requirement', [{'sandbox': 'read-only'}, {'approval_policy': 'untrusted'}])
def test_unsupported_launch_profile_cannot_replace_claude_conversation(connected_local, requirement):
    from nexus_connector_core.native.adapters.claude_code_stream import ClaudeCodeStreamConnector
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    from test_harness_claude_code_connector import _FAKE_CLAUDE_SCRIPT
    setup, binding, _ = connected_local
    peers = []
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            peer = ClaudeCodeStreamConnector(binary=sys._base_executable, argv=['-u', '-c', _FAKE_CLAUDE_SCRIPT],
                version_argv=['-c', "print('2.1.281 (Claude Code)')"], cwd=str(setup[-1]), env={})
            peers.append(peer)
            native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
            return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch, context=context)
    setup[1].state.embedded_dispatch_owner.native_factory = Factory()
    before = profile(setup, binding)
    response = setup[2].patch('/api/v1/harness/profiles/' + before['profile_id'], headers=setup[3]['operator'],
        json=dict(expected_revision=before['revision'], config=requirement))
    assert response.status_code == 422, response.text
    assert profile(setup, binding) == before and not peers
    opened = admit(setup, binding, 'unchanged-claude-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    sent = admit(setup, binding, 'unchanged-claude-turn', 'turn.submit', session_id=opened['scope']['session_id'], text='Compatible conversation')
    wait_receipt(setup, sent, stages=('SUCCEEDED',))
    eventually(lambda: terminal_events(setup, sent['operation_id']))
    assert 'echo:Compatible conversation' in json.dumps(terminal_events(setup, sent['operation_id']))
    assert len(peers) == 1
    wait_receipt(setup, admit(setup, binding, 'unchanged-claude-close', 'runtime.close', session_id=opened['scope']['session_id']), stages=('SUCCEEDED',))
