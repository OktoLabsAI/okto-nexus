"""Production composition: canonical delivery, durable dispatch and exclusive consumption."""
import threading
import time
import json
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

import pytest

from okto_nexus.application.runtime_dispatcher import RuntimeDispatcher
from okto_nexus.domain.base import iso_plus
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, wait_sent, tool
from runtime_http_client import process_tool

runtime = runtime_fixture


def stop_dispatcher(runtime):
    deps = runtime[0]
    old = deps.runtime_dispatcher
    old.close()
    return old


def restart_dispatcher(runtime, old):
    deps = runtime[0]
    new = RuntimeDispatcher(connection_factory=deps.connection_factory, repo=old.repo,
        clock=deps.clock, validate=old.validate, dispatch=old.dispatch)
    deps.runtime_dispatcher = new
    assert new.start()
    return new


def operation(runtime, operation_id):
    deps = runtime[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return deps.runtime_dispatcher.repo.get(uow, operation_id)


def wait_status(runtime, operation_id, status):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        row = operation(runtime, operation_id)
        if row["status"] == status:
            return row
        time.sleep(0.01)
    pytest.fail(f"operation remained {row['status']}, expected {status}")




def test_p05_lost_wake_recovered_by_new_owner_without_new_logical_delivery(runtime):
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    old = stop_dispatcher(runtime)
    result = send_message(runtime, body="recover exactly this intent")
    operation_id = result["runtime_operations"][0]
    assert operation(runtime, operation_id)["status"] == "PENDING"
    restart_dispatcher(runtime, old)
    wait_sent(peers)
    row = wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
    assert row["ack_level"] == "TRANSPORT_WRITE"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM message_deliveries").fetchone()[0] == 1






@pytest.mark.parametrize("previous_status", ["SENDING", "SENT_UNCONFIRMED", "ACCEPTED"])
def test_p06_takeover_never_replays_a_send_intent(runtime, previous_status):
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    old = stop_dispatcher(runtime)
    result = send_message(runtime)
    operation_id = result["runtime_operations"][0]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE delivery_outbox SET status=?,owner_epoch=?,attempt_id='old-attempt' WHERE operation_id=?",
                               (previous_status, old.epoch, operation_id))
    new = restart_dispatcher(runtime, old)
    assert operation(runtime, operation_id)["status"] == "OUTCOME_UNKNOWN"
    new.scan_once()
    assert peers[0].sent == []
    with deps.connection_factory.unit_of_work() as uow:
        assert not new.repo.observe(uow, operation_id=operation_id, epoch=old.epoch, attempt_id="old-attempt",
            expected="SENDING", status="ACCEPTED", now=deps.clock.now_iso())






def test_p06_http_process_producer_wakes_serve_without_owning_runtime(runtime):
    deps, _, root, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    owner = deps.runtime_dispatcher.owner_id

    result = process_tool(runtime, "message_create", {"project_root": root, "from_agent_id": "caller",
        "subject": "cross-process fixture", "body": "one durable intent",
        "target": {"strategy": "direct", "agent_id": "worker"}})
    assert result["ok"], result
    operation_id = result["data"]["runtime_operations"][0]
    wait_sent(peers)
    wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT owner_id FROM runtime_dispatcher_owner").fetchone()[0] == owner






def test_p05_open_reply_persistence_failure_does_not_repeat_start(runtime, monkeypatch):
    _, client, root, peers, operator, _ = runtime
    from okto_nexus.adapters.outbound.sqlite.runtime_requests_repo import SqliteRuntimeRequestRepo
    original = SqliteRuntimeRequestRepo.finish

    def fail_once(self, uow, *, request_id, status):
        if status == "COMPLETED":
            raise OSError("fixture reply persistence failure")
        return original(self, uow, request_id=request_id, status=status)

    monkeypatch.setattr(SqliteRuntimeRequestRepo, "finish", fail_once)
    arguments = {"agent_id": "worker", "kind": "pi", "project_root": root, "idempotency_key": "lost-reply"}
    first = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=arguments)
    assert first.status_code == 500
    assert "application/json" in first.headers.get("content-type", ""), "open failure lost the canonical error envelope"
    assert first.json()["error"]["code"] == "INTERNAL_ERROR"
    monkeypatch.setattr(SqliteRuntimeRequestRepo, "finish", original)
    second = tool(client, operator, "harness_open", arguments)
    assert second["ok"] and second["data"]["reused"], second
    assert len(peers) == 1


def test_p06_http_process_open_runs_only_in_the_existing_serve_owner(runtime):
    deps, client, root, peers, operator, _ = runtime
    from pathlib import Path
    # If a client process incorrectly spawns locally, it can only attempt an
    # absent fixture executable. Never probe an ambient Pi installation.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_profiles SET config=? WHERE profile_id='profile-pi'",
            (json.dumps({"command": [str(Path(root) / "absent-fixture.exe"), "--mode", "rpc"]}),))
    grant = client.post("/api/v1/harness/grants", headers={"x-api-key": operator}, json={
        "actor_agent_id": "caller", "endpoint_id": "endpoint-pi", "actions": ["open"],
        "expires_at": iso_plus(deps.clock.now_iso(), 3600)})
    assert grant.status_code == 200, grant.text

    result = process_tool(runtime, "harness_open", {"agent_id": "worker", "kind": "pi",
        "endpoint_id": "endpoint-pi", "project_root": root, "idempotency_key": "http-process-owner"})
    assert result["ok"], result
    session_id = result["data"]["session_id"]
    assert len(peers) == 1
    assert deps.harness_supervisor.get(session_id) is not None
