"""Claude control protocol uses the shared durable approval service."""
import sys
import time
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_native_approvals import pending
from test_runtime_handoff_dispatch import wait_result

runtime = runtime_fixture

PEER = r'''
import json,sys
def emit(value):
    print(json.dumps(value),flush=True)
for line in sys.stdin:
    value=json.loads(line)
    if value.get("type")=="user":
        emit({"type":"system","subtype":"init","session_id":"fixture-session"})
        emit({"type":"control_request","request_id":"permission-1","request":{
            "subtype":"can_use_tool","tool_name":"Write","tool_use_id":"tool-1",
            "input":{"file_path":"fixture.txt","content":"fixture"}}})
    elif value.get("type")=="control_response":
        emit({"type":"result","subtype":"success","result":json.dumps(value)})
'''


def claude_peer(runtime, source=PEER):
    from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
    deps, client, root, _, operator, _ = runtime
    deps.config.feature_hitl = True
    deps.harness_connector_factories["claude_code"] = lambda **kwargs: ClaudeCodeStreamConnector(
        binary=sys._base_executable, argv=["-u", "-c", source], cwd=root, env=kwargs["backend"]["env"],
        version_argv=["-c", "print('2.1.281 (Claude Code)')"])
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "claude_code", "endpoint_id": "endpoint-claude_code.stream", "project_root": root})
    assert opened.status_code == 200, opened.text
    return opened.json()["data"]["session_id"]


@pytest.mark.parametrize("decision,wire", [("approve", "allow"), ("reject", "deny")])
def test_claude_permission_roundtrip_uses_canonical_hitl(runtime, decision, wire):
    _, client, _, _, operator, caller = runtime
    claude_peer(runtime)
    sent = send_message(runtime, body="Isolated permission fixture")
    request = pending(runtime)
    url = f"/api/v1/approvals/{request['approval_id']}/decision"
    assert client.post(url, headers={"x-api-key": caller}, json={"decision": decision}).status_code == 403
    response = client.post(url, headers={"x-api-key": operator}, json={"decision": decision})
    assert response.status_code == 200, response.text
    result = wait_result(runtime, sent["runtime_operations"][0])
    assert f'"behavior": "{wire}"' in result["output_text"]
    assert '"request_id": "permission-1"' in result["output_text"]
    assert "updatedPermissions" not in result["output_text"]
    if wire == "allow":
        assert '"updatedInput"' in result["output_text"]


@pytest.mark.parametrize("ending", ["cancel", "terminal"])
def test_claude_late_decision_cannot_revive_native_request(runtime, ending):
    deps, client, _, _, operator, _ = runtime
    signal = ({"type": "control_cancel_request", "request_id": "permission-1"} if ending == "cancel"
              else {"type": "result", "subtype": "success", "result": "already ended"})
    source = PEER.replace('    elif value.get("type")=="control_response":',
                          f'        emit({signal!r})\n    elif value.get("type")=="control_response":')
    claude_peer(runtime, source)
    sent = send_message(runtime, body="Isolated cancelled permission")
    # Wait for the durable request; terminal-before-intercept legitimately
    # rejects without creating a human approval.
    deadline = time.monotonic() + 6
    row = None
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_native_approvals").fetchone()
        if row and row["state"] != "NEW":
            break
        time.sleep(.01)
    assert row and row["state"] != "NEW"
    if row["approval_id"]:
        response = client.post(f"/api/v1/approvals/{row['approval_id']}/decision",
            headers={"x-api-key": operator}, json={"decision": "approve"})
        assert response.status_code == 200, response.text
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            state = uow.connection.execute("SELECT state FROM runtime_native_approvals").fetchone()[0]
        if state == "NOT_SENT":
            break
        time.sleep(.01)
    assert state == "NOT_SENT"
    if ending == "terminal":
        assert wait_result(runtime, sent["runtime_operations"][0])["output_text"] == "already ended"


def test_claude_consumed_request_id_is_not_reused_in_next_turn(runtime):
    _, client, _, _, operator, _ = runtime
    claude_peer(runtime)
    first = send_message(runtime, body="First isolated permission")
    request = pending(runtime)
    response = client.post(f"/api/v1/approvals/{request['approval_id']}/decision",
        headers={"x-api-key": operator}, json={"decision": "reject"})
    assert response.status_code == 200, response.text
    wait_result(runtime, first["runtime_operations"][0])
    second = send_message(runtime, body="Second isolated permission")
    result = wait_result(runtime, second["runtime_operations"][0])
    wire = json.loads(result["output_text"])
    assert wire["response"]["subtype"] == "error"
    assert "behavior" not in wire["response"]
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_native_approvals").fetchone()[0] == 1


@pytest.mark.parametrize("tool_name", ["ExitPlanMode", "AskUserQuestion", "unknown"])
def test_claude_permission_does_not_implicitly_change_policy_or_answer_questions(runtime, tool_name):
    claude_peer(runtime, PEER.replace('"tool_name":"Write"', f'"tool_name":{json.dumps(tool_name)}'))
    sent = send_message(runtime, body="Unsupported control fixture")
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["response"]["subtype"] == "error"
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0


@pytest.mark.parametrize("answer,multi,decision", [("blue", False, "approve"),
    (["blue", "green"], True, "approve"), ("custom fixture answer", False, "approve"), (None, False, "reject")])
def test_claude_question_requires_explicit_answer_then_returns_original_questions(runtime, answer, multi, decision):
    _, client, _, _, operator, _ = runtime
    questions = [{"question": "Choose fixture color", "header": "Color", "multiSelect": multi,
                  "options": [{"label": "blue", "description": "Fixture blue"}, {"label": "green", "description": "Fixture green"}]}]
    source = PEER.replace('"tool_name":"Write"', '"tool_name":"AskUserQuestion"').replace(
        '"input":{"file_path":"fixture.txt","content":"fixture"}', '"input":' + repr({"questions": questions}))
    claude_peer(runtime, source)
    sent = send_message(runtime, body="Isolated question fixture")
    request = pending(runtime)
    url = f"/api/v1/approvals/{request['approval_id']}/decision"
    assert client.post(url, headers={"x-api-key": operator}, json={"decision": "approve"}).status_code == 422
    response = client.post(url, headers={"x-api-key": operator}, json={"decision": decision,
        **({"response": {"answers": {"Choose fixture color": answer}}} if decision == "approve" else {})})
    assert response.status_code == 200, response.text
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    if decision == "approve":
        assert wire["response"]["response"] == {"behavior": "allow", "updatedInput": {
            "questions": questions, "answers": {"Choose fixture color": answer}}}
    else:
        assert wire["response"]["response"]["behavior"] == "deny"
        assert "updatedInput" not in wire["response"]["response"]
