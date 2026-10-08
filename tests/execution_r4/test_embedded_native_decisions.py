"""Installed embedded decision conformance with the remote suite's native peer."""
import time

import pytest
from nexus_connector_core import RuntimeEvent

from test_embedded_dispatch import (
    local_setup, connected_local, qualified_contract, admit, wait_receipt,
)


def test_inactive_agent_retained_approval_is_non_actionable(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, "retained-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    turned = admit(setup, binding, "retained-turn", "turn.submit",
                   session_id=opened["scope"]["session_id"], text="Hello")
    wait_receipt(setup, turned)
    owner = app.state.embedded_dispatch_owner
    with deps.connection_factory.unit_of_work() as uow:
        stream = dict(uow.connection.execute("SELECT * FROM execution_local_streams").fetchone())
        uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='subject'")
    request = dict(schema_version=1, request_id=7, request_hash="a" * 64,
        method="item/commandExecution/requestApproval",
        params={"threadId": "native-thread", "turnId": "turn-from-native", "itemId": "item"})
    # Core must assign sequence numbers and durably capture the approval.
    # Inserting a fabricated sequence directly into Server ingress conflicts
    # with the actual stream and prevents its final shutdown publication.
    client.portal.call(native.native.queue.put, RuntimeEvent(stream["server_id"], stream["executor_id"],
        stream["session_id"], stream["stream_epoch"], 0, "approval_request", request["method"],
        {"native_approval": request, "native_approval_display": dict(request)}, turned["operation_id"]))
    from test_agent_recovery_isolation import eventually
    def retained():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT 1 FROM execution_native_requests').fetchone() is not None
    eventually(retained)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT state FROM execution_native_requests").fetchone()[0] == "STALE"
        assert uow.connection.execute("SELECT is_active FROM agents WHERE agent_id='subject'").fetchone()[0] == 0
    response = client.get("/api/v1/approvals", headers=headers["operator"],
        params={"workspace": binding["workspace_id"], "status": "pending"})
    assert response.status_code == 200, response.text
    assert not [row for row in response.json()["data"]["items"]
                if row["action"] == "execution.native.respond"]


@pytest.mark.parametrize("kind,choice", [
    ("approval", "approve"), ("approval", "deny"),
    ("input", "approve"), ("input", "deny"),
])
@pytest.mark.parametrize("enabled", [True, False])
def test_embedded_native_decision_roundtrip(connected_local, kind, choice, enabled):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    deps.config.feature_hitl = enabled
    opened = admit(setup, binding, "decision-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    session = opened["scope"]["session_id"]
    turned = admit(setup, binding, "decision-turn", "turn.submit", session_id=session, text="Hello")
    wait_receipt(setup, turned)
    replies = []

    async def reply(request, decision, response):
        replies.append((request, decision, response))

    native.native.reply_native_approval = reply
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute("SELECT * FROM execution_local_streams").fetchone())
    request = dict(schema_version=1, request_id=7, request_hash="a" * 64,
        method="item/tool/requestUserInput" if kind == "input" else "item/commandExecution/requestApproval",
        params={"threadId": "native-thread", "turnId": "turn-from-native", "itemId": "item"})
    if kind == "input":
        request["params"].update(isBlocking=True, questions=[
            {"id": "question", "header": "Response", "question": "Provide input.", "isOther": True}])
    client.portal.call(native.native.queue.put, RuntimeEvent(
        stream["server_id"], stream["executor_id"], session, stream["stream_epoch"], 0,
        "input_request" if kind == "input" else "approval_request", request["method"],
        {"native_approval": request, "native_approval_display": dict(request)}, turned["operation_id"]))
    until = time.monotonic() + 10
    while True:
        queued = client.get("/api/v1/approvals", headers=headers["operator"],
            params={"workspace": binding["workspace_id"], "status": "pending"})
        assert queued.status_code == 200, queued.text
        rows = [row for row in queued.json()["data"]["items"] if row["action"] == "execution.native.respond"]
        if rows:
            break
        assert app.state.embedded_dispatch_owner.failure is None
        assert time.monotonic() < until, queued.text
        time.sleep(.02)
    assert len(rows) == 1
    detail = client.get("/api/v1/approvals/" + rows[0]["approval_id"], headers=headers["operator"])
    assert detail.status_code == 200, detail.text
    proposal = detail.json()["data"]["request_payload"]["kwargs"]
    body = {key: proposal[key] for key in ("approval_key", "expected_revision", "request_hash", "cas_token")}
    body.update(client_intent_id="embedded-native-decision", decision=choice)
    response = {"answers": {"question": {"answers": ["embedded-private-input-marker"]}}} if kind == "input" and choice == "approve" else None
    if response is not None:
        body["response"] = response
    # This fixture's direct turn is initiated by subject, so questions return
    # to subject. Permission decisions still belong to the operator.
    recipient = "subject" if kind == "input" else "operator"
    wrong_actor = "operator" if kind == "input" else "subject"
    assert client.post("/v1/runtime/approval-decisions", headers=headers[wrong_actor], json=body).status_code == 403
    assert replies == []
    confirmed = client.post("/v1/runtime/approval-decisions", headers=headers[recipient], json=body)
    assert confirmed.status_code == 202, confirmed.text
    decision = confirmed.json()
    repeated = client.post("/v1/runtime/approval-decisions", headers=headers[recipient], json=body)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["native_operation_id"] == decision["native_operation_id"]
    until = time.monotonic() + 10
    while True:
        result = client.get("/v1/runtime/approval-decisions/" + decision["decision_id"], headers=headers["operator"])
        assert result.status_code == 200, result.text
        view = result.json()
        if view["native_stage"] == ("SUBMITTED" if enabled else "REFUSED_BEFORE_EFFECT"):
            break
        # A durable Core in-flight receipt can precede the native reply ACK.
        # Only the final SUBMITTED/REFUSED state satisfies this test.
        assert view["native_stage"] in ("DISPATCH_PENDING", "OUTCOME_UNKNOWN"), str(view)
        assert app.state.embedded_dispatch_owner.failure is None
        assert time.monotonic() < until, view
        time.sleep(.02)
    assert view["canonical_state"] == ("CONFIRMED" if choice == "approve" else "DENIED")
    frozen = {key: request[key] for key in ("request_id", "request_hash", "method", "params")}
    expected = "accept" if choice == "approve" else "cancel" if kind == "input" else "decline"
    expected_replies = [(frozen, expected, response)] if enabled else []
    assert replies == expected_replies
    closed = admit(setup, binding, "decision-close", "runtime.close", session_id=session)
    wait_receipt(setup, closed, stages=("SUCCEEDED",))
    assert native.native.stopped and native.opens == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert "embedded-private-input-marker" not in "\n".join(uow.connection.iterdump())
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_link_tickets").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_decisions").fetchone()[0] == 1
    assert replies == expected_replies
