"""Core native pipe failures and stale controls retain scoped durable evidence."""
import asyncio
import json
import sys
import time

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_agent_recovery_isolation import eventually
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


def open_native(connected, source):
    from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    setup, binding, _ = connected
    _, app, _, _, *_, root = setup
    peers = []
    log = root / "native-wire.jsonl"
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source, str(log)],
                cwd=str(root), env={})
            peers.append(peer)
            native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
            return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch, context=context)
    app.state.embedded_dispatch_owner.native_factory = Factory()
    opened = admit(setup, binding, "protocol-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    return setup, binding, opened["scope"]["session_id"], peers[0], log


def events(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return [json.loads(r[0]) for r in uow.connection.execute("SELECT payload_json FROM execution_event_ingress")]


@pytest.mark.parametrize("fault", ["oversized", "unknown_threads"])
def test_native_protocol_fault_is_durable_and_reaps_peer_without_success(connected_local, fault):
    injection = ('        sys.stdout.write("x" * 2000000)\n        sys.stdout.flush()\n        time.sleep(60)\n'
        if fault == "oversized" else
        '        for i in range(512):\n            write_msg({"method":"item/agentMessage/delta", '
        '"params":{"threadId":"unknown-"+str(i), "delta":"fixture"}})\n        return\n')
    source = _FAKE_SERVER_SOURCE.replace('    if "TRIGGER_HOLD" in text:',
        '    if "TRIGGER_FAULT" in text:\n' + injection + '    if "TRIGGER_HOLD" in text:')
    assert source != _FAKE_SERVER_SOURCE
    setup, binding, sid, peer, _ = open_native(connected_local, source)
    sent = admit(setup, binding, "protocol-fault", "turn.submit", session_id=sid, text="TRIGGER_FAULT")
    marker = "frame_limit_exceeded" if fault == "oversized" else "early_event_limit_exceeded"
    eventually(lambda: marker in json.dumps(events(setup)))
    assert peer._transport._proc.wait(timeout=5) != 0
    observed = events(setup)
    faults = [e for e in observed if marker in json.dumps(e)]
    assert faults and all(e["sequence"] > 0 for e in faults)
    assert all(len(json.dumps(e)) < 5000 for e in faults)
    assert not [e for e in observed if e["payload"].get("delivery_outcome") == "success"]
    view = setup[2].get(f"/v1/runtime/operations/{sent['operation_id']}", headers=setup[3]["subject"])
    assert view.status_code == 200 and view.json().get("executor_stage") != "SUCCEEDED", view.text


def test_stale_native_target_is_rejected_and_matching_interrupt_completes_original_turn(connected_local):
    setup, binding, sid, peer, log = open_native(connected_local, _FAKE_SERVER_SOURCE)
    sent = admit(setup, binding, "held-turn", "turn.submit", session_id=sid, text="TRIGGER_HOLD")
    wait_receipt(setup, sent)
    state = next(iter(peer._sessions_by_id.values()))
    eventually(lambda: bool(state.active_turn_id))
    target = state.active_turn_id
    stale = admit(setup, binding, "stale-native-target", "turn.steer", session_id=sid, text="Must not reach native pipe",
        target=dict(kind="native_turn_id", expected_turn_id="stale-turn"))
    refused = wait_receipt(setup, stale, stages=("FAILED",))
    assert refused["possible_effect"] is False
    wire = [json.loads(line) for line in log.read_text().splitlines()]
    assert not [m for m in wire if m.get("method") == "turn/steer"]
    interrupted = admit(setup, binding, "matching-interrupt", "turn.interrupt", session_id=sid,
        target=dict(kind="native_turn_id", expected_turn_id=target))
    wait_receipt(setup, interrupted)
    wait_receipt(setup, sent, stages=("CANCELLED",))
    wait_receipt(setup, admit(setup, binding, "protocol-close", "runtime.close", session_id=sid), stages=("SUCCEEDED",))
    assert peer._transport._proc.wait(timeout=5) is not None
