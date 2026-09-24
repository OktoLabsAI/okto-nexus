"""Phase 3 (harness-integrations, ADR 0004 D6) - the Codex connector.

Exercises ``okto_nexus.adapters.outbound.harness.codex.CodexAppServerConnector``
against a FAKE ``codex app-server`` - a small standalone Python script
speaking the real JSON-RPC 2.0 stdio framing (request/response/notification/
server-request), launched with ``sys.executable`` so no ``codex`` binary is
required for this file to pass. This exercises the connector's actual
framing, threading and demux code paths, not a mock of the connector itself.

One test (``test_live_against_real_codex_lan_box``) drives the REAL
``codex`` binary against the LAN backend from ADR 0004 D5
(``http://192.168.31.152:8123/v1``, ``qwen3.8-flash``). It is skipped unless
BOTH the real binary is on ``PATH`` and ``OKTO_NEXUS_CODEX_LIVE=1`` is set,
so a normal ``pytest`` run never touches the network or requires codex to be
installed. It writes its config to ``tmp_path`` (``CODEX_HOME``), never to
``~/.codex/config.toml``, and never targets ``192.168.31.222`` (reserved for
a running benchmark per the task's hard constraint).
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pytest

from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from okto_nexus.domain.harness import (
    STEER_TIMING_IMMEDIATE,
    HarnessCommand,
    HarnessEvent,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

# No pytest-timeout dependency in this repo; every blocking wait below is
# bounded explicitly instead - see `_collect_until` / `_wait_for_log_entry`.


# --------------------------------------------------------------------------- #
# Fake ``codex app-server`` - real JSON-RPC 2.0 stdio framing, scripted
# turn behaviour selected by a TRIGGER keyword embedded in the turn's text.
# --------------------------------------------------------------------------- #
_FAKE_SERVER_SOURCE = r'''
import json
import os
import sys
import threading
import time

LOG_PATH = sys.argv[1] if len(sys.argv) > 1 else None
_write_lock = threading.Lock()
_log_lock = threading.Lock()
_counter_lock = threading.Lock()
_thread_counter = 0
_turn_counter = 0


def write_msg(obj):
    with _write_lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def log(entry):
    if not LOG_PATH:
        return
    with _log_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


def next_thread_id():
    global _thread_counter
    with _counter_lock:
        _thread_counter += 1
        return "th_%d" % _thread_counter


def next_turn_id():
    global _turn_counter
    with _counter_lock:
        _turn_counter += 1
        return "turn_%d" % _turn_counter


def handle_turn(thread_id, turn_id, text, req_id):
    if "TRIGGER_ERROR" in text:
        write_msg({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": "boom"}})
        return

    write_msg({"jsonrpc": "2.0", "id": req_id, "result": {"turn": {"id": turn_id, "status": "inProgress"}}})
    write_msg({"method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": "inProgress"}}})

    if "TRIGGER_SERVER_REQUEST" in text:
        # Live-verified real ServerRequest method name (codex app-server
        # generate-json-schema + a live probe against 0.144.6/LAN box,
        # 2026-09-20): "item/tool/call" is not a real ServerRequest method -
        # the real ones are item/commandExecution/requestApproval,
        # item/fileChange/requestApproval, item/tool/requestUserInput, etc.
        # Harmless either way (this connector's reply_method_not_found does
        # not branch on the method name - any id+method combo gets -32601),
        # but corrected for fidelity to the real wire shape.
        write_msg({"jsonrpc": "2.0", "id": 9001, "method": "item/commandExecution/requestApproval", "params": {}})

    if "TRIGGER_MALFORMED" in text:
        with _write_lock:
            sys.stdout.write("not-json-garbage\n")
            sys.stdout.flush()

    if "TRIGGER_EMPTY_METHOD" in text:
        # JSON-RPC-legal (parses fine) but domain-invalid: HarnessEvent
        # rejects an empty native_event. Reproduces the reader-thread wedge
        # class distinct from TRIGGER_MALFORMED's JSONDecodeError.
        write_msg({"method": "", "params": {}})

    if "TRIGGER_ARRAY_PARAMS" in text:
        # JSON-RPC 2.0 explicitly permits "params" as an array. This
        # connector's _extract_thread_id calls params.get(...), which
        # raises AttributeError on a list - the second reader-thread-wedge
        # trigger shape.
        write_msg({"method": "item/started", "params": ["not", "a", "dict"]})

    if "TRIGGER_CRASH" in text:
        time.sleep(0.05)
        os._exit(7)

    if "TRIGGER_HOLD" in text:
        return

    if "TRIGGER_DELAYED_COMPLETE" in text:
        # A deliberate pause between turn/started and the rest of the turn's
        # events, wide enough for a test to reliably call end() WHILE the
        # turn is still in flight (i.e. before turn/completed is even
        # written) rather than racing a turn that completes near-instantly.
        time.sleep(0.3)

    item_id = "item_" + turn_id
    write_msg({"method": "item/started", "params": {"threadId": thread_id, "turnId": turn_id, "item": {"id": item_id, "type": "agentMessage"}, "startedAtMs": 0}})
    write_msg({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "itemId": item_id, "delta": text}})
    write_msg({"method": "item/completed", "params": {"threadId": thread_id, "turnId": turn_id, "item": {"id": item_id, "type": "agentMessage", "text": text}, "completedAtMs": 0}})
    write_msg({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": "completed"}}})


def main():
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        if method is None:
            # A response to a request WE (the fake server) sent - e.g. the
            # connector's -32601 reply to our unsolicited server-request.
            log({"response_to_server_request": msg})
            continue

        if method == "initialize":
            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {"userAgent": "okto-nexus/0.156.1"}})
        elif method == "thread/start":
            thread_id = next_thread_id()
            if params.get("_early_notify"):
                write_msg({"method": "thread/started", "params": {"thread": {"id": thread_id}}})
            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {"thread": {"id": thread_id}}})
        elif method == "turn/start":
            log({"method": "turn/start", "params": params})
            thread_id = params["threadId"]
            text = params["input"][0]["text"]
            turn_id = next_turn_id()
            threading.Thread(target=handle_turn, args=(thread_id, turn_id, text, req_id), daemon=True).start()
        elif method == "turn/steer":
            log({"method": "turn/steer", "params": params})
            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {}})
        elif method == "turn/interrupt":
            log({"method": "turn/interrupt", "params": params})
            # RES-C2 fix: real capture (EV-CX-001-raw_capture_interrupt.jsonl,
            # live-verified against codex 0.144.6/.152) shows the RPC result
            # and turn/completed(status="interrupted") arrive TOGETHER, no
            # separate settle notification and no delay - the fake used to
            # ack and then emit NOTHING further, an omission that let no test
            # observe correct-or-wrong post-interrupt ordering at all. Now
            # matches the real wire: result first, then turn/completed with
            # status "interrupted" for the SAME turnId, written back-to-back.
            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {}})
            write_msg(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": params["threadId"],
                        "turn": {"id": params["turnId"], "status": "interrupted"},
                    },
                }
            )
        elif method == "thread/unsubscribe":
            log({"method": "thread/unsubscribe", "params": params})
            # Live-verified result shape (same probe as above): the real
            # response is {"status": "unsubscribed"}, not {"status": "ok"}.
            # Harmless either way - this connector discards a successful
            # fire-and-forget response entirely and never reads this field -
            # but corrected for fidelity.
            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {"status": "unsubscribed"}})
        else:
            write_msg({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "unhandled by fake server"}})


if __name__ == "__main__":
    main()
'''


@pytest.fixture()
def fake_server_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake_codex_app_server.py"
    script.write_text(_FAKE_SERVER_SOURCE, encoding="utf-8")
    return script


@pytest.fixture()
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "fake_server_log.jsonl"


@pytest.fixture()
def connector(fake_server_script: Path, log_path: Path):
    conn = CodexAppServerConnector(command=[sys.executable, str(fake_server_script), str(log_path)])
    yield conn
    conn.close()


def read_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _collect_until(
    conn: CodexAppServerConnector,
    predicate: Callable[[HarnessEvent], bool],
    *,
    timeout_s: float = 10.0,
) -> list[HarnessEvent]:
    """Drain ``conn.events()`` until ``predicate`` matches, bounded by
    ``timeout_s``. Test-only bounded wait (a ``Queue.get(timeout=...)`` on a
    background pump thread) - NOT the production path, which blocks
    unbounded on ``Queue.get()``; see the module's own docstring on why
    that is not polling.
    """
    q: "queue.Queue[HarnessEvent]" = queue.Queue()

    def pump() -> None:
        for ev in conn.events():
            q.put(ev)

    threading.Thread(target=pump, daemon=True).start()
    collected: list[HarnessEvent] = []
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"predicate not satisfied within {timeout_s}s; collected={collected!r}")
        try:
            ev = q.get(timeout=remaining)
        except queue.Empty:
            raise AssertionError(f"predicate not satisfied within {timeout_s}s; collected={collected!r}") from None
        collected.append(ev)
        if predicate(ev):
            return collected


def _wait_for_log_entry(log_path: Path, predicate: Callable[[dict[str, Any]], bool], *, timeout_s: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for entry in read_log(log_path):
            if predicate(entry):
                return entry
        time.sleep(0.02)
    raise AssertionError(f"no matching log entry within {timeout_s}s; log={read_log(log_path)!r}")


# --------------------------------------------------------------------------- #
# Capabilities (D6)
# --------------------------------------------------------------------------- #
def test_capabilities_match_adr_d6(connector: CodexAppServerConnector) -> None:
    caps = connector.capabilities
    assert caps.send_only is False
    assert caps.steer_timing == STEER_TIMING_IMMEDIATE
    assert caps.interrupt_requires_settle_wait is False
    assert caps.multiplexes_sessions is True
    assert caps.observes_session_end is True


# --------------------------------------------------------------------------- #
# start() - handshake, minting, single-process multiplexing
# --------------------------------------------------------------------------- #
def test_start_mints_session_and_spawns_process_once(connector: CodexAppServerConnector) -> None:
    session_a = connector.start(owning_agent_id="nxs_agent_a")
    transport_after_first = connector._transport

    session_b = connector.start(owning_agent_id="nxs_agent_b")
    transport_after_second = connector._transport

    assert session_a.session_id.startswith("hsess_")
    assert session_b.session_id.startswith("hsess_")
    assert session_a.session_id != session_b.session_id
    assert session_a.harness_kind == "codex"
    assert session_a.status == "STARTING"
    assert session_a.metadata["thread_id"] != session_b.metadata["thread_id"]
    # Only the FIRST start() spawns+initializes; multiplexing reuses it.
    assert transport_after_first is transport_after_second


# --------------------------------------------------------------------------- #
# send_turn - normal completion sequence
# --------------------------------------------------------------------------- #
def test_send_turn_produces_ordered_events_for_the_right_session(connector: CodexAppServerConnector) -> None:
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "ECHO_ME"}),
    )
    events = _collect_until(connector, lambda ev: ev.kind == "turn_completed")

    kinds = [ev.kind for ev in events]
    assert "turn_started" in kinds
    assert "output_delta" in kinds
    assert kinds[-1] == "turn_completed"
    assert all(ev.session_id == session.session_id for ev in events)
    assert all(ev.thread_id in (None, session.metadata["thread_id"]) for ev in events)

    delta_events = [ev for ev in events if ev.native_event == "item/agentMessage/delta"]
    assert delta_events and delta_events[0].payload["delta"] == "ECHO_ME"


# --------------------------------------------------------------------------- #
# Two concurrent sessions - demux must never cross-talk (SYS-09 shape)
# --------------------------------------------------------------------------- #
def test_two_concurrent_sessions_demux_independently(connector: CodexAppServerConnector) -> None:
    session_a = connector.start(owning_agent_id="nxs_agent_a")
    session_b = connector.start(owning_agent_id="nxs_agent_b")

    connector.send(session_a, HarnessCommand(session_id=session_a.session_id, verb="send_turn", payload={"text": "FROM_A"}))
    connector.send(session_b, HarnessCommand(session_id=session_b.session_id, verb="send_turn", payload={"text": "FROM_B"}))

    q: "queue.Queue[HarnessEvent]" = queue.Queue()

    def pump() -> None:
        for ev in connector.events():
            q.put(ev)

    threading.Thread(target=pump, daemon=True).start()

    completed_for: set[str] = set()
    deadline = time.monotonic() + 10.0
    collected: list[HarnessEvent] = []
    while completed_for != {session_a.session_id, session_b.session_id}:
        remaining = deadline - time.monotonic()
        assert remaining > 0, f"timed out; completed_for={completed_for}, collected={collected!r}"
        ev = q.get(timeout=remaining)
        collected.append(ev)
        if ev.kind == "turn_completed":
            completed_for.add(ev.session_id)

    thread_by_session = {session_a.session_id: session_a.metadata["thread_id"], session_b.session_id: session_b.metadata["thread_id"]}
    for ev in collected:
        if ev.thread_id is not None:
            assert ev.thread_id == thread_by_session[ev.session_id], "event routed to the wrong session"

    a_deltas = [ev.payload["delta"] for ev in collected if ev.session_id == session_a.session_id and ev.native_event == "item/agentMessage/delta"]
    b_deltas = [ev.payload["delta"] for ev in collected if ev.session_id == session_b.session_id and ev.native_event == "item/agentMessage/delta"]
    assert a_deltas == ["FROM_A"]
    assert b_deltas == ["FROM_B"]


# --------------------------------------------------------------------------- #
# An unwaited turn/start error response is not silently dropped
# --------------------------------------------------------------------------- #
def test_turn_start_error_response_becomes_error_event(connector: CodexAppServerConnector) -> None:
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_ERROR"}))
    events = _collect_until(connector, lambda ev: ev.kind == "error")
    error_event = events[-1]
    assert error_event.session_id == session.session_id
    assert error_event.native_event == "jsonrpc/error_response"
    assert error_event.payload["message"] == "boom"


def test_fast_native_error_before_write_returns_keeps_request_attribution(connector, monkeypatch):
    session = connector.start(owning_agent_id="fixture")
    transport = connector._transport
    response_seen = threading.Event()
    original_response = transport._on_unmatched_response
    original_write = transport._write

    def observe_response(*args):
        original_response(*args)
        response_seen.set()

    def write_with_fast_peer(payload):
        original_write(payload)
        assert response_seen.wait(2), "scripted native response did not arrive"

    monkeypatch.setattr(transport, "_on_unmatched_response", observe_response)
    monkeypatch.setattr(transport, "_write", write_with_fast_peer)
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn",
        payload={"text": "TRIGGER_ERROR"}))
    errors = [event for event in connector._event_history if event.native_event == "jsonrpc/error_response"]
    assert len(errors) == 1, "response arrived before post-write request registration and was lost"
    assert errors[0].session_id == session.session_id
    assert errors[0].payload["message"] == "boom"
    assert not connector._ff_pending


def test_close_pending_start_waits_for_native_identity_then_interrupts(connector, monkeypatch):
    session = connector.start(owning_agent_id="fixture")
    arrived, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = connector._transport._on_notification
    errors = []

    def delayed_notification(method, params):
        if method == "turn/started":
            arrived.set()
            assert release.wait(5)
        original(method, params)

    monkeypatch.setattr(connector._transport, "_on_notification", delayed_notification)
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn",
        payload={"text": "TRIGGER_HOLD"}))

    def close():
        try:
            connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()

    closer = threading.Thread(target=close, daemon=True)
    try:
        assert arrived.wait(2)
        with pytest.raises(OktoNexusError, match="pending or active turn"):
            connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn",
                payload={"text": "must not race the pending start"}))
        closer.start()
        assert not finished.wait(.1), "unsubscribe raced turn/start's native identity"
    finally:
        release.set()
        if closer.ident:
            closer.join(5)
    assert finished.is_set() and not errors
    terminals = [event for event in connector._event_history if event.native_event == "turn/completed"]
    assert len(terminals) == 1
    assert terminals[0].payload["turn"]["status"] == "interrupted"


# --------------------------------------------------------------------------- #
# steer / interrupt: fail fast with no active turn; use the tracked turnId
# --------------------------------------------------------------------------- #
def test_steer_without_active_turn_raises_validation_error(connector: CodexAppServerConnector) -> None:
    session = connector.start(owning_agent_id="nxs_agent")
    with pytest.raises(OktoNexusError) as exc:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="steer", payload={"text": "x"}))
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_interrupt_without_active_turn_raises_validation_error(connector: CodexAppServerConnector) -> None:
    session = connector.start(owning_agent_id="nxs_agent")
    with pytest.raises(OktoNexusError) as exc:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt", payload={}))
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_steer_and_interrupt_use_the_tracked_turn_id(connector: CodexAppServerConnector, log_path: Path) -> None:
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_HOLD"}))
    started = _collect_until(connector, lambda ev: ev.kind == "turn_started")
    turn_id = started[-1].payload["turn"]["id"]

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="steer", payload={"text": "more please"}))
    steer_entry = _wait_for_log_entry(log_path, lambda e: e.get("method") == "turn/steer")
    assert steer_entry["params"]["expectedTurnId"] == turn_id
    assert steer_entry["params"]["threadId"] == session.metadata["thread_id"]

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt", payload={}))
    interrupt_entry = _wait_for_log_entry(log_path, lambda e: e.get("method") == "turn/interrupt")
    assert interrupt_entry["params"]["turnId"] == turn_id
    assert interrupt_entry["params"]["threadId"] == session.metadata["thread_id"]

    # RES-C2: the fake now emits turn/completed(status="interrupted") right
    # after turn/interrupt's ack, matching the real wire capture
    # (EV-CX-001-raw_capture_interrupt.jsonl, live-verified against codex
    # 0.144.6/.152 - result and turn/completed(interrupted) arrive together,
    # no separate settle event). Assert the ordering is actually observable
    # now: a turn_completed event for THIS turn_id, carrying status
    # "interrupted", is delivered on the event stream after the interrupt
    # was issued.
    completed = _collect_until(connector, lambda ev: ev.kind == "turn_completed")
    interrupted_completion = completed[-1]
    assert interrupted_completion.payload["turn"]["id"] == turn_id
    assert interrupted_completion.payload["turn"]["status"] == "interrupted"


def test_interrupt_clears_active_turn_id_so_a_second_interrupt_is_rejected(
    connector: CodexAppServerConnector,
) -> None:
    """RES-C2 ordering, from the connector's own bookkeeping side: once the
    fake's post-interrupt turn/completed (now emitted - see the test above)
    is dispatched, ``_on_notification`` clears ``state.active_turn_id`` (the
    same handling any other ``turn/completed`` gets). A second interrupt
    issued after that point must therefore fail the same
    no-active-turn VALIDATION_ERROR any interrupt with nothing to interrupt
    does - proving the connector actually observes the completion, not just
    that the wire bytes went by.
    """
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_HOLD"}))
    _collect_until(connector, lambda ev: ev.kind == "turn_started")

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt", payload={}))
    completed = _collect_until(connector, lambda ev: ev.kind == "turn_completed")
    assert completed[-1].payload["turn"]["status"] == "interrupted"

    with pytest.raises(OktoNexusError) as exc:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt", payload={}))
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


# --------------------------------------------------------------------------- #
# end() - local teardown only; the shared process must survive
# --------------------------------------------------------------------------- #
def test_end_unsubscribes_without_killing_the_shared_process(connector: CodexAppServerConnector, log_path: Path) -> None:
    session_a = connector.start(owning_agent_id="nxs_agent_a")
    session_b = connector.start(owning_agent_id="nxs_agent_b")

    connector.send(session_a, HarnessCommand(session_id=session_a.session_id, verb="end", payload={}))
    unsub_entry = _wait_for_log_entry(log_path, lambda e: e.get("method") == "thread/unsubscribe")
    assert unsub_entry["params"]["threadId"] == session_a.metadata["thread_id"]

    with pytest.raises(OktoNexusError) as exc:
        connector.send(session_a, HarnessCommand(session_id=session_a.session_id, verb="send_turn", payload={"text": "x"}))
    assert exc.value.code == ErrorCode.NOT_FOUND

    # The shared child must still be alive and serving session B.
    connector.send(session_b, HarnessCommand(session_id=session_b.session_id, verb="send_turn", payload={"text": "STILL_ALIVE"}))
    events = _collect_until(connector, lambda ev: ev.kind == "turn_completed" and ev.session_id == session_b.session_id)
    assert events[-1].session_id == session_b.session_id


# --------------------------------------------------------------------------- #
# Server -> client REQUEST (has id AND method) must be answered, not hung on
# --------------------------------------------------------------------------- #
def test_unknown_server_request_gets_method_not_found_reply(connector: CodexAppServerConnector, log_path: Path) -> None:
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_SERVER_REQUEST"}))
    _collect_until(connector, lambda ev: ev.kind == "turn_completed")

    reply_entry = _wait_for_log_entry(log_path, lambda e: "response_to_server_request" in e)
    reply = reply_entry["response_to_server_request"]
    assert reply["id"] == 9001
    assert reply["error"]["code"] == -32601


# --------------------------------------------------------------------------- #
# A malformed line must not crash the reader thread or the stream
# --------------------------------------------------------------------------- #
def test_malformed_line_is_surfaced_and_stream_continues(connector: CodexAppServerConnector) -> None:
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_MALFORMED"}))
    events = _collect_until(connector, lambda ev: ev.kind == "turn_completed")
    malformed_events = [ev for ev in events if ev.native_event == "transport/malformed_line"]
    assert malformed_events
    # A transport-level malformed line is an ERROR, not indistinguishable
    # from routine tool_activity noise - observes_session_end depends on
    # this distinction being real (see the connector's mismatch note 9).
    assert malformed_events[0].kind == "error"
    assert events[-1].kind == "turn_completed"


# --------------------------------------------------------------------------- #
# Abrupt child death: no hang, a surfaced event, then clean StopIteration
# --------------------------------------------------------------------------- #
def test_child_death_surfaces_process_exited_and_stops_cleanly(connector: CodexAppServerConnector) -> None:
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_CRASH"}))

    collected: list[HarnessEvent] = []
    finished = threading.Event()

    def drain() -> None:
        for ev in connector.events():
            collected.append(ev)
        finished.set()

    t = threading.Thread(target=drain, daemon=True)
    t.start()
    t.join(timeout=15.0)
    assert finished.is_set(), "events() did not terminate after child death - it hung"
    exit_events = [ev for ev in collected if ev.native_event == "process/exited"]
    assert exit_events
    # A dead child is an ERROR, not indistinguishable from routine
    # tool_activity noise - a supervisor branching on `kind` alone must be
    # able to tell this apart from a token-usage update (mismatch note 9).
    assert exit_events[0].kind == "error"

    # _on_child_exit marks every live session locally ended (the same
    # bookkeeping state end() sets), so this is NOT_FOUND - "no live
    # thread" - not a fresh INTERNAL_ERROR per call; the INTERNAL_ERROR
    # path is for a still-registered, not-yet-ended session whose transport
    # dies between checks (see `send`'s liveness check).
    with pytest.raises(OktoNexusError) as exc:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "x"}))
    assert exc.value.code == ErrorCode.NOT_FOUND


# --------------------------------------------------------------------------- #
# Early thread/started racing the thread/start RESPONSE (buffer + replay)
# --------------------------------------------------------------------------- #
def test_early_thread_started_notification_is_buffered_and_replayed(fake_server_script: Path, log_path: Path) -> None:
    conn = CodexAppServerConnector(command=[sys.executable, str(fake_server_script), str(log_path)], thread_start_overrides={"_early_notify": True})
    try:
        session = conn.start(owning_agent_id="nxs_agent")
        conn.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "AFTER_EARLY_NOTIFY"}))
        events = _collect_until(conn, lambda ev: ev.kind == "turn_completed")
        assert any(ev.native_event == "thread/started" and ev.session_id == session.session_id for ev in events)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# PRIORITY 1 - reader-thread wedge: a JSON-RPC-legal but domain-invalid
# notification must never kill the reader thread or block it forever on an
# unbounded proc.wait() while the child is still alive and healthy.
# --------------------------------------------------------------------------- #
def test_empty_method_notification_does_not_wedge_the_reader_thread(connector: CodexAppServerConnector) -> None:
    """{"method": "", ...} is JSON-RPC-legal (parses fine) but domain-invalid:
    HarnessEvent.__post_init__ rejects an empty native_event. Reproduces the
    class of bug where an unguarded _dispatch() call let that exception
    unwind into the reader thread's unbounded finally-block proc.wait(),
    permanently wedging the reader with the child still alive - fixed by
    guarding _dispatch and bounding proc.wait(). Requires a LIVE session
    (the connection-scoped fan-out this notification takes, having no
    threadId, is a no-op with zero live sessions).
    """
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_EMPTY_METHOD"}),
    )
    events = _collect_until(connector, lambda ev: ev.kind == "turn_completed", timeout_s=10.0)
    dispatch_errors = [ev for ev in events if ev.native_event == "transport/dispatch_error"]
    assert dispatch_errors, "the bad notification must be surfaced, not silently eaten"
    assert dispatch_errors[0].kind == "error"
    # The reader thread must have kept draining stdout: the turn's own
    # completion sequence still arrived after the bad notification.
    assert events[-1].kind == "turn_completed"
    assert connector._transport is not None and connector._transport.is_alive()


def test_array_params_notification_does_not_wedge_the_reader_thread(connector: CodexAppServerConnector) -> None:
    """JSON-RPC 2.0 permits "params" as a bare array. _extract_thread_id
    calls params.get(...), which raises AttributeError on a list - the
    second reproduction shape for the same reader-thread-wedge class as
    the empty-method case above (this one fires unconditionally: it is
    dispatched before any live-session check).
    """
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_ARRAY_PARAMS"}),
    )
    events = _collect_until(connector, lambda ev: ev.kind == "turn_completed", timeout_s=10.0)
    dispatch_errors = [ev for ev in events if ev.native_event == "transport/dispatch_error"]
    assert dispatch_errors, "the bad notification must be surfaced, not silently eaten"
    assert dispatch_errors[0].kind == "error"
    assert events[-1].kind == "turn_completed"
    assert connector._transport is not None and connector._transport.is_alive()


# --------------------------------------------------------------------------- #
# PRIORITY 2 - end() mid-turn must not strand the turn's own trailing events.
# --------------------------------------------------------------------------- #
def test_end_mid_turn_delivers_trailing_events_instead_of_stranding_them(
    connector: CodexAppServerConnector, log_path: Path
) -> None:
    """Ending a session while its turn is still in flight must not silently
    and permanently drop that turn's remaining events (including
    turn_completed) into an unbounded, never-replayed buffer.

    TRIGGER_DELAYED_COMPLETE gives the fake server a deliberate 0.3s pause
    between turn/started and the rest of the turn - wide enough that
    end() (called immediately after the fake server's log confirms it
    received turn/start, well under 0.3s away) reliably lands BEFORE
    turn/completed is even written, so this genuinely exercises "end()
    mid-turn", not a turn that happened to already finish (a plain text
    turn completes near-instantly - the fake server's own log entry for
    receiving turn/start is not by itself proof the turn hasn't ALSO
    already finished by the time it's observed). Uses a SINGLE
    `_collect_until` call (never two on the same connector - see that
    helper's docstring: a second call starts a second orphaned pump thread
    competing for the same shared queue and can silently steal the very
    event a later call is waiting for).
    """
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_DELAYED_COMPLETE"}),
    )
    _wait_for_log_entry(log_path, lambda e: e.get("method") == "turn/start")

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end", payload={}))

    events = _collect_until(connector, lambda ev: ev.kind == "turn_completed", timeout_s=10.0)
    assert any(ev.native_event == "turn/completed" for ev in events)

    thread_id = session.metadata["thread_id"]
    assert not connector._unmapped_thread_events.get(thread_id), (
        "trailing events for an ended thread must be delivered through the "
        "normal path, never stranded in the early-event replay buffer"
    )


# --------------------------------------------------------------------------- #
# Cross-cutting defect class: single-consume shutdown sentinel. A second
# (or later) call to events() must return, never hang, within one poll
# period of close()/child exit - from any thread, any number of times.
# --------------------------------------------------------------------------- #
def test_events_called_twice_after_close_returns_both_times(connector: CodexAppServerConnector) -> None:
    connector.start(owning_agent_id="nxs_agent")
    connector.close()

    first = list(connector.events())
    assert first == []

    second_result: list[Any] = []
    finished = threading.Event()

    def second_call() -> None:
        second_result.extend(connector.events())
        finished.set()

    t = threading.Thread(target=second_call, daemon=True)
    t.start()
    t.join(timeout=5.0)
    assert finished.is_set(), "a second events() call after close() hung instead of returning"
    assert second_result == []


def test_events_called_twice_after_unexpected_child_exit_returns_both_times(
    connector: CodexAppServerConnector,
) -> None:
    session = connector.start(owning_agent_id="nxs_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_CRASH"}))
    _collect_until(connector, lambda ev: ev.native_event == "process/exited", timeout_s=15.0)

    # A first consumer may already be draining via _collect_until's pump
    # thread; a genuinely SECOND, independent caller must still return
    # promptly rather than deadlock on an already-consumed sentinel.
    second_result: list[Any] = []
    finished = threading.Event()

    def second_call() -> None:
        for ev in connector.events():
            second_result.append(ev)
        finished.set()

    t = threading.Thread(target=second_call, daemon=True)
    t.start()
    t.join(timeout=5.0)
    assert finished.is_set(), "a second events() call after child exit hung instead of returning"


# --------------------------------------------------------------------------- #
# subprocess.Popen() must be wrapped: a missing binary is a classified
# OktoNexusError(CONFIG_ERROR), not a raw FileNotFoundError/OSError.
# --------------------------------------------------------------------------- #
def test_missing_binary_raises_config_error_not_raw_oserror() -> None:
    conn = CodexAppServerConnector(command=["definitely-not-a-real-codex-binary-xyz"])
    try:
        with pytest.raises(OktoNexusError) as exc:
            conn.start(owning_agent_id="nxs_agent")
        assert exc.value.code == ErrorCode.CONFIG_ERROR
        assert exc.value.details.get("binary") == "definitely-not-a-real-codex-binary-xyz"
        assert exc.value.details.get("argv") == ["definitely-not-a-real-codex-binary-xyz"]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# A failed initialize handshake must not permanently wedge the connector:
# self._transport is set only after initialize succeeds, so a later start()
# retries the spawn instead of firing thread/start at a dead connection.
# --------------------------------------------------------------------------- #
def test_failed_handshake_does_not_permanently_wedge_the_connector(tmp_path: Path, monkeypatch) -> None:
    from okto_nexus.adapters.outbound.harness import codex as codex_module
    original_spawn = codex_module.spawn_owned_process
    spawned = []

    def capture_owned_process(*args, **kwargs):
        process = original_spawn(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(codex_module, "spawn_owned_process", capture_owned_process)
    pid_path = tmp_path / "hung_child.pid"
    # A child that never answers `initialize` at all (writes nothing back),
    # so the handshake's own bounded request() times out.
    hang_script = (
        "import os, sys, time\n"
        f"open({str(pid_path)!r}, 'w').write(str(os.getpid()))\n"
        "sys.stdin.readline()\n"  # consume the initialize write without answering
        "time.sleep(30)\n"
    )
    conn = CodexAppServerConnector(
        command=[sys.executable, "-c", hang_script],
        handshake_timeout_s=0.3,
    )
    try:
        with pytest.raises(OktoNexusError):
            conn.start(owning_agent_id="nxs_agent")

        # The wedge fix: a failed handshake must not leave a transport
        # behind, or every FUTURE start() would skip respawning entirely.
        assert conn._transport is None

        # Wait on the exact owned process instance, not a numeric PID.
        # os.kill(pid, 0) is not a harmless liveness query on Windows.
        assert pid_path.exists(), "handshake must actually reach the child"
        assert len(spawned) == 1
        assert spawned[0].wait(timeout=5) is not None
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Every blocking wait has a timeout: the stdin write lock must not be able
# to wedge every sender behind a write stuck on a full/unresponsive pipe.
# --------------------------------------------------------------------------- #
def test_stdin_write_lock_acquisition_is_bounded(connector: CodexAppServerConnector, monkeypatch: pytest.MonkeyPatch) -> None:
    import okto_nexus.adapters.outbound.harness.codex as harness_codex_mod

    monkeypatch.setattr(harness_codex_mod, "_STDIN_WRITE_LOCK_TIMEOUT_S", 0.2)
    connector.start(owning_agent_id="nxs_agent")
    transport = connector._transport
    assert transport is not None

    # Simulate a write already stuck holding the lock (e.g. blocked on a
    # full pipe): the write lock is held by someone else, forever.
    transport._write_lock.acquire()
    try:
        with pytest.raises(OktoNexusError) as exc:
            transport._write({"jsonrpc": "2.0", "id": 999999, "method": "noop", "params": {}})
        assert exc.value.code == ErrorCode.INTERNAL_ERROR
    finally:
        transport._write_lock.release()


# --------------------------------------------------------------------------- #
# _emit_for_thread's lookup-or-buffer decision must be atomic under
# _sessions_lock, matching start()'s own register-then-pop lock scope -
# otherwise a registration landing between an unlocked lookup and an
# unlocked append can strand a buffered event permanently.
# --------------------------------------------------------------------------- #
def test_emit_for_thread_buffer_append_is_lock_protected(connector: CodexAppServerConnector) -> None:
    """White-box regression for the _emit_for_thread/start() TOCTOU
    (mismatch note 13): probes whether _sessions_lock is actually held at
    the instant of the append into _unmapped_thread_events for a
    genuinely-unmapped thread id, deterministically (a lock-contention
    probe on the real critical section) rather than relying on the
    scheduler to hit a several-instruction-wide race window.
    """
    probe_lock = connector._sessions_lock
    held_during_append: list[bool] = []
    real_dict = connector._unmapped_thread_events

    class _LockProbeDict(dict):
        def setdefault(self, key, default=None):  # type: ignore[override]
            got: list[bool] = []

            def try_acquire() -> None:
                got.append(probe_lock.acquire(timeout=0.2))

            probe_thread = threading.Thread(target=try_acquire)
            probe_thread.start()
            probe_thread.join(timeout=1.0)
            acquired = bool(got and got[0])
            if acquired:
                probe_lock.release()
            held_during_append.append(not acquired)
            return super().setdefault(key, default)

    connector._unmapped_thread_events = _LockProbeDict(real_dict)
    connector._emit_for_thread("th_never_registered", "item/started", {"threadId": "th_never_registered"})

    assert held_during_append == [True], (
        "the append into _unmapped_thread_events happened without "
        "_sessions_lock held - a concurrent start() could register between "
        "the lookup and the append and lose this event permanently"
    )


# --------------------------------------------------------------------------- #
# SYS-06 (structural): SleepPollWaiter must never appear on this path.
# Checked structurally (imports and instantiation), not by banning the NAME
# outright - the module's own docstrings legitimately discuss it by name to
# explain why it does not appear.
# --------------------------------------------------------------------------- #
def test_module_never_imports_or_instantiates_sleep_poll_waiter() -> None:
    import ast

    import okto_nexus.adapters.outbound.harness.codex as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "waiter" not in node.module, f"imports the waiter module: {node.module}"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "waiter" not in alias.name, f"imports the waiter module: {alias.name}"
    assert "SleepPollWaiter(" not in source, "instantiates SleepPollWaiter"
    assert "time.sleep(" not in source, "sleeps in a loop instead of blocking on I/O"


# --------------------------------------------------------------------------- #
# RES-A3 (general) / RES-B3 (cleanup paths specifically): structural check,
# not a timing check. Greps the module source for every blocking primitive
# class named in the task (Queue.get, lock acquire, thread/lock .join(),
# proc.wait(), socket recv/connect/select) and asserts each call site
# carries an explicit timeout. This module is stdio-only (no sockets) and
# never .join()s its daemon reader threads at all - both are asserted, not
# assumed.
# --------------------------------------------------------------------------- #
def test_every_blocking_wait_in_module_carries_a_timeout() -> None:
    import re

    import okto_nexus.adapters.outbound.harness.codex as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    # Real call sites only - drop comment/docstring lines (which reference
    # these primitives by name in prose, e.g. "the reader thread's own
    # ``proc.wait()``") and blank lines, so only actual code is checked.
    lines = [
        (i, line) for i, line in enumerate(source.splitlines(), 1)
        if line.strip() and not line.strip().startswith(("#", "*", '"""', "'''"))
    ]

    queue_get_sites = [
        (i, line) for i, line in lines
        if re.search(r"\b(reply_q|self\._event_queue)\.get\(", line)
    ]
    assert queue_get_sites, "expected at least one Queue.get() call site - test is stale if the module's shape changed"
    for lineno, line in queue_get_sites:
        assert "timeout" in line, f"line {lineno}: Queue.get() with no visible timeout: {line!r}"

    acquire_sites = [(i, line) for i, line in lines if ".acquire(" in line]
    assert acquire_sites, "expected at least one lock .acquire() call site"
    for lineno, line in acquire_sites:
        assert "timeout" in line, f"line {lineno}: .acquire() with no visible timeout: {line!r}"

    proc_wait_sites = [(i, line) for i, line in lines if re.search(r"\.wait\(", line)]
    assert proc_wait_sites, "expected at least one proc.wait() call site"
    for lineno, line in proc_wait_sites:
        assert "timeout" in line, f"line {lineno}: .wait() with no visible timeout: {line!r}"

    # `.join(` on a thread/lock, excluding string joins like `"\n".join(...)`
    # (a `.join(` immediately preceded by a closing quote is a str.join, not
    # a blocking primitive).
    join_sites = [
        (i, line) for i, line in lines
        if re.search(r'(?<!["\'])\.join\(', line)
    ]
    assert join_sites == [], (
        f"unexpected thread/lock .join() call site(s), verify bounded: {join_sites!r} "
        "- this module was assumed to never join its daemon reader threads"
    )

    for prim in ("recv(", "connect(", "select("):
        assert prim not in source, f"unexpected socket primitive {prim!r} - this module was assumed stdio-only"


# --------------------------------------------------------------------------- #
# RES-A2: two CONCURRENT events() consumers must each receive the FULL
# stream, never a split of it (EV-REV-002/EV-REV-003 Class A/C2 - pi.py
# failed exactly this: "thread A got all 17 events, thread B got zero").
# --------------------------------------------------------------------------- #
def test_two_concurrent_events_consumers_split_the_stream_instead_of_each_getting_the_full_stream(
    connector: CodexAppServerConnector,
) -> None:
    """DEFECT-WITNESS test, now proving the FIX (Phase-4 campaign, RES-A2).

    pi.py was remediated for this exact class (own mismatch note 9/C2):
    ``events()`` hands each caller its OWN subscriber queue seeded from a
    shared history under a lock, so N concurrent consumers each see every
    event. codex.py originally lacked the equivalent fix: ``events()`` did
    ``self._event_queue.get(timeout=...)`` against ONE shared
    ``queue.Queue``, so two concurrent callers raced for the SAME items and
    the stream was SPLIT between them, not duplicated to each. This test
    failed 3/3 deterministically against that code (recorded pre-fix
    output: ``total=5`` instead of the expected ``total=10``). codex.py's
    ``events()``/``_push_event`` now carry the same history+per-subscriber-
    queue fan-out as pi.py (see codex.py's own mismatch note 14a); this
    test now passes and stays as the regression guard for that fan-out.

    Deterministic proof, independent of which thread wins which item: with
    correct per-consumer fan-out the TOTAL item count across 2 concurrent
    consumers of an N-event stream is 2N (each gets all N); with a shared
    queue split it is exactly N (the items are partitioned). Both consumer
    threads are started and given time to genuinely park on the blocking
    ``get()`` BEFORE any event is produced, so a pass is unambiguous
    evidence of correct fan-out, not a lucky race.
    """
    session = connector.start(owning_agent_id="nxs_agent")

    consumer_a: list[HarnessEvent] = []
    consumer_b: list[HarnessEvent] = []
    a_done = threading.Event()
    b_done = threading.Event()

    def drain(sink: list[HarnessEvent], done_flag: threading.Event) -> None:
        for ev in connector.events():
            sink.append(ev)
            if ev.kind == "turn_completed":
                break
        done_flag.set()

    ta = threading.Thread(target=drain, args=(consumer_a, a_done), daemon=True)
    tb = threading.Thread(target=drain, args=(consumer_b, b_done), daemon=True)
    ta.start()
    tb.start()
    time.sleep(0.3)  # let both threads genuinely park on the blocking get()

    connector.send(
        session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "SPLIT_CHECK"})
    )

    ta.join(timeout=8.0)
    tb.join(timeout=8.0)
    if not a_done.is_set() or not b_done.is_set():
        # A consumer that never saw turn_completed (because the OTHER
        # consumer got it) would otherwise block until _closed_event fires -
        # close() unblocks it within one _EVENTS_POLL_S poll period so this
        # test itself stays bounded regardless of the defect's shape.
        connector.close()
        ta.join(timeout=3.0)
        tb.join(timeout=3.0)
    assert a_done.is_set() and b_done.is_set(), "a consumer thread never terminated even after close()"

    total = len(consumer_a) + len(consumer_b)
    expected_full_stream = 5  # turn_started, item/started, item/agentMessage/delta, item/completed, turn/completed
    assert total == 2 * expected_full_stream, (
        f"expected each of 2 concurrent events() consumers to receive the FULL "
        f"{expected_full_stream}-event stream (total={2 * expected_full_stream}); got "
        f"total={total} (A={len(consumer_a)}, B={len(consumer_b)}) - the stream was SPLIT "
        "between them. events() should now fan out via per-consumer subscriber queues "
        "seeded from a shared history (codex.py mismatch note 14a), matching pi.py's "
        "remediated equivalent (its own C2 fix)."
    )


# --------------------------------------------------------------------------- #
# RES-A4: a FAILED start() must still leave events() terminable (EV-REV-003
# C3 - pi.py was remediated for exactly this: _closed_event set in start()'s
# except branch).
# --------------------------------------------------------------------------- #
def test_failed_start_leaves_events_terminable(tmp_path: Path) -> None:
    """DEFECT-WITNESS test, now proving the FIX (Phase-4 campaign, RES-A4).

    ``_spawn_and_initialize``'s failure path (mismatch note 12) called
    ``transport.close()`` on a failed handshake - but that only set
    ``_CodexTransport._closed`` (the TRANSPORT's own internal flag, used
    solely to suppress ``_on_child_exit`` when its reader thread reaches
    EOF after a deliberate close). It never set
    ``CodexAppServerConnector._closed_event`` - the ONE flag ``events()``
    actually checks on every ``queue.Empty``. A caller of ``events()`` after
    a failed ``start()`` (with no separate, explicit ``close()`` call) was
    therefore never told to stop: the generator looped forever, bounded
    only by this TEST's own timeout, not by the connector - reproduced 3/3
    deterministically pre-fix (recorded: no termination within 5s). FIX:
    ``_spawn_and_initialize``'s ``except`` clause now also sets
    ``self._closed_event`` (codex.py's own mismatch note 14b), mirroring
    pi.py's C3 fix; this test now passes and stays as the regression guard.

    Uses a child that reads (consumes) the ``initialize`` write but never
    answers it, so the handshake's own bounded ``request()`` times out
    cleanly (the same shape as ``test_failed_handshake_does_not_permanently_
    wedge_the_connector``, which this test does not duplicate - that one
    checks ``_transport is None``; this one checks ``events()`` termination,
    a different failure surface entirely).
    """
    hang_script = "import sys, time\nsys.stdin.readline()\ntime.sleep(30)\n"
    conn = CodexAppServerConnector(
        command=[sys.executable, "-c", hang_script], handshake_timeout_s=0.3
    )
    with pytest.raises(OktoNexusError):
        conn.start(owning_agent_id="nxs_agent")

    collected: list[Any] = []
    finished = threading.Event()

    def drain() -> None:
        for ev in conn.events():
            collected.append(ev)
        finished.set()

    t = threading.Thread(target=drain, daemon=True)
    t.start()
    t.join(timeout=5.0)
    try:
        assert finished.is_set(), (
            "events() after a FAILED start() (no close() call) did not terminate within "
            "5s. _spawn_and_initialize's failure path should set "
            "CodexAppServerConnector._closed_event, not just the TRANSPORT's own separate "
            "internal _closed flag (codex.py mismatch note 14b)."
        )
    finally:
        conn.close()  # always clean up regardless of the assertion outcome


def test_events_stays_live_after_a_failed_start_is_followed_by_a_successful_retry(
    tmp_path: Path,
) -> None:
    """RES-A4 fix, second-order check: setting ``_closed_event`` on a FAILED
    ``start()`` must not permanently poison a connector that is retried and
    SUCCEEDS. ``_spawn_and_initialize`` only re-runs (``start()``'s guard is
    ``if self._transport is None``) when the previous attempt never reached
    ``self._transport = transport`` - i.e. exactly the failed-then-retry
    path this test exercises, never the "already closed" path (``close()``
    leaves ``self._transport`` non-``None``, so a post-``close()`` ``start()``
    skips ``_spawn_and_initialize`` entirely and never reaches this clear).

    Uses ONE script, invoked TWICE by the SAME connector instance (its
    ``command`` is fixed at construction - a real retry re-spawns the exact
    same argv): a marker file on disk makes the FIRST invocation hang (never
    answers ``initialize``, so the handshake times out and ``start()`` #1
    raises) and the SECOND invocation behave like a minimal, real app-server
    (answers ``initialize`` and ``thread/start``, so ``start()`` #2
    succeeds) - the same "flip behaviour via a stateful marker" shape used
    throughout this file's fakes, applied across two separate process
    spawns instead of within one.
    """
    marker = tmp_path / "spawned_once.marker"
    script = tmp_path / "flaky_then_ok.py"
    script.write_text(
        "import json, os, sys, time\n"
        f"marker = {str(marker)!r}\n"
        "if not os.path.exists(marker):\n"
        "    open(marker, 'w').close()\n"
        "    sys.stdin.readline()\n"  # consume `initialize` without answering
        "    time.sleep(30)\n"
        "else:\n"
        "    for raw in sys.stdin:\n"
        "        line = raw.strip()\n"
        "        if not line:\n"
        "            continue\n"
        "        msg = json.loads(line)\n"
        "        if msg.get('method') == 'initialize':\n"
        "            sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': {}}) + chr(10))\n"
        "            sys.stdout.flush()\n"
        "        elif msg.get('method') == 'thread/start':\n"
        "            sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'thread': {'id': 'th_retry'}}}) + chr(10))\n"
        "            sys.stdout.flush()\n",
        encoding="utf-8",
    )
    conn = CodexAppServerConnector(
        command=[sys.executable, str(script)],
        handshake_timeout_s=0.3,
    )
    t: threading.Thread | None = None
    try:
        with pytest.raises(OktoNexusError):
            conn.start(owning_agent_id="nxs_agent")  # spawn #1: hangs, times out, sets _closed_event

        session = conn.start(owning_agent_id="nxs_agent")  # spawn #2 (retry): succeeds
        assert session.session_id

        collected: list[Any] = []
        finished = threading.Event()

        def drain() -> None:
            for ev in conn.events():
                collected.append(ev)
            finished.set()

        t = threading.Thread(target=drain, daemon=True)
        t.start()
        t.join(timeout=2.5)
        assert not finished.is_set(), (
            "events() on a connector that SUCCEEDED on retry terminated immediately, as if "
            "still closed - the earlier failed start()'s _closed_event was never cleared on "
            "the successful respawn (codex.py mismatch note 14c)."
        )
        assert collected == []
    finally:
        conn.close()
        if t is not None:
            t.join(timeout=3.0)


# --------------------------------------------------------------------------- #
# RES-B2: a reader thread that exits for ANY reason signals shutdown to
# EVERY consumer - exercised here with TWO consumers genuinely blocked
# concurrently before the child dies (the existing
# test_events_called_twice_after_unexpected_child_exit_returns_both_times
# calls events() sequentially, one after the other; this is the true
# concurrent shape). _closed_event is a single shared flag set
# unconditionally by _on_child_exit, independent of the (now fanned-out,
# post-RES-A2-fix) per-consumer event delivery.
# --------------------------------------------------------------------------- #
def test_two_concurrent_events_consumers_are_both_signalled_on_child_death(
    connector: CodexAppServerConnector,
) -> None:
    session = connector.start(owning_agent_id="nxs_agent")

    consumer_a: list[HarnessEvent] = []
    consumer_b: list[HarnessEvent] = []
    a_done = threading.Event()
    b_done = threading.Event()

    def drain(sink: list[HarnessEvent], done_flag: threading.Event) -> None:
        for ev in connector.events():
            sink.append(ev)
        done_flag.set()

    ta = threading.Thread(target=drain, args=(consumer_a, a_done), daemon=True)
    tb = threading.Thread(target=drain, args=(consumer_b, b_done), daemon=True)
    ta.start()
    tb.start()
    time.sleep(0.3)  # both genuinely parked before the crash trigger fires

    connector.send(
        session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_CRASH"})
    )

    ta.join(timeout=15.0)
    tb.join(timeout=15.0)
    assert a_done.is_set(), "consumer A's events() did not terminate after child death"
    assert b_done.is_set(), "consumer B's events() did not terminate after child death"


# --------------------------------------------------------------------------- #
# RES-C3: the fake must be able to FAIL, not only succeed. The existing
# fake already rejects a turn/start (TRIGGER_ERROR), dies mid-turn
# (TRIGGER_CRASH), and corrupts a line (TRIGGER_MALFORMED) - the one shape
# missing from the suite is codex REJECTING the handshake itself (an
# auth/protocol rejection), distinct from the already-covered "never
# answers at all" timeout shape.
# --------------------------------------------------------------------------- #
_REJECT_INIT_SOURCE = r'''
import json
import sys

def write(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

for raw in sys.stdin:
    line = raw.strip()
    if not line:
        continue
    msg = json.loads(line)
    if msg.get("method") == "initialize":
        write({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32600, "message": "auth rejected"}})
    else:
        write({"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32601, "message": "unexpected"}})
'''


def test_rejected_initialize_surfaces_as_oktonexuserror(tmp_path: Path) -> None:
    script = tmp_path / "reject_init.py"
    script.write_text(_REJECT_INIT_SOURCE, encoding="utf-8")
    conn = CodexAppServerConnector(command=[sys.executable, str(script)], handshake_timeout_s=5.0)
    try:
        with pytest.raises(OktoNexusError) as exc:
            conn.start(owning_agent_id="nxs_agent")
        assert "auth rejected" in str(exc.value)
        # Same wedge-guard as the timeout-shaped failure: no transport left behind.
        assert conn._transport is None
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Live, opt-in: the real codex binary against the LAN backend (ADR 0004 D5)
# --------------------------------------------------------------------------- #
_LIVE_CODEX_CONFIG = """\
model = "qwen3.8-flash"
model_provider = "lanqwen"

[model_providers.lanqwen]
name = "lanqwen"
base_url = "http://192.168.31.152:8123/v1"
env_key = "LANQWEN_API_KEY"
wire_api = "responses"
"""


@pytest.mark.skipif(
    shutil.which("codex") is None or os.environ.get("OKTO_NEXUS_CODEX_LIVE") != "1",
    reason="opt-in live test: needs the real `codex` binary AND OKTO_NEXUS_CODEX_LIVE=1",
)
def test_live_against_real_codex_lan_box(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(_LIVE_CODEX_CONFIG, encoding="utf-8")

    conn = CodexAppServerConnector(env={"CODEX_HOME": str(codex_home), "LANQWEN_API_KEY": "unused"})
    try:
        session = conn.start(owning_agent_id="nxs_live_agent")
        conn.send(
            session,
            HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "Reply with exactly the single word: pong"}),
        )
        events = _collect_until(conn, lambda ev: ev.kind == "turn_completed", timeout_s=60.0)
        deltas = "".join(ev.payload.get("delta", "") for ev in events if ev.native_event == "item/agentMessage/delta")
        assert "pong" in deltas.lower()
    finally:
        conn.close()
