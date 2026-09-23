"""Explicit human answers, never implicit data from a binary approval."""
import json
import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_native_approvals import approval_peer, pending
from test_runtime_handoff_dispatch import wait_result

runtime = runtime_fixture

QUESTION = {"isBlocking": True, "questions": [{"id": "color", "header": "Color", "question": "Choose fixture color",
    "isOther": False, "isSecret": False, "options": [{"label": "blue", "description": "Fixture only"}]}]}


def test_native_input_requires_valid_explicit_operator_answers(runtime):
    _, client, _, _, operator, caller = runtime
    approval_peer(runtime, method="item/tool/requestUserInput", extra_params=QUESTION)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    url = f"/api/v1/approvals/{request['approval_id']}/decision"
    answer = {"answers": {"color": {"answers": ["blue"]}}}
    assert client.post(url, headers={"x-api-key": caller}, json={"decision": "approve", "response": answer}).status_code == 403
    assert client.post(url, headers={"x-api-key": operator}, json={"decision": "approve"}).status_code == 422
    assert client.post(url, headers={"x-api-key": operator}, json={"decision": "approve", "response": {"answers": {}}}).status_code == 422
    approved = client.post(url, headers={"x-api-key": operator}, json={"decision": "approve", "response": answer})
    assert approved.status_code == 200, approved.text
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["result"] == answer
    retry = client.post(url, headers={"x-api-key": operator}, json={"decision": "approve", "response": answer})
    assert retry.status_code == 200 and retry.json()["data"]["reused"], retry.text
    detail_url = f"/api/v1/approvals/{request['approval_id']}"
    assert client.get(detail_url, headers={"x-api-key": caller}).status_code == 403
    detail = client.get(detail_url, headers={"x-api-key": operator})
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["decision_detail"]["response"] == answer


FORM = {"mode": "form", "serverName": "fixture", "message": "Choose fixture options",
    "requestedSchema": {"type": "object", "properties": {
        "color": {"type": "string", "enum": ["blue", "green"]},
        "count": {"type": "integer", "minimum": 1, "maximum": 3},
        "enabled": {"type": "boolean"}}, "required": ["color", "count", "enabled"]}}


@pytest.mark.parametrize("method,params,answer", [
    ("item/tool/requestUserInput", QUESTION, {"answers": {"color": {"answers": ["blue"]}}}),
    ("mcpServer/elicitation/request", FORM, {"content": {"color": "blue", "count": 2, "enabled": True}}),
])
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_native_input_and_elicitation_keep_answer_separate_from_permission(runtime, method, params, answer, decision):
    _, client, _, _, operator, _ = runtime
    approval_peer(runtime, method=method, extra_params=params)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    url = f"/api/v1/approvals/{request['approval_id']}/decision"
    response = client.post(url, headers={"x-api-key": operator}, json={"decision": decision,
        **({"response": answer} if decision == "approve" else {})})
    assert response.status_code == 200, response.text
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])["result"]
    expected = (answer if method == "item/tool/requestUserInput" else {"action": "accept", **answer}) if decision == "approve" else (
        {"answers": {}} if method == "item/tool/requestUserInput" else {"action": "decline"})
    assert wire == expected


@pytest.mark.parametrize("content", [
    {"color": "red", "count": 2, "enabled": True},
    {"color": "blue", "count": True, "enabled": True},
    {"color": "blue", "count": 4, "enabled": True},
    {"color": "blue", "count": 2, "enabled": True, "extra": "not in schema"},
])
def test_invalid_form_answer_stays_pending_without_native_write(runtime, content):
    _, client, _, _, operator, _ = runtime
    approval_peer(runtime, method="mcpServer/elicitation/request", extra_params=FORM)
    send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    response = client.post(f"/api/v1/approvals/{request['approval_id']}/decision", headers={"x-api-key": operator},
        json={"decision": "approve", "response": {"content": content}})
    assert response.status_code == 422, response.text
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT state,response_payload FROM runtime_native_approvals").fetchone()
        assert row["state"] == "PENDING" and row["response_payload"] is None


@pytest.mark.parametrize("params", [
    {**QUESTION, "questions": [{**QUESTION["questions"][0], "isSecret": True}]},
    {**QUESTION, "isBlocking": False},
])
def test_unsupported_native_inputs_are_not_advertised_as_human_approvals(runtime, params):
    approval_peer(runtime, method="item/tool/requestUserInput", extra_params=params)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["error"]["code"] == -32601
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0


@pytest.mark.parametrize("params", [
    {"mode": "url", "serverName": "fixture", "url": "https://invalid.example", "elicitationId": "fixture"},
    {**FORM, "requestedSchema": {**FORM["requestedSchema"], "$ref": "https://invalid.example/schema"}},
    {**FORM, "turnId": None},
])
def test_uncorrelated_url_and_remote_schema_elicitation_are_rejected_without_followup(runtime, params):
    approval_peer(runtime, method="mcpServer/elicitation/request", extra_params=params)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["error"]["code"] == -32601
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_native_approvals").fetchone()[0] == 0


def test_input_answer_and_human_decision_rollback_together(runtime, monkeypatch):
    deps, client, _, _, operator, _ = runtime
    approval_peer(runtime, method="mcpServer/elicitation/request", extra_params=FORM)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    original = deps.approvals._approvals.mark_decided
    def fail_after_flip(*args, **kwargs):
        original(*args, **kwargs)
        from okto_nexus.errors import OktoNexusError, ErrorCode
        raise OktoNexusError(ErrorCode.CONFLICT, "Injected transactional cut", {})
    monkeypatch.setattr(deps.approvals._approvals, "mark_decided", fail_after_flip)
    url = f"/api/v1/approvals/{request['approval_id']}/decision"
    payload = {"decision": "approve", "response": {"content": {"color": "blue", "count": 2, "enabled": True}}}
    assert client.post(url, headers={"x-api-key": operator}, json=payload).status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT response_payload FROM runtime_native_approvals").fetchone()[0] is None
        assert uow.connection.execute("SELECT status FROM approvals WHERE approval_id=?", (request["approval_id"],)).fetchone()[0] == "pending"
    monkeypatch.setattr(deps.approvals._approvals, "mark_decided", original)
    assert client.post(url, headers={"x-api-key": operator}, json=payload).status_code == 200
    wait_result(runtime, sent["runtime_operations"][0])
    payload["response"]["content"]["color"] = "green"
    assert client.post(url, headers={"x-api-key": operator}, json=payload).status_code == 409


def test_expired_human_input_returns_decline_without_sending_the_answer(runtime):
    deps, client, _, _, operator, _ = runtime
    approval_peer(runtime, method="mcpServer/elicitation/request", extra_params=FORM)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_native_approvals SET expires_at='2000-01-01T00:00:00.000000Z'")
    payload = {"decision": "approve", "response": {"content": {"color": "blue", "count": 2, "enabled": True}}}
    assert client.post(f"/api/v1/approvals/{request['approval_id']}/decision", headers={"x-api-key": operator}, json=payload).status_code == 200
    wire = json.loads(wait_result(runtime, sent["runtime_operations"][0])["output_text"])
    assert wire["result"] == {"action": "decline"}
