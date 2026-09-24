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


@pytest.mark.parametrize("runtime", [False], indirect=True)
def test_activation_does_not_replay_old_unread_and_legacy_notifications_do_not_duplicate_transport(runtime):
    old, _, root, _, operator, caller = runtime
    previous = [send_message(runtime, subject=f"historical-{i}", body="OLD_UNREAD_FIXTURE") for i in range(3)]
    with old.connection_factory.unit_of_work(write=False) as uow:
        before = [dict(row) for row in uow.connection.execute("SELECT * FROM message_deliveries ORDER BY delivery_id")]
        assert len(before) == 3 and all(row["status"] == "unread" for row in before)
        assert not uow.connection.execute("SELECT 1 FROM delivery_outbox").fetchone()

    # Existing store is explicitly enabled in a new production lifespan. The
    # old OFF app has no runtime owner and performs no more writes here.
    deps = bootstrap({}, ["--home", str(old.config.home_dir)])
    deps.config.feature_harness_integrations = True
    assert not hasattr(deps, "harness_connector_factories")
    source = _FAKE_SERVER_SOURCE.replace(
        "LOG_PATH = sys.argv[1] if len(sys.argv) > 1 else None", "LOG_PATH = 'wire.jsonl'")
    assert source != _FAKE_SERVER_SOURCE
    Path(root, "app-server").write_text(source, encoding="utf-8")
    headers = {"x-api-key": operator}
    with TestClient(build_app(deps), base_url="http://127.0.0.1:18790") as client:
        created = client.post("/api/v1/harness/profiles", headers=headers, json={
            "profile_id": "rollout-fixture", "adapter_id": "codex", "enabled": True,
            "inherit_ambient": False, "config": {"command": [sys.executable, "app-server"]}})
        assert created.status_code == 200, created.text
        created = client.post("/api/v1/harness/endpoints", headers=headers, json={
            "endpoint_id": "rollout-fixture", "agent_id": "worker", "adapter_id": "codex",
            "project_root": root, "profile_id": "rollout-fixture", "enabled": True,
            "response_policy": "conversation"})
        assert created.status_code == 200, created.text
        opened = tool(client, operator, "harness_open", {"agent_id": "worker", "kind": "codex",
            "project_root": root, "endpoint_id": "rollout-fixture"})
        assert opened["ok"], opened
        sid = opened["data"]["session_id"]
        peer = deps.harness_supervisor._live[sid].connector.native
        process = peer._transport._proc
        deps.runtime_dispatcher.scan_once()
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute("SELECT 1 FROM delivery_outbox").fetchone()
        active = deps, client, root, [], operator, caller
        fresh = send_message(active, subject="post-activation", body="NEW_DELIVERY_FIXTURE")
        assert len(fresh["runtime_operations"]) == 1
        wait_operation(active, fresh["runtime_operations"][0], lambda row: row["result_durable"])
        # Actual MessageService already publishes post-commit notifications.
        # Repeating them is harmless because serve has retired the executable
        # inbox callback; durable outbox owns all transport execution.
        assert deps.harness_supervisor._inbox_notifier is None
        for data in [fresh, fresh, *previous]:
            deps.inbox_delivery_notifier.publish("worker", data)
        deps.runtime_dispatcher.scan_once()
        closed = tool(client, operator, "harness_close", {"session_id": sid})
        assert closed["ok"], closed
        assert wait_close_result(client, operator, closed)["lifecycle_state"] == "stopped"
        assert process.wait(timeout=5) is not None
        # Read the owned peer's real stdin observations after process cleanup,
        # so absence of duplicates is not based on a short scheduling sleep.
        records = [json.loads(line) for line in Path(root, "wire.jsonl").read_text(encoding="utf-8").splitlines()]
        turns = [row for row in records if row.get("method") == "turn/start"]
        assert len(turns) == 1 and "NEW_DELIVERY_FIXTURE" in json.dumps(turns)
        assert "OLD_UNREAD_FIXTURE" not in json.dumps(turns)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            for original in before:
                current = dict(uow.connection.execute("SELECT * FROM message_deliveries WHERE delivery_id=?",
                    (original["delivery_id"],)).fetchone())
                assert current == original
            outbox = uow.connection.execute("SELECT message_id FROM delivery_outbox").fetchall()
            assert [row[0] for row in outbox] == [fresh["message_id"]]


@pytest.mark.parametrize("runtime", ["stored_runtime"], indirect=True)
@pytest.mark.parametrize("cut", ["accepted", "sending_unknown"])
def test_disable_with_accepted_turn_and_pending_journal_retains_capture_and_exclusion(runtime, tmp_path, cut):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
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
