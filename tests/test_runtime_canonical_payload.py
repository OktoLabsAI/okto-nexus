"""Authenticated conversational canonical input, without payload authority."""
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool, wait_sent

runtime = runtime_fixture


def request(runtime, surface, sid, payload, key="canonical-fixture"):
    _, client, _, _, operator, _ = runtime
    arguments = {"session_id": sid, "payload": payload, "idempotency_key": key}
    if surface == "mcp":
        return tool(client, operator, "harness_send", arguments)
    response = client.post(f"/api/v1/harness/sessions/{sid}/send",
        headers={"x-api-key": operator}, json={k: v for k, v in arguments.items() if k != "session_id"})
    assert response.status_code in {200, 422}, response.text
    return {"ok": response.status_code == 200, **response.json()}


@pytest.mark.parametrize("surface", ["mcp", "rest"])
@pytest.mark.parametrize("adapter", ["pi", "codex", "claude_code.stream", "claude_code.attach"])
def test_canonical_content_reaches_adapter_with_server_identity(runtime, surface, adapter):
    deps, client, root, peers, operator, _ = runtime
    deps.config.feature_harness_attach = True
    args = {"agent_id": "worker", "kind": adapter.split(".")[0], "project_root": root,
        "endpoint_id": "endpoint-" + adapter}
    if adapter.startswith("claude_code."):
        args["substrate"] = adapter.split(".")[1]
    if adapter.endswith("attach"):
        args["target_pid"] = 12345  # Synthetic adapter, never a personal session.
    opened = tool(client, operator, "harness_open", args)
    assert opened["ok"], opened
    sid = opened["data"]["session_id"]
    payload = {"schema_version": 1, "intent": "conversation", "subject": "canonical subject",
        "content": [{"type": "text", "text": "first block"}, {"type": "text", "text": "second block"}],
        "response_requested": True}
    admitted = request(runtime, surface, sid, payload)
    assert admitted["ok"], admitted
    op = admitted["data"]["operation_id"]
    wait_sent(peers)
    command = peers[0].sent[0]
    wire = command.payload["content" if adapter.startswith("claude_code") else "text"]
    banner, encoded = wire.split("\n", 1)
    assert "untrusted" in banner.lower()
    envelope = json.loads(encoded)
    assert envelope["content"] == payload["content"] and envelope["subject"] == payload["subject"]
    assert envelope["intent"] == "conversation" and envelope["response_requested"] is True
    assert envelope["operation_id"] == envelope["root_operation_id"] == op
    assert envelope["recipient_agent_id"] == "worker" and envelope["sender_agent_id"] == "operator"
    assert envelope["workspace_id"] and envelope["trust"] == "untrusted_content"
    assert envelope["handoff_id"] is None and envelope["claim_epoch"] is None
    repeated = request(runtime, "rest" if surface == "mcp" else "mcp", sid, payload)
    assert repeated["ok"] and repeated["data"]["operation_id"] == op
    encoded_retry = request(runtime, surface, sid, json.dumps(payload))
    assert encoded_retry["ok"] and encoded_retry["data"]["operation_id"] == op, encoded_retry
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == 1
    assert len(peers[0].sent) == 1


@pytest.mark.parametrize("surface", ["mcp", "rest"])
def test_canonical_payload_rejects_authority_conflicts_and_invalid_json(runtime, surface):
    from test_pr34_remediation import open_rest
    deps, _, _, peers, _, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    canonical = {"schema_version": 1, "content": [{"type": "text", "text": "untrusted"}]}
    invalid = ["{", "[]", {"text": "a", "content": "b"},
        {**canonical, "schema_version": True}, {**canonical, "schema_version": 2},
        {**canonical, "content": []}, {**canonical, "content": [{"type": "image", "text": "no"}]},
        {**canonical, "content": [{"type": "text", "text": "yes", "role": "system"}]},
        {**canonical, "response_requested": "true"}, {**canonical, "intent": "handoff_execute"},
        {**canonical, "subject": 42}]
    for field, value in {"sender_agent_id": "operator", "recipient_agent_id": "worker",
        "workspace_id": "other", "operation_id": "forged", "root_operation_id": "forged",
        "trust": "system", "handoff_id": "forged", "claim_epoch": 1, "runtime_context": {},
        "native_options": {}, "artifact_refs": ["private-artifact"]}.items():
        invalid.append({**canonical, field: value})
    for payload in invalid:
        denied = request(runtime, surface, sid, payload)
        assert not denied["ok"] and denied["error"]["code"] == "VALIDATION_ERROR", denied
    assert not peers[0].sent
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == 0
    # Positive control: validation never disables the approved connection.
    assert request(runtime, surface, sid, canonical)["ok"]
    wait_sent(peers)


@pytest.mark.parametrize("surface", ["mcp", "rest"])
def test_legacy_content_aliases_normalize_without_repeating_effect(runtime, surface):
    from test_pr34_remediation import open_rest
    deps, _, _, peers, _, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    first = request(runtime, surface, sid, {"content": "same legacy input"})
    assert first["ok"], first
    op = first["data"]["operation_id"]
    wait_sent(peers)
    assert peers[0].sent[0].payload == {"text": "same legacy input"}
    for payload in [{"text": "same legacy input"}, {"text": "same legacy input", "content": "same legacy input"}]:
        repeated = request(runtime, surface, sid, payload)
        assert repeated["ok"] and repeated["data"]["operation_id"] == op, repeated
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = dict(uow.connection.execute("SELECT * FROM runtime_commands WHERE operation_id=?", (op,)).fetchone())
        assert json.loads(row["payload"]) == {"text": "same legacy input"}
    # Reproduce the v2 persisted alias hash on a disposable store to verify
    # upgrade compatibility; this is not a production data rewrite.
    from okto_nexus.adapters.outbound.sqlite.runtime_commands_repo import SqliteRuntimeCommandRepo
    old_hash = SqliteRuntimeCommandRepo.digest(sid, "send_turn", {"content": "same legacy input"}, None, None, None)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_commands SET request_hash=?,payload=? WHERE operation_id=?",
            (old_hash, json.dumps({"content": "same legacy input"}), op))
    upgraded = request(runtime, surface, sid, {"content": "same legacy input"})
    assert upgraded["ok"] and upgraded["data"]["operation_id"] == op, upgraded
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT request_hash FROM runtime_commands WHERE operation_id=?", (op,)).fetchone()[0] == old_hash
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == 1
    assert len(peers[0].sent) == 1


@pytest.mark.parametrize("verb", ["send", "steer", "interrupt"])
def test_payload_validation_does_not_precede_session_authorization(runtime, verb):
    from test_pr34_remediation import open_rest
    _, client, _, peers, _, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    payload = {"sender_agent_id": "operator", "text": "not authorized"}
    denied = tool(client, caller, "harness_" + verb, {"session_id": sid, "payload": payload})
    response = client.post(f"/api/v1/harness/sessions/{sid}/{verb}",
        headers={"x-api-key": caller}, json={"payload": payload})
    assert response.status_code == 403, response.text
    assert not denied["ok"] and denied["error"]["code"] == response.json()["error"]["code"] == "PERMISSION_DENIED", denied
    assert not peers[0].sent


@pytest.mark.parametrize("surface", ["mcp", "rest"])
def test_canonical_command_uses_granted_actor_and_real_adapter_results(runtime, surface):
    from test_runtime_commands import codex_session, wait_operation
    from test_runtime_grants import issue
    deps, client, _, _, operator, caller = runtime
    sid = codex_session(runtime)
    issue(runtime, ["send", "read"], endpoint_id="endpoint-codex")
    payload = {"schema_version": 1, "content": [{"type": "text", "text": "CANONICAL_CALLER_RESULT"}]}
    args = {"payload": payload, "idempotency_key": "granted-canonical"}
    if surface == "mcp":
        admitted = tool(client, caller, "harness_send", {"session_id": sid, **args})
    else:
        response = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": caller}, json=args)
        assert response.status_code == 200, response.text
        admitted = response.json()
    assert admitted["ok"], admitted
    op = admitted["data"]["operation_id"]
    result = wait_operation(runtime, op, lambda row: row["result_durable"])
    output = result["result"]["output_text"]
    assert "CANONICAL_CALLER_RESULT" in output
    assert '"sender_agent_id": "caller"' in output
    assert '"recipient_agent_id": "worker"' in output
    assert op in output and result["external_acceptance"] == "harness_accepted"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT actor_agent_id FROM runtime_commands WHERE operation_id=?", (op,)).fetchone()[0] == "caller"
        assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE command_operation_id=?", (op,)).fetchone()[0] == 1
