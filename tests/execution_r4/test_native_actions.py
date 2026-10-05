"""Native HTTP actions share canonical work; READY/provider qualification is synthetic."""

from concurrent.futures import ThreadPoolExecutor
import json

from fastapi.testclient import TestClient
import pytest

from test_mcp_session_capabilities import opening, activate, seed_work, rpc, envelope, args
from test_session_capabilities import issue


def native_cap(state, **kwargs):
    return activate(state, audience='nexus-native-session',
                    actions=kwargs.get('actions', ['handoff.get', 'handoff.claim', 'handoff.complete']))


def request_body(cap, action='claim', action_id='claim-1', **payload):
    supplied = {'handoff_id': 'work'}
    if action == 'claim':
        supplied['idempotency_key'] = 'claim-key'
    supplied.update(payload)
    return dict(action_id=action_id, scope=cap['scope'], action=action, payload=supplied)


def invoke(state, cap, body=None):
    return TestClient(state[1]).post('/v1/runtime/native-actions',
        headers={'Authorization': 'Bearer ' + cap['capability']},
        json=body or request_body(cap))


def rows(state):
    with state[0].connection_factory.unit_of_work(write=False) as uow:
        return (
            tuple(uow.connection.execute("SELECT status,claim_epoch FROM handoffs WHERE handoff_id='work'").fetchone()),
            uow.connection.execute('SELECT count(*) FROM execution_native_actions').fetchone()[0],
            uow.connection.execute("SELECT count(*) FROM events WHERE type='handoff.claimed'").fetchone()[0],
        )


@pytest.mark.parametrize('opening', ['strict'], indirect=True)
def test_native_public_lifecycle_durable_replay_and_strict_identity(opening):
    cap = native_cap(opening)
    seed_work(opening)
    context = request_body(cap, 'context', 'read-1')
    assert invoke(opening, cap, context).json()['result']['status'] == 'OPEN'
    claimed = invoke(opening, cap)
    assert claimed.status_code == 200, claimed.text
    assert claimed.headers['cache-control'] == 'no-store'
    epoch = claimed.json()['result']['claim_epoch']
    assert invoke(opening, cap).json() == claimed.json()
    complete = request_body(cap, 'complete', 'complete-1', claim_epoch=epoch, result={'summary': 'Reviewed.'})
    result = invoke(opening, cap, complete)
    assert result.status_code == 200, result.text
    assert result.json()['state'] == 'COMPLETED'
    assert invoke(opening, cap, complete).json() == result.json()
    assert rows(opening) == (('COMPLETED', 1), 3, 1)
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM sessions').fetchone()[0] == 0
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='handoff.completed'").fetchone()[0] == 1


@pytest.mark.parametrize('change', ['scope', 'boolean_revision', 'extra', 'agent', 'key', 'epoch', 'action'])
def test_native_invalid_or_cross_scope_requests_have_no_effect(opening, change):
    cap = native_cap(opening)
    seed_work(opening)
    body = request_body(cap)
    if change == 'scope':
        body['scope'] = dict(body['scope'], workspace_id='other')
    elif change == 'boolean_revision':
        body['scope'] = dict(body['scope'], credential_epoch=True)
    elif change == 'extra':
        body['extra'] = True
    elif change == 'agent':
        body['payload']['agent_id'] = 'other'
    elif change == 'key':
        body['payload']['idempotency_key'] = ''
    elif change == 'epoch':
        body['payload']['claim_epoch'] = True
    else:
        body['action'] = 'handoff.claim'
    response = invoke(opening, cap, body)
    assert response.status_code in (403, 422), response.text
    assert rows(opening) == (('OPEN', 0), 0, 0)


def test_native_actions_use_domain_permission_not_mcp_permission(opening):
    cap = native_cap(opening, actions=['tools/call', 'handoff_claim'])
    seed_work(opening)
    assert invoke(opening, cap).status_code == 403
    assert rows(opening) == (('OPEN', 0), 0, 0)


def test_native_route_rejects_mcp_canonical_and_missing_credentials(opening):
    cap = activate(opening)
    seed_work(opening)
    assert invoke(opening, cap).status_code == 401
    assert invoke(opening, dict(cap, capability=opening[1].state.test_agent_keys['subject'])).status_code == 401
    assert TestClient(opening[1]).post('/v1/runtime/native-actions', json=request_body(cap)).status_code == 401


def test_native_replay_revalidates_revocation_and_digest(opening):
    cap = native_cap(opening)
    seed_work(opening)
    assert invoke(opening, cap).status_code == 200
    assert invoke(opening, cap, request_body(cap, idempotency_key='different')).status_code == 409
    assert invoke(opening, cap, request_body(cap, action_id='different-id')).status_code == 409
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'")
    assert invoke(opening, cap).status_code == 401
    assert rows(opening) == (('CLAIMED', 1), 1, 1)


def test_native_receipt_failure_rolls_back_domain_and_claim_ownership(opening):
    cap = native_cap(opening)
    seed_work(opening)
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_native_receipt BEFORE INSERT ON execution_native_actions "
                               "BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    response = invoke(opening, cap)
    assert response.status_code == 503, response.text
    assert rows(opening) == (('OPEN', 0), 0, 0)
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM execution_tool_claims').fetchone()[0] == 0


def test_native_concurrent_replay_has_one_effect(opening):
    cap = native_cap(opening)
    seed_work(opening)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: invoke(opening, cap), range(2)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert responses[0].json() == responses[1].json()
    assert rows(opening) == (('CLAIMED', 1), 1, 1)


def test_mcp_and_native_share_the_same_claim_and_complete(opening):
    native = issue(opening, request_id='native-reservation', audience='nexus-native-session',
                   actions=['handoff.get', 'handoff.claim', 'handoff.complete']).json()
    mcp = activate(opening)
    seed_work(opening)
    claimed = envelope(rpc(opening, mcp['capability'], 'handoff_claim', args()))
    assert claimed['ok']
    epoch = claimed['data']['claim_epoch']
    adopted = invoke(opening, native, request_body(native, claim_epoch=epoch))
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()['result']['claim_epoch'] == epoch
    completed = invoke(opening, native, request_body(native, 'complete', 'complete-1',
                                                      claim_epoch=epoch, result='Completed from the native bridge.'))
    assert completed.status_code == 200, completed.text
    assert rows(opening) == (('COMPLETED', 1), 2, 1)


def test_native_to_mcp_completion_and_simultaneous_claim(opening):
    native = issue(opening, request_id='native-reservation', audience='nexus-native-session',
                   actions=['handoff.get', 'handoff.claim', 'handoff.complete']).json()
    mcp = activate(opening)
    seed_work(opening)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(invoke, opening, native)
        b = pool.submit(lambda: envelope(rpc(opening, mcp['capability'], 'handoff_claim', args())))
        native_result, mcp_result = a.result(), b.result()
    assert (native_result.status_code == 200) != mcp_result['ok'], (native_result.text, mcp_result)
    if native_result.status_code == 200:
        result = envelope(rpc(opening, mcp['capability'], 'handoff_complete', args(claim_epoch=1, result='Done.')))
        assert result['ok'], result
    else:
        assert native_result.status_code == 409
    assert rows(opening)[2] == 1


@pytest.mark.parametrize('raw', ['{"action_id":"a","action_id":"b"}', '{"result":NaN}', '[]'])
def test_native_strict_json(opening, raw):
    cap = native_cap(opening)
    response = TestClient(opening[1]).post('/v1/runtime/native-actions',
        headers={'Authorization': 'Bearer ' + cap['capability'], 'Content-Type': 'application/json'},
        content=raw)
    assert response.status_code in (400, 422), response.text


def test_native_bounds_before_effect_and_eligibility(opening):
    cap = native_cap(opening)
    seed_work(opening, target='other')
    assert invoke(opening, cap).status_code == 403
    body = request_body(cap, 'complete', 'big', claim_epoch=1, result='x' * 17000)
    assert invoke(opening, cap, body).status_code == 413
    assert rows(opening) == (('OPEN', 0), 0, 0)


def test_native_response_lost_after_commit_recovers_the_original_result(opening, monkeypatch):
    from okto_nexus.application.execution_native_actions import NativeActionService
    cap = native_cap(opening)
    seed_work(opening)
    original = NativeActionService.invoke
    receipts = []
    def lose_response(self, **kwargs):
        receipts.append(original(self, **kwargs))
        raise RuntimeError('Injected response loss after commit.')
    monkeypatch.setattr(NativeActionService, 'invoke', lose_response)
    response = invoke(opening, cap)
    assert response.status_code == 503
    assert response.json()['error']['possible_effect'] is True
    assert response.json()['error']['operation_id'] == 'claim-1'
    assert rows(opening) == (('CLAIMED', 1), 1, 1)
    monkeypatch.setattr(NativeActionService, 'invoke', original)
    assert invoke(opening, cap).json() == receipts[0]
    assert rows(opening) == (('CLAIMED', 1), 1, 1)


def test_native_rechecks_authority_after_transport_authentication(opening, monkeypatch):
    from okto_nexus.application.execution_native_actions import NativeActionService
    cap = native_cap(opening)
    seed_work(opening)
    original = NativeActionService.invoke
    def revoke(self, **kwargs):
        with opening[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'")
        return original(self, **kwargs)
    monkeypatch.setattr(NativeActionService, 'invoke', revoke)
    assert invoke(opening, cap).status_code == 403
    assert rows(opening) == (('OPEN', 0), 0, 0)


def test_native_oversized_claim_result_rolls_back(opening):
    cap = native_cap(opening)
    seed_work(opening)
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET payload=? WHERE handoff_id='work'", ('x' * 17000,))
    assert invoke(opening, cap).status_code == 413
    assert rows(opening) == (('OPEN', 0), 0, 0)


def test_native_complete_receipt_failure_rolls_back_notifications_and_result(opening):
    cap = native_cap(opening)
    seed_work(opening)
    assert invoke(opening, cap).status_code == 200
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_completion_receipt BEFORE INSERT ON execution_native_actions "
                               "WHEN NEW.action='complete' BEGIN SELECT RAISE(ABORT,'injected failure'); END")
        previous_messages = uow.connection.execute('SELECT count(*) FROM messages').fetchone()[0]
    body = request_body(cap, 'complete', 'complete-1', claim_epoch=1, result='Done.')
    assert invoke(opening, cap, body).status_code == 503
    assert rows(opening) == (('CLAIMED', 1), 1, 1)
    with opening[0].connection_factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT count(*) FROM messages').fetchone()[0] == previous_messages
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='handoff.completed'").fetchone()[0] == 0
        uow.connection.execute('DROP TRIGGER fail_completion_receipt')
    assert invoke(opening, cap, body).status_code == 200


def test_native_context_and_complete_cannot_cross_workspace_or_claim_scope(opening):
    cap = native_cap(opening)
    seed_work(opening, workspace='other-workspace')
    assert invoke(opening, cap, request_body(cap, 'context', 'read-1')).status_code == 404
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET workspace_id='ws',status='CLAIMED',claimed_by='subject',claim_epoch=1")
    body = request_body(cap, 'complete', 'complete-1', claim_epoch=1, result='Done.')
    assert invoke(opening, cap, body).status_code == 403


@pytest.mark.parametrize('expire_through_context', [False, True])
def test_native_context_replay_cannot_reveal_payload_after_claim_expiration(opening, expire_through_context):
    cap = native_cap(opening)
    seed_work(opening)
    assert invoke(opening, cap).status_code == 200
    body = request_body(cap, 'context', 'owned-context')
    original = invoke(opening, cap, body)
    assert original.status_code == 200 and 'payload' in original.json()['result']
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET lease_expires_at='2000-01-01T00:00:00.000000Z' WHERE handoff_id='work'")
    if expire_through_context:
        current = invoke(opening, cap, request_body(cap, 'context', 'current-context'))
        assert current.status_code == 200, current.text
        assert current.json()['result']['status'] == 'OPEN'
        assert 'payload' not in current.json()['result']
    assert invoke(opening, cap, body).status_code == 403
    assert invoke(opening, cap).status_code == 403


def test_native_replay_survives_new_application_and_connection_factory(opening):
    from dataclasses import replace
    from okto_nexus.adapters.inbound.http.app import build_app
    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    cap = native_cap(opening)
    seed_work(opening)
    original = invoke(opening, cap)
    assert original.status_code == 200
    deps = replace(opening[0], connection_factory=ConnectionFactory(opening[0].config))
    app = build_app(deps)
    replay = TestClient(app).post('/v1/runtime/native-actions',
        headers={'Authorization': 'Bearer ' + cap['capability']}, json=request_body(cap))
    assert replay.status_code == 200, replay.text
    assert replay.json() == original.json()
    assert rows(opening) == (('CLAIMED', 1), 1, 1)


def test_native_replay_does_not_disclose_context_after_visibility_changes(opening):
    cap = native_cap(opening)
    seed_work(opening)
    body = request_body(cap, 'context', 'read-1')
    assert invoke(opening, cap, body).status_code == 200
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET visibility='private',target=? WHERE handoff_id='work'",
                               (json.dumps({'strategy': 'direct', 'agent_id': 'other'}),))
    assert invoke(opening, cap, body).status_code == 403
