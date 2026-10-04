"""Session-authenticated answers retain their own authority through dispatch."""
import json

import pytest

from okto_nexus.domain.execution_principal import current_execution_principal, current_execution_tool
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError
from okto_nexus.application.execution_input_authority import MANAGED_INPUT_PREFIX
from okto_nexus.application.execution_native_decisions import validate_native_dispatch
from test_open_bootstrap import opening
from test_native_decisions import decision_state
from test_session_capabilities import issue, service
from test_mcp_session_capabilities import rpc, envelope
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from pathlib import Path


@pytest.mark.parametrize('decision_state', ['agent_input'], indirect=True)
@pytest.mark.parametrize('revoke_before_dispatch', [False, True])
def test_managed_reply_is_scoped_and_reauthorized_at_dispatch(opening, decision_state, revoke_before_dispatch):
    deps, app, body = decision_state
    response = issue(opening, actions=['tools/call', 'runtime_input_list', 'runtime_input_respond'])
    assert response.status_code == 200, response.text
    issued = response.json()
    authority = service(opening)
    principal = authority.authenticate_transport(token=issued['capability'], audience='nexus-mcp-session')
    principal_token = current_execution_principal.set(principal)
    tool_token = current_execution_tool.set('runtime_input_list')
    context = RuntimeRequestContext('subject', 'session_capability')
    try:
        listed = deps.native_decisions.pending_inputs(context=context)
        assert len(listed) == 1
        with pytest.raises(OktoNexusError):
            deps.native_decisions.pending_inputs(context=context, workspace_id='other-workspace')
        with pytest.raises(OktoNexusError):
            deps.native_decisions.pending_inputs(context=RuntimeRequestContext('operator', 'session_capability'))
        current_execution_tool.set('runtime_input_respond')
        result, reused = deps.native_decisions.confirm(context=context, request=body)
        assert not reused and result['actor_agent_id'] == 'subject'
    finally:
        current_execution_tool.reset(tool_token)
        current_execution_principal.reset(principal_token)

    with deps.connection_factory.unit_of_work() as uow:
        decision = uow.connection.execute('SELECT * FROM execution_decisions').fetchone()
        guard = decision['actor_guard_digest']
        assert guard.startswith(MANAGED_INPUT_PREFIX)
        assert issued['capability'] not in guard and principal.secret_hash not in guard
        operation = uow.connection.execute('SELECT * FROM execution_operations WHERE decision_id=?',
                                           (decision['decision_id'],)).fetchone()
        semantic = json.loads(operation['semantic_payload'])
        if revoke_before_dispatch:
            uow.connection.execute('UPDATE execution_session_capabilities SET revoked_at=? WHERE capability_id=?',
                                   (deps.clock.now_iso(), principal.capability_id))
            with pytest.raises(OktoNexusError):
                validate_native_dispatch(uow, operation=operation, semantic=semantic, access=opening[2])
        else:
            validate_native_dispatch(uow, operation=operation, semantic=semantic, access=opening[2])


@pytest.mark.parametrize('decision_state,can_answer', [('agent_input', True), ('input', False), ('mcp_permission', False)], indirect=['decision_state'])
def test_managed_questions_use_public_mcp_tools(opening, decision_state, can_answer):
    deps, _, body = decision_state
    response = issue(opening, actions=['tools/call', 'runtime_input_list', 'runtime_input_respond'])
    assert response.status_code == 200, response.text
    token = response.json()['capability']
    listed = envelope(rpc(opening, token, 'runtime_input_list'))
    assert listed['ok'], listed
    if not can_answer:
        assert listed['data']['items'] == []
        denied = envelope(rpc(opening, token, 'runtime_input_respond', {'request': body}))
        assert denied['ok'] is False, denied
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM execution_decisions').fetchone()[0] == 0
        return
    item, = listed['data']['items']
    assert item['recipient_agent_id'] == 'subject'
    assert item['approval_key'] == body['approval_key']
    denied = envelope(rpc(opening, token, 'runtime_input_list', {'workspace_id': 'other'}))
    assert denied['ok'] is False
    malformed = dict(body, response={'answers': {'wrong': {'answers': ['blue']}}})
    invalid = envelope(rpc(opening, token, 'runtime_input_respond', {'request': malformed}))
    assert invalid['ok'] is False
    assert len(envelope(rpc(opening, token, 'runtime_input_list'))['data']['items']) == 1
    answered = envelope(rpc(opening, token, 'runtime_input_respond', {'request': body}))
    assert answered['ok'], answered
    assert answered['data']['decision']['canonical_state'] == 'CONFIRMED'
    assert answered['data']['decision']['native_stage'] == 'DISPATCH_PENDING'
    assert envelope(rpc(opening, token, 'runtime_input_list'))['data']['items'] == []


@pytest.mark.parametrize('decision_state', ['agent_input'], indirect=True)
def test_native_question_tools_share_canonical_decision_and_replay(opening, decision_state):
    deps, app, body = decision_state
    issued = issue(opening, audience='nexus-native-session', actions=['runtime.input.list', 'runtime.input.respond'])
    assert issued.status_code == 200, issued.text
    cap = issued.json()
    client = TestClient(app)
    schema = json.loads((Path(__file__).parents[2]/'plans/contratos/http-target.schema.json').read_text())
    def call(action, payload, action_id='pi-question'):
        request = {'action_id':action_id, 'scope':cap['scope'], 'action':action, 'payload':payload}
        Draft202012Validator(dict(schema, **{'$ref':'#/$defs/NativeActionRequest'}), format_checker=FormatChecker()).validate(request)
        result = client.post('/v1/runtime/native-actions', headers={'Authorization': 'Bearer '+cap['capability']}, json=request)
        if result.status_code == 200:
            Draft202012Validator(dict(schema, **{'$ref':'#/$defs/NativeActionResult'})).validate(result.json())
        return result
    listed = call('input_list', {})
    assert listed.status_code == 200, listed.text
    assert len(listed.json()['result']['items']) == 1
    answer = {k:v for k,v in body.items() if k != 'client_intent_id'}
    accepted = call('input_respond', {'request':answer})
    assert accepted.status_code == 200, accepted.text
    result = accepted.json()['result']
    assert result['decision']['canonical_state'] == 'CONFIRMED' and result['reused'] is False
    replay = call('input_respond', {'request':answer})
    assert replay.status_code == 200 and replay.json()['result']['reused'] is True, replay.text
    changed = dict(answer, response={'answers': {'question': {'answers': ['different']}}})
    conflict = call('input_respond', {'request':changed})
    assert conflict.status_code == 409, conflict.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT * FROM execution_decisions').fetchone()
        assert row['actor_guard_digest'].startswith(MANAGED_INPUT_PREFIX)
        assert uow.connection.execute('SELECT count(*) FROM execution_decisions').fetchone()[0] == 1
