"""Canonical inbox stays exclusive after acceptance or uncertain transport."""
import json
import socket
import time

import pytest

from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.domain.runtime_commands import RuntimeCommandNotSent
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_commands import codex_session
from test_runtime_handoff_dispatch import wait_result
from test_runtime_outbox import operation, wait_status

runtime = runtime_fixture


def worker_key(runtime):
    deps = runtime[0]
    with deps.connection_factory.unit_of_work() as uow:
        return AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker")


def pull(runtime, key):
    result = tool(runtime[1], key, "inbox_pull", {"agent_id": "worker"})
    assert result["ok"], result
    return result["data"]["messages"]


def test_native_acceptance_then_terminal_never_redelivers_to_pull(runtime):
    deps, client, _, _, operator, _ = runtime
    key = worker_key(runtime)
    sid = codex_session(runtime)
    created = send_message(runtime, body="TRIGGER_HOLD")
    op = created["runtime_operations"][0]
    accepted = wait_status(runtime, op, "ACCEPTED")
    assert accepted["ack_level"] == "HARNESS_ACCEPTED"
    assert accepted["terminal_event_id"] is None
    assert pull(runtime, key) == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT status,consumer_kind FROM message_deliveries WHERE delivery_id=?",
                                     (accepted["delivery_id"],)).fetchone()
        assert tuple(row) == ("unread", "push"), "native acceptance is not processing completion"
    interrupted = tool(client, operator, "harness_interrupt", {
        "session_id": sid, "expected_operation_id": op, "expected_turn_id": accepted["native_turn_id"]})
    assert interrupted["ok"], interrupted
    result = wait_result(runtime, op)
    assert result["attempt_id"] == accepted["attempt_id"]
    assert pull(runtime, key) == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM message_deliveries WHERE delivery_id=?",
            (accepted["delivery_id"],)).fetchone()[0] == "read"
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE operation_id=?", (op,)).fetchone()[0] == 1
        receipts = uow.connection.execute("SELECT body FROM messages WHERE subject LIKE 'runtime processing receipt:%'").fetchall()
        assert len(receipts) == 1 and json.loads(receipts[0][0])["ack_source"] == "native_terminal"
    events = deps.harness_supervisor.replay_events(sid)
    assert sum(e.native_event == "turn/started" for e in events) == 1


def test_lost_confirmation_and_expired_transport_lease_keep_push_reservation(runtime, monkeypatch):
    deps, _, _, peers, _, _ = runtime
    key = worker_key(runtime)
    assert open_rest(runtime).status_code == 200
    original = peers[0].send

    def write_then_lose_confirmation(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("Disposable lost confirmation after native effect")

    monkeypatch.setattr(peers[0], "send", write_then_lose_confirmation)
    created = send_message(runtime)
    op = created["runtime_operations"][0]
    unknown = wait_status(runtime, op, "OUTCOME_UNKNOWN")
    assert len(peers[0].sent) == 1

    # Deterministic lease-expiry stimulus without changing host time or donating
    # the live owner lease. Expiry alone is not proof of native non-delivery.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE delivery_outbox SET lease_expires_at='2000-01-01T00:00:00Z' WHERE operation_id=?", (op,))
    for _ in range(3):
        deps.runtime_dispatcher.scan_once()
        assert pull(runtime, key) == []
    after = operation(runtime, op)
    assert after["status"] == "OUTCOME_UNKNOWN"
    assert after["attempt_id"] == unknown["attempt_id"] and after["attempt_count"] == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT status,consumer_kind,consumer_operation_id FROM message_deliveries WHERE delivery_id=?",
                                     (unknown["delivery_id"],)).fetchone()
        assert tuple(row) == ("unread", "push", op)
    assert len(peers[0].sent) == 1

def test_two_refused_sockets_do_not_consume_inbox_attempts_or_lease(runtime, monkeypatch):
    deps, client, root, peers, operator, _ = runtime
    headers = {"x-api-key": operator}
    group = "approved-socket-fixture-fallback"
    response = client.patch("/api/v1/harness/endpoints/endpoint-pi", headers=headers,
        json={"expected_revision": 1, "selection_group": group, "priority": 30})
    assert response.status_code == 200, response.text
    endpoints = ["endpoint-pi", "socket-fallback-b", "socket-fallback-c"]
    for index, endpoint in enumerate(endpoints[1:], start=1):
        response = client.post("/api/v1/harness/endpoints", headers=headers, json={
            "endpoint_id": endpoint, "agent_id": "worker", "adapter_id": "pi",
            "project_root": root, "profile_id": "profile-pi", "enabled": True,
            "response_policy": "conversation", "selection_group": group, "priority": 30-index})
        assert response.status_code == 200, response.text
    for endpoint in endpoints:
        opened = client.post("/api/v1/harness/sessions", headers=headers, json={
            "agent_id": "worker", "kind": "pi", "endpoint_id": endpoint, "project_root": root})
        assert opened.status_code == 200, opened.text
    clock = [deps.clock.now_iso()]
    monkeypatch.setattr(deps.clock, "now_iso", lambda: clock[0])
    deps.runtime_dispatcher.retry_jitter = lambda: 0
    refused = []
    # Reserved loopback port without listen: an actual refused connect, with
    # no possibility of sending payload bytes or contacting an ambient peer.
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        address = reserved.getsockname()

        def before_write(session, command):
            with socket.socket() as connection:
                # Windows retries a refused loopback connect for about2s.
                # Only explicit refusal is typed NOT_SENT; timeout stays unknown.
                connection.settimeout(5)
                try:
                    connection.connect(address)
                except ConnectionRefusedError:
                    refused.append(session.session_id)
                    raise RuntimeCommandNotSent("Fixture socket refused before any write") from None
            pytest.fail("Reserved non-listening fixture port unexpectedly accepted a connection")

        for peer in peers[:2]:
            monkeypatch.setattr(peer, "send", before_write)
        sent = send_message(runtime, body="third approved endpoint receives one delivery")
        op = sent["runtime_operations"][0]
        first = wait_status(runtime, op, "RETRY_WAIT")

        def inbox_state():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return tuple(uow.connection.execute("SELECT attempts,lease_expires_at,status,consumer_kind,consumer_operation_id "
                    "FROM message_deliveries WHERE delivery_id=?", (first["delivery_id"],)).fetchone())

        before = inbox_state()
        assert before == (0, None, "unread", "push", op)
        clock[0] = first["next_attempt_at"]
        deps.runtime_dispatcher.wake()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            second = operation(runtime, op)
            if second["status"] == "RETRY_WAIT" and second["attempt_count"] == 2:
                break
            time.sleep(.01)
        assert second["status"] == "RETRY_WAIT" and second["attempt_count"] == 2
        assert inbox_state() == before
        clock[0] = second["next_attempt_at"]
        deps.runtime_dispatcher.wake()
        delivered = wait_status(runtime, op, "SENT_UNCONFIRMED")
        assert delivered["attempt_count"] == 3 and delivered["endpoint_id"] == endpoints[2]
        assert inbox_state() == before
        assert len(refused) == 2 and len(set(refused)) == 2
        assert [len(peer.sent) for peer in peers] == [0, 0, 1]
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT count(*) FROM message_deliveries").fetchone()[0] == 1
            assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
            attempted = uow.connection.execute("SELECT DISTINCT endpoint_id FROM runtime_delivery_attempt_events "
                "WHERE operation_id=? AND state='SENDING'", (op,)).fetchall()
            assert {row[0] for row in attempted} == set(endpoints)



@pytest.mark.parametrize("adapter", ["pi", "codex", "claude_code.stream", "claude_code.attach"])
@pytest.mark.parametrize("action", ["create", "update"])
@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_unsafe_mirror_configuration_cannot_add_an_executor(runtime, adapter, action, surface):
    deps, client, root, peers, operator, _ = runtime
    assert open_rest(runtime).status_code == 200
    original_endpoint = "endpoint-" + adapter
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = tuple(uow.connection.execute("SELECT revision,consumption,enabled FROM agent_endpoints WHERE endpoint_id=?",
                                              (original_endpoint,)).fetchone())
    body = {"consumption": "mirror_only"}
    endpoint = "unsafe-mirror" if action == "create" else original_endpoint
    if action == "create":
        body.update(endpoint_id=endpoint, agent_id="worker", adapter_id=adapter,
                    project_root=root, enabled=True, response_policy="conversation")
        if adapter == "claude_code.attach":
            body["public_config"] = {"target_pid": 12345}  # never attached
        else:
            body["profile_id"] = "profile-" + adapter
    else:
        body["expected_revision"] = before[0]
    if surface == "rest":
        response = (client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json=body)
                    if action == "create" else client.patch(f"/api/v1/harness/endpoints/{endpoint}",
                        headers={"x-api-key": operator}, json=body))
        assert response.status_code == 422, response.text
        result = response.json()
    else:
        result = tool(client, operator, "harness_list", {"view": "endpoints", "maintenance": {
            **body, "action": action, "endpoint_id": endpoint}})
    assert not result["ok"] and result["error"]["code"] == "VALIDATION_ERROR", result
    assert "mirror" in result["error"]["message"].lower()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute("SELECT revision,consumption,enabled FROM agent_endpoints WHERE endpoint_id=?",
            (original_endpoint,)).fetchone()) == before
        assert not uow.connection.execute("SELECT 1 FROM agent_endpoints WHERE endpoint_id='unsafe-mirror'").fetchone()
    assert len(peers) == 1 and peers[0].sent == []
    sent = send_message(runtime, body="authorized executor still works")
    wait_status(runtime, sent["runtime_operations"][0], "SENT_UNCONFIRMED")
    assert len(peers) == 1 and [c.verb for c in peers[0].sent] == ["send_turn"]
