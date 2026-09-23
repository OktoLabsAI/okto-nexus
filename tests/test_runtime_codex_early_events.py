"""Unattributed native notifications must not grow an unbounded startup cache."""
import sys
import time

import pytest

from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


@pytest.mark.parametrize("payload_chars", [8, 32768])
def test_unknown_thread_flood_has_explicit_bounded_failure(payload_chars):
    peer = CodexAppServerConnector()
    with pytest.raises(RuntimeError, match="early_event_limit_exceeded"):
        for index in range(512):
            peer._on_notification("item/agentMessage/delta", {
                "threadId": str(index), "delta": "x" * payload_chars,
            })
    retained = sum(len(events) for events in peer._unmapped_thread_events.values())
    assert retained <= 128
    assert sum(len(params["delta"].encode()) for events in
               peer._unmapped_thread_events.values() for _, params in events) <= 1024 * 1024


def test_early_turn_state_replays_and_releases_capacity(tmp_path):
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    source = _FAKE_SERVER_SOURCE.replace(
        'write_msg({"method": "thread/started", "params": {"thread": {"id": thread_id}}})',
        'write_msg({"method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": "early"}}})')
    peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source],
        cwd=str(tmp_path), env={"_NEXUS_PROFILE_ENV_SEALED": "1"},
        thread_start_overrides={"_early_notify": True})
    try:
        for _ in range(3):
            session = peer.start(owning_agent_id="fixture")
            assert peer._sessions_by_id[session.session_id].active_turn_id == "early"
            assert peer._early_event_count == peer._early_event_bytes == 0
            assert peer._unmapped_thread_events == {}
    finally:
        peer.close()


def test_unknown_thread_flood_reaps_process_and_journals_fault(runtime):
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, _, operator_key, _ = runtime
    source = _FAKE_SERVER_SOURCE.replace(
        '    if "TRIGGER_HOLD" in text:',
        '    if "TRIGGER_UNKNOWN" in text:\n'
        '        for i in range(512):\n'
        '            write_msg({"method":"item/agentMessage/delta", "params":{'
        '"threadId":"unknown-"+str(i), "delta":"fixture"}})\n'
        '        return\n'
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
    sent = client.post(f"/api/v1/harness/sessions/{session_id}/send", headers=headers,
                      json={"payload": {"text": "TRIGGER_UNKNOWN"}})
    assert sent.status_code == 200, sent.text
    assert peers[0]._transport._proc.wait(timeout=5) != 0
    deadline = time.monotonic() + 10
    events = []
    while time.monotonic() < deadline:
        events = deps.harness_supervisor.replay_events(session_id)
        if any(event.native_event == "transport/dispatch_error" for event in events):
            break
        time.sleep(.02)
    failure = next(event for event in events if event.native_event == "transport/dispatch_error")
    assert failure.payload == {"line": "", "error": "early_event_limit_exceeded"}
    assert failure.event_id and failure.sequence
    assert not any(event.kind == "turn_completed" for event in events)
