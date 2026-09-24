"""Actual production inbox/dispatcher/native pipe/journal result correlation."""
import sys
import time
import json
import threading

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_outbox import operation

runtime = runtime_fixture


@pytest.mark.parametrize("rollback_receipt", [False, True])
@pytest.mark.parametrize("large_output", [False, True])
def test_terminal_is_correlated_to_transport_attempt_and_releases_lane(runtime, monkeypatch, rollback_receipt, large_output):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, peers, operator_key, _ = runtime
    source = _FAKE_SERVER_SOURCE
    if large_output:
        original = '    write_msg({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "itemId": item_id, "delta": text}})'
        source = source.replace(original, '    for _ in range(12):\n' + original.replace('"delta": text', '"delta": "x" * 100000').replace('    write_msg', '        write_msg'))
        assert source != _FAKE_SERVER_SOURCE
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source],
        cwd=root, env=kwargs["backend"]["env"])
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator_key},
        json={"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    failed, recovered = threading.Event(), False
    allow_projection = threading.Event()
    ingress = deps.harness_supervisor.event_ingress
    consume = ingress.consume_terminal

    def consume_with_failure(uow, event):
        consume(uow, event)
        if event.delivery_phase == "terminal" and not allow_projection.is_set():
            failed.set()
            raise OSError("fixture rollback after receipt creation")

    if rollback_receipt:
        monkeypatch.setattr(ingress, "consume_terminal", consume_with_failure)
    for _ in range(2):
        created = send_message(runtime, body="fixture result")
        operation_id = created["runtime_operations"][0]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            row = operation(runtime, operation_id)
            if failed.is_set() and not recovered:
                assert row["terminal_event_id"] is None
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    assert uow.connection.execute("SELECT status FROM message_deliveries WHERE delivery_id=?",
                        (row["delivery_id"],)).fetchone()[0] == "unread"
                # Keep automatic retries failing until the rollback snapshot is
                # checked; a valid fast background recovery must not race it.
                allow_projection.set()
                ingress.recover()
                recovered = True
            if row["status"] == "ACCEPTED" and row.get("terminal_event_id"):
                break
            time.sleep(.02)
        assert row["status"] == "ACCEPTED", "native completion left transport unconfirmed"
        assert row.get("terminal_event_id"), "terminal has no durable attempt correlation"
        with deps.connection_factory.unit_of_work(write=False) as uow:
            result = uow.connection.execute("SELECT * FROM runtime_results WHERE event_id=?",
                (row["terminal_event_id"],)).fetchone()
            assert result["operation_id"] == operation_id and result["attempt_id"] == row["attempt_id"]
            delivery = uow.connection.execute("SELECT status FROM message_deliveries WHERE delivery_id=?",
                (row["delivery_id"],)).fetchone()
            assert delivery["status"] == "read", "observed processing never consumes the reserved logical delivery"
            if large_output:
                assert len(result["output_text"].encode()) == 1024 * 1024
                assert result["output_truncated"] and result["output_event_count"] == 12
            else:
                assert "fixture result" in dict(result).get("output_text", ""), "durable result omits assembled output"
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_journal_checkpoint SET ordinal=0")
    ingress = deps.harness_supervisor.event_ingress
    for _ in range(20):
        ingress.recover()
        if not ingress.projection_pending:
            break
    assert not ingress.projection_pending
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE operation_id IS NOT NULL").fetchone()[0] == 2
        receipts = list(uow.connection.execute("SELECT body FROM messages WHERE subject LIKE 'runtime processing receipt:%'"))
        assert len(receipts) == 2
        for receipt in receipts:
            body = json.loads(receipt["body"])
            assert body["ack_source"] == "native_terminal" and body["human_read"] is False


def test_stale_terminal_cannot_free_lane_and_matching_interrupt_wakes_next(runtime):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    from test_runtime_outbox import wait_status
    deps, client, root, _, operator_key, _ = runtime
    source = _FAKE_SERVER_SOURCE.replace('    if "TRIGGER_HOLD" in text:',
        '    if "TRIGGER_HOLD" in text:\n'
        '        write_msg({"method":"turn/completed", "params":{"threadId":thread_id, "turn":{"id":"stale", "status":"completed"}}})\n'
        '    if "TRIGGER_HOLD" in text:')
    source = source.replace('"result": {"userAgent": "okto-nexus/0.156.1"}',
        '"result": {"userAgent": "okto-nexus/0.156.1"}', 1)
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source], cwd=root, env=kwargs["backend"]["env"])
    headers = {"x-api-key": operator_key}
    opened = client.post("/api/v1/harness/sessions", headers=headers,
        json={"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    session_id = opened.json()["data"]["session_id"]
    first = send_message(runtime, body="TRIGGER_HOLD")["runtime_operations"][0]
    wait_status(runtime, first, "ACCEPTED")
    second = send_message(runtime, body="next fixture")["runtime_operations"][0]
    deps.runtime_dispatcher.scan_once()
    assert operation(runtime, second)["status"] == "PENDING"
    assert operation(runtime, first)["terminal_event_id"] is None
    deadline = time.monotonic() + 5
    stale = None
    while time.monotonic() < deadline:
        stale = next((event for event in deps.harness_supervisor.replay_events(session_id)
                      if event.turn_id == "stale"), None)
        if stale:
            break
        time.sleep(.02)
    assert stale is not None and stale.operation_id is None
    interrupted = client.post(f"/api/v1/harness/sessions/{session_id}/interrupt", headers=headers, json={})
    assert interrupted.status_code == 200, interrupted.text
    wait_status(runtime, second, "ACCEPTED")
    assert operation(runtime, first)["terminal_event_id"] is not None
