"""Only approved equivalent endpoints may receive a proven-unsent operation."""
import json
import time
from pathlib import Path

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_safe_retry import busy_lane
from test_runtime_outbox import wait_status

runtime = runtime_fixture


def fallback_pair(runtime, monkeypatch, group="interchangeable-fixture", *, agent="worker", other_workspace=False,
                  profile_id="profile-pi", open_target=True):
    deps, client, root, _, operator, _ = runtime
    changed = client.patch("/api/v1/harness/endpoints/endpoint-pi", headers={"x-api-key": operator},
        json={"expected_revision": 1, "selection_group": group, "priority": 10})
    assert changed.status_code == 200, changed.text
    first, clock = busy_lane(runtime, monkeypatch)
    if agent != "worker":
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.agents.upsert(uow, agent_id=agent)
    if other_workspace:
        target_root = Path(root) / "other-workspace"
        target_root.mkdir()
        root = str(target_root)
    if profile_id != "profile-pi":
        created_profile = client.post("/api/v1/harness/profiles", headers={"x-api-key": operator}, json={
            "profile_id": profile_id, "adapter_id": "pi", "enabled": True})
        assert created_profile.status_code == 200, created_profile.text
    created = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": "zz-fallback", "agent_id": agent, "adapter_id": "pi", "project_root": root,
        "profile_id": profile_id, "enabled": True, "response_policy": "conversation", "selection_group": group})
    assert created.status_code == 200, created.text
    if open_target:
        opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
            "agent_id": agent, "kind": "pi", "endpoint_id": "zz-fallback", "project_root": root})
        assert opened.status_code == 200, opened.text
    return first, clock










def test_conversation_continuation_keeps_its_original_binding(runtime, monkeypatch):
    _, client, root, peers, _, caller = runtime
    fallback_pair(runtime, monkeypatch)
    parent = send_message(runtime, target={"strategy": "direct", "agent_id": "operator"})
    reply = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "subject": "continuation", "body": "original context", "parent_message_id": parent["message_id"],
        "target": {"strategy": "direct", "agent_id": "worker"}})
    assert reply["ok"], reply
    operation_id = reply["data"]["runtime_operations"][0]
    row = wait_status(runtime, operation_id, "RETRY_WAIT")
    assert row["next_binding"] is None
    assert not peers[1].sent




def test_unqualified_on_demand_native_contract_falls_back_before_any_turn_write(runtime, monkeypatch):
    from test_runtime_effective_capabilities import configure_codex
    deps, client, root, peers, operator, _ = runtime
    configure_codex(runtime, version="99.0.0")
    headers = {"x-api-key": operator}
    for adapter in ("pi", "claude_code.stream", "claude_code.attach"):
        result = client.patch(f"/api/v1/harness/endpoints/endpoint-{adapter}", headers=headers,
            json={"expected_revision": 1, "enabled": False})
        assert result.status_code == 200, result.text
    result = client.patch("/api/v1/harness/endpoints/endpoint-codex", headers=headers,
        json={"expected_revision": 1, "selection_group": "approved-native-alternatives", "priority": 10})
    assert result.status_code == 200, result.text
    result = client.post("/api/v1/harness/endpoints", headers=headers, json={
        "endpoint_id": "zz-fallback", "agent_id": "worker", "adapter_id": "pi", "project_root": root,
        "profile_id": "profile-pi", "enabled": True, "response_policy": "conversation",
        "selection_group": "approved-native-alternatives"})
    assert result.status_code == 200, result.text
    clock = [deps.clock.now_iso()]
    monkeypatch.setattr(deps.clock, "now_iso", lambda: clock[0])
    operation_id = send_message(runtime)["runtime_operations"][0]
    refused = wait_status(runtime, operation_id, "RETRY_WAIT")
    assert refused["endpoint_id"] == "endpoint-codex" and refused["retry_basis"] == "APPROVED_ENDPOINT_BEFORE_WRITE"
    clock[0] = refused["next_attempt_at"]
    deps.runtime_dispatcher.wake()
    sent = wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
    assert sent["endpoint_id"] == "zz-fallback" and sent["operation_id"] == operation_id
    wire = [json.loads(line) for line in (Path(root) / "capability-wire.jsonl").read_text().splitlines()]
    assert any(item.get("request_method") == "thread/start" for item in wire)
    assert not any(item.get("request_method") == "turn/start" for item in wire)
    assert len(peers) == 1 and sum(command.verb == "send_turn" for command in peers[0].sent) == 1


@pytest.mark.parametrize("runtime", ["additional"], indirect=True)
@pytest.mark.parametrize("supports_binding", [True, False])
def test_registered_processless_adapter_requires_versioned_fallback_binding(runtime, monkeypatch, supports_binding):
    deps, client, root, peers, operator, _ = runtime
    _, clock = fallback_pair(runtime, monkeypatch)
    endpoint_id = "endpoint-fixture.additional.v1"
    if not supports_binding:
        deps.harness_adapter_registry.get("fixture.additional.v1").input_schema.pop("transport_binding_contract")
    changed = client.patch(f"/api/v1/harness/endpoints/{endpoint_id}", headers={"x-api-key": operator},
        json={"expected_revision": 1, "selection_group": "interchangeable-fixture", "priority": 5})
    assert changed.status_code == 200, changed.text
    opened = tool(client, operator, "harness_open", {"agent_id": "worker", "kind": "fixture.additional.v1",
        "endpoint_id": endpoint_id, "project_root": root})
    assert opened["ok"], opened
    operation_id = send_message(runtime)["runtime_operations"][0]
    before = wait_status(runtime, operation_id, "RETRY_WAIT")
    expected = endpoint_id if supports_binding else "zz-fallback"
    assert json.loads(before["next_binding"])["endpoint_id"] == expected
    clock[0] = before["next_attempt_at"]
    deps.runtime_dispatcher.wake()
    after = wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
    assert after["endpoint_id"] == expected
    if supports_binding:
        command = next(command for command in peers[-1].sent if command.verb == "send_turn")
        assert command.payload["envelope"] == json.loads(before["envelope"])
        assert command.payload["transport_binding"]["endpoint_id"] == endpoint_id
    else:
        assert not peers[-1].sent
        assert sum(command.verb == "send_turn" for command in peers[1].sent) == 1
