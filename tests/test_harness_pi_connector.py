"""Phase 3 (harness-integrations, ADR 0004 D4) - the Pi connector.

Exercises ``okto_nexus.adapters.outbound.harness.pi.PiRpcConnector`` against a
FAKE ``pi --mode rpc`` - a small standalone Python script speaking the real
strict-LF JSON-lines framing verified live in
``docs/harness-integrations/research/pi-rpc-protocol-reference.md`` and
``docs/harness-integrations/evidence/EV-PI-001-protocol-verified.md``
(response envelope shape, the 7-line ``extension_ui_request`` startup burst,
``queue_update`` timing, abort/settle ordering), launched with
``sys.executable`` so no ``pi`` binary is required for this file to pass.
This exercises the connector's actual framing, threading and correlation
code paths, not a mock of the connector itself.

One test (``test_live_against_real_pi_zai``) drives the REAL ``pi`` binary
against ``zai/glm-5.3`` (ADR 0004 D4/D5's box-safety rule: pi's default
``local-mac`` provider maps to ``192.168.31.222``, reserved for a running
benchmark, so this connector's ``provider``/``model`` override is REQUIRED,
never left to pi's own default). It is skipped unless BOTH the real binary
is on ``PATH`` and ``OKTO_NEXUS_PI_LIVE=1`` is set, so a normal ``pytest``
run never touches the network or requires pi to be installed, and reads
credentials only from the gitignored ``.secrets/harness.env`` (never
hardcoded), skipping itself (not failing) if that file is absent.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import sys
import threading
import time
import weakref
from pathlib import Path
from typing import Any, Callable

import pytest

from okto_nexus.adapters.outbound.harness.pi import PiRpcConnector
from okto_nexus.domain.harness import (
    STEER_TIMING_NEXT_TURN_BOUNDARY,
    HarnessCommand,
    HarnessEvent,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

# No pytest-timeout dependency in this repo; every blocking wait below is
# bounded explicitly instead - see `_collect_until`.


# --------------------------------------------------------------------------- #
# Fake ``pi --mode rpc`` - real strict-LF JSON-lines framing, scripted turn
# behaviour selected by a TRIGGER keyword embedded in the prompt/steer text.
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
_ui_counter = 0
_state_lock = threading.Lock()
_pending_steer = []
_abort_requested = threading.Event()
_die_on_abort = threading.Event()
NO_ACK_GET_STATE = len(sys.argv) > 2 and sys.argv[2] == "NO_ACK_GET_STATE"
# Real pi wire order (protocol reference section 6(b)): agent_settled for the
# ABORTED turn arrives BEFORE response(abort, success:true) - the ack is not
# the safe-to-reprompt signal, agent_settled is. This flag/lock pair defers
# the abort ack until the aborted turn has actually finished settling,
# instead of answering it the instant the abort command is read (which is
# the wrong order and was the fake server's own bug - see C1).
_abort_response_lock = threading.Lock()
_abort_response_owed = False


def _send_abort_response_once():
    global _abort_response_owed
    with _abort_response_lock:
        if not _abort_response_owed:
            return
        _abort_response_owed = False
    write_msg({"type": "response", "command": "abort", "success": True})


def write_line(text):
    with _write_lock:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def write_msg(obj):
    write_line(json.dumps(obj))


def log(entry):
    if not LOG_PATH:
        return
    with _log_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


def next_ui_id():
    global _ui_counter
    _ui_counter += 1
    return "ui_%d" % _ui_counter


def emit_startup_noise():
    for _ in range(7):
        write_msg({"type": "extension_ui_request", "id": next_ui_id(), "method": "setStatus", "statusKey": "statusline"})


def handle_turn(text):
    _abort_requested.clear()
    write_msg({"type": "agent_start"})
    write_msg({"type": "turn_start"})
    write_msg({"type": "message_start", "role": "user"})
    write_msg({"type": "message_end", "role": "user"})

    if "TRIGGER_MALFORMED" in text:
        write_line("not-json-garbage-from-pi")

    if "TRIGGER_SPURIOUS_RESPONSE" in text:
        write_msg({"type": "response", "command": "get_session_stats", "success": True, "data": {}})

    if "TRIGGER_CRASH" in text:
        write_msg({"type": "message_start", "role": "assistant"})
        time.sleep(0.05)
        os._exit(7)

    if "TRIGGER_HOLD_FOR_STEER" in text:
        write_msg({"type": "tool_execution_start", "toolCallId": "tc1", "toolName": "bash"})
        deadline = time.time() + 5.0
        while time.time() < deadline:
            with _state_lock:
                steer_pending = list(_pending_steer)
            if steer_pending:
                break
            time.sleep(0.02)
        write_msg({"type": "tool_execution_end", "toolCallId": "tc1", "isError": False, "result": "done"})
        write_msg({"type": "turn_end"})
        write_msg({"type": "turn_start"})
        with _state_lock:
            drained = list(_pending_steer)
            _pending_steer.clear()
        write_msg({"type": "queue_update", "steering": [], "followUp": []})
        for _steer_text in drained:
            write_msg({"type": "message_start", "role": "user"})
            write_msg({"type": "message_end", "role": "user"})
        write_msg({"type": "message_start", "role": "assistant"})
        write_msg({"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "steered-ok"}})
        write_msg({"type": "message_end", "role": "assistant", "stopReason": "stop"})
        write_msg({"type": "turn_end"})
        write_msg({"type": "agent_end"})
        write_msg({"type": "agent_settled"})
        return

    if "TRIGGER_DIE_ON_ABORT" in text:
        write_msg({"type": "tool_execution_start", "toolCallId": "tc3", "toolName": "bash"})
        _die_on_abort.set()
        time.sleep(5.0)
        return

    if "TRIGGER_HOLD_FOR_ABORT" in text:
        write_msg({"type": "tool_execution_start", "toolCallId": "tc2", "toolName": "bash"})
        deadline = time.time() + 5.0
        while time.time() < deadline and not _abort_requested.is_set():
            time.sleep(0.02)
        if _abort_requested.is_set():
            # Deterministic window (real pi: ~17-30ms per the protocol
            # reference's measured abort-mid-tool-call case) between the
            # abort write landing and the aborted turn actually finishing -
            # gives C1's race-window test something reliable to hit instead
            # of a few-ms window inherent in the fast path below.
            time.sleep(0.3)
            write_msg({"type": "tool_execution_end", "toolCallId": "tc2", "isError": True, "result": "Operation aborted"})
            write_msg({"type": "turn_end"})
            write_msg({"type": "message_start", "role": "assistant"})
            write_msg({"type": "message_end", "role": "assistant", "stopReason": "error"})
            write_msg({"type": "turn_end"})
            write_msg({"type": "agent_end"})
            write_msg({"type": "agent_settled"})
            # Real order (protocol reference 6(b)): agent_settled for the
            # ABORTED turn arrives BEFORE response(abort,success:true).
            _send_abort_response_once()
            return
        write_msg({"type": "tool_execution_end", "toolCallId": "tc2", "isError": False, "result": "done"})
        write_msg({"type": "turn_end"})
        write_msg({"type": "message_start", "role": "assistant"})
        write_msg({"type": "message_end", "role": "assistant", "stopReason": "stop"})
        write_msg({"type": "turn_end"})
        write_msg({"type": "agent_end"})
        write_msg({"type": "agent_settled"})
        return

    write_msg({"type": "message_start", "role": "assistant"})
    write_msg({"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": text}})
    write_msg({"type": "message_end", "role": "assistant", "stopReason": "stop"})
    write_msg({"type": "turn_end"})
    write_msg({"type": "agent_end"})
    write_msg({"type": "agent_settled"})


def main():
    emit_startup_noise()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            write_msg({"type": "response", "command": "parse", "success": False, "error": "bad json"})
            continue
        log({"recv": msg})
        verb = msg.get("type")
        if verb == "get_state":
            if NO_ACK_GET_STATE:
                continue  # deliberately never answer - for the C3 handshake-timeout test
            write_msg({"type": "response", "command": "get_state", "success": True, "data": {"sessionId": "fake"}})
        elif verb == "extension_ui_response":
            continue
        elif verb == "prompt":
            text = msg.get("message", "")
            if "TRIGGER_ERROR" in text:
                write_msg({"type": "response", "command": "prompt", "success": False, "error": "rejected"})
                continue
            write_msg({"type": "response", "command": "prompt", "success": True})
            threading.Thread(target=handle_turn, args=(text,), daemon=True).start()
        elif verb == "steer":
            text = msg.get("message", "")
            with _state_lock:
                _pending_steer.append(text)
            write_msg({"type": "response", "command": "steer", "success": True})
            write_msg({"type": "queue_update", "steering": list(_pending_steer), "followUp": []})
        elif verb == "abort":
            if _die_on_abort.is_set():
                os._exit(9)
            global _abort_response_owed
            with _abort_response_lock:
                _abort_response_owed = True
            _abort_requested.set()
            # NOTE: protocol case (a) (abort with nothing in flight, which
            # settles - and therefore acks - in ~2ms live) is not exercised
            # by any test in this file; only the mid-tool-call case
            # (TRIGGER_HOLD_FOR_ABORT) is. A time-based fallback ack was
            # deliberately NOT added here: it would race the deterministic
            # 0.3s delay TRIGGER_HOLD_FOR_ABORT's own abort path uses to
            # widen the settle-gate test window, and could re-introduce the
            # exact wrong-order bug (ack before agent_settled) this fix
            # exists to eliminate. If a future test needs the no-tool-in-
            # flight abort path, it needs its own explicit trigger that
            # calls _send_abort_response_once() itself, not a timer race.
        else:
            write_msg({"type": "response", "command": verb, "success": False, "error": "Unknown command: %s" % verb})


if __name__ == "__main__":
    main()
'''


@pytest.fixture()
def fake_server_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake_pi_rpc.py"
    script.write_text(_FAKE_SERVER_SOURCE, encoding="utf-8")
    return script


@pytest.fixture()
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "fake_server_log.jsonl"


@pytest.fixture()
def connector(fake_server_script: Path, log_path: Path):
    conn = PiRpcConnector(command=[sys.executable, str(fake_server_script), str(log_path)])
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


#: One pump thread/queue per connector, reused across every `_collect_until`
#: call against it. `events()` is a single shared generator over one
#: underlying `queue.Queue`; spawning a FRESH pump thread on every call (as
#: a naive helper would) creates multiple concurrent consumers racing each
#: other for the same items - the second call then starves (its own local
#: queue never receives the events the first call's now-orphaned thread
#: silently siphoned off) and burns its full timeout. Keyed by object
#: identity via a `WeakKeyDictionary` so it never outlives the connector.
_pump_queues: "weakref.WeakKeyDictionary[PiRpcConnector, queue.Queue]" = weakref.WeakKeyDictionary()
_pump_lock = threading.Lock()


def _pump_queue_for(conn: PiRpcConnector) -> "queue.Queue[HarnessEvent]":
    with _pump_lock:
        q = _pump_queues.get(conn)
        if q is None:
            q = queue.Queue()
            _pump_queues[conn] = q

            def pump() -> None:
                for ev in conn.events():
                    q.put(ev)

            threading.Thread(target=pump, daemon=True, name="test-event-pump").start()
        return q


def _collect_until(
    conn: PiRpcConnector,
    predicate: Callable[[HarnessEvent], bool],
    *,
    timeout_s: float = 10.0,
) -> list[HarnessEvent]:
    """Drain ``conn.events()`` until ``predicate`` matches, bounded by
    ``timeout_s``. Test-only bounded wait (a ``Queue.get(timeout=...)`` on a
    background pump thread) over the SAME bounded
    ``Queue.get(timeout=_EVENTS_POLL_S)`` loop production uses (see the
    module's own docstring on why that periodic re-check is not polling for
    events). Safe to call more than once against the same connector (see
    :func:`_pump_queue_for`).
    """
    q = _pump_queue_for(conn)
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


# --------------------------------------------------------------------------- #
# Capabilities (D4)
# --------------------------------------------------------------------------- #
def test_capabilities_match_adr_d4(connector: PiRpcConnector) -> None:
    caps = connector.capabilities
    assert caps.send_only is False
    assert caps.steer_timing == STEER_TIMING_NEXT_TURN_BOUNDARY
    assert caps.interrupt_requires_settle_wait is True
    assert caps.multiplexes_sessions is False
    assert caps.observes_session_end is True


# --------------------------------------------------------------------------- #
# start() - readiness probe, startup noise, single-session ownership
# --------------------------------------------------------------------------- #
def test_start_probes_readiness_and_answers_startup_noise(connector: PiRpcConnector, log_path: Path) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    assert session.harness_kind == "pi"
    assert session.owning_agent_id == "nxs_test_agent"
    assert session.status == "STARTING"
    assert session.capabilities is connector.capabilities
    assert session.metadata["pi_session_id"] == session.session_id

    # The fake server logs every RECEIVED line, including our auto-replies
    # to its 7 startup extension_ui_request lines.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        entries = read_log(log_path)
        ui_responses = [e["recv"] for e in entries if e.get("recv", {}).get("type") == "extension_ui_response"]
        if len(ui_responses) >= 7:
            break
        time.sleep(0.02)
    entries = read_log(log_path)
    ui_responses = [e["recv"] for e in entries if e.get("recv", {}).get("type") == "extension_ui_response"]
    assert len(ui_responses) == 7
    assert all(r.get("cancelled") is True for r in ui_responses)
    assert {r["id"] for r in ui_responses} == {f"ui_{i}" for i in range(1, 8)}


def test_second_start_on_same_connector_raises(connector: PiRpcConnector) -> None:
    connector.start(owning_agent_id="nxs_a")
    with pytest.raises(OktoNexusError) as excinfo:
        connector.start(owning_agent_id="nxs_b")
    assert excinfo.value.code == ErrorCode.VALIDATION_ERROR


# --------------------------------------------------------------------------- #
# send_turn - ordered event stream, push proof (INT-04)
# --------------------------------------------------------------------------- #
def test_send_turn_produces_ordered_events(connector: PiRpcConnector) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "hello"}))

    events = _collect_until(connector, lambda ev: ev.native_event == "agent_settled", timeout_s=10.0)
    # The 7 startup extension_ui_request events (forwarded for traceability,
    # per mismatch note 5) arrive before the turn ever starts; ignore them
    # here, this test is about the turn's own ordering.
    turn_events = [ev for ev in events if ev.native_event != "extension_ui_request"]
    native_types = [ev.native_event for ev in turn_events]
    assert native_types == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "message_start",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
        "agent_settled",
    ]
    assert all(ev.session_id == session.session_id and ev.harness_kind == "pi" for ev in events)

    delta_event = next(ev for ev in events if ev.native_event == "message_update")
    assert delta_event.kind == "output_delta"
    assert delta_event.payload["assistantMessageEvent"]["delta"] == "hello"

    settled_event = events[-1]
    assert settled_event.kind == "turn_completed"


def test_send_turn_requires_non_empty_text(connector: PiRpcConnector) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    with pytest.raises(OktoNexusError) as excinfo:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={}))
    assert excinfo.value.code == ErrorCode.VALIDATION_ERROR


def test_prompt_rejected_by_pi_surfaces_error_event_without_raising(connector: PiRpcConnector) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(
        session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_ERROR"})
    )
    events = _collect_until(connector, lambda ev: ev.kind == "error", timeout_s=5.0)
    error_event = events[-1]
    assert error_event.native_event == "response"
    assert error_event.payload["command"] == "prompt"
    assert error_event.payload["success"] is False


# --------------------------------------------------------------------------- #
# Steer - NEXT_TURN_BOUNDARY delivery (INT-05)
# --------------------------------------------------------------------------- #
def test_steer_is_queued_immediately_and_delivered_at_turn_boundary(connector: PiRpcConnector) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_HOLD_FOR_STEER go"}),
    )
    _collect_until(connector, lambda ev: ev.native_event == "tool_execution_start", timeout_s=5.0)

    connector.send(
        session, HarnessCommand(session_id=session.session_id, verb="steer", payload={"text": "STEER_MARKER"})
    )

    events = _collect_until(connector, lambda ev: ev.native_event == "agent_settled", timeout_s=10.0)
    native_types = [ev.native_event for ev in events]

    first_queue_update = native_types.index("queue_update")
    tool_end = native_types.index("tool_execution_end")
    turn_end_first = native_types.index("turn_end")
    # The queue update (steering queued) must land BEFORE the tool call
    # finishes and the turn boundary crosses - confirming delivery is
    # deferred, not immediate (protocol reference §5).
    assert first_queue_update < tool_end
    assert tool_end < turn_end_first

    steering_payloads = [ev.payload.get("steering") for ev in events if ev.native_event == "queue_update"]
    assert steering_payloads[0] == ["STEER_MARKER"]  # queued
    assert steering_payloads[-1] == []  # drained at the boundary

    assert events[-1].native_event == "agent_settled"


def test_steer_requires_non_empty_text(connector: PiRpcConnector) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    with pytest.raises(OktoNexusError) as excinfo:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="steer", payload={"text": ""}))
    assert excinfo.value.code == ErrorCode.VALIDATION_ERROR


# --------------------------------------------------------------------------- #
# Interrupt / settle-wait gate (INT-06) - the classic hang, enforced not just
# documented (mismatch note 4).
# --------------------------------------------------------------------------- #
def test_interrupt_blocks_further_sends_until_agent_settled(connector: PiRpcConnector) -> None:
    """C1: the OLD version of this test asserted that a reprompt immediately
    after ``interrupt()`` returns must be refused. That assumption was an
    artifact of the fake server's WRONG wire order (it used to answer the
    abort ack the instant it read the command, before the aborted turn
    finished). The protocol reference (section 6(b), verified live) proves
    the real order is the opposite: ``agent_settled`` for the aborted turn
    arrives BEFORE ``response(abort,success:true)``. Since both are
    dispatched sequentially on the SAME reader thread, by the time
    ``interrupt()`` (which blocks on the ack) returns, the settle event has
    ALREADY been processed and the gate is already clear - so a reprompt
    right after ``interrupt()`` returns is legitimately safe, not a race.
    The actual danger window - a caller sending WHILE ``interrupt()`` is
    still blocked waiting on the delayed ack - is covered separately by
    ``test_interrupt_gate_holds_during_real_race_window``, which is the
    test that replaces this one's original (mock-artifact-driven) intent.
    """
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_HOLD_FOR_ABORT go"}),
    )
    _collect_until(connector, lambda ev: ev.native_event == "tool_execution_start", timeout_s=5.0)

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))

    # By the time interrupt() returns, agent_settled for the aborted turn
    # has already been observed (it arrives before the ack on the real
    # wire) - so the gate is already clear and this succeeds immediately.
    connector.send(
        session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "after settle"})
    )
    events = _collect_until(connector, lambda ev: ev.native_event == "agent_settled", timeout_s=10.0)
    assert events[-1].native_event == "agent_settled"


def test_interrupt_gate_holds_during_real_race_window(connector: PiRpcConnector) -> None:
    """C1's actual protected window: `interrupt()` sets the settle-wait gate
    and THEN blocks on the (deliberately delayed, ~300ms in the fake -
    ~17-30ms measured live) abort ack. A `send_turn` issued by another
    thread WHILE `interrupt()` is still blocked in that window must be
    refused with CONFLICT - this is the real hang the protocol reference's
    §6 warns about, not the mock-artifact scenario the old version of
    `test_interrupt_blocks_further_sends_until_agent_settled` asserted.
    """
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_HOLD_FOR_ABORT go"}),
    )
    _collect_until(connector, lambda ev: ev.native_event == "tool_execution_start", timeout_s=5.0)

    interrupt_outcome: dict[str, Any] = {}

    def run_interrupt() -> None:
        try:
            connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))
            interrupt_outcome["ok"] = True
        except OktoNexusError as exc:  # pragma: no cover - only on real failure
            interrupt_outcome["error"] = exc

    interrupt_thread = threading.Thread(target=run_interrupt, daemon=True)
    interrupt_thread.start()
    # Give interrupt() time to set the gate and block on the fake's
    # deliberately delayed (0.3s) abort ack - well inside that window.
    time.sleep(0.1)

    with pytest.raises(OktoNexusError) as excinfo:
        connector.send(
            session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "too soon"})
        )
    assert excinfo.value.code == ErrorCode.CONFLICT

    interrupt_thread.join(timeout=5.0)
    assert not interrupt_thread.is_alive()
    assert interrupt_outcome.get("ok") is True, interrupt_outcome

    _collect_until(connector, lambda ev: ev.native_event == "agent_settled", timeout_s=10.0)

    # Now it is safe.
    connector.send(
        session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "after settle"})
    )
    events = _collect_until(connector, lambda ev: ev.native_event == "agent_settled", timeout_s=10.0)
    assert events[-1].native_event == "agent_settled"


def test_second_interrupt_while_awaiting_settle_raises_conflict(connector: PiRpcConnector) -> None:
    """C1: with the fake corrected to the real wire order, a SYNCHRONOUS
    first ``interrupt()`` call already blocks until the aborted turn's
    ``agent_settled`` (the ack arrives right after it) - so by the time it
    RETURNS, the gate is already clear and a second, later ``interrupt()``
    would instead try to abort a turn that has already finished (and time
    out, since nothing is listening for that stray abort). The genuine
    "second interrupt while the first is still pending" case is a
    concurrency scenario: the second interrupt must be issued WHILE the
    first is still blocked inside ``interrupt()``, exactly like
    ``test_interrupt_gate_holds_during_real_race_window`` does for
    ``send_turn``.
    """
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_HOLD_FOR_ABORT go"}),
    )
    _collect_until(connector, lambda ev: ev.native_event == "tool_execution_start", timeout_s=5.0)

    first_outcome: dict[str, Any] = {}

    def run_first_interrupt() -> None:
        try:
            connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))
            first_outcome["ok"] = True
        except OktoNexusError as exc:  # pragma: no cover - only on real failure
            first_outcome["error"] = exc

    first_thread = threading.Thread(target=run_first_interrupt, daemon=True)
    first_thread.start()
    # Give the first interrupt() time to set the gate and block on the
    # fake's deliberately delayed (0.3s) abort ack.
    time.sleep(0.1)

    with pytest.raises(OktoNexusError) as excinfo:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))
    assert excinfo.value.code == ErrorCode.CONFLICT

    first_thread.join(timeout=5.0)
    assert not first_thread.is_alive()
    assert first_outcome.get("ok") is True, first_outcome


# --------------------------------------------------------------------------- #
# end - full teardown (no wire verb; mismatch note 2)
# --------------------------------------------------------------------------- #
def test_end_terminates_process_and_ends_event_stream(connector: PiRpcConnector) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and connector._transport.is_alive():  # noqa: SLF001 - white-box teardown check
        time.sleep(0.02)
    assert not connector._transport.is_alive()  # noqa: SLF001

    with pytest.raises(OktoNexusError) as excinfo:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "x"}))
    assert excinfo.value.code == ErrorCode.NOT_FOUND


def test_events_generator_terminates_after_close(connector: PiRpcConnector) -> None:
    """Isolated from ``_collect_until``'s shared pump thread (this connector
    has consumed no events yet), so ``events()`` here is the sole consumer -
    the only safe way to prove the generator itself terminates (its bounded
    ``Queue.get(timeout=_EVENTS_POLL_S)`` loop observes ``_closed_event``
    and returns) instead of blocking forever on an empty queue.
    """
    connector.start(owning_agent_id="nxs_test_agent")
    connector.close()
    # The point under test is that this call RETURNS at all (the bounded
    # poll loop observing _closed_event) rather than blocking forever; the 7
    # startup extension_ui_request events legitimately precede the shutdown
    # in the backlog, so a non-empty list is expected, not a bug.
    remaining = list(connector.events())
    assert all(isinstance(ev, HarnessEvent) for ev in remaining)


# --------------------------------------------------------------------------- #
# C2 - events() fan-out: two independent concurrent consumers.
# --------------------------------------------------------------------------- #
def test_events_fan_out_to_two_independent_concurrent_consumers(connector: PiRpcConnector) -> None:
    """Reproduces C2 directly (bypassing the shared ``_pump_queue_for`` test
    helper, which deliberately routes everything through ONE consumer):
    two independent threads each call ``connector.events()`` and each must
    see the FULL stream through ``agent_settled``, not a split of it. Before
    the fan-out fix, one shared ``queue.Queue`` meant the two threads
    competed for the same items - the reviewer's reproduction had thread A
    receive all 17 events and thread B receive ZERO, still blocked after an
    8s join.
    """
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "hello"}))

    results: dict[str, list[HarnessEvent]] = {"a": [], "b": []}

    def consume(key: str) -> None:
        for ev in connector.events():
            results[key].append(ev)
            if ev.native_event == "agent_settled":
                return

    thread_a = threading.Thread(target=consume, args=("a",), daemon=True)
    thread_b = threading.Thread(target=consume, args=("b",), daemon=True)
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=8.0)
    thread_b.join(timeout=8.0)

    assert not thread_a.is_alive(), "consumer A never saw agent_settled (starved by consumer B)"
    assert not thread_b.is_alive(), "consumer B never saw agent_settled (starved by consumer A)"

    for key in ("a", "b"):
        native_types = [ev.native_event for ev in results[key] if ev.native_event != "extension_ui_request"]
        assert native_types == [
            "agent_start",
            "turn_start",
            "message_start",
            "message_end",
            "message_start",
            "message_update",
            "message_end",
            "turn_end",
            "agent_end",
            "agent_settled",
        ], (key, native_types)


# --------------------------------------------------------------------------- #
# Error edges (INT-08) - child crash, malformed line, unmatched response
# --------------------------------------------------------------------------- #
def test_child_crash_surfaces_process_exited_and_stops_cleanly(connector: PiRpcConnector) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(
        session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_CRASH"})
    )
    events = _collect_until(connector, lambda ev: ev.native_event == "pi/process_exited", timeout_s=5.0)
    crash_event = events[-1]
    assert crash_event.kind == "error"
    assert crash_event.payload["returncode"] == 7


def test_malformed_line_from_child_is_surfaced_and_stream_continues(connector: PiRpcConnector) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_MALFORMED hi"}),
    )
    events = _collect_until(connector, lambda ev: ev.native_event == "agent_settled", timeout_s=10.0)
    malformed = [ev for ev in events if ev.native_event == "pi/transport_malformed_line"]
    assert len(malformed) == 1
    assert malformed[0].kind == "error"
    assert "not-json-garbage-from-pi" in malformed[0].payload["line"]
    # The stream survived the garbage line and still reached settle.
    assert events[-1].native_event == "agent_settled"


def test_unmatched_response_from_child_is_surfaced_not_dropped(connector: PiRpcConnector) -> None:
    session = connector.start(owning_agent_id="nxs_test_agent")
    connector.send(
        session,
        HarnessCommand(
            session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_SPURIOUS_RESPONSE hi"}
        ),
    )
    events = _collect_until(connector, lambda ev: ev.native_event == "agent_settled", timeout_s=10.0)
    spurious = [ev for ev in events if ev.kind == "error" and ev.native_event == "response"]
    assert len(spurious) == 1
    assert spurious[0].payload["command"] == "get_session_stats"
    assert events[-1].native_event == "agent_settled"


def test_send_against_unknown_session_raises_not_found(connector: PiRpcConnector) -> None:
    connector.start(owning_agent_id="nxs_test_agent")
    from okto_nexus.domain.harness import HarnessSession

    bogus = HarnessSession(
        session_id="hsess_does_not_exist",
        harness_kind="pi",
        owning_agent_id="nxs_test_agent",
        status="STARTING",
        capabilities=connector.capabilities,
        started_at="2026-09-20T00:00:00.000000Z",
    )
    with pytest.raises(OktoNexusError) as excinfo:
        connector.send(bogus, HarnessCommand(session_id=bogus.session_id, verb="send_turn", payload={"text": "x"}))
    assert excinfo.value.code == ErrorCode.NOT_FOUND


# --------------------------------------------------------------------------- #
# C3 - a failed start() must not leave events() looping forever.
# --------------------------------------------------------------------------- #
def test_failed_start_still_terminates_events(fake_server_script: Path, log_path: Path) -> None:
    """Reproduces C3: a fake pi that never acks ``get_state`` makes
    ``start()`` raise ``INTERNAL_ERROR`` (the handshake timeout), as
    expected. Before the fix, ``transport.close()`` in that except block
    only set the TRANSPORT's own ``_closed`` Event, never the CONNECTOR's
    separate ``_closed_event`` that ``events()`` actually checks - so
    ``list(conn.events())`` never returned. Bounded with a short
    ``handshake_timeout_s`` so this test itself cannot hang.
    """
    conn = PiRpcConnector(
        command=[sys.executable, str(fake_server_script), str(log_path), "NO_ACK_GET_STATE"],
        handshake_timeout_s=0.5,
    )
    try:
        with pytest.raises(OktoNexusError) as excinfo:
            conn.start(owning_agent_id="nxs_test_agent")
        assert excinfo.value.code == ErrorCode.INTERNAL_ERROR

        done: dict[str, bool] = {}

        def drain() -> None:
            list(conn.events())
            done["finished"] = True

        drainer = threading.Thread(target=drain, daemon=True)
        drainer.start()
        drainer.join(timeout=5.0)
        assert not drainer.is_alive(), "events() never terminated after a failed start()"
        assert done.get("finished") is True
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# M2 - a dead child must fail pending requests immediately, not after the
# full command_timeout_s.
# --------------------------------------------------------------------------- #
def test_child_death_fails_pending_request_immediately(fake_server_script: Path, log_path: Path) -> None:
    """Reproduces M2: the fake ``os._exit()``s the instant it reads
    ``abort`` (via ``TRIGGER_DIE_ON_ABORT``), without ever answering it.
    Before the fix, the blocked ``interrupt()`` call waited out the FULL
    ``command_timeout_s`` even though the reader thread detected the child's
    exit immediately. A small, explicit ``command_timeout_s`` (2.0s) makes
    the defect obvious without this test itself needing to wait long: the
    fixed connector must fail in well under a second, not ~2s.
    """
    conn = PiRpcConnector(
        command=[sys.executable, str(fake_server_script), str(log_path)],
        command_timeout_s=2.0,
    )
    try:
        session = conn.start(owning_agent_id="nxs_test_agent")
        conn.send(
            session,
            HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"text": "TRIGGER_DIE_ON_ABORT go"}),
        )
        _collect_until(conn, lambda ev: ev.native_event == "tool_execution_start", timeout_s=5.0)

        # `interrupt()`'s underlying `request()` does NOT raise here - a
        # failed-pending request comes back as a synthetic `success:false`
        # response (this module's own established convention: "success:false
        # is pi's clean, non-fatal error path ... surfaced as an event,
        # never raised synchronously"), which `_interrupt` then surfaces via
        # `_surface_if_rejected` as an `error` HarnessEvent. The property
        # under test is that this happens FAST (the reader thread already
        # knows the child died) rather than after the full command_timeout_s
        # spent blocked in a dead queue.Queue.get().
        started = time.monotonic()
        conn.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, f"send() blocked {elapsed:.2f}s waiting out (most of) command_timeout_s=2.0"

        # Both a `response(abort,success:false)` error event (from the
        # unblocked, now-failed `request()`) and a `pi/process_exited` error
        # event (from `_on_child_exit`) are pushed on two different threads
        # racing each other, so either may land first - two sequential
        # bounded collects, each looking for a different one, together see
        # both regardless of arrival order (whichever isn't the direct
        # target of a call is still captured as a side effect of draining
        # up to the one that is).
        events_a = _collect_until(conn, lambda ev: ev.native_event == "pi/process_exited", timeout_s=5.0)
        already_has_response = any(
            ev.native_event == "response" and ev.payload.get("success") is False for ev in events_a
        )
        events_b = (
            []
            if already_has_response
            else _collect_until(
                conn,
                lambda ev: ev.native_event == "response" and ev.payload.get("success") is False,
                timeout_s=5.0,
            )
        )
        all_events = events_a + events_b
        assert any(ev.native_event == "pi/process_exited" and ev.kind == "error" for ev in all_events)
        assert any(
            ev.native_event == "response" and ev.kind == "error" and ev.payload.get("success") is False
            for ev in all_events
        )
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Structural: no SleepPollWaiter anywhere in this module (D1). Checked
# structurally (imports and instantiation), not by banning the NAME outright
# - the module's own docstrings legitimately discuss it by name.
# --------------------------------------------------------------------------- #
def test_module_never_imports_or_instantiates_sleep_poll_waiter() -> None:
    import ast

    import okto_nexus.adapters.outbound.harness.pi as mod

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
# Live, opt-in: the real pi binary against zai/glm-5.3 (ADR 0004 D4)
# --------------------------------------------------------------------------- #
def _load_harness_secrets(repo_root: Path) -> dict[str, str]:
    """Parse ``.secrets/harness.env`` (``export KEY=VALUE`` lines) without
    ever hardcoding credentials in this file. Returns ``{}`` if absent.
    """
    env_path = repo_root / ".secrets" / "harness.env"
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    shutil.which("pi") is None or os.environ.get("OKTO_NEXUS_PI_LIVE") != "1",
    reason="opt-in live test: needs the real `pi` binary AND OKTO_NEXUS_PI_LIVE=1",
)
def test_live_against_real_pi_zai() -> None:
    secrets = _load_harness_secrets(_REPO_ROOT)
    if "ZAI_API_KEY" not in secrets or "ZAI_BASE_URL" not in secrets:
        pytest.skip("no .secrets/harness.env with ZAI_API_KEY/ZAI_BASE_URL for the live pi test")

    # Explicit provider/model override is REQUIRED (D4/D5): pi's default
    # `local-mac` provider maps to 192.168.31.222, off-limits for a running
    # benchmark. This test must never rely on pi's own settings.json default.
    conn = PiRpcConnector(provider="zai", model="glm-5.3", env=secrets)
    try:
        session = conn.start(owning_agent_id="nxs_live_agent")
        conn.send(
            session,
            HarnessCommand(
                session_id=session.session_id,
                verb="send_turn",
                payload={"text": "Reply with the single word: ok"},
            ),
        )
        events = _collect_until(conn, lambda ev: ev.native_event == "agent_settled", timeout_s=60.0)
        deltas = "".join(
            ev.payload.get("assistantMessageEvent", {}).get("delta", "")
            for ev in events
            if ev.native_event == "message_update"
        )
        assert "ok" in deltas.lower()
    finally:
        conn.close()
