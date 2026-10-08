"""Adapter-owned event retention and subscriptions must have explicit bounds."""
import pytest
import sys
import time
import threading

from legacy_native_fixture.codex import CodexAppServerConnector
from legacy_native_fixture.pi import PiRpcConnector
from legacy_native_fixture.claude_code_stream import ClaudeCodeStreamConnector
from legacy_native_fixture.claude_code_attach import ClaudeCodeAttachConnector
from okto_nexus.domain.harness import HarnessSession
from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


def event_source(kind, tmp_path):
    if kind == "codex":
        peer = CodexAppServerConnector(env={})
        def emit(payload):
            peer._push_event("fixture", "item/agentMessage/delta", payload, thread_id="thread", turn_id="turn")
    elif kind == "pi":
        peer = PiRpcConnector(env={})
        peer._session_id = "fixture"
        def emit(payload):
            peer._push_event("output_delta", "fixture_delta", payload)
    elif kind == "claude":
        peer = ClaudeCodeStreamConnector(env={})
        peer._session = HarnessSession(session_id="fixture", harness_kind="claude_code", owning_agent_id="agent",
            status="STARTING", capabilities=peer.capabilities, started_at="2026-09-22T00:00:00Z")
        def emit(payload):
            peer._emit("output_delta", "fixture_delta", payload)
    else:
        peer = ClaudeCodeAttachConnector(4242, sessions_dir=tmp_path, env={})
        def emit(payload):
            peer._record_local_event(kind="error", native_event="fixture_error", payload=payload)
    return peer, emit


@pytest.mark.parametrize("kind", ["codex", "pi", "claude", "attach"])
def test_native_history_has_byte_bound_and_explicit_expired_replay(kind, tmp_path):
    peer, emit = event_source(kind, tmp_path)
    for index in range(1024):
        emit({"text": str(index) + "x" * 8192})
    assert len(peer._event_history) <= 512, "native history retained over four MiB of payload"
    with pytest.raises(RuntimeError, match="replay"):
        list(peer._event_history)


@pytest.mark.parametrize("kind", ["codex", "pi", "claude"])
@pytest.mark.parametrize("payload_chars", [4096, 32768])
def test_slow_subscriber_is_bounded_and_reports_a_gap(kind, payload_chars, tmp_path):
    peer, emit = event_source(kind, tmp_path)
    emit({"text": "first"})
    events = peer.events()
    assert next(events).payload["text"] == "first"
    for index in range(1024):
        emit({"text": str(index) + "x" * payload_chars})
    assert peer._subscribers[0].qsize() <= 128, "subscriber retained an unbounded backlog"
    peer._closed_event.set()
    retained_bytes = 0
    with pytest.raises(RuntimeError, match="overflow"):
        for event in events:
            retained_bytes += len(event.payload["text"].encode())
    assert retained_bytes <= 2 * 1024 * 1024
    assert peer._subscribers == []


@pytest.mark.parametrize("kind", ["codex", "pi", "claude"])
def test_subscriber_admission_is_bounded_and_releases_capacity(kind, tmp_path):
    peer, emit = event_source(kind, tmp_path)
    emit({"text": "seed"})
    streams = []
    try:
        for _ in range(16):
            stream = peer.events()
            assert next(stream).payload["text"] == "seed"
            streams.append(stream)
        with pytest.raises(RuntimeError, match="subscription capacity"):
            next(peer.events())
        streams.pop().close()
        replacement = peer.events()
        assert next(replacement).payload["text"] == "seed"
        replacement.close()
    finally:
        for stream in streams:
            stream.close()
    assert peer._subscribers == []


def test_expired_codex_thread_history_does_not_block_new_thread_subscription(tmp_path):
    peer, emit = event_source("codex", tmp_path)
    for _ in range(1024):
        emit({"text": "x" * 8192})
    peer._push_event("new-session", "thread/started", {"text": "new"}, thread_id="new-thread", turn_id=None)
    stream = peer.events_for_session("new-session")
    assert next(stream).session_id == "new-session"
    stream.close()
    with pytest.raises(RuntimeError, match="replay expired"):
        next(peer.events_for_session("fixture"))


def test_retained_terminal_drains_before_explicit_overflow():
    from legacy_native_fixture.event_buffers import NativeEventQueue
    from okto_nexus.domain.harness import HarnessEvent
    queue = NativeEventQueue(max_events=2)
    event = HarnessEvent(session_id="fixture", harness_kind="codex", kind="turn_completed",
        native_event="turn/completed", occurred_at="2026-09-22T00:00:00Z", payload={"text": "final"})
    assert queue.put(event)
    assert queue.put(event)
    assert not queue.put(event)
    assert queue.get(timeout=0) is event
    assert queue.get(timeout=0) is event
    with pytest.raises(RuntimeError, match="overflow"):
        queue.get(timeout=0)
