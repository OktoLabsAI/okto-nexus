"""Every canonical target strategy reaches the same durable Core delivery path."""
import json

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_result_publication import current_turn


@pytest.mark.parametrize("target", [
    dict(strategy="direct", agent_id="subject"), dict(strategy="capability", capability="review"),
    dict(strategy="role", role="reviewer"), dict(strategy="tag", selector={"org": ["fixture"]}),
    dict(strategy="broadcast"),
], ids=["direct", "capability", "role", "tag", "broadcast"])
def test_all_target_strategies_preserve_authenticated_envelope_and_single_claim(connected_local, monkeypatch, target):
    from test_vertical_inventory import _Native
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    assert client.post("/api/v1/capabilities", headers=headers["operator"], json=dict(name="review")).status_code == 200
    assert client.post("/api/v1/tags", headers=headers["operator"], json=dict(key="org")).status_code == 200
    assert client.post("/api/v1/tags/org/values", headers=headers["operator"], json=dict(value="fixture")).status_code == 200
    edited = client.patch("/api/v1/agents/subject", headers=headers["operator"],
        json=dict(role="reviewer", capabilities={"review": True}, tags={"org": ["fixture"]}))
    assert edited.status_code == 200, edited.text
    enable(setup, binding)
    payloads = []
    original = _Native.send
    async def capture(peer, verb, payload, operation_id, **kwargs):
        payloads.append(payload)
        return await original(peer, verb, payload, operation_id, **kwargs)
    monkeypatch.setattr(_Native, "send", capture)
    sent = send(setup, monkeypatch, target=target)
    assert sent["ok"], sent
    data = sent["data"]
    assert data["delivered_count"] == 1 and data["recipients"] == ["subject"]
    assert len(data["runtime_operations"]) == 1
    wait_receipt(setup, current_turn(setup))
    assert native.opens == 1 and len(native.native.sent) == 1 and len(payloads) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM delivery_outbox").fetchone()
        envelope = json.loads(row["envelope"])
        assert envelope["operation_id"] == data["runtime_operations"][0]
        assert envelope["sender_agent_id"] == "operator" and envelope["recipient_agent_id"] == "subject"
        assert envelope["message_id"] == data["message_id"]
        assert envelope["subject"] == "Canonical conversation"
        assert "Please review this message." in str(payloads[0])
        assert data["message_id"] in str(payloads[0]) and envelope["operation_id"] in str(payloads[0])
        delivery = uow.connection.execute("SELECT consumer_kind,consumer_operation_id FROM message_deliveries WHERE message_id=?", (data["message_id"],)).fetchone()
        assert delivery[:] == ("push", envelope["operation_id"])
        assert deps.repos.agents.get(uow, "subject").capabilities == {"review": True}
        assert uow.connection.execute("SELECT COUNT(*) FROM harness_sessions").fetchone()[0] == 0
