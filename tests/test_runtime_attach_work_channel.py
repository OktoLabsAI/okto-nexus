"""Attach work requires an approved, authenticated external Nexus session."""
import json
import os
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_handoff_dispatch import work
from test_runtime_grants import issue

from test_claude_code_attach_connector import fake_server as attach_server_fixture, _write_registry, _write_key

runtime = runtime_fixture
fake_server = attach_server_fixture


def admitted(runtime, *, target_pid=12345, socket_peer=None, surface="mcp", claim_fault=None):
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
    def claim_request():
        if surface == "mcp":
            return tool(client, worker_key, "handoff_claim", args)
        return client.post(f"/api/v1/workspaces/{workspace}/handoffs/{handoff}/claim",
            headers={"x-api-key": worker_key}, json={k: v for k, v in args.items() if k not in {"project_root", "handoff_id"}}).json()
    denied = claim_request()
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    assert peers == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (handoff,)).fetchone()[0] == "OPEN"
    approved = client.patch("/api/v1/harness/endpoints/endpoint-claude_code.attach", headers={"x-api-key": operator},
        json={"expected_revision": 1, "public_config": {"target_pid": target_pid,
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
    if claim_fault == "missing_proof":
        args.pop("session_id")
        args.pop("session_secret")
    elif claim_fault == "wrong_secret":
        args["session_secret"] = "incorrect-fixture-secret"
    elif claim_fault == "structured_completion":
        args["completion_mode"] = "structured_result_v1"
    elif claim_fault == "foreign_actor":
        worker_key = runtime[-1]
        grant = issue(runtime, ["execute_work", "read"], endpoint_id="endpoint-claude_code.attach", actor_agent_id="caller")
        args["execution_grant_id"] = grant["grant_id"]
    accepted = claim_request()
    if claim_fault:
        assert not accepted["ok"] and accepted["error"]["code"] == "PERMISSION_DENIED", accepted
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (handoff,)).fetchone()[0] == "OPEN"
            assert not uow.connection.execute("SELECT 1 FROM runtime_handoff_bindings").fetchone()
            assert not uow.connection.execute("SELECT 1 FROM delivery_outbox").fetchone()
            assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 0
        assert not any(peer.sent for peer in peers)
        return None

    assert accepted["ok"], accepted
    operation_id = accepted["data"]["runtime_operation"]["operation_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            operation = dict(uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?", (operation_id,)).fetchone())
        if operation["status"] != "PENDING" and operation["status"] != "SENDING" and operation["status"] != "CLAIMED":
            break
        time.sleep(.01)
    assert operation["status"] == "SENT_UNCONFIRMED", operation
    assert operation["terminal_event_id"] is None
    assert operation["ack_level"] == "TRANSPORT_WRITE"
    if socket_peer is None:
        assert sum(len(peer.sent) for peer in peers) == 1
    else:
        socket_peer.wait_for_connections(2)
        assert socket_peer.connections[0] == []
        wire = socket_peer.connections[1][1]
        assert wire["type"] == "user"
        assert operation["message_id"] in wire["message"]["content"]
        assert proof["session_secret"] not in wire["message"]["content"]
        assert worker_key not in wire["message"]["content"]
    return handoff, worker_key, proof, grant, accepted, operation


@pytest.mark.parametrize("action", ["complete", "reject"])
@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_attach_managed_claim_requires_an_approved_external_nexus_channel(runtime, action, surface):
    complete_fixture_work(runtime, action, admitted(runtime, surface=surface))


def complete_fixture_work(runtime, action, admission):
    deps, client, root, peers, _, _ = runtime
    handoff, worker_key, proof, grant, accepted, operation = admission
    operation_id = operation["operation_id"]
    complete_args = {"project_root": root, "handoff_id": handoff, "agent_id": "worker",
        "claim_epoch": accepted["data"]["claim_epoch"], ("result" if action == "complete" else "reason"): "fixture result", **proof}
    before_ack = tool(client, worker_key, "handoff_" + action, complete_args)
    assert not before_ack["ok"] and before_ack["error"]["code"] == "PERMISSION_DENIED", before_ack
    ack_args = {"agent_id": "worker", "message_ids": [operation["message_id"]], **proof}
    missing_proof = tool(client, worker_key, "inbox_ack", {"agent_id": "worker", "message_ids": ack_args["message_ids"]})
    assert not missing_proof["ok"] and missing_proof["error"]["code"] == "PERMISSION_DENIED", missing_proof
    ack = tool(client, worker_key, "inbox_ack", ack_args)
    assert ack["ok"] and ack["data"]["acknowledged"] == 1, ack
    repeated = tool(client, worker_key, "inbox_ack", ack_args)
    assert repeated["ok"] and repeated["data"]["acknowledged"] == 0, repeated
    complete = tool(client, worker_key, "handoff_" + action, complete_args)
    assert complete["ok"], complete
    with deps.connection_factory.unit_of_work(write=False) as uow:
        final = dict(uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?", (operation_id,)).fetchone())
        assert final["ack_level"] == "AGENT_ACK" and final["external_completed_at"]
        assert final["terminal_event_id"] is None
        assert not uow.connection.execute("SELECT 1 FROM runtime_results WHERE operation_id=?", (operation_id,)).fetchone()
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (handoff,)).fetchone()[0] == ("COMPLETED" if action == "complete" else "REJECTED")

    repeated_after_completion = tool(client, worker_key, "inbox_ack", ack_args)
    assert repeated_after_completion["ok"] and repeated_after_completion["data"]["acknowledged"] == 0, repeated_after_completion
    inspected = tool(client, worker_key, "harness_get", {"operation_id": operation_id})
    assert inspected["ok"], inspected
    observed = inspected["data"]
    assert observed["external_work"]["completion_action"] == action
    assert observed["external_work"]["completed_at"]
    assert observed["external_acceptance"] == "observed" and not observed["result_durable"]
    assert observed["result"] is None
    discovered = tool(client, runtime[4], "harness_list", {"view": "bindings"})
    assert discovered["ok"], discovered
    endpoint = next(e for agent in discovered["data"]["agents"] for e in agent["endpoints"] if e["endpoint_id"] == operation["endpoint_id"])
    assert endpoint["external_work_channel"] == {"contract_version": 1, "configured": True, "authentication_required": True, "native_ack": False}
    assert proof["session_id"] not in json.dumps(discovered)
    assert proof["session_secret"] not in json.dumps(discovered)



@pytest.mark.parametrize("fault", ["session_closed", "secret_rotated", "key_rotated", "grant_revoked", "wrong_session", "stale_claim", "foreign_actor", "creator_policy"])
@pytest.mark.parametrize("stage", ["ack", "complete"])
def test_external_work_revalidates_return_authority(runtime, fault, stage):
    deps, client, root, _, _, caller_key = runtime
    handoff, worker_key, proof, grant, accepted, operation = admitted(runtime)
    ack_args = {"agent_id": "worker", "message_ids": [operation["message_id"]], **proof}
    if stage == "complete":
        ack = tool(client, worker_key, "inbox_ack", ack_args)
        assert ack["ok"] and ack["data"]["acknowledged"] == 1, ack
    if fault in {"session_closed", "secret_rotated", "key_rotated", "grant_revoked", "stale_claim", "creator_policy"}:
        with deps.connection_factory.unit_of_work() as uow:
            if fault == "creator_policy":
                uow.connection.execute('UPDATE agents SET permissions=? WHERE agent_id=?', ('{"handoffs":{"create":false}}', 'caller'))
            elif fault == "session_closed":
                uow.connection.execute("UPDATE sessions SET status='closed',closed_at=? WHERE session_id=?", (deps.clock.now_iso(), proof["session_id"]))
            elif fault == "secret_rotated":
                uow.connection.execute("UPDATE sessions SET session_secret='replacement-fixture-secret' WHERE session_id=?", (proof["session_id"],))
                proof = proof | {"session_secret": "replacement-fixture-secret"}
            elif fault == "key_rotated":
                from okto_nexus.application.auth import AgentKeyAuthService
                worker_key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker")
            elif fault == "grant_revoked":
                uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at=?,revision=revision+1 WHERE grant_id=?", (deps.clock.now_iso(), grant["grant_id"]))
            elif fault == "stale_claim":
                uow.connection.execute("UPDATE handoffs SET claim_epoch=claim_epoch+1 WHERE handoff_id=?", (handoff,))
    elif fault == "wrong_session":
        fresh = tool(client, worker_key, "session_open", {"agent_id": "worker", "workspace_id": operation["workspace_id"]})
        assert fresh["ok"], fresh
        proof = {key: fresh["data"][key] for key in ("session_id", "session_secret")}
    elif fault == "foreign_actor":
        worker_key = caller_key
    args = ({"agent_id": "worker", "message_ids": [operation["message_id"]], **proof} if stage == "ack" else
        {"project_root": root, "handoff_id": handoff, "agent_id": "worker", "claim_epoch": accepted["data"]["claim_epoch"],
            "result": "must not apply", **proof})
    result = tool(client, worker_key, "inbox_ack" if stage == "ack" else "handoff_complete", args)
    assert not result["ok"], result
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (handoff,)).fetchone()[0] == "CLAIMED"
        final = uow.connection.execute("SELECT external_completed_at,ack_level FROM delivery_outbox WHERE operation_id=?", (operation["operation_id"],)).fetchone()
        assert final["external_completed_at"] is None
        assert final["ack_level"] == ("TRANSPORT_WRITE" if stage == "ack" else "AGENT_ACK")


@pytest.mark.skipif(os.name != "posix", reason="NOT_RUN: attach socket ownership requires POSIX")
def test_external_work_over_real_attach_socket_and_authenticated_nexus(runtime, tmp_path, fake_server):
    from okto_nexus.adapters.outbound.harness.claude_code_attach import ClaudeCodeAttachConnector
    deps, _, _, _, _, _ = runtime
    pid = os.getpid()
    _write_registry(tmp_path, pid, socket_path=str(fake_server.sock_path), peer_protocol=1)
    _write_key(tmp_path, pid)
    deps.harness_connector_factories["claude_code"] = lambda **kw: ClaudeCodeAttachConnector(kw["target_pid"], sessions_dir=tmp_path)
    complete_fixture_work(runtime, "complete", admitted(runtime, target_pid=pid, socket_peer=fake_server))
    assert len(fake_server.connections) == 2
    os.kill(pid, 0)  # Nexus never owned or terminated this external fixture.


def test_external_work_can_return_after_native_detach_and_quarantine(runtime):
    deps, _, _, _, _, _ = runtime
    admission = admitted(runtime)
    operation = admission[-1]
    closed = deps.harness_supervisor.close(operation["runtime_session_id"])
    assert closed.lifecycle_state == "detached"
    # Simulate the persisted quarantine from owner recovery, not a PID kill.
    # The separate canonical Nexus session and its proof remain active.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET health='quarantined',health_reason='owner_lost' WHERE endpoint_id=?", (operation["endpoint_id"],))
    complete_fixture_work(runtime, "complete", admission)


def test_external_completion_releases_lane_for_a_new_canonical_delivery(runtime):
    from test_pr34_remediation import send_message, wait_sent
    deps, _, _, peers, _, _ = runtime
    admission = admitted(runtime)
    complete_fixture_work(runtime, "complete", admission)
    sent = send_message(runtime, body="distinct authorized continuation")
    assert len(sent["runtime_operations"]) == 1
    wait_sent(peers, count=2)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 2
        assert uow.connection.execute("SELECT count(*) FROM runtime_handoff_bindings").fetchone()[0] == 1
        assert uow.connection.execute("SELECT external_completed_at FROM delivery_outbox WHERE operation_id=?", (admission[-1]["operation_id"],)).fetchone()[0]


@pytest.mark.parametrize("surface", ["rest", "mcp"])
@pytest.mark.parametrize("fault", ["missing_proof", "wrong_secret", "structured_completion", "foreign_actor"])
def test_configured_attach_requires_authenticated_self_claim_proof(runtime, surface, fault):
    admitted(runtime, surface=surface, claim_fault=fault)
