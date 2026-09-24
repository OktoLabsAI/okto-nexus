"""A blocked SQLite projector must not block durable native ingress."""
import sys
import time

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector

runtime = runtime_fixture


def test_native_burst_is_journaled_while_projection_is_blocked(runtime, tmp_path):
    deps, client, root, _, operator, _ = runtime
    gate = tmp_path / "emit-burst"
    source = _FAKE_SERVER_SOURCE.replace('if "TRIGGER_HOLD" in text:\n        return',
        'if "TRIGGER_HOLD" in text:\n'
        '        deadline = time.monotonic() + 10\n'
        f'        while not os.path.exists({str(gate)!r}) and time.monotonic() < deadline: time.sleep(.01)\n'
        '        for index in range(256):\n'
        '            write_msg({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "delta": "x"}})\n'
        '            time.sleep(.002)\n'
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
    assert ingress._project_lock.acquire(timeout=3)
    try:
        before = ingress.journal.watermark
        gate.write_text("ready")
        deadline = time.monotonic() + 8
        while ingress.journal.watermark < before + 260 and time.monotonic() < deadline:
            time.sleep(.01)
        assert ingress.journal.watermark >= before + 260, "SQLite projection blocked native durable capture"
        assert peers[0]._transport._proc.poll() is None, "Normal burst overflowed the native queue"
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute("SELECT 1 FROM runtime_results WHERE command_operation_id=?", (op,)).fetchone()
    finally:
        ingress._project_lock.release()
    result = wait_operation(runtime, op, lambda row: row["result_durable"])
    assert result["result"]["output_text"] == "x" * 256 + "BURST_COMPLETE"
