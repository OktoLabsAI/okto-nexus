"""Native terminals join canonical receipts, output and inbox consumption once."""
import json
import threading
import time

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local, enable, send
from test_canonical_grant_regressions import mcp_helpers
from test_canonical_native_protocol_regressions import open_native
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("large", [False, True])
def test_native_terminal_projection_is_atomic_bounded_and_releases_next_delivery(connected_local, monkeypatch, rollback, large):
    from okto_nexus.application import execution_results
    setup, binding, _ = connected_local
    source = _FAKE_SERVER_SOURCE
    if large:
        original = '    write_msg({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "itemId": item_id, "delta": text}})'
        source = source.replace(original, '    for _ in range(40):\n' + original.replace('"delta": text', '"delta": "x" * 30000').replace('    write_msg', '        write_msg'))
        assert source != _FAKE_SERVER_SOURCE
    setup, binding, _, _, log = open_native(connected_local, source)
    deps, app, client, *_ = setup
    enable(setup, binding)
    failed, allow = threading.Event(), threading.Event()
    original_project = execution_results.project_domain_result
    def project(conn, **kwargs):
        original_project(conn, **kwargs)
        if rollback and not allow.is_set() and conn.execute("SELECT 1 FROM runtime_results WHERE canonical_operation_id=?",
                (kwargs["operation_id"],)).fetchone():
            failed.set()
            raise OSError("Fixture cut after terminal result creation")
    monkeypatch.setattr(execution_results, "project_domain_result", project)
    operations = []
    for index in range(2):
        created = send(setup, monkeypatch)
        assert created["ok"], created
        domain = created["data"]["runtime_operations"][0]
        operations.append(domain)
        deadline = time.monotonic() + 20
        while True:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                raw = uow.connection.execute("SELECT * FROM runtime_results WHERE operation_id=?", (domain,)).fetchone()
                row = dict(raw) if raw else None
                delivered = uow.connection.execute("SELECT status FROM message_deliveries WHERE message_id=? AND recipient_agent_id='subject'",
                    (created["data"]["message_id"],)).fetchone()[0]
            if rollback and failed.is_set() and not allow.is_set():
                assert row is None and delivered != "read"
                allow.set()  # No manual retry or dispatcher wake follows.
            if row and delivered == "read":
                break
            assert time.monotonic() < deadline, (row, delivered)
            time.sleep(.02)
        assert row["canonical_operation_id"] and row["event_id"] is None
        if large:
            assert len(row["output_text"].encode()) == 1024 * 1024
            assert row["output_truncated"] and row["output_event_count"] == 41  # 40 deltas plus the empty terminal output
        else:
            assert "Please review this message." in row["output_text"]
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT canonical_terminal_operation_id FROM delivery_outbox WHERE operation_id=?",
                (domain,)).fetchone()[0] == row["canonical_operation_id"]
        # Fault recovery contains only the affected session; wait for its
        # automatic readiness before admitting the independent next delivery.
        while "subject" in app.state.embedded_dispatch_owner.agents.blocked:
            assert time.monotonic() < deadline
            time.sleep(.02)
    from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service
    inbox = build_service(deps)
    assert inbox.consume_canonical_runtime_results() == 0
    with deps.connection_factory.unit_of_work() as uow:
        for _ in range(2):
            for row in uow.connection.execute("SELECT m.server_id,m.executor_id,m.operation_id FROM execution_domain_deliveries m JOIN execution_operations o USING(server_id,executor_id,operation_id) WHERE o.action='turn.submit'").fetchall():
                original_project(uow.connection, **dict(row))
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_results WHERE canonical_operation_id IS NOT NULL").fetchone()[0] == 2
        receipts = [json.loads(r[0]) for r in uow.connection.execute("SELECT body FROM messages WHERE subject LIKE 'runtime processing receipt:%'")]
        assert len(receipts) == 2 and all(r["human_read"] is False for r in receipts)
        assert all(r["ack_source"] == "canonical_native_terminal" for r in receipts)
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()
    wire = [json.loads(line) for line in log.read_text().splitlines()]
    assert len([r for r in wire if r.get("method") == "turn/start"]) == 2


def test_foreign_native_terminal_is_contained_without_releasing_or_replaying_message(connected_local, monkeypatch):
    from test_embedded_dispatch import admit, wait_receipt
    from test_agent_recovery_isolation import eventually
    from test_pr34_remediation import tool
    source = _FAKE_SERVER_SOURCE.replace('    if "TRIGGER_HOLD" in text:',
        '    if "TRIGGER_HOLD" in text:\n'
        '        write_msg({"method":"turn/completed", "params":{"threadId":thread_id, "turn":{"id":"stale", "status":"completed"}}})\n'
        '        write_msg({"method":"item/agentMessage/delta", "params":{"threadId":thread_id, "turnId":turn_id, "itemId":"marker-item", "delta":"after-stale-terminal-marker"}})\n'
        '    if "TRIGGER_HOLD" in text:')
    assert source != _FAKE_SERVER_SOURCE
    setup, binding, sid, peer, log = open_native(connected_local, source)
    deps, _, client, headers, *_, root = setup
    enable(setup, binding)
    client.headers["host"] = "127.0.0.1:8000"
    first = tool(client, headers["operator"]["Authorization"].removeprefix("Bearer "), "message_create",
        dict(project_root=str(root), from_agent_id="operator", subject="Held turn", body="TRIGGER_HOLD",
             target=dict(strategy="direct", agent_id="subject")))
    assert first["ok"], first
    domain = first["data"]["runtime_operations"][0]
    state = next(iter(peer._sessions_by_id.values()))
    eventually(lambda: bool(state.active_turn_id))
    second = send(setup, monkeypatch)
    assert second["ok"], second
    # Core treats a terminal for another native turn as an ambiguous stream.
    # It must contain that stream, never guess success or release the next turn.
    def fault_observed():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return any("core.event_pump_failed" in r[0] for r in uow.connection.execute("SELECT payload_json FROM execution_event_ingress"))
    eventually(fault_observed)
    assert peer._transport._proc.wait(timeout=10) is not None
    def restored():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            closed = uow.connection.execute("SELECT lifecycle_state FROM execution_sessions WHERE session_id=?", (sid,)).fetchone()[0]
            recovery = uow.connection.execute("SELECT state FROM execution_agent_recovery WHERE agent_id='subject'").fetchone()
            return closed == "CLOSED" and recovery is not None and recovery[0] == "READY"
    try:
        eventually(restored)
    except AssertionError:
        owner = setup[1].state.embedded_dispatch_owner
        with deps.connection_factory.unit_of_work(write=False) as uow:
            pytest.fail(str(dict(resources=owner.host.shutdown_resources(), sessions=[dict(r) for r in uow.connection.execute("SELECT * FROM execution_sessions")], recovery=[dict(r) for r in uow.connection.execute("SELECT * FROM execution_agent_recovery")], operations=[dict(r) for r in uow.connection.execute("SELECT operation_id,admission_state FROM execution_operations")])) )
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT canonical_terminal_operation_id FROM delivery_outbox WHERE operation_id=?", (domain,)).fetchone()[0] is None
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_results WHERE canonical_operation_id IS NOT NULL").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_receipts r JOIN execution_operations o USING(server_id,executor_id,operation_id) WHERE o.action='turn.submit' AND r.stage='SUCCEEDED'").fetchone()[0] == 0
    wire = [json.loads(line) for line in log.read_text().splitlines()]
    assert len([r for r in wire if r.get("method") == "turn/start"]) == 1
    fresh = admit(setup, binding, "after-stream-recovery", "runtime.start", new_session=True)
    wait_receipt(setup, fresh)
    fresh_turn = admit(setup, binding, "fresh-work-after-stream-recovery", "turn.submit",
        session_id=fresh["scope"]["session_id"], text="New authorized work")
    wait_receipt(setup, fresh_turn, stages=("SUCCEEDED",))
