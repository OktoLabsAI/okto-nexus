"""Native permission requests traverse actual Core pipes and operator decisions."""
import asyncio
import json
import sys
import threading
import time

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


from functools import partial
from test_canonical_native_approvals import approval_peer as native_peer
approval_peer = partial(native_peer, operator_turn=True)


QUESTION = {"isBlocking": True, "questions": [{"id": "color", "header": "Color", "question": "Choose fixture color",
    "isOther": False, "isSecret": False, "options": [{"label": "blue", "description": "Fixture only"}]}]}
FORM = {"mode": "form", "serverName": "fixture", "message": "Choose fixture options",
    "requestedSchema": {"type": "object", "properties": {
        "color": {"type": "string", "enum": ["blue", "green"]},
        "count": {"type": "integer", "minimum": 1, "maximum": 3},
        "enabled": {"type": "boolean"}}, "required": ["color", "count", "enabled"]}}


def replies(log):
    return [r["response_to_server_request"] for r in map(json.loads, log.read_text(encoding="utf-8").splitlines())
            if "response_to_server_request" in r]


@pytest.mark.parametrize("method,params,answer", [
    ("item/tool/requestUserInput", QUESTION, {"answers": {"color": {"answers": ["blue"]}}}),
    ("mcpServer/elicitation/request", FORM, {"content": {"color": "blue", "count": 2, "enabled": True}}),
])
@pytest.mark.parametrize("choice", ["approve", "deny"])
def test_explicit_input_roundtrip_and_idempotency(connected_local, method, params, answer, choice):
    setup, _, turn, body, _, log = approval_peer(connected_local, method=method, extra_params=params)
    path = "/v1/runtime/approval-decisions"
    body.update(decision=choice)
    if choice == "approve":
        assert setup[2].post(path, headers=setup[3]["operator"], json=body).status_code == 422
        if method == "item/tool/requestUserInput":
            invalid = setup[2].post(path, headers=setup[3]["operator"], json=dict(body, response={"answers": {}}))
            assert invalid.status_code == 422, invalid.text
        body["response"] = answer
    assert setup[2].post(path, headers=setup[3]["subject"], json=body).status_code == 403
    response = setup[2].post(path, headers=setup[3]["operator"], json=body)
    assert response.status_code == 202, response.text
    repeat = setup[2].post(path, headers=setup[3]["operator"], json=body)
    assert repeat.status_code == 200 and repeat.json()["native_operation_id"] == response.json()["native_operation_id"], repeat.text
    wait_receipt(setup, turn, stages=("SUCCEEDED",))
    wire = replies(log)
    expected = (answer if method == "item/tool/requestUserInput" else {"action": "accept", **answer}) if choice == "approve" else (
        {"answers": {}} if method == "item/tool/requestUserInput" else {"action": "decline"})
    assert len(wire) == 1 and wire[0]["result"] == expected, wire


@pytest.mark.parametrize("content", [
    {"color": "red", "count": 2, "enabled": True},
    {"color": "blue", "count": True, "enabled": True},
    {"color": "blue", "count": 4, "enabled": True},
    {"color": "blue", "count": 2, "enabled": True, "extra": "not in schema"},
])
def test_invalid_input_remains_pending_without_native_effect(connected_local, content):
    setup, _, _, body, _, log = approval_peer(connected_local, method="mcpServer/elicitation/request", extra_params=FORM)
    response = setup[2].post("/v1/runtime/approval-decisions", headers=setup[3]["operator"], json=dict(body, response={"content": content}))
    assert response.status_code == 422, response.text
    assert replies(log) == []
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_decisions").fetchone()[0] == 0
        assert uow.connection.execute("SELECT state FROM execution_native_requests").fetchone()[0] == "PENDING"


@pytest.mark.parametrize("method,params", [
    ("item/tool/requestUserInput", {**QUESTION, "questions": [{**QUESTION["questions"][0], "isSecret": True}]}),
    ("item/tool/requestUserInput", {**QUESTION, "isBlocking": "false"}),
    ("mcpServer/elicitation/request", {"mode": "url", "serverName": "fixture", "url": "https://invalid.example", "elicitationId": "fixture"}),
    ("mcpServer/elicitation/request", {**FORM, "requestedSchema": {**FORM["requestedSchema"], "$ref": "https://invalid.example/schema"}}),
    ("mcpServer/elicitation/request", {**FORM, "turnId": None}),
])
def test_unsupported_inputs_never_create_human_approval(connected_local, method, params):
    setup, _, _, _, _, log = approval_peer(connected_local, method=method, extra_params=params, expect_request=False)
    wire = replies(log)
    assert len(wire) == 1 and wire[0]["error"]["code"] == -32601, wire
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_native_requests").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM approvals WHERE action='execution.native.respond'").fetchone()[0] == 0


def test_input_and_decision_rollback_together_then_retry_once(connected_local, monkeypatch):
    setup, _, turn, body, _, log = approval_peer(connected_local, method="mcpServer/elicitation/request", extra_params=FORM)
    deps = setup[0]
    original = deps.approvals._approvals.mark_decided
    def fail_after_flip(*args, **kwargs):
        original(*args, **kwargs)
        from okto_nexus.errors import OktoNexusError, ErrorCode
        raise OktoNexusError(ErrorCode.CONFLICT, "Injected transactional cut", {})
    monkeypatch.setattr(deps.approvals._approvals, "mark_decided", fail_after_flip)
    body["response"] = {"content": {"color": "blue", "count": 2, "enabled": True}}
    path = "/v1/runtime/approval-decisions"
    response = setup[2].post(path, headers=setup[3]["operator"], json=body)
    assert response.status_code == 409, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_decisions").fetchone()[0] == 0
        assert uow.connection.execute("SELECT status FROM approvals WHERE action='execution.native.respond'").fetchone()[0] == "pending"
    assert replies(log) == []
    monkeypatch.setattr(deps.approvals._approvals, "mark_decided", original)
    response = setup[2].post(path, headers=setup[3]["operator"], json=body)
    assert response.status_code == 202, response.text
    wait_receipt(setup, turn, stages=("SUCCEEDED",))
    assert len(replies(log)) == 1
    body["response"]["content"]["color"] = "green"
    assert setup[2].post(path, headers=setup[3]["operator"], json=body).status_code == 409


def test_expired_input_cannot_send_a_response_under_stale_authority(connected_local):
    setup, _, _, body, _, log = approval_peer(connected_local, method="mcpServer/elicitation/request", extra_params=FORM)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_native_requests SET expires_at='2000-01-01T00:00:00Z'")
    body["response"] = {"content": {"color": "blue", "count": 2, "enabled": True}}
    response = setup[2].post("/v1/runtime/approval-decisions", headers=setup[3]["operator"], json=body)
    assert response.status_code == 409, response.text
    assert replies(log) == []
