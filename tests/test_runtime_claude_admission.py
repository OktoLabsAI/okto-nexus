"""Bound pending input before writing or interrupting a real disposable pipe peer."""
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import time

from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
from okto_nexus.domain.harness import HarnessCommand
from okto_nexus.errors import OktoNexusError


def test_pending_turn_limit_precedes_native_send_and_steer_effects(tmp_path):
    script = tmp_path / "peer.py"
    log = tmp_path / "input.jsonl"
    script.write_text('''import sys,json
with open(sys.argv[1], 'w', buffering=1) as log:
    for line in sys.stdin:
        log.write(line)
        if json.loads(line)['type'] == 'control_request':
            print(json.dumps({'type':'result','subtype':'success'}), flush=True)
        print(json.dumps({'type':'stream_event','event':{'type':'content_block_start'}}), flush=True)
''')
    peer = ClaudeCodeStreamConnector(binary=sys._base_executable,
        argv=["-u", str(script), str(log)], cwd=str(tmp_path),
        env={"_NEXUS_PROFILE_ENV_SEALED": "1"})
    session = peer.start(owning_agent_id="fixture")

    def attempt(verb):
        try:
            peer.send(session, HarnessCommand(session_id=session.session_id,
                verb=verb, payload={"content": "fixture"}))
            return True
        except OktoNexusError as exc:
            assert "capacity" in str(exc)
            return False

    try:
        with ThreadPoolExecutor(max_workers=8) as workers:
            admitted = list(workers.map(attempt, ["send_turn"] * 40))
        assert sum(admitted) == 32
        assert len(peer._pending_turns) == 32
        assert peer._turn_generating.wait(5)
        assert not attempt("steer")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            lines = log.read_text().splitlines() if log.exists() else []
            if len(lines) >= 32:
                break
            time.sleep(.01)
        assert len(lines) == 32
        assert all(json.loads(line)["type"] == "user" for line in lines)
        peer.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt", payload={}))
        deadline = time.monotonic() + 5
        while len(peer._pending_turns) == 32 and time.monotonic() < deadline:
            time.sleep(.01)
        assert len(peer._pending_turns) == 31
        assert attempt("send_turn")
        assert len(peer._pending_turns) == 32
    finally:
        peer.close()
