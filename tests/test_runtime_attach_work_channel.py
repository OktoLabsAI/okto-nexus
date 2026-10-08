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
