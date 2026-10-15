"""Unattributed native notifications must not grow an unbounded startup cache."""
import sys
import time

import pytest

from legacy_native_fixture.codex import CodexAppServerConnector
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




def test_connection_thread_admission_is_bounded_before_native_effects(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    source = _FAKE_SERVER_SOURCE.replace(
        'elif method == "thread/start":',
        'elif method == "thread/start":\n            log({"admitted_thread": True})')
    script = tmp_path / "peer.py"
    script.write_text(source)
    log = tmp_path / "peer.jsonl"
    peer = CodexAppServerConnector(command=[sys._base_executable, "-u", str(script), str(log)],
        cwd=str(tmp_path), env={"_NEXUS_PROFILE_ENV_SEALED": "1"})

    def attempt(_):
        from okto_nexus.errors import OktoNexusError
        try:
            return peer.start(owning_agent_id="fixture")
        except OktoNexusError as exc:
            assert "capacity" in str(exc)
            return None

    try:
        with ThreadPoolExecutor(max_workers=8) as workers:
            sessions = list(workers.map(attempt, range(80)))
        assert sum(session is not None for session in sessions) == 64
        assert len(peer._sessions_by_id) == len(peer._sessions_by_thread) == 64
        assert log.read_text().count('"admitted_thread": true') == 64
    finally:
        peer.close()


def test_uncertain_thread_starts_do_not_recycle_connection_capacity(tmp_path):
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    from okto_nexus.errors import OktoNexusError
    source = _FAKE_SERVER_SOURCE.replace(
        'thread_id = next_thread_id()',
        'thread_id = next_thread_id()\n            if _thread_counter > 1:\n                continue')
    peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source],
        cwd=str(tmp_path), env={"_NEXUS_PROFILE_ENV_SEALED": "1"})
    try:
        peer.start(owning_agent_id="fixture")
        peer._handshake_timeout_s = .02
        for _ in range(63):
            with pytest.raises(OktoNexusError, match="did not answer"):
                peer.start(owning_agent_id="fixture")
        with pytest.raises(OktoNexusError, match="capacity"):
            peer.start(owning_agent_id="fixture")
        assert len(peer._sessions_by_id) == 1
        assert not peer._transport._pending
    finally:
        peer.close()
