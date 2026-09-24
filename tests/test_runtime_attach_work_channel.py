"""Attach work requires an approved, authenticated external Nexus session."""
from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_handoff_dispatch import work
from test_runtime_grants import issue

runtime = runtime_fixture


def test_attach_managed_claim_requires_an_approved_external_nexus_channel(runtime):
    deps, client, root, peers, operator, _ = runtime
    deps.config.feature_harness_attach = True
    handoff, worker_key = work(runtime)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute("SELECT workspace_id FROM agent_endpoints WHERE endpoint_id=?",
            ("endpoint-claude_code.attach",)).fetchone()[0]
    external = tool(client, worker_key, "session_open", {"agent_id": "worker", "workspace_id": workspace})
    assert external["ok"], external
    proof = {key: external["data"][key] for key in ("session_id", "session_secret")}
    grant = issue(runtime, ["execute_work", "read"], endpoint_id="endpoint-claude_code.attach", actor_agent_id="worker")
    args = {"project_root": root, "handoff_id": handoff, "agent_id": "worker",
        "runtime_endpoint_id": "endpoint-claude_code.attach", "execution_grant_id": grant["grant_id"],
        "idempotency_key": "external-work", **proof}
    denied = tool(client, worker_key, "handoff_claim", args)
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    assert peers == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (handoff,)).fetchone()[0] == "OPEN"
    approved = client.patch("/api/v1/harness/endpoints/endpoint-claude_code.attach", headers={"x-api-key": operator},
        json={"expected_revision": 1, "public_config": {"target_pid": 12345,
            "nexus_work_session_id": proof["session_id"]}})
    assert approved.status_code == 200, approved.text
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "claude_code", "substrate": "attach",
        "endpoint_id": "endpoint-claude_code.attach", "project_root": root})
    assert opened.status_code == 200, opened.text
    # Native capabilities remain honest even when the separate Nexus channel
    # permits managed work. Neither events nor a native ACK is invented.
    effective = opened.json()["data"]["compatibility_report"]["effective_capabilities"]
    assert not effective["managed_work"] and not effective["events"]
    # Endpoint configuration invalidates prior grants by design. Prove the
    # positive admission contract with authority issued for this configuration.
    grant = issue(runtime, ["execute_work", "read"], endpoint_id="endpoint-claude_code.attach", actor_agent_id="worker")
    args["execution_grant_id"] = grant["grant_id"]
    accepted = tool(client, worker_key, "handoff_claim", args)
    assert accepted["ok"], accepted
    assert accepted["data"]["runtime_operation"]["operation_id"]
