"""Canonical message admission preserves inbox ownership and commit boundaries."""
import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_result_publication import current_turn
from test_canonical_grant_regressions import mcp_helpers
from test_agent_recovery_isolation import eventually


def test_message_event_failure_rolls_back_delivery_and_execution(connected_local, monkeypatch):
    setup, binding, native = connected_local
    enable(setup, binding)
    def fail(*args, **kwargs):
        raise OSError("Fixture message event transaction cut")
    monkeypatch.setattr(setup[0].event_emitter, "emit", fail)
    result = send(setup, monkeypatch)
    assert not result["ok"], result
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox", "execution_operations", "execution_sessions"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0, table
    assert native.opens == 0


def test_push_claim_cannot_be_pulled_or_manually_acked(connected_local, monkeypatch):
    from okto_nexus.domain.base import iso_plus
    setup, binding, native = connected_local
    enable(setup, binding)
    deps = setup[0]
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    result = send(setup, monkeypatch)
    assert result["ok"], result
    with deps.connection_factory.unit_of_work() as uow:
        assert deps.repos.deliveries.claim_pending(uow, recipient_agent_id="subject", limit=10,
            now=deps.clock.now_iso(), lease_expires_at=iso_plus(deps.clock.now_iso(), 30), max_attempts=5) == []
        assert deps.repos.deliveries.mark_read(uow, recipient_agent_id="subject",
            message_ids=[result["data"]["message_id"]], read_at=deps.clock.now_iso()) == []
    assert native.opens == 0


def test_unauthenticated_internal_sender_creates_only_logical_inbox(connected_local):
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    setup, binding, native = connected_local
    enable(setup, binding)
    result = build_service(setup[0]).create_message(project_root=str(setup[-1]), from_agent_id="operator",
        subject="Internal information", body="No authenticated execution authority",
        target=dict(strategy="direct", agent_id="subject"))
    assert result["delivered_count"] == 1 and "runtime_operations" not in result
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
    assert native.opens == 0


def test_permission_change_refuses_committed_delivery_before_native_effect(connected_local, monkeypatch):
    setup, binding, native = connected_local
    enable(setup, binding)
    deps, app, client, *_ = setup
    gate = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(gate.acquire)
    try:
        assert send(setup, monkeypatch)["ok"]
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='operator'",
                (json.dumps(dict(messages=dict(send_direct=False))),))
    finally:
        client.portal.call(gate.release)
    def refused():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute("SELECT COUNT(*) FROM execution_dispatch_outbox WHERE dispatch_state='RESOLVED_TERMINAL' AND last_error IS NOT NULL").fetchone()[0] > 0
    eventually(refused)
    assert native.opens == 0


def test_native_send_does_not_hold_server_sqlite_writer(connected_local, monkeypatch):
    from test_vertical_inventory import _Native
    setup, binding, native = connected_local
    deps, _, client, *_ = setup
    enable(setup, binding)
    entered, release = threading.Event(), asyncio.Event()
    original = _Native.send
    async def held(self, *args, **kwargs):
        entered.set()
        await release.wait()
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(_Native, "send", held)
    try:
        assert send(setup, monkeypatch)["ok"]
        assert entered.wait(5)
        # A distinct connection can acquire and commit a write while native
        # execution is still blocked, proving no Server transaction spans it.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET role=role WHERE agent_id='operator'")
        assert not release.is_set()
    finally:
        client.portal.call(release.set)
    wait_receipt(setup, current_turn(setup))
    assert native.opens == 1 and len(native.native.sent) == 1


@pytest.mark.parametrize("concurrent", [False, True])
def test_same_open_key_across_rest_and_mcp_has_one_native_effect(connected_local, concurrent):
    from test_pr34_remediation import tool
    setup, binding, native = connected_local
    _, _, client, headers, *_, root = setup
    client.headers["host"] = "127.0.0.1:8000"
    key = headers["subject"]["Authorization"].removeprefix("Bearer ")
    body = dict(agent_id="subject", kind="codex", project_root=str(root),
        endpoint_id=binding["endpoint_id"], idempotency_key="shared-rest-mcp-open")
    barrier = threading.Barrier(2) if concurrent else None
    def invoke(surface):
        if barrier:
            barrier.wait(5)
        if surface == "mcp":
            return tool(client, key, "harness_open", body)
        return client.post("/api/v1/harness/sessions", headers=headers["subject"], json=body).json()
    if concurrent:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(invoke, ("rest", "mcp")))
    else:
        responses = [invoke("rest"), invoke("mcp")]
    assert all(r["ok"] for r in responses), responses
    assert responses[0]["data"]["operation_id"] == responses[1]["data"]["operation_id"]
    wait_receipt(setup, responses[0]["data"])
    assert native.opens == 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 1
    # A credential with no subject grant cannot reuse this cached reply.
    from test_agent_recovery_isolation import create_agent
    outsider = create_agent(setup, "outside")
    foreign_key = outsider[3]["subject"]["Authorization"].removeprefix("Bearer ")
    denied = tool(client, foreign_key, "harness_open", body)
    assert not denied["ok"] and native.opens == 1


def test_sqlite_capacity_cannot_acknowledge_message_or_execution(connected_local, monkeypatch):
    from test_pr34_remediation import tool
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    enable(setup, binding)
    client.headers["host"] = "127.0.0.1:8000"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        pages = uow.connection.execute("PRAGMA page_count").fetchone()[0]
    connect = deps.connection_factory.get_connection
    def limited():
        conn = connect()
        conn.execute(f"PRAGMA max_page_count={pages}")
        return conn
    with monkeypatch.context() as patch:
        patch.setattr(deps.connection_factory, "get_connection", limited)
        response = tool(client, headers["operator"]["Authorization"].removeprefix("Bearer "), "message_create",
            dict(project_root=str(root), from_agent_id="operator", target=dict(strategy="direct", agent_id="subject"),
                body="x" * 60000, subject="Storage capacity"))
    assert not response["ok"] and response["error"]["code"] == "DB_ERROR", response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox", "execution_operations"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()
    assert native.opens == 0
    assert send(setup, monkeypatch)["ok"]
    wait_receipt(setup, current_turn(setup))
    assert native.opens == 1 and len(native.native.sent) == 1
