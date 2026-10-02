"""A blocked SQLite projector must not block durable native ingress."""
import sys
import threading
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from legacy_native_fixture.codex import CodexAppServerConnector

runtime = runtime_fixture


def wait_progress(read, complete, *, stage, stall_seconds, record_property):
    """Bound stalls independently of the duration of a progressing disk backlog."""
    began = advanced = time.monotonic()
    previous = None
    while True:
        value, progress = read()
        now = time.monotonic()
        assert now - began < 30, f"{stage} exceeded campaign bound; last watermark {progress}"
        if complete(value):
            record_property(stage + "_seconds", now - began)
            record_property(stage + "_watermark", progress)
            return value
        if progress != previous:
            previous, advanced = progress, now
        assert now - advanced < stall_seconds, f"{stage} stalled at {progress}"
        time.sleep(.01)


@pytest.mark.parametrize("capture_delay", [0, .04], ids=["normal", "slow-storage"])
def test_native_burst_is_journaled_while_projection_is_blocked(runtime, tmp_path, monkeypatch, capture_delay, record_property):
    deps, client, root, _, operator, _ = runtime
    gate = tmp_path / "emit-burst"
    ack_prefix = str(tmp_path / "captured-")
    source = _FAKE_SERVER_SOURCE.replace('if "TRIGGER_HOLD" in text:\n        return',
        'if "TRIGGER_HOLD" in text:\n'
        '        deadline = time.monotonic() + 10\n'
        f'        while not os.path.exists({str(gate)!r}) and time.monotonic() < deadline: time.sleep(.01)\n'
        '        for index in range(256):\n'
        '            write_msg({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "delta": "x"}})\n'
        '            if (index + 1) % 32 == 0:\n'
        f'                ack = {ack_prefix!r} + str(index + 1)\n'
        '                deadline = time.monotonic() + 30\n'
        '                while not os.path.exists(ack) and time.monotonic() < deadline: time.sleep(.01)\n'
        '                assert os.path.exists(ack), "Durable capture did not acknowledge the batch"\n'
        '        text = "BURST_COMPLETE"')
    peers = []
    def factory(**options):
        peer = CodexAppServerConnector(command=[sys.executable, "-u", "-c", source], cwd=root,
            env=options["backend"]["env"])
        peers.append(peer)
        return peer
    deps.harness_connector_factories["codex"] = factory
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    sid = opened.json()["data"]["session_id"]
    sent = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "TRIGGER_HOLD"}})
    assert sent["ok"], sent
    op = sent["data"]["operation_id"]
    wait_operation(runtime, op, lambda row: row["external_acceptance"] == "harness_accepted")
    ingress = deps.harness_supervisor.event_ingress
    append = ingress.journal.append
    terminal_captured = threading.Event()
    captured_deltas = 0
    def delayed_append(event, **kwargs):
        nonlocal captured_deltas
        if capture_delay:
            time.sleep(capture_delay)
        record = append(event, **kwargs)  # Real file write and fsync remain required.
        if event.session_id == sid and event.payload.get("delta") == "x":
            captured_deltas += 1
            if captured_deltas % 32 == 0:
                # The peer waits for capture only, never for SQLite projection.
                # Overflow behavior has separate negative coverage.
                (tmp_path / f"captured-{captured_deltas}").touch()
        if event.session_id == sid and event.delivery_phase == "terminal":
            terminal_captured.set()
        return record
    monkeypatch.setattr(ingress.journal, "append", delayed_append)
    assert ingress._project_lock.acquire(timeout=3)
    try:
        before = ingress.journal.watermark
        gate.write_text("ready")
        wait_progress(lambda: (ingress.journal.watermark, ingress.journal.watermark),
            lambda watermark: watermark >= before + 260 and terminal_captured.is_set(),
            stage="capture", stall_seconds=8, record_property=record_property)
        assert peers[0]._transport._proc.poll() is None, "Normal burst overflowed the native queue"
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute("SELECT 1 FROM runtime_results WHERE command_operation_id=?", (op,)).fetchone()
    finally:
        ingress._project_lock.release()
    def projection():
        response = client.get(f"/api/v1/harness/operations/{op}", headers={"x-api-key": operator})
        assert response.status_code == 200, response.text
        with deps.connection_factory.unit_of_work(write=False) as uow:
            checkpoint = ingress.repo.checkpoint(uow, store_id=ingress.journal.store_id)
        return response.json()["data"], checkpoint
    result = wait_progress(projection, lambda row: row["result_durable"],
        stage="projection", stall_seconds=5, record_property=record_property)
    assert result["result"]["output_text"] == "x" * 256 + "BURST_COMPLETE"
