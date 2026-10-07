"""Canonical target routing through authenticated production serve.

Legacy callback/TTL relay assertions are covered by test_runtime_relay,
test_runtime_causality and test_runtime_relay_process_restart. See the explicit
migration map in P11_TARGET_GRAMMAR_MIGRATION.md; no implicit Agent registration.
"""
import json
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import wait_status

runtime = runtime_fixture




def test_failed_transport_preserves_durable_delivery_and_blocks_duplicate_lane(runtime, monkeypatch):
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    attempts = []
    def uncertain_write(session, command):
        attempts.append(command)
        raise OSError("fixture transport failed after potentially writing bytes")
    monkeypatch.setattr(peers[0], "send", uncertain_write)
    first = send_message(runtime)
    wait_status(runtime, first["runtime_operations"][0], "OUTCOME_UNKNOWN")
    second = send_message(runtime, body="independent logical delivery")
    wait_status(runtime, second["runtime_operations"][0], "PENDING")
    assert first["delivered_count"] == second["delivered_count"] == 1
    assert len(attempts) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT status,consumer_kind FROM message_deliveries ORDER BY created_at").fetchall()
        assert len(rows) == 2
        assert all(r["status"] == "unread" and r["consumer_kind"] == "push" for r in rows)


def test_send_only_target_keeps_write_distinct_from_ack(runtime):
    deps, client, root, peers, operator, _ = runtime
    deps.config.feature_harness_attach = True
    opened = tool(client, operator, "harness_open", {
        "agent_id": "worker", "kind": "claude_code", "substrate": "attach",
        "endpoint_id": "endpoint-claude_code.attach", "project_root": root,
        "target_pid": 12345})  # fixture factory only, never a personal session
    assert opened["ok"], opened
    sent = send_message(runtime)
    row = wait_status(runtime, sent["runtime_operations"][0], "SENT_UNCONFIRMED")
    assert row["ack_level"] != "HARNESS_ACCEPTED"
    assert [c.verb for p in peers for c in p.sent] == ["send_turn"]


def test_correlated_relay_can_reach_send_only_target_without_inventing_a_reply(runtime):
    from test_runtime_relay import configure
    deps, client, root, peers, operator, _ = runtime
    configure(runtime, depth=1)
    deps.config.feature_harness_attach = True
    response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": "caller-attach", "agent_id": "caller", "adapter_id": "claude_code.attach",
        "project_root": root, "enabled": True, "priority": 100,
        "response_policy": "conversation", "public_config": {"target_pid": 12345}})
    assert response.status_code == 200, response.text
    opened = tool(client, operator, "harness_open", {
        "agent_id": "caller", "kind": "claude_code", "substrate": "attach",
        "endpoint_id": "caller-attach", "project_root": root, "target_pid": 12345})
    assert opened["ok"], opened
    source = send_message(runtime)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            child = uow.connection.execute("SELECT * FROM delivery_outbox WHERE endpoint_id='caller-attach'").fetchone()
        if child:
            break
        time.sleep(.01)
    assert child is not None
    row = wait_status(runtime, child["operation_id"], "SENT_UNCONFIRMED")
    assert row["terminal_event_id"] is None and row["ack_level"] != "HARNESS_ACCEPTED"
    assert [c.verb for p in peers for c in p.sent] == ["send_turn"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        parent = uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?",
                                       (source["runtime_operations"][0],)).fetchone()
        assert row["root_operation_id"] == parent["root_operation_id"]
        assert uow.connection.execute("SELECT count(*) FROM runtime_results").fetchone()[0] == 1
    rejected = tool(client, operator, "harness_steer", {
        "session_id": opened["data"]["session_id"], "payload": {"content": "unsupported"},
        "idempotency_key": "unsupported-fixture-steer"})
    assert not rejected["ok"] and rejected["error"]["code"] == "VALIDATION_ERROR", rejected
    assert [c.verb for p in peers for c in p.sent] == ["send_turn"]
