"""Production composition: canonical delivery, durable dispatch and exclusive consumption."""
import threading
import time
import asyncio
import json
import sys
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

import pytest

from okto_nexus.application.runtime_dispatcher import RuntimeDispatcher
from okto_nexus.domain.base import iso_plus
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, wait_sent, tool, stdio_environment

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


def test_p05_message_delivery_outbox_rollback_together(runtime, monkeypatch):
    deps, client, root, peers, _, caller = runtime
    assert open_rest(runtime).status_code == 200

    def fail(*args, **kwargs):
        raise OSError("fixture commit path failure")

    monkeypatch.setattr(deps.event_emitter, "emit", fail)
    result = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "subject": "rollback", "body": "fixture", "target": {"strategy": "direct", "agent_id": "worker"}})
    assert not result["ok"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox"):
            assert uow.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert peers[0].sent == []


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


def test_p05_reserved_push_delivery_cannot_also_be_claimed_or_acked_by_pull(runtime):
    deps = runtime[0]
    assert open_rest(runtime).status_code == 200
    stop_dispatcher(runtime)
    result = send_message(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        claimed = deps.repos.deliveries.claim_pending(uow, recipient_agent_id="worker", limit=10,
            now=deps.clock.now_iso(), lease_expires_at=iso_plus(deps.clock.now_iso(), 30), max_attempts=5)
        assert claimed == []
        assert deps.repos.deliveries.mark_read(uow, recipient_agent_id="worker",
            message_ids=[result["message_id"]], read_at=deps.clock.now_iso()) == []


def test_p06_changed_policy_blocks_previously_committed_intent(runtime):
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    old = stop_dispatcher(runtime)
    result = send_message(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='caller'", ('{"messages":{"send_direct":false}}',))
    restart_dispatcher(runtime, old)
    wait_status(runtime, result["runtime_operations"][0], "REJECTED")
    assert peers[0].sent == []


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


def test_p06_native_send_is_outside_sqlite_write_transaction(runtime, monkeypatch):
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    original_uow = deps.connection_factory.unit_of_work
    thread_state = threading.local()

    @contextmanager
    def tracked_uow(write=True):
        with original_uow(write=write) as uow:
            old = getattr(thread_state, "write", False)
            thread_state.write = old or write
            try:
                yield uow
            finally:
                thread_state.write = old

    monkeypatch.setattr(deps.connection_factory, "unit_of_work", tracked_uow)
    send = peers[0].send
    observed = threading.Event()

    def observed_send(*args, **kwargs):
        assert not getattr(thread_state, "write", False)
        observed.set()
        return send(*args, **kwargs)

    monkeypatch.setattr(peers[0], "send", observed_send)
    send_message(runtime)
    assert observed.wait(5)
    wait_sent(peers)


def test_p05_unverified_internal_sender_only_gets_logical_inbox(runtime):
    deps, _, root, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    result = build_service(deps).create_message(project_root=root, from_agent_id="caller",
        subject="legacy information", body="not authenticated", target={"strategy": "direct", "agent_id": "worker"})
    assert result["delivered_count"] == 1
    assert "runtime_operations" not in result
    assert peers[0].sent == []


def test_p06_stdio_producer_wakes_serve_without_owning_runtime(runtime):
    deps, _, root, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    owner = deps.runtime_dispatcher.owner_id

    async def produce():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "okto_nexus.adapters.inbound.mcp.server", "--home", str(deps.config.home_dir),
                  "--feature-harness-integrations", "true"], env=stdio_environment(runtime))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                result = await client.call_tool("message_create", {"project_root": root, "from_agent_id": "caller",
                    "subject": "cross-process fixture", "body": "one durable intent",
                    "target": {"strategy": "direct", "agent_id": "worker"}})
                result = result.structuredContent or json.loads(result.content[0].text)
                assert result["ok"], result
                return result["data"]["runtime_operations"][0]

    operation_id = asyncio.run(asyncio.wait_for(produce(), timeout=30))
    wait_sent(peers)
    wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT owner_id FROM runtime_dispatcher_owner").fetchone()[0] == owner


def test_p05_open_idempotency_reuses_one_session_across_surfaces(runtime):
    _, client, root, peers, operator, caller = runtime
    arguments = {"agent_id": "worker", "kind": "pi", "project_root": root, "idempotency_key": "same-open"}
    first = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=arguments)
    assert first.status_code == 200, first.text
    second = tool(client, operator, "harness_open", arguments)
    assert second["ok"], second
    assert second["data"]["session_id"] == first.json()["data"]["session_id"]
    assert second["data"]["reused"] is True
    assert len(peers) == 1
    assert tool(client, caller, "harness_open", arguments)["error"]["code"] == "PERMISSION_DENIED"
    assert tool(client, operator, "harness_open", arguments | {"metadata": {"changed": True}})["error"]["code"] == "CONFLICT"
    assert len(peers) == 1


def test_p05_concurrent_open_key_never_starts_twice(runtime):
    _, client, root, peers, operator, _ = runtime
    arguments = {"agent_id": "worker", "kind": "pi", "project_root": root, "idempotency_key": "concurrent-open"}

    def open_one(_):
        return client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=arguments).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(open_one, [1, 2]))
    assert 200 in codes and set(codes) <= {200, 409}
    assert len(peers) == 1


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


def test_p06_stdio_open_runs_only_in_the_existing_serve_owner(runtime):
    deps, client, root, peers, operator, _ = runtime
    from pathlib import Path
    # If the stdio process incorrectly spawns locally, it can only attempt an
    # absent fixture executable. Never probe an ambient Pi installation.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_profiles SET config=? WHERE profile_id='profile-pi'",
            (json.dumps({"command": [str(Path(root) / "absent-fixture.exe"), "--mode", "rpc"]}),))
    grant = client.post("/api/v1/harness/grants", headers={"x-api-key": operator}, json={
        "actor_agent_id": "caller", "endpoint_id": "endpoint-pi", "actions": ["open"],
        "expires_at": iso_plus(deps.clock.now_iso(), 3600)})
    assert grant.status_code == 200, grant.text

    async def request_open():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "okto_nexus.adapters.inbound.mcp.server", "--home", str(deps.config.home_dir),
                  "--feature-harness-integrations", "true"], env=stdio_environment(runtime))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool("harness_open", {"agent_id": "worker", "kind": "pi",
                    "endpoint_id": "endpoint-pi", "project_root": root, "idempotency_key": "stdio-owner"})
                result = result.structuredContent or json.loads(result.content[0].text)
                assert result["ok"], result
                return result["data"]["session_id"]

    session_id = asyncio.run(asyncio.wait_for(request_open(), timeout=30))
    assert len(peers) == 1
    assert deps.harness_supervisor.get(session_id) is not None
