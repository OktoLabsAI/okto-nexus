"""Activation preserves old logical inbox work and has one transport executor."""
import json
from pathlib import Path
import sys
import threading
import time

from fastapi.testclient import TestClient
import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_commands import wait_close_result, wait_operation

runtime = runtime_fixture




@pytest.mark.parametrize("runtime", ["stored_runtime"], indirect=True)
@pytest.mark.parametrize("cut", ["accepted", "sending_unknown"])
def test_disable_with_accepted_turn_and_pending_journal_retains_capture_and_exclusion(runtime, tmp_path, cut):
    from legacy_native_fixture.codex import CodexAppServerConnector
    from okto_nexus.domain.base import iso_plus
    deps, client, root, _, operator, _ = runtime
    gate = tmp_path / "emit-terminal"
    wire = tmp_path / "accepted-wire.jsonl"
    source = _FAKE_SERVER_SOURCE.replace('if "TRIGGER_HOLD" in text:\n        return',
        'if "TRIGGER_HOLD" in text:\n'
        '        deadline = time.monotonic() + 30\n'
        f'        while not os.path.exists({str(gate)!r}) and time.monotonic() < deadline: time.sleep(.01)\n'
        '        text = "CAPTURE_AFTER_DISABLE"')
    assert source != _FAKE_SERVER_SOURCE
    deps.harness_connector_factories["codex"] = lambda **options: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source, str(wire)], cwd=root, env=options["backend"]["env"])
    opened = tool(client, operator, "harness_open", {"agent_id": "worker", "kind": "codex",
        "project_root": root, "endpoint_id": "endpoint-codex"})
    assert opened["ok"], opened
    sid = opened["data"]["session_id"]
    ingress = deps.harness_supervisor.event_ingress
    entered, release = threading.Event(), threading.Event()
    locked = False
    if cut == "sending_unknown":
        peer = deps.harness_supervisor._live[sid].connector.native
        original = peer.send

        def uncertain_send(session, command):
            nonlocal locked
            if command.verb == "send_turn":
                locked = ingress._project_lock.acquire(timeout=3)
                assert locked
            result = original(session, command)
            if command.verb == "send_turn":
                entered.set()
                assert release.wait(15)
                raise OSError("fixture outcome lost after actual native write")
            return result

        peer.send = uncertain_send
        # Acquire the projection barrier in the active transport worker.
        # Taking it before dispatch would also stall the owner coordinator
        # before it could schedule this send.
    try:
        sent = send_message(runtime, body="TRIGGER_HOLD")
        op = sent["runtime_operations"][0]
        if cut == "sending_unknown":
            assert entered.wait(5)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                accepted = deps.runtime_dispatcher.repo.get(uow, op)
                assert accepted["status"] == "SENDING"
        else:
            accepted = wait_operation(runtime, op, lambda row: row["external_acceptance"] == "observed")
            locked = ingress._project_lock.acquire(timeout=3)
            assert locked
        before = ingress.journal.watermark
        gate.write_text("emit", encoding="utf-8")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            captured = ingress.journal.read_after(before)
            if any(row["event"].get("delivery_phase") == "terminal" for row in captured):
                break
            time.sleep(.01)
        assert any(row["event"].get("delivery_phase") == "terminal" for row in captured)
        changed = client.patch("/api/v1/settings", headers={"x-api-key": operator},
            json={"feature_harness_integrations": False})
        assert changed.status_code == 200, changed.text
        denied = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "MUST_NOT_SEND"}})
        assert not denied["ok"], denied
        if cut == "sending_unknown":
            release.set()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    state = deps.runtime_dispatcher.repo.get(uow, op)["status"]
                if state == "OUTCOME_UNKNOWN":
                    break
                time.sleep(.01)
            assert state == "OUTCOME_UNKNOWN"
        with deps.connection_factory.unit_of_work() as uow:
            assert uow.connection.execute("SELECT admission_enabled FROM runtime_writer_contract").fetchone()[0] == 0
            assert not uow.connection.execute("SELECT 1 FROM runtime_results WHERE operation_id=?", (op,)).fetchone()
            assert deps.repos.deliveries.claim_pending(uow, recipient_agent_id="worker", limit=10,
                now=deps.clock.now_iso(), lease_expires_at=iso_plus(deps.clock.now_iso(), 30), max_attempts=5) == []
    finally:
        release.set()
        if locked:
            ingress._project_lock.release()
    # Maintenance must continue projecting already captured facts with OFF.
    deadline = time.monotonic() + 8
    result = None
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_results WHERE operation_id=?", (op,)).fetchone()
            result = dict(row) if row else None
        if result:
            break
        time.sleep(.01)
    assert result and result["publication_state"] in {"PENDING_AUTHORIZATION", "BLOCKED"}, result
    assert result["output_text"] == "CAPTURE_AFTER_DISABLE" and not result["publication_message_id"]
    # OFF may retain pending authorization for an explicit later rollout. The
    # invariant is no publication now, not a fabricated permanent rejection.
    deps.runtime_dispatcher.publish_results()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT publication_message_id FROM runtime_results WHERE operation_id=?",
            (op,)).fetchone()[0] is None
        operation = deps.runtime_dispatcher.repo.get(uow, op)
        assert operation["attempt_id"] == accepted["attempt_id"] and operation["attempt_count"] == 1
        assert operation["terminal_event_id"] == result["event_id"]
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
    records = [json.loads(line) for line in wire.read_text(encoding="utf-8").splitlines()]
    assert len([row for row in records if row.get("method") == "turn/start"]) == 1
