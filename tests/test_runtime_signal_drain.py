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
from dataclasses import asdict
from nexus_connector_core.journal import SQLiteJournal
from okto_nexus.bootstrap.embedded_events import EmbeddedEventPublisher
from okto_nexus.bootstrap.server_shutdown import ServerShutdownCoordinator
held=threading.Event()
released=asyncio.Event()
capture_original=SQLiteJournal.record_event
publish_original=EmbeddedEventPublisher.step
shutdown_original=embedded_dispatch.EmbeddedDispatchOwner._close
request_original=ServerShutdownCoordinator.request
async def short_request(self,**kwargs):
    return await request_original(self,**dict({'timeout_seconds':2},**kwargs))
ServerShutdownCoordinator.request=short_request
def record(name,value):
    path=Path(marker).with_name(name)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(path)
async def capture_pending(self,event):
    target='pending during signal' in json.dumps(asdict(event))
    if target: held.set()
    result=await capture_original(self,event)
    if target:
        record('pending.json',asdict(result))
    return result
async def publish_pending(self,scope):
    if held.is_set() and not released.is_set():
        record('publication-held.json',scope)
        await released.wait()
    return await publish_original(self,scope)
async def begin_drain(self):
    if held.is_set():
        record('shutdown-boundary.json',{'pending':not released.is_set()})
        released.set()
    try:
        await shutdown_original(self)
    except Exception as error:
        record('shutdown-error.json',{'type':type(error).__name__,'error':str(error)})
        raise
    record('journal-closed.json',{'resources':len(self.host._runtime_tasks)})
SQLiteJournal.record_event=capture_pending
EmbeddedEventPublisher.step=publish_pending
embedded_dispatch.EmbeddedDispatchOwner._close=begin_drain
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
        emit({"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"pending during signal with a sufficiently long trailing stream buffer"}})
        continue
    if msg.get("type"):''')
    launcher = fixture.LAUNCHER.replace('Original=uvicorn.Server', INSTRUMENT + '\nOriginal=uvicorn.Server')
    assert launcher != fixture.LAUNCHER
    monkeypatch.setattr(fixture, "PEER", peer)
    monkeypatch.setattr(fixture, "LAUNCHER", launcher)
    server = fixture.ServeFixture(tmp_path)
    def rows(sql, params=()):
        with closing(sqlite3.connect(server.home / "nexus.db")) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(r) for r in connection.execute(sql, params)]
    try:
        sid = server.open(actions=('open', 'send', 'close'))
        sent = tool(server.client, server.subject, "harness_send", {"session_id": sid,
            "idempotency_key": "signal-drain-turn", "payload": {"text": "hold active until serve shutdown"}})
        assert sent["ok"], sent
        op = sent["data"]["operation_id"]
        pending_path = tmp_path / "pending.json"
        deadline = time.monotonic() + 8
        while not (pending_path.exists() and (tmp_path / "publication-held.json").exists()):
            assert time.monotonic() < deadline, server.log_path.read_text(encoding='utf-8')
            time.sleep(.02)
        pending = json.loads(pending_path.read_text())
        assert pending["operation_id"] == op and pending["sequence"] > 0
        event_key = (sid, pending['stream_epoch'], pending['sequence'])
        event_sql = "SELECT * FROM execution_event_ingress WHERE session_id=? AND stream_epoch=? AND sequence=?"
        assert rows(event_sql, event_key) == []
        assert rows("SELECT * FROM runtime_results WHERE canonical_operation_id=?", (op,)) == []
        began = time.monotonic()
        server.stop(mode)
        assert time.monotonic()-began < 20
        # serve deliberately converges graceful SIGTERM on normal cleanup/exit0.
        assert server.process.returncode == 0
        boundary = json.loads((tmp_path / "shutdown-boundary.json").read_text())
        assert boundary["pending"]
        captured = rows(event_sql, event_key)
        assert len(captured) == 1 and "pending during signal" in captured[0]["payload_json"]
        assert rows("SELECT * FROM runtime_results WHERE canonical_operation_id=?", (op,)) == []
        receipts = rows("SELECT canonical_frame FROM execution_receipts WHERE operation_id=? ORDER BY receipt_revision DESC", (op,))
        # Core's accepted receipt remains historical evidence. Proven resource
        # release closes the session without inventing a terminal/result.
        assert json.loads(receipts[0]['canonical_frame'])['stage'] == 'SUBMITTED'
        assert rows('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?', (sid,)) == [
            {'lifecycle_state': 'CLOSED', 'lease_state': 'CLOSED'}]
        assert rows("SELECT * FROM execution_event_ingress WHERE json_extract(payload_json,'$.payload.delivery_phase')='terminal'") == []
        closed = json.loads((tmp_path / "journal-closed.json").read_text())
        assert closed['resources'] == 0
        assert rows("SELECT committed_contiguous FROM execution_event_watermarks WHERE session_id=? AND stream_epoch=?",
                    (sid, pending['stream_epoch']))[0]['committed_contiguous'] >= pending['sequence']
        assert rows("PRAGMA foreign_key_check") == []
    finally:
        server.close()
