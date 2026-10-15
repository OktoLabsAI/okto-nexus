"""Real Core native adapters preserve fragmented output under pipe pressure."""
import asyncio
import json
import sys
import time
from pathlib import Path

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers


@pytest.mark.parametrize("local_setup", ["pi_rpc", "codex_app_server", "claude_stream"], indirect=True)
def test_core_fragmented_utf8_and_full_pipes_preserve_two_turns(connected_local):
    from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
    from nexus_connector_core.native.adapters.pi import PiRpcConnector
    from nexus_connector_core.native.adapters.claude_code_stream import ClaudeCodeStreamConnector
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE as codex_source
    from test_harness_pi_connector import _FAKE_SERVER_SOURCE as pi_source
    from test_harness_claude_code_connector import _FAKE_CLAUDE_SCRIPT as claude_source
    from test_runtime_fragmented_pipes import WIRE
    setup, binding, _ = connected_local
    deps, app, client, headers, _, candidate, root = setup
    adapter = candidate.adapter_id
    stats = root / "wire-stats.json"
    source = {"pi_rpc": pi_source, "codex_app_server": codex_source, "claude_stream": claude_source}[adapter]
    source = source.replace("json.dumps(obj)", "json.dumps(obj, ensure_ascii=False)")
    source = source.replace("sys.stdout.write(", "wire_write(")
    source = "STATS_PATH=" + repr(str(stats)) + "\n" + WIRE + "\n" + source
    peers = []
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            if adapter == "claude_stream":
                peer = ClaudeCodeStreamConnector(binary=sys._base_executable, argv=["-u", "-c", source],
                    version_argv=["-c", "print('2.1.281 (Claude Code)')"], cwd=str(root), env={})
            else:
                cls = PiRpcConnector if adapter == "pi_rpc" else CodexAppServerConnector
                version = {"version_command": [sys._base_executable, "-c", "print('0.85.1')"]} if adapter == "pi_rpc" else {}
                peer = cls(command=[sys._base_executable, "-u", "-c", source], cwd=str(root), env={}, **version)
            peers.append(peer)
            native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
            return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch, context=context)
    app.state.embedded_dispatch_owner.native_factory = Factory()
    opened = admit(setup, binding, "pressure-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    sid = opened["scope"]["session_id"]
    for index in range(2):
        text = f"turn {index}: ação 🧪 漢字"
        sent = admit(setup, binding, f"pressure-turn-{index}", "turn.submit", session_id=sid, text=text)
        wait_receipt(setup, sent, stages=("SUCCEEDED",))
        until = time.monotonic() + 10
        while True:
            result = client.get(f"/api/v1/harness/operations/{sent['operation_id']}", headers=headers["subject"])
            assert result.status_code == 200, result.text
            if text in json.dumps(result.json(), ensure_ascii=False):
                break
            assert time.monotonic() < until, result.text
            time.sleep(.02)
    observed = json.loads(stats.read_text())
    assert observed["fragmented_frames"] >= 2 and observed["stdout_bytes"] > 262144
    assert observed["stderr_bytes"] == 2 * 1024 * 1024
    with deps.connection_factory.unit_of_work(write=False) as uow:
        events = [json.loads(r[0]) for r in uow.connection.execute("SELECT payload_json FROM execution_event_ingress")]
        assert not [e for e in events if e["category"] == "error"], events
        assert len([e for e in events if e["payload"].get("delivery_phase") == "terminal"]) == 2
    peer = peers[0]
    assert len(peers) == 1
    if adapter == "claude_stream":
        assert len(peer._stderr_tail) <= 50 and sum(len(s) for s in peer._stderr_tail) <= 50 * 4096
        process = peer._proc
    else:
        assert len(peer._transport.stderr_tail()) <= 200 * (4096 + 1)
        process = peer._transport._proc
    closed = admit(setup, binding, "pressure-close", "runtime.close", session_id=sid)
    wait_receipt(setup, closed, stages=("SUCCEEDED",))
    assert process.wait(timeout=5) is not None
