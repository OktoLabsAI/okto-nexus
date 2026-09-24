"""Known capture failure must stop new executable admission across writers."""
import errno
import os
import asyncio
import json
import sqlite3
import sys

import pytest

from okto_nexus.domain.harness import HarnessEvent
from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool, stdio_environment, send_message, wait_sent
from test_runtime_commands import wait_operation

runtime = runtime_fixture


@pytest.fixture
def capture_runtime(runtime):
    ingress = runtime[0].harness_supervisor.event_ingress
    quota = ingress.journal.quota
    try:
        yield runtime
    finally:
        # The deliberately damaged disposable journal must be reopened before
        # the common fixture requests normal lifecycle capture during cleanup.
        # This is test teardown only, never evidence of automatic recovery.
        with ingress._project_lock:
            ingress.journal.close()
            ingress.journal.quota = quota
            ingress.journal.start()


@pytest.mark.parametrize("fault", ["quota", "fsync"])
@pytest.mark.parametrize("surface", ["command", "message", "stdio"])
def test_known_capture_failure_rejects_new_execution_before_intent(capture_runtime, monkeypatch, caplog, fault, surface):
    runtime = capture_runtime
    deps, client, root, peers, operator, caller = runtime
    opened = open_rest(runtime)
    assert opened.status_code == 200, opened.text
    sid = opened.json()["data"]["session_id"]
    ingress = deps.harness_supervisor.event_ingress
    journal = ingress.journal
    watermark = journal.watermark
    failed = HarnessEvent(session_id=sid, harness_kind="pi", kind="turn_completed",
        native_event="fixture/uncaptured", occurred_at=deps.clock.now_iso(), payload={"text": "uncaptured fixture"})
    with monkeypatch.context() as patch:
        if fault == "quota":
            journal.quota = journal._total + 1
        else:
            def full(_fd):
                raise OSError(errno.ENOSPC, "Disposable journal fsync capacity fault")
            patch.setattr(os, "fsync", full)
        with pytest.raises(OSError):
            ingress.capture(failed)
    assert journal.watermark == watermark
    assert not journal.diagnostics()["healthy"]
    assert any(record.levelname == "ERROR" and record.getMessage() ==
        "Runtime journal capture unavailable; new executions paused." for record in caplog.records)
    if surface == "command":
        response = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": operator},
            json={"payload": {"text": "must not admit"}, "idempotency_key": "capture-unavailable"})
        assert response.status_code == 409, response.text
        reply = response.json()
    elif surface == "message":
        reply = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
            "target": {"strategy": "direct", "agent_id": "worker"}, "body": "must not admit", "subject": "capture fault"})
    else:
        async def produce():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(command=sys.executable,
                args=["-m", "okto_nexus.adapters.inbound.mcp.server", "--home", str(deps.config.home_dir),
                    "--feature-harness-integrations", "true"], env=stdio_environment(runtime))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool("message_create", {"project_root": root,
                        "from_agent_id": "caller", "target": {"strategy": "direct", "agent_id": "worker"},
                        "body": "independent writer must not admit", "subject": "capture fault"})
                    return response.structuredContent or json.loads(response.content[0].text)
        reply = asyncio.run(asyncio.wait_for(produce(), timeout=30))
    assert not reply["ok"], reply
    assert reply["error"]["code"] == "CONFLICT", reply
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("runtime_commands", "delivery_outbox", "messages", "runtime_results"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert peers[0].sent == []


def test_quota_compaction_resumes_admission_without_losing_projected_events(capture_runtime):
    runtime = capture_runtime
    deps, client, _, peers, operator, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    ingress = deps.harness_supervisor.event_ingress
    ingress.journal.segment_bytes = 900
    for index in range(5):
        ingress.capture(HarnessEvent(session_id=sid, harness_kind="pi", kind="tool_activity",
            native_event="fixture/context", occurred_at=deps.clock.now_iso(), payload={"index": index}))
    before = ingress.journal.watermark
    ingress.journal.quota = ingress.journal._total + 1
    with pytest.raises(OSError, match="quota"):
        ingress.capture(HarnessEvent(session_id=sid, harness_kind="pi", kind="tool_activity",
            native_event="fixture/overflow", occurred_at=deps.clock.now_iso(), payload={}))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT capture_available FROM runtime_writer_contract").fetchone()[0] == 0
    compact = client.post("/api/v1/harness/journal", headers={"x-api-key": operator}, json={"compact": True})
    assert compact.status_code == 200, compact.text
    assert compact.json()["data"]["removed_segments"] > 0
    assert ingress.journal.watermark == before
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT capture_available FROM runtime_writer_contract").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM harness_events WHERE native_event='fixture/context'").fetchone()[0] == 5
    assert send_message(runtime)["runtime_operations"]
    wait_sent(peers)


def test_capture_fence_preserves_cached_reply_blocks_new_open_and_fences_stale_owner(capture_runtime):
    deps, client, root, peers, operator, _ = capture_runtime
    sid = open_rest(capture_runtime).json()["data"]["session_id"]
    args = {"session_id": sid, "payload": {"text": "existing reply"}, "idempotency_key": "existing-before-full"}
    admitted = tool(client, operator, "harness_send", args)
    assert admitted["ok"], admitted
    op = admitted["data"]["operation_id"]
    wait_operation(capture_runtime, op, lambda row: row["state"] == "SENT_UNCONFIRMED")
    owner = deps.runtime_dispatcher
    journal = owner.event_ingress.journal
    journal.quota = journal._total + 1
    with pytest.raises(OSError):
        owner.event_ingress.capture(HarnessEvent(session_id=sid, harness_kind="pi", kind="tool_activity",
            native_event="fixture/full", occurred_at=deps.clock.now_iso(), payload={}))
    repeated = tool(client, operator, "harness_send", args)
    assert repeated["ok"] and repeated["data"]["operation_id"] == op
    with deps.connection_factory.unit_of_work() as uow:
        assert not owner.repo.set_capture_available(uow, owner_id=owner.owner_id,
            epoch=owner.epoch - 1, available=True, now=deps.clock.now_iso())
        assert uow.connection.execute("SELECT capture_available FROM runtime_writer_contract").fetchone()[0] == 0
        # A writer bypassing the repository still encounters the additive
        # database fence. No current source marker is required for this trigger.
        with pytest.raises(sqlite3.IntegrityError, match="runtime_capture_unavailable"):
            uow.connection.execute("INSERT INTO runtime_open_requests(request_id,actor_agent_id,idempotency_key,request_hash,status,created_at) "
                "VALUES('fixture-raw-open','operator','fixture-raw','fixture','RESERVED',?)", (deps.clock.now_iso(),))
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 409, opened.text
    assert len(peers) == 1 and len(peers[0].sent) == 1


def test_sqlite_page_limit_cannot_acknowledge_an_executable_intent(runtime, monkeypatch):
    deps, client, root, peers, _, caller = runtime
    assert open_rest(runtime).status_code == 200
    with deps.connection_factory.unit_of_work(write=False) as uow:
        pages = uow.connection.execute("PRAGMA page_count").fetchone()[0]
    connect = deps.connection_factory.get_connection

    def limited():
        connection = connect()
        connection.execute(f"PRAGMA max_page_count={pages}")
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(deps.connection_factory, "get_connection", limited)
        response = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
            "target": {"strategy": "direct", "agent_id": "worker"}, "body": "x" * 60000, "subject": "SQLite capacity"})
    assert not response["ok"] and response["error"]["code"] == "DB_ERROR", response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()
    assert peers[0].sent == []
    assert send_message(runtime, body="capacity restored")["runtime_operations"]
    wait_sent(peers)
