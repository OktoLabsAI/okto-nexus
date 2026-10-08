"""Core capture remains durable while the Server projector is paused."""
import asyncio
import json
import threading
import time

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_native_protocol_regressions import open_native
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


@pytest.mark.parametrize("capture_delay", [0, .04], ids=["normal", "slow-storage"])
def test_core_captures_native_burst_while_server_projection_is_paused(connected_local, monkeypatch, capture_delay):
    from nexus_connector_core.journal import SQLiteJournal
    from okto_nexus.bootstrap.embedded_events import EmbeddedEventPublisher
    setup = connected_local[0]
    root = setup[-1]
    gate = root / "emit-burst"
    prefix = str(root / "captured-")
    source = _FAKE_SERVER_SOURCE.replace('if "TRIGGER_HOLD" in text:\n        return',
        'if "TRIGGER_HOLD" in text:\n'
        '        deadline = time.monotonic() + 30\n'
        f'        while not os.path.exists({str(gate)!r}) and time.monotonic() < deadline: time.sleep(.01)\n'
        '        for index in range(256):\n'
        '            write_msg({"method":"item/agentMessage/delta", "params":{"threadId":thread_id,"turnId":turn_id,"delta":"x"}})\n'
        '            if (index+1) % 32 == 0:\n'
        f'                ack = {prefix!r} + str(index+1)\n'
        '                deadline = time.monotonic() + 30\n'
        '                while not os.path.exists(ack) and time.monotonic() < deadline: time.sleep(.01)\n'
        '                assert os.path.exists(ack), "Capture did not commit the batch"\n'
        '        text = "BURST_COMPLETE"')
    assert source != _FAKE_SERVER_SOURCE
    setup, binding, sid, peer, _ = open_native(connected_local, source)
    turn = admit(setup, binding, "capture-burst", "turn.submit", session_id=sid, text="TRIGGER_HOLD")
    wait_receipt(setup, turn)
    original_record = SQLiteJournal.record_event
    captured = []
    terminal = threading.Event()
    async def record(journal, event):
        if capture_delay:
            await asyncio.sleep(capture_delay)
        result = await original_record(journal, event)
        if event.session_id == sid:
            captured.append(result)
            count = sum(e.native_type == "item/agentMessage/delta" for e in captured)
            if count and count % 32 == 0:
                (root / f"captured-{count}").touch()
            if event.payload.get("delivery_phase") == "terminal":
                terminal.set()
        return result
    monkeypatch.setattr(SQLiteJournal, "record_event", record)
    original_step = EmbeddedEventPublisher.step
    paused, release = threading.Event(), threading.Event()
    async def step(publisher, scope):
        if scope["session_id"] == sid and not release.is_set():
            paused.set()
            while not release.is_set():
                await asyncio.sleep(.01)
        return await original_step(publisher, scope)
    monkeypatch.setattr(EmbeddedEventPublisher, "step", step)
    try:
        assert paused.wait(10)
        gate.write_text("ready", encoding="utf-8")
        assert terminal.wait(25), len(captured)
        assert peer._transport._proc.poll() is None
        assert sum(e.native_type == "item/agentMessage/delta" for e in captured) == 257
        assert all(e.sequence > 0 for e in captured)
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute("SELECT 1 FROM execution_event_ingress WHERE session_id=? AND payload_json LIKE '%BURST_COMPLETE%'", (sid,)).fetchone()
    finally:
        release.set()
    wait_receipt(setup, turn, stages=("SUCCEEDED",))
    deadline = time.monotonic() + 10
    while True:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            events = [event for r in uow.connection.execute("SELECT payload_json FROM execution_event_ingress WHERE session_id=? ORDER BY sequence", (sid,)) if (event := json.loads(r[0])).get("operation_id") == turn["operation_id"]]
        if any(e["payload"].get("delivery_phase") == "terminal" for e in events):
            break
        assert time.monotonic() < deadline
        time.sleep(.02)
    assert sum(e["native_type"] == "item/agentMessage/delta" for e in events) == 257
    assert "".join(e["payload"].get("output_text", "") for e in events) == "x" * 256 + "BURST_COMPLETE"
    wait_receipt(setup, admit(setup, binding, "capture-close", "runtime.close", session_id=sid), stages=("SUCCEEDED",))
    assert peer._transport._proc.wait(timeout=5) is not None
