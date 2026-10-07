"""PR34 invariants exercised through the current authenticated Core boundary.

These regressions deliberately use the production R4 dispatcher. They must not
replace the removed legacy opener or inject a legacy HarnessSupervisor.
"""
from dataclasses import asdict
from pathlib import Path

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send


def mcp(setup, monkeypatch, key, name, arguments):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    setup[2].headers['host'] = '127.0.0.1:8000'
    return tool(setup[2], key, name, arguments)


def test_enabling_runtime_does_not_replay_historical_unread_messages(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, _, _, _, *_ = setup
    # Messages received before execution was enabled retain their inbox state.
    deps.config.feature_harness_integrations = False
    historical = [send(setup, monkeypatch) for _ in range(3)]
    assert all(item['ok'] for item in historical), historical
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = [dict(row) for row in uow.connection.execute('SELECT * FROM message_deliveries ORDER BY delivery_id')]
        assert len(before) == 3 and all(row['status'] == 'unread' for row in before)
        assert not uow.connection.execute('SELECT 1 FROM delivery_outbox').fetchone()
    deps.config.feature_harness_integrations = True
    enable(setup, binding)
    fresh = send(setup, monkeypatch)
    assert fresh['ok'], fresh
    with deps.connection_factory.unit_of_work(write=False) as uow:
        operation = uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit'").fetchone()[0]
    wait_receipt(setup, dict(operation_id=operation))
    # Historical and repeated post-commit notifications cannot create work.
    for item in [fresh, fresh, *historical]:
        deps.inbox_delivery_notifier.publish('subject', item['data'])
    deps.runtime_dispatcher.scan_once()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for row in before:
            assert dict(uow.connection.execute('SELECT * FROM message_deliveries WHERE delivery_id=?', (row['delivery_id'],)).fetchone()) == row
        assert [r[0] for r in uow.connection.execute('SELECT message_id FROM delivery_outbox')] == [fresh['data']['message_id']]
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert native.opens == 1 and len(native.native.sent) == 1


def test_open_close_preserves_registered_agent_profile(connected_local):
    setup, binding, native = connected_local
    deps = setup[0]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET role='reviewer',capabilities=?,metadata=? WHERE agent_id='subject'",
                               ('{"review":true}', '{"keep":"profile"}'))
        before = asdict(deps.repos.agents.get(uow, 'subject'))
    opened = admit(setup, binding, 'profile-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    wait_receipt(setup, admit(setup, binding, 'profile-close', 'runtime.close',
                             session_id=opened['session_id']), stages=('SUCCEEDED',))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = asdict(deps.repos.agents.get(uow, 'subject'))
        # Authenticated requests update presence, never the configured profile.
        assert after.pop('last_seen_at') is not None
        before.pop('last_seen_at')
        assert after == before
        assert uow.connection.execute('SELECT COUNT(*) FROM harness_sessions').fetchone()[0] == 0
    assert native.opens == 1 and native.native.stopped


@pytest.mark.parametrize('transport', ['rest', 'mcp'])
@pytest.mark.parametrize('verb', ['send', 'steer', 'interrupt', 'close', 'get', 'events'])
def test_foreign_agent_cannot_control_or_read_a_canonical_session(connected_local, monkeypatch, transport, verb):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'private-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    session = opened['session_id']
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id='outsider')
        key = app.state.auth.issue_key(uow, agent_id='outsider')
    payload = dict(session_id=session, idempotency_key='foreign-' + verb)
    if verb in ('send', 'steer'):
        payload['payload'] = {'text': 'must never reach native'}
    if verb == 'steer':
        payload['expected_turn_id'] = 'turn-from-native'
    if transport == 'mcp':
        name = 'harness_event_list' if verb == 'events' else 'harness_' + verb
        if verb in ('get', 'events'):
            payload.pop('idempotency_key')
        result = mcp(setup, monkeypatch, key, name, payload)
        assert not result['ok'], result
        assert result['error']['code'] in ('PERMISSION_DENIED', 'NOT_FOUND'), result
    else:
        path = f'/api/v1/harness/sessions/{session}'
        if verb in ('get', 'events'):
            response = client.get(path + ('/events' if verb == 'events' else ''),
                                  headers={'Authorization': 'Bearer ' + key})
        else:
            payload.pop('session_id')
            response = client.post(path + '/' + verb, json=payload,
                                   headers={'Authorization': 'Bearer ' + key})
        assert response.status_code in (403, 404), response.text
    assert native.native.sent == [] and not native.native.stopped
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 1
    wait_receipt(setup, admit(setup, binding, 'private-close', 'runtime.close',
                             session_id=session), stages=('SUCCEEDED',))


def test_committed_message_recovers_without_post_commit_notification(connected_local, monkeypatch):
    from okto_nexus.application.messages import MessageService
    from okto_nexus.adapters.inbound.mcp.tools import messages
    setup, binding, native = connected_local
    enable(setup, binding)
    original = messages.build_service
    def without_wake(*args, **kwargs):
        service = original(*args, **kwargs)
        service._runtime_wake = lambda: None
        return service
    monkeypatch.setattr(messages, 'build_service', without_wake)
    monkeypatch.setattr(MessageService, '_maybe_notify_inbox_subscribers', lambda *a, **kw: None)
    result = send(setup, monkeypatch)
    assert result['ok'], result
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        operations = [dict(row) for row in uow.connection.execute('SELECT operation_id,session_id,action FROM execution_operations')]
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM message_deliveries').fetchone()[0] == 1
    turn = next(row for row in operations if row['action'] == 'turn.submit')
    wait_receipt(setup, turn)
    assert native.opens == 1 and len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'lost-wake-close', 'runtime.close',
                             session_id=turn['session_id']), stages=('SUCCEEDED',))
