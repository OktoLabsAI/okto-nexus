"""Claude stream permissions and explicit questions traverse the current Core."""
import asyncio
import json
import sys
import time

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_runtime_claude_approvals import PEER

pytestmark = pytest.mark.parametrize('local_setup', ['claude_stream'], indirect=True)


def native_peer(connected, *, tool_name='Write', inputs=None, expect_request=True, operator_turn=False):
    from nexus_connector_core.native.adapters.claude_code_stream import ClaudeCodeStreamConnector
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    setup, binding, _ = connected
    setup[0].config.feature_hitl = True
    source = PEER.replace('    if value.get("type")=="user":',
        '    if value.get("type")=="control_request":\n'
        '        emit({"type":"control_response","response":{"subtype":"success","request_id":value["request_id"],"response":{}}})\n'
        '    elif value.get("type")=="user":')
    source = source.replace('"tool_name":"Write"', '"tool_name":'+repr(tool_name))
    source = source.replace('    elif value.get("type")=="control_response":',
        '    elif value.get("type")=="fixture_ending":\n'
        '        emit({"type":"control_cancel_request","request_id":"permission-1"} if value["ending"]=="cancel" else {"type":"result","subtype":"success","result":"already ended"})\n'
        '    elif value.get("type")=="control_response":')
    if inputs is not None:
        source = source.replace('"input":{"file_path":"fixture.txt","content":"fixture"}', '"input":'+repr(inputs))
    log = setup[-1] / 'claude-permission-wire.jsonl'
    source = source.replace('    value=json.loads(line)',
        '    value=json.loads(line)\n'
        '    with open(sys.argv[1],"a",encoding="utf-8") as log: log.write(json.dumps(value)+"\\n")')
    peers = []
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            peer = ClaudeCodeStreamConnector(binary=sys._base_executable,
                argv=['-u', '-c', source, str(log)], cwd=str(setup[-1]), env={},
                version_argv=['-c', "print('2.1.281 (Claude Code)')"])
            peer.native_approvals_enabled = True
            peers.append(peer)
            native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
            return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch, context=context)
    setup[1].state.embedded_dispatch_owner.native_factory = Factory()
    opened = admit(setup, binding, 'claude-permission-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    if operator_turn:
        from test_operator_runtime import resolve, submit
        response = resolve(setup, binding, intent_id='claude-permission-turn', intent='turn.submit',
            session_id=opened['session_id'], text='Isolated question for the operator')
        assert response.status_code == 200, response.text
        turn = response.json()
        submitted = submit(setup, turn)
        assert submitted.status_code == 202, submitted.text
    else:
        turn = admit(setup, binding, 'claude-permission-turn', 'turn.submit', session_id=opened['session_id'], text='Isolated permission fixture')
    wait_receipt(setup, turn)
    if not expect_request:
        wait_receipt(setup, turn, stages=('SUCCEEDED',))
        return setup, binding, turn, None, log, peers[0]
    deadline = time.monotonic() + 12
    while True:
        response = setup[2].get('/api/v1/approvals', headers=setup[3]['operator'],
            params=dict(workspace=binding['workspace_id'], status='pending'))
        assert response.status_code == 200, response.text
        rows = [r for r in response.json()['data']['items'] if r['action'] == 'execution.native.respond']
        if rows:
            break
        assert time.monotonic() < deadline, response.text
        time.sleep(.02)
    assert len(rows) == 1
    detail = setup[2].get('/api/v1/approvals/'+rows[0]['approval_id'], headers=setup[3]['operator'])
    proposal = detail.json()['data']['request_payload']['kwargs']
    body = {k: proposal[k] for k in ('approval_key', 'expected_revision', 'request_hash', 'cas_token')}
    body.update(client_intent_id='claude-permission-decision', decision='approve')
    return setup, binding, turn, body, log, peers[0]


def replies(log):
    return [r for r in map(json.loads, log.read_text(encoding='utf-8').splitlines()) if r.get('type') == 'control_response']


def completed_result(setup, turn):
    result = wait_receipt(setup, turn, stages=('SUCCEEDED',))
    deadline = time.monotonic() + 10
    while result.get('result') is None:
        assert time.monotonic() < deadline, result
        time.sleep(.02)
        result = setup[2].get('/v1/runtime/operations/'+turn['operation_id'], headers=setup[3]['subject']).json()
    return result['result']


@pytest.mark.parametrize('decision,wire', [('approve', 'allow'), ('deny', 'deny')])
def test_claude_permission_uses_operator_authority_and_one_exact_reply(connected_local, decision, wire):
    setup, _, turn, body, log, _ = native_peer(connected_local)
    body['decision'] = decision
    path = '/v1/runtime/approval-decisions'
    assert setup[2].post(path, headers=setup[3]['subject'], json=body).status_code == 403
    response = setup[2].post(path, headers=setup[3]['operator'], json=body)
    assert response.status_code == 202, response.text
    repeat = setup[2].post(path, headers=setup[3]['operator'], json=body)
    assert repeat.status_code == 200 and repeat.json()['native_operation_id'] == response.json()['native_operation_id'], repeat.text
    result = completed_result(setup, turn)
    actual = replies(log)
    assert len(actual) == 1 and actual[0]['response']['request_id'] == 'permission-1', actual
    assert json.loads(result['output_text']) == actual[0]
    answer = actual[0]['response']['response']
    assert answer['behavior'] == wire and 'updatedPermissions' not in answer
    if decision == 'approve':
        assert answer['updatedInput'] == dict(file_path='fixture.txt', content='fixture')


@pytest.mark.parametrize('answer,multi,decision', [('blue', False, 'approve'),
    (['blue','green'], True, 'approve'), ('custom fixture answer', False, 'approve'), (None, False, 'deny')])
def test_claude_question_requires_explicit_answer_and_preserves_question(connected_local, answer, multi, decision):
    questions = [dict(question='Choose fixture color', header='Color', multiSelect=multi,
        options=[dict(label='blue', description='Fixture blue'), dict(label='green', description='Fixture green')])]
    setup, _, turn, body, log, _ = native_peer(connected_local, tool_name='AskUserQuestion', inputs=dict(questions=questions), operator_turn=True)
    path = '/v1/runtime/approval-decisions'
    assert setup[2].post(path, headers=setup[3]['operator'], json=body).status_code == 422
    body['decision'] = decision
    if decision == 'approve':
        body['response'] = dict(answers={'Choose fixture color': answer})
    response = setup[2].post(path, headers=setup[3]['operator'], json=body)
    assert response.status_code == 202, response.text
    wait_receipt(setup, turn, stages=('SUCCEEDED',))
    actual = replies(log)
    assert len(actual) == 1, actual
    wire = actual[0]['response']['response']
    if decision == 'approve':
        assert wire == dict(behavior='allow', updatedInput=dict(questions=questions, answers={'Choose fixture color': answer}))
    else:
        assert wire['behavior'] == 'deny' and 'updatedInput' not in wire


@pytest.mark.parametrize('tool_name', ['ExitPlanMode', 'AskUserQuestion', 'unknown'])
def test_claude_unsupported_permission_cannot_change_policy_or_invent_answer(connected_local, tool_name):
    setup, _, _, _, log, _ = native_peer(connected_local, tool_name=tool_name, expect_request=False)
    actual = replies(log)
    assert len(actual) == 1 and actual[0]['response']['subtype'] == 'error', actual
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_native_requests').fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM approvals WHERE action='execution.native.respond'").fetchone()[0] == 0


@pytest.mark.parametrize('ending', ['cancel', 'terminal'])
def test_claude_native_cancellation_or_terminal_prevents_late_decision(connected_local, ending):
    from test_agent_recovery_isolation import eventually
    setup, binding, turn, body, log, peer = native_peer(connected_local)
    peer._write_json(dict(type='fixture_ending', ending=ending))
    eventually(lambda: not peer._approval_requests['permission-1']['pending'])
    path = '/v1/runtime/approval-decisions'
    response = setup[2].post(path, headers=setup[3]['operator'], json=body)
    if response.status_code == 202:
        def refused():
            result = setup[2].get(path+'/'+response.json()['decision_id'], headers=setup[3]['operator'])
            assert result.status_code == 200, result.text
            return result.json()['native_stage'] == 'REFUSED_BEFORE_EFFECT'
        eventually(refused)
    else:
        assert response.status_code in (403, 409), response.text
    assert replies(log) == []
    if ending == 'terminal':
        assert completed_result(setup, turn)['output_text'] == 'already ended'
        assert 'subject' not in setup[1].state.embedded_dispatch_owner.agents.blocked
        following = admit(setup, binding, 'after-late-permission', 'turn.submit',
            session_id=turn['session_id'], text='The session remains available')
        wait_receipt(setup, following, stages=('SUCCEEDED',))
    closed = admit(setup, binding, 'claude-late-close', 'runtime.close', session_id=turn['session_id'])
    # Public close allows 30 seconds to drain and 15 to interrupt an active turn.
    deadline = time.monotonic() + 55
    while True:
        result = setup[2].get('/v1/runtime/operations/'+closed['operation_id'], headers=setup[3]['subject']).json()
        if result.get('executor_stage') == 'SUCCEEDED':
            break
        assert time.monotonic() < deadline, result
        time.sleep(.05)
    assert peer._proc.poll() is not None


def test_claude_consumed_request_id_cannot_authorize_following_turn(connected_local):
    setup, binding, turn, body, log, _ = native_peer(connected_local)
    response = setup[2].post('/v1/runtime/approval-decisions', headers=setup[3]['operator'], json=dict(body, decision='deny'))
    assert response.status_code == 202, response.text
    wait_receipt(setup, turn, stages=('SUCCEEDED',))
    second = admit(setup, binding, 'claude-second-permission', 'turn.submit',
        session_id=turn['session_id'], text='Do not reuse a consumed native request')
    wait_receipt(setup, second, stages=('SUCCEEDED',))
    actual = replies(log)
    assert len(actual) == 2 and actual[1]['response']['subtype'] == 'error', actual
    assert 'behavior' not in actual[1]['response']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_native_requests').fetchone()[0] == 1
