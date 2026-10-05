"""Existing message claims feed canonical execution without a second inbox."""
import json
from pathlib import Path
import time

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connect_local, qualified_contract, admit, wait_receipt


@pytest.fixture
def connected_local(local_setup):
    from okto_nexus.domain.ids import resolve_workspace_id
    deps, _, _, _, body, _, root = local_setup
    workspace = resolve_workspace_id(str(root))
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=workspace, root_realpath=str(root), last_seen_at=deps.clock.now_iso())
    body["workspace_id"] = workspace
    return connect_local(local_setup)


def send(setup, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    _, _, client, headers, *_, root = setup
    client.headers["host"] = "127.0.0.1:8000"
    return tool(client, headers["operator"]["Authorization"].removeprefix("Bearer "), "message_create",
        dict(project_root=str(root), from_agent_id="operator", subject="Canonical conversation",
             body="Please review this message.", target=dict(strategy="direct", agent_id="subject")))


def enable(setup, binding):
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation' "
                               "WHERE endpoint_id=?", (binding["endpoint_id"],))


def test_message_admits_open_and_turn_atomically(connected_local, monkeypatch):
    from test_vertical_inventory import _Native
    setup, binding, native = connected_local
    payloads = []
    original = _Native.send
    async def capture(peer, verb, payload, operation_id, **kwargs):
        payloads.append(payload)
        return await original(peer, verb, payload, operation_id, **kwargs)
    monkeypatch.setattr(_Native, "send", capture)
    enable(setup, binding)
    result = send(setup, monkeypatch)
    assert result["ok"], result
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT p.* FROM execution_operations p JOIN execution_domain_deliveries m "
            "USING(server_id,executor_id,operation_id) ORDER BY action").fetchall()
        assert [row["action"] for row in rows] == ["runtime.open", "turn.submit"], (result, [dict(r) for r in uow.connection.execute("SELECT * FROM agent_endpoints")])
        assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 1
        claim = uow.connection.execute("SELECT consumer_kind,consumer_operation_id FROM message_deliveries").fetchone()
        assert claim[0] == "push"
        envelope = json.loads(uow.connection.execute("SELECT envelope FROM delivery_outbox").fetchone()[0])
        assert envelope["operation_id"] == claim[1]
        assert uow.connection.execute("SELECT COUNT(*) FROM harness_sessions").fetchone()[0] == 0
    wait_receipt(setup, dict(operation_id=rows[1]["operation_id"]))
    assert native.opens == 1 and len(native.native.sent) == 1
    assert "Please review this message." in str(payloads)
    assert claim[1] in str(payloads) and envelope["root_operation_id"] in str(payloads)
    from nexus_connector_core import RuntimeEvent
    deps, _, client, *_ = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute("SELECT * FROM execution_local_streams").fetchone())
        assert uow.connection.execute("SELECT status,canonical_terminal_operation_id FROM delivery_outbox").fetchone()[:] == ("ACCEPTED", None)
    # Queued logical deliveries keep the same session and wait for the first
    # terminal receipt, not merely its SUBMITTED acknowledgement.
    assert send(setup, monkeypatch)["ok"]
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch
    assert reserve_execution_dispatch(deps.connection_factory, server_id=stream["server_id"],
        executor_id=stream["executor_id"], remote_ready=True) is None
    assert len(native.native.sent) == 1
    client.portal.call(native.native.queue.put, RuntimeEvent(stream["server_id"], stream["executor_id"],
        stream["session_id"], stream["stream_epoch"], 0, "turn_state", "technical.complete",
        {"delivery_phase": "terminal", "delivery_outcome": "success"}, operation_id=rows[1]["operation_id"]))
    wait_receipt(setup, dict(operation_id=rows[1]["operation_id"]), stages=("SUCCEEDED",))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT canonical_terminal_operation_id FROM delivery_outbox WHERE operation_id=?", (claim[1],)).fetchone()[0] == rows[1]["operation_id"]
        assert uow.connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0
    # A subsequent delivery uses the established session and preserves one claim.
    deadline = time.monotonic() + 10
    while len(native.native.sent) < 2:
        assert time.monotonic() < deadline
        time.sleep(.02)
    assert native.opens == 1
    closed = admit(setup, binding, "delivery-close", "runtime.close", session_id=rows[0]["session_id"])
    wait_receipt(setup, closed, stages=("SUCCEEDED",))


def test_failed_canonical_admission_rolls_back_message_and_claim(connected_local, monkeypatch):
    from okto_nexus.bootstrap import execution_compat
    setup, binding, native = connected_local
    enable(setup, binding)
    info = execution_compat.protocol_info()
    monkeypatch.setattr(execution_compat, "protocol_info", lambda: {**info, "remote_execution_ready": False})
    result = send(setup, monkeypatch)
    assert not result["ok"], result
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox", "execution_operations", "execution_domain_deliveries"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0, table
    assert native.opens == 0


def test_post_admission_failure_rolls_back_canonical_rows(connected_local, monkeypatch):
    from okto_nexus.application import execution_domain_delivery
    from okto_nexus.errors import OktoNexusError, ErrorCode
    setup, binding, native = connected_local
    enable(setup, binding)
    original = execution_domain_delivery.submit_execution_operation
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise OktoNexusError(ErrorCode.CONFLICT, "Technical post-admission failure.", {})
    monkeypatch.setattr(execution_domain_delivery, "submit_execution_operation", fail)
    assert not send(setup, monkeypatch)["ok"]
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox", "execution_client_intents", "execution_operations", "execution_sessions", "execution_dispatch_outbox"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0, table
    assert native.opens == 0


def test_canonical_observer_does_not_receive_executable_prompt(connected_local, monkeypatch):
    setup, binding, native = connected_local
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='mirror_only',response_policy='none' WHERE endpoint_id=?", (binding["endpoint_id"],))
    assert send(setup, monkeypatch)["ok"]
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
        assert uow.connection.execute("SELECT consumer_kind FROM message_deliveries").fetchone()[0] is None
    assert native.opens == 0


def test_sender_revocation_blocks_admitted_delivery(connected_local, monkeypatch):
    setup, binding, native = connected_local
    enable(setup, binding)
    deps, app, client, *_ = setup
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        result = send(setup, monkeypatch)
        assert result["ok"], result
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET api_key_hash='revoked' WHERE agent_id='operator'")
    finally:
        client.portal.call(lock.release)
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT dispatch_state,last_error FROM execution_dispatch_outbox").fetchone()
        if row[0] == "RESOLVED_TERMINAL":
            assert "PERMISSION_DENIED" in row[1]
            break
        assert time.monotonic() < deadline, tuple(row)
        time.sleep(.02)
    assert native.opens == 0
