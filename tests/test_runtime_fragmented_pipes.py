"""Real pipe byte fragmentation and concurrent stdout/stderr pressure."""
import json
from pathlib import Path
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation

runtime = runtime_fixture

WIRE = r'''
import os,threading,time
from pathlib import Path
_pressure_started=False
_stats={'fragmented_frames':0,'stdout_bytes':0,'stderr_bytes':0}
def _write_all(fd,data):
    while data:
        count=os.write(fd,data)
        data=data[count:]
def wire_write(text):
    global _pressure_started
    encoded=text.encode('utf-8')
    marker='🧪'.encode('utf-8')
    at=encoded.find(marker)
    flood=None
    if at>=0:
        # Legal JSON whitespace makes a frame larger than ordinary pipe
        # capacity while staying below the unchanged parser frame limit.
        encoded=encoded.rstrip(b'\n')+b' '*131072+b'\n'
        if not _pressure_started:
            _pressure_started=True
            def stderr_flood():
                data=b'e'*4096
                for _ in range(512):
                    _write_all(2,data)
                    _stats['stderr_bytes']+=len(data)
            flood=threading.Thread(target=stderr_flood)
            flood.start()
        _write_all(1,encoded[:at+1])
        for byte in encoded[at+1:at+4]:
            time.sleep(.002)
            _write_all(1,bytes([byte]))
        _write_all(1,encoded[at+4:])
        _stats['fragmented_frames']+=1
    else:
        _write_all(1,encoded)
    _stats['stdout_bytes']+=len(encoded)
    if flood:
        flood.join(10)
        assert not flood.is_alive(), 'stderr not drained'
    Path(STATS_PATH).write_text(json.dumps(_stats))
'''


@pytest.mark.parametrize("adapter", ["pi", "codex", "claude_code.stream"])
def test_fragmented_utf8_and_full_pipes_preserve_two_turns(runtime, adapter):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from okto_nexus.adapters.outbound.harness.pi import PiRpcConnector
    from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE as codex_source
    from test_harness_pi_connector import _FAKE_SERVER_SOURCE as pi_source
    from test_harness_claude_code_connector import _FAKE_CLAUDE_SCRIPT as claude_source
    deps, client, root, _, operator, _ = runtime
    stats = Path(root) / "wire-stats.json"
    source = {"pi": pi_source, "codex": codex_source, "claude_code.stream": claude_source}[adapter]
    source = source.replace('json.dumps(obj)', 'json.dumps(obj, ensure_ascii=False)')
    source = source.replace('sys.stdout.write(', 'wire_write(')
    source = 'STATS_PATH=' + repr(str(stats)) + '\n' + WIRE + '\n' + source
    peers = []
    def factory(**kwargs):
        env = kwargs["backend"]["env"]
        if adapter == "claude_code.stream":
            peer = ClaudeCodeStreamConnector(binary=sys._base_executable, argv=["-u", "-c", source],
                version_argv=["-c", "print('2.1.281 (Claude Code)')"], cwd=root, env=env)
        else:
            cls = PiRpcConnector if adapter == "pi" else CodexAppServerConnector
            version = {"version_command": [sys._base_executable, "-c", "print('0.85.1')"]} if adapter == "pi" else {}
            peer = cls(command=[sys._base_executable, "-u", "-c", source], cwd=root, env=env, **version)
        peers.append(peer)
        return peer
    kind = "claude_code" if adapter == "claude_code.stream" else adapter
    deps.harness_connector_factories[kind] = factory
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": kind, "endpoint_id": "endpoint-" + adapter, "project_root": root})
    assert opened.status_code == 200, opened.text
    sid = opened.json()["data"]["session_id"]
    for index in range(2):
        text = f"turn {index}: ação 🧪 漢字"
        sent = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": text}})
        assert sent["ok"], sent
        result = wait_operation(runtime, sent["data"]["operation_id"], lambda row: row["result_durable"])
        assert text in result["result"]["output_text"]
    observed = json.loads(stats.read_text())
    assert observed["fragmented_frames"] >= 2
    assert observed["stdout_bytes"] > 262144
    assert observed["stderr_bytes"] == 2*1024*1024
    events = deps.harness_supervisor.replay_events(sid)
    assert not any(e.kind == "error" for e in events)
    assert len([e for e in events if e.delivery_phase == "terminal"]) == 2
    peer = peers[0]
    if adapter == "claude_code.stream":
        assert len(peer._stderr_tail) <= 50
        assert sum(len(s) for s in peer._stderr_tail) <= 50*4096
        process = peer._proc
    else:
        assert len(peer._transport.stderr_tail()) <= 200*(4096+1)
        process = peer._transport._proc
    closed = tool(client, operator, "harness_close", {"session_id": sid})
    assert closed["ok"]
    wait_operation(runtime, closed["data"]["operation_id"], lambda row: row["state"] == "DONE")
    assert process.wait(timeout=5) is not None
