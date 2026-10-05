"""Real REST/MCP configuration boundaries for an external Nexus work channel.

This qualifies reference approval only. Claim/ACK/complete remains a separate
end-to-end gate in test_runtime_attach_work_channel.py.
"""
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool, open_rest
from test_runtime_handoff_dispatch import work

runtime = runtime_fixture


def configure(runtime, surface, *, action="update", key=None, config=None, **changes):
    _, client, root, _, operator, _ = runtime
    parameters = {"public_config": config, **changes}
    if action == "create":
        parameters.update(endpoint_id="external-attach", agent_id="worker",
            adapter_id="claude_code.attach", project_root=root, enabled=True)
    else:
        parameters.setdefault("expected_revision", 1)
    if surface == "mcp":
        return tool(client, key or operator, "harness_list", {"view": "endpoints", "maintenance": {
            "action": action, **({"endpoint_id": "endpoint-claude_code.attach"} if action == "update" else {}),
            **parameters}})
    response = (client.post("/api/v1/harness/endpoints", headers={"x-api-key": key or operator}, json=parameters)
        if action == "create" else client.patch("/api/v1/harness/endpoints/endpoint-claude_code.attach",
            headers={"x-api-key": key or operator}, json=parameters))
    return response.json()


def session(runtime, *, agent="worker", workspace=None, key=None):
    deps, client, _, _, _, caller = runtime
    if key is None:
        _, key = work(runtime)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = workspace or uow.connection.execute(
            "SELECT workspace_id FROM agent_endpoints WHERE endpoint_id='endpoint-claude_code.attach'").fetchone()[0]
    result = tool(client, key if agent == "worker" else caller, "session_open",
        {"agent_id": agent, "workspace_id": workspace})
    assert result["ok"], result
    return result["data"]


@pytest.mark.parametrize("surface", ["rest", "mcp"])
@pytest.mark.parametrize("action", ["create", "update"])
def test_external_channel_approves_reference_without_native_capability_or_secret(runtime, surface, action):
    deps, client, root, peers, operator, _ = runtime
    deps.config.feature_harness_attach = True
    proof = session(runtime)
    config = {"target_pid": 12345, "nexus_work_session_id": proof["session_id"]}
    result = configure(runtime, surface, action=action, config=config)
    assert result["ok"], result
    assert proof["session_secret"] not in json.dumps(result)
    assert peers == []
    endpoint_id = "external-attach" if action == "create" else "endpoint-claude_code.attach"
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "claude_code", "substrate": "attach",
        "endpoint_id": endpoint_id, "project_root": root})
    assert opened.status_code == 200, opened.text
    effective = opened.json()["data"]["compatibility_report"]["effective_capabilities"]
    assert not effective["managed_work"] and not effective["events"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        persisted = uow.connection.execute("SELECT public_config FROM agent_endpoints WHERE endpoint_id=?",
            (endpoint_id,)).fetchone()[0]
        assert json.loads(persisted) == config
        assert proof["session_secret"] not in persisted
        assert not uow.connection.execute("SELECT 1 FROM runtime_handoff_bindings").fetchone()
        assert not uow.connection.execute("SELECT 1 FROM delivery_outbox").fetchone()


@pytest.mark.parametrize("surface", ["rest", "mcp"])
@pytest.mark.parametrize("action", ["create", "update"])
@pytest.mark.parametrize("invalid", ["unknown", "foreign_agent", "foreign_workspace", "closed", "missing_secret", "harness_presence"])
def test_external_channel_rejects_unusable_session_references_atomically(runtime, surface, action, invalid, tmp_path):
    deps, client, _, peers, operator, _ = runtime
    if invalid == "foreign_agent":
        proof = session(runtime, agent="caller")
    elif invalid == "foreign_workspace":
        other = tmp_path / "other-project"
        other.mkdir()
        resolved = tool(client, operator, "workspace_resolve", {"project_root": str(other)})
        assert resolved["ok"], resolved
        proof = session(runtime, workspace=resolved["data"]["workspace_id"])
    elif invalid == "harness_presence":
        opened = open_rest(runtime)
        assert opened.status_code == 200, opened.text
        proof = {"session_id": opened.json()["data"]["presence_session_id"]}
    else:
        proof = session(runtime)
    if invalid in {"closed", "missing_secret"}:
        with deps.connection_factory.unit_of_work() as uow:
            if invalid == "closed":
                uow.connection.execute("UPDATE sessions SET status='closed',closed_at=? WHERE session_id=?",
                    (deps.clock.now_iso(), proof["session_id"]))
            else:
                uow.connection.execute("UPDATE sessions SET session_secret=NULL WHERE session_id=?", (proof["session_id"],))
    selected = "unknown-session" if invalid == "unknown" else proof["session_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = [dict(row) for row in uow.connection.execute("SELECT * FROM agent_endpoints ORDER BY endpoint_id")]
        audits = uow.connection.execute("SELECT count(*) FROM runtime_access_audit WHERE resource_kind='endpoint'").fetchone()[0]
    peers_before = len(peers)
    result = configure(runtime, surface, action=action, config={"target_pid": 12345, "nexus_work_session_id": selected})
    assert not result["ok"] and result["error"]["code"] == "PERMISSION_DENIED", result
    assert result["error"].get("details", {}) == {}
    assert selected not in json.dumps(result)
    assert len(peers) == peers_before
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert [dict(row) for row in uow.connection.execute("SELECT * FROM agent_endpoints ORDER BY endpoint_id")] == before
        assert uow.connection.execute("SELECT count(*) FROM runtime_access_audit WHERE resource_kind='endpoint'").fetchone()[0] == audits


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_external_channel_recovery_can_disable_or_remove_closed_reference(runtime, surface):
    deps, client, _, _, operator, caller = runtime
    proof = session(runtime)
    config = {"target_pid": 12345, "nexus_work_session_id": proof["session_id"]}
    denied = configure(runtime, surface, key=caller, config=config)
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    assert configure(runtime, surface, config=config)["ok"]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE sessions SET status='closed',closed_at=? WHERE session_id=?",
            (deps.clock.now_iso(), proof["session_id"]))
    disabled = client.patch("/api/v1/harness/endpoints/endpoint-claude_code.attach",
        headers={"x-api-key": operator}, json={"expected_revision": 2, "enabled": False})
    assert disabled.status_code == 200, disabled.text
    enabled = client.patch("/api/v1/harness/endpoints/endpoint-claude_code.attach",
        headers={"x-api-key": operator}, json={"expected_revision": 3, "enabled": True})
    assert enabled.status_code == 403, enabled.text
    removed = configure(runtime, surface, config={"target_pid": 12345, "nexus_work_session_id": None}, expected_revision=3)
    assert removed["ok"], removed
    assert removed["data"]["public_config"] == {"target_pid": 12345}
