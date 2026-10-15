"""Canonical runtime input and reverse output obey private communication scopes."""
import json
import threading

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, connect_local, wait_receipt
from test_canonical_delivery import enable
from test_canonical_grant_regressions import mcp_helpers
from test_canonical_result_publication import emit, wait_result, current_turn
from test_agent_recovery_isolation import create_agent


def message(setup, caller, text="Private output"):
    from test_pr34_remediation import tool
    client = setup[2]
    client.headers["host"] = "127.0.0.1:8000"
    key = caller[3]["subject"]["Authorization"].removeprefix("Bearer ")
    return tool(client, key, "message_create", dict(project_root=str(setup[-1]), from_agent_id="caller",
        target=dict(strategy="direct", agent_id="subject"), subject="Private audience", body=text))


def tagged(setup):
    caller = create_agent(setup, "caller")
    _, _, client, headers, *_ = setup
    tag = "private_runtime_audience"
    assert client.post("/api/v1/tags", headers=headers["operator"], json=dict(key=tag)).status_code == 200
    for value in ("allowed", "excluded-private-rule"):
        assert client.post(f"/api/v1/tags/{tag}/values", headers=headers["operator"], json=dict(value=value)).status_code == 200
    for agent in ("subject", "caller"):
        response = client.patch(f"/api/v1/agents/{agent}", headers=headers["operator"], json=dict(tags={tag: ["allowed"]}))
        assert response.status_code == 200, response.text
    return caller, tag


def set_scope(setup, agent, direction, tag, value):
    response = setup[2].patch(f"/api/v1/agents/{agent}", headers=setup[3]["operator"],
        json=dict(comm_scope={direction: {tag: [value]}}))
    assert response.status_code == 200, response.text


def connect_workspace(setup):
    from okto_nexus.domain.ids import resolve_workspace_id
    deps, _, _, _, body, _, root = setup
    deps.runtime_dispatcher.recovery_seconds = 60
    body["workspace_id"] = resolve_workspace_id(str(root))
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=body["workspace_id"], root_realpath=str(root), last_seen_at=deps.clock.now_iso())
    setup, binding, native = connect_local(setup)
    enable(setup, binding)
    return setup, binding, native


@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_private_scope_denies_input_and_changed_reverse_audience_without_policy_leak(local_setup, monkeypatch, direction):
    from okto_nexus.application.runtime_results import RuntimeResultService
    setup = local_setup
    deps = setup[0]
    caller, tag = tagged(setup)
    actor = "subject" if direction == "inbound" else "caller"
    set_scope(setup, actor, direction, tag, "excluded-private-rule")
    denied = message(setup, caller, "Excluded input")
    assert denied.get("error", {}).get("code") == "PERMISSION_DENIED", denied
    assert tag not in json.dumps(denied) and "excluded-private-rule" not in json.dumps(denied)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "delivery_outbox", "execution_operations"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
    set_scope(setup, actor, direction, tag, "allowed")
    setup, binding, native = connect_workspace(setup)
    entered, release = threading.Event(), threading.Event()
    original = RuntimeResultService.prepare
    def held(self, result_id, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(self, result_id, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeResultService, "prepare", held)
        try:
            sent = message(setup, caller)
            assert sent["ok"], sent
            turn = current_turn(setup)
            wait_receipt(setup, turn)
            emit(setup, native, turn, "Retained private output")
            if not entered.wait(5):
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    pytest.fail(str([dict(r) for r in uow.connection.execute("SELECT publication_state,publication_reason,output_text FROM runtime_results")]))
            set_scope(setup, "caller" if direction == "inbound" else "subject", direction, tag, "excluded-private-rule")
        finally:
            release.set()
        stored = wait_result(setup, "BLOCKED")
    assert stored["output_text"] == "Retained private output" and not stored["publication_message_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM messages WHERE subject='Runtime result'").fetchone()[0] == 0
        envelope = uow.connection.execute("SELECT envelope FROM delivery_outbox").fetchone()[0]
    assert tag not in envelope and "excluded-private-rule" not in envelope and "comm_scope" not in envelope
    assert native.opens == 1 and len(native.native.sent) == 1


def test_private_reply_does_not_require_origin_to_send_to_itself(local_setup):
    setup = local_setup
    caller, tag = tagged(setup)
    # Origin can send to the subject's tag, but cannot send to its own tag.
    assert setup[2].patch("/api/v1/agents/caller", headers=setup[3]["operator"],
        json=dict(tags={tag: ["excluded-private-rule"]})).status_code == 200
    set_scope(setup, "caller", "outbound", tag, "allowed")
    setup, binding, native = connect_workspace(setup)
    sent = message(setup, caller)
    assert sent["ok"], sent
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    emit(setup, native, turn, "Private response")
    row = wait_result(setup, "PUBLISHED")
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        recipients = [r[0] for r in uow.connection.execute("SELECT recipient_agent_id FROM message_deliveries WHERE message_id=?",
            (row["publication_message_id"],))]
        assert recipients == ["caller"]
        assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 1
    assert native.opens == 1 and len(native.native.sent) == 1
