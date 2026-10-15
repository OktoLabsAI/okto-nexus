"""Real reserved admission/leases authorize only the winning session's tools."""
import json

import pytest

from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt, admit
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, assert_unclaimed
from test_canonical_result_publication import current_turn, workspace
from test_reserved_handoff_admission import reserve
from test_mcp_session_capabilities import envelope


def capability(setup, binding, session_id, audience):
    actions = (['handoff.get', 'handoff.claim', 'handoff.complete'] if audience == 'native'
               else ['tools/call', 'handoff_get', 'handoff_claim', 'handoff_complete'])
    response = setup[2].post(f'/v1/runtime/sessions/{session_id}/capability',
        headers=setup[3]['subject'], json=dict(capability_request_id='tools-' + session_id,
            binding_id=binding['binding_id'], audience='nexus-' + ('native' if audience == 'native' else 'mcp') + '-session',
            actions=actions))
    assert response.status_code == 200, response.text
    return response.json()


def invoke(setup, cap, action, hid, **values):
    headers = {'Authorization': 'Bearer ' + cap['capability']}
    if cap['audience'] == 'nexus-native-session':
        payload = dict(handoff_id=hid, **values)
        if action == 'claim':
            payload['idempotency_key'] = 'recover-original-claim'
        response = setup[2].post('/v1/runtime/native-actions', headers=headers,
            json=dict(action_id='tools-' + action, scope=cap['scope'], action=action, payload=payload))
        return (response.json()['result'] if response.status_code == 200 else response.json()), response.status_code
    name = 'handoff_get' if action == 'context' else 'handoff_' + action
    response = setup[2].post('/mcp/', headers=headers | {'Accept': 'application/json, text/event-stream'},
        json=dict(jsonrpc='2.0', id=1, method='tools/call', params=dict(name=name,
            arguments=dict(workspace_id=workspace(setup), agent_id='subject', handoff_id=hid, **values))))
    result = envelope(response)
    return (result['data'], 200) if result['ok'] else (result, 403)


@pytest.mark.parametrize('audience', ['native', 'mcp'])
@pytest.mark.parametrize('warm', [False, True])
def test_reserved_winner_can_recover_and_complete_but_sibling_cannot(runtime, audience, warm):
    setup, binding, native = runtime
    deps, _, client, *_ = setup
    _, hid, _, port, held, claim = reserve(runtime, warm=warm)
    made = claim()
    operation_id = made['runtime_operation']['operation_id']
    client.portal.call(build_capacity_admission(deps, capacity=port).consume, operation_id)
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    winner_native = native.native
    cap = capability(setup, binding, turn['session_id'], audience)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        owner = uow.connection.execute('SELECT scope_json FROM execution_tool_claims WHERE handoff_id=?', (hid,)).fetchone()
        assert json.loads(owner[0]) == cap['scope']
    foreign = admit(setup, binding, 'sibling-session', 'runtime.start', new_session=True)
    wait_receipt(setup, foreign)
    sibling = capability(setup, binding, foreign['session_id'], audience)
    read, status = invoke(setup, sibling, 'context', hid)
    assert status == 200 and 'payload' not in read, read
    for action, values in [('claim', {}), ('complete', {'result': 'must not apply'})]:
        denied, status = invoke(setup, sibling, action, hid, claim_epoch=made['claim_epoch'], **values)
        assert status == 403 and denied['error']['code'] == 'PERMISSION_DENIED', denied
    read, status = invoke(setup, cap, 'context', hid)
    assert status == 200 and read['payload'] == 'Perform the authorized broadcast work', read
    recovered, status = invoke(setup, cap, 'claim', hid, claim_epoch=made['claim_epoch'])
    assert status == 200 and recovered['claim_epoch'] == made['claim_epoch'], recovered
    done, status = invoke(setup, cap, 'complete', hid, claim_epoch=made['claim_epoch'], result='Reviewed')
    assert status == 200 and done['status'] == 'COMPLETED', done
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM events WHERE type='handoff.completed'").fetchone()[0] == 1
    assert winner_native.sent == [('send_turn', turn['operation_id'])]
    # Business completion never fabricates a physical release of the running turn.
    async def release():
        return await port.release_capacity(held.request, held.reservation_id, 'COMPLETED')
    assert client.portal.call(release).state == 'RELEASE_PENDING'


def test_reserved_claim_scope_failure_rolls_back_entire_admission(runtime):
    _, hid, gid, port, held, claim = reserve(runtime)
    with runtime[0][0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_winner_scope BEFORE INSERT ON execution_tool_claims "
                               "BEGIN SELECT RAISE(ABORT,'claim scope cut'); END")
    with pytest.raises(Exception, match='claim scope cut'):
        claim()
    assert_unclaimed(runtime, hid, gid)
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_tool_claims').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_capacity_admissions').fetchone()[0] == 0
    assert runtime[0][2].portal.call(port.get_capacity_reservation, held.request).state == 'HELD'
    with runtime[0][0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER fail_winner_scope')
    claim()
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_tool_claims').fetchone()[0] == 1
    assert runtime[2].opens == 0


@pytest.mark.parametrize('audience', ['native', 'mcp'])
def test_reserved_winner_completion_preserves_verification(runtime, audience):
    setup, binding, _ = runtime
    deps, _, client, *_ = setup
    deps.config.feature_verification = True
    _, hid, _, port, _, claim = reserve(runtime, acceptance_criteria=['Review the evidence'])
    made = claim()
    client.portal.call(build_capacity_admission(deps, capacity=port).consume,
                       made['runtime_operation']['operation_id'])
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    cap = capability(setup, binding, turn['session_id'], audience)
    done, status = invoke(setup, cap, 'complete', hid, claim_epoch=made['claim_epoch'], result='Evidence')
    assert status == 200 and done['status'] == 'VERIFYING', done
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute('SELECT status,claimed_by,claim_epoch FROM handoffs '
            'WHERE handoff_id=?', (hid,)).fetchone()) == ('VERIFYING', 'subject', made['claim_epoch'])
        assert uow.connection.execute("SELECT COUNT(*) FROM events WHERE type='handoff.completed'").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM events WHERE type='handoff.verification_requested'").fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == 1
