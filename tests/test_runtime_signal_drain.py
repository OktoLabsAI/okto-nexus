"""Actual serve signal/clean exit with an active peer and unprojected journal."""
from contextlib import closing
import json
import os
import sqlite3
import time

import pytest

import runtime_serve_shutdown_fixture as fixture
from test_pr34_remediation import tool


INSTRUMENT = r'''
from pathlib import Path
import json
from okto_nexus.application.runtime_event_ingress import RuntimeEventIngress
from okto_nexus.application.harness_supervisor import HarnessSupervisor
held=threading.Event()
released=threading.Event()
capture_original=RuntimeEventIngress.capture
recover_original=RuntimeEventIngress.recover
shutdown_original=HarnessSupervisor.begin_shutdown
close_original=RuntimeEventIngress.close
def record(name,value):
    path=Path(marker).with_name(name)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(path)
def capture_pending(self,event,**kwargs):
    if event.kind=='output_delta': held.set()
    result=capture_original(self,event,**kwargs)
    if event.kind=='output_delta':
        record('pending.json',{
            'event_id':result.event_id,'operation_id':result.operation_id,
            'watermark':self.journal.watermark,'pending':self.projection_pending})
    return result
def recover_pending(self):
    if held.is_set() and not released.is_set():
        self.projection_pending=True
        return 0
    return recover_original(self)
def begin_drain(self,**kwargs):
    if held.is_set():
        record('shutdown-boundary.json',{
            'pending':self.event_ingress.projection_pending,
            'watermark':self.event_ingress.journal.watermark})
        released.set()
    return shutdown_original(self,**kwargs)
def close_drained(self):
    close_original(self)
    record('journal-closed.json',{'watermark':self.journal.watermark,'pending':self.projection_pending})
RuntimeEventIngress.capture=capture_pending
RuntimeEventIngress.recover=recover_pending
HarnessSupervisor.begin_shutdown=begin_drain
RuntimeEventIngress.close=close_drained
'''


@pytest.mark.parametrize("mode", ["clean", pytest.param("term", marks=pytest.mark.skipif(
    os.name != "posix", reason="POSIX SIGTERM; clean mode exercises Windows graceful shutdown"))])
def test_active_turn_and_unprojected_journal_drain_before_serve_exits(tmp_path, monkeypatch, mode):
    peer = fixture.PEER.replace('for line in sys.stdin:', '''def emit(value):
    print(json.dumps(value),flush=True)
for line in sys.stdin:''')
    peer = peer.replace('    if msg.get("type"):', '''    if msg.get("type")=="prompt":
        emit({"type":"response","command":"prompt","success":True,"data":{}})
        emit({"type":"agent_start"})
        emit({"type":"turn_start"})
        emit({"type":"message_start","role":"assistant"})
        emit({"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"pending during signal"}})
        continue
    if msg.get("type"):''')
    launcher = fixture.LAUNCHER.replace('original_bootstrap=mcp_server.bootstrap', INSTRUMENT + '\noriginal_bootstrap=mcp_server.bootstrap')
    launcher = launcher.replace('PiRpcConnector(command=', 'PiRpcConnector(version_command=[sys._base_executable,"-c","print(\'0.85.1\')"],command=')
    monkeypatch.setattr(fixture, "PEER", peer)
    monkeypatch.setattr(fixture, "LAUNCHER", launcher)
    server = fixture.ServeFixture(tmp_path)
    def rows(sql, params=()):
        with closing(sqlite3.connect(server.home / "nexus.db")) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(r) for r in connection.execute(sql, params)]
    try:
        sid = server.open()
        sent = tool(server.client, server.operator, "harness_send", {"session_id": sid,
            "payload": {"text": "hold active until serve shutdown"}})
        assert sent["ok"], sent
        op = sent["data"]["operation_id"]
        pending_path = tmp_path / "pending.json"
        deadline = time.monotonic() + 8
        while not pending_path.exists():
            assert time.monotonic() < deadline
            time.sleep(.02)
        pending = json.loads(pending_path.read_text())
        assert pending["operation_id"] == op and pending["pending"] and pending["watermark"] > 0
        assert rows("SELECT * FROM harness_events WHERE event_id=?", (pending["event_id"],)) == []
        assert rows("SELECT * FROM runtime_results WHERE command_operation_id=?", (op,)) == []
        assert not rows("SELECT terminal_event_id FROM runtime_commands WHERE operation_id=?", (op,))[0]["terminal_event_id"]
        began = time.monotonic()
        server.stop(mode)
        assert time.monotonic()-began < 20
        # serve deliberately converges graceful SIGTERM on normal cleanup/exit0.
        assert server.process.returncode == 0
        boundary = json.loads((tmp_path / "shutdown-boundary.json").read_text())
        assert boundary["pending"] and boundary["watermark"] >= pending["watermark"]
        captured = rows("SELECT * FROM harness_events WHERE event_id=?", (pending["event_id"],))
        assert len(captured) == 1 and "pending during signal" in captured[0]["payload"]
        assert rows("SELECT * FROM runtime_results WHERE command_operation_id=?", (op,)) == []
        operation = rows("SELECT status,terminal_event_id,reason FROM runtime_commands WHERE operation_id=?", (op,))[0]
        assert operation == {"status": "OUTCOME_UNKNOWN", "terminal_event_id": None, "reason": "runtime_lost"}
        assert rows("SELECT * FROM harness_events WHERE delivery_phase='terminal'") == []
        closed = json.loads((tmp_path / "journal-closed.json").read_text())
        assert not closed["pending"] and closed["watermark"] >= boundary["watermark"]
        assert rows("SELECT ordinal FROM runtime_journal_checkpoint")[0]["ordinal"] == closed["watermark"]
        assert rows("PRAGMA foreign_key_check") == []
    finally:
        server.close()
