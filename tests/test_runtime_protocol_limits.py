"""Real disposable pipe peers: oversized unterminated frames cannot wedge readers."""
import os
import sys
import threading
import time
from io import StringIO

import pytest

from okto_nexus.adapters.outbound.harness.codex import _CodexTransport
from okto_nexus.adapters.outbound.harness.pi import _PiTransport
from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


@pytest.mark.parametrize("kind", ["codex", "pi", "claude"])
def test_unterminated_oversized_frame_rejects_and_reaps_owned_peer(kind, tmp_path):
    source = tmp_path / "oversized.py"
    source.write_text("import sys,time\nsys.stdout.write('x'*2000000)\nsys.stdout.flush()\ntime.sleep(60)\n")
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}}
    env["_NEXUS_PROFILE_ENV_SEALED"] = "1"
    detected = threading.Event()
    diagnostics = []

    def diagnostic(line, error):
        diagnostics.append((line, error))
        if "frame_limit_exceeded" in error:
            detected.set()

    common = dict(cwd=str(tmp_path), env=env, on_child_exit=lambda *args: None,
                  on_malformed_line=diagnostic, on_unmatched_response=lambda *args: None)
    argv = [sys._base_executable, "-u", str(source)]
    if kind == "codex":
        peer = _CodexTransport(argv, on_notification=lambda *args: None,
                               on_dispatch_error=diagnostic, **common)
        peer.start()
    elif kind == "pi":
        peer = _PiTransport(argv, on_push_event=lambda *args: None,
                            on_line_processing_error=diagnostic,
                            on_reader_exit=lambda: None, **common)
        peer.start()
    else:
        peer = ClaudeCodeStreamConnector(binary=argv[0], argv=argv[1:], cwd=str(tmp_path), env=env)
        emit = peer._emit

        def observe(kind, native_event, payload):
            emit(kind, native_event, payload)
            if native_event == "transport_frame_limit_exceeded":
                diagnostic("", "frame_limit_exceeded")

        peer._emit = observe
        peer.start(owning_agent_id="fixture")
    try:
        assert detected.wait(5), "reader waited for EOF/newline instead of enforcing a frame limit"
        assert peer._proc.wait(timeout=5) != 0
        assert all(len(line) <= 2000 for line, _ in diagnostics)
    finally:
        if peer._proc.poll() is None:
            peer._proc.kill()
            peer._proc.wait(timeout=5)
        peer.close()


def test_frames_preserve_unicode_boundaries_and_bound_stderr_without_newline():
    from okto_nexus.adapters.outbound.harness.framing import (
        MAX_FRAME_CHARS, STDERR_CHUNK_CHARS, FrameLimitExceeded, protocol_lines, stderr_chunks,
    )
    text = "á😀" * (MAX_FRAME_CHARS // 2)
    assert list(protocol_lines(StringIO(text + "\n{}\n"))) == [text + "\n", "{}\n"]
    with pytest.raises(FrameLimitExceeded, match="frame_limit_exceeded"):
        list(protocol_lines(StringIO(text + "x")))
    chunks = list(stderr_chunks(StringIO(text * 3)))
    assert all(len(chunk) <= STDERR_CHUNK_CHARS for chunk in chunks)
    assert "".join(chunks) == text * 3


def test_oversized_turn_fault_reaches_production_journal_without_completion(runtime):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, _, operator_key, _ = runtime
    source = _FAKE_SERVER_SOURCE.replace(
        '    if "TRIGGER_HOLD" in text:',
        '    if "TRIGGER_OVERSIZED" in text:\n'
        '        sys.stdout.write("x" * 2000000)\n'
        '        sys.stdout.flush()\n'
        '        time.sleep(60)\n'
        '    if "TRIGGER_HOLD" in text:')
    peers = []

    def factory(**kwargs):
        peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source],
                                       cwd=root, env=kwargs["backend"]["env"])
        peers.append(peer)
        return peer

    deps.harness_connector_factories["codex"] = factory
    headers = {"x-api-key": operator_key}
    opened = client.post("/api/v1/harness/sessions", headers=headers, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    session_id = opened.json()["data"]["session_id"]
    response = client.post(f"/api/v1/harness/sessions/{session_id}/send", headers=headers,
                           json={"payload": {"text": "TRIGGER_OVERSIZED"}})
    assert response.status_code == 200, response.text
    deadline = time.monotonic() + 5
    events = []
    while time.monotonic() < deadline:
        events = deps.harness_supervisor.replay_events(session_id)
        if any(event.native_event == "transport/malformed_line" for event in events):
            break
        time.sleep(.02)
    fault = next(event for event in events if event.native_event == "transport/malformed_line")
    assert "frame_limit_exceeded" in fault.payload["error"]
    assert fault.payload["line"] == ""
    assert fault.event_id and fault.sequence
    assert not any(event.kind == "turn_completed" for event in events)
    assert peers[0]._transport._proc.wait(timeout=5) != 0
