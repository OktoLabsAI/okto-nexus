"""Tests for the Claude Code PRIMARY connector (ADR 0004 D7a).

Two tiers, per the harness-integrations quality bar ("must pass and must not
require the real binary to be present unless marked"):

* FAKE-BINARY tests (always run, no real ``claude`` needed): a tiny stdlib
  script (``_FAKE_CLAUDE_SCRIPT``), run under ``sys.executable``, stands in
  for the real CLI and reproduces the exact wire shapes captured empirically
  against claude 2.1.278 - including the fatal early-interrupt race window
  this connector must gate against. These exercise the connector's
  threading, event-mapping and error-handling logic deterministically.
* REAL-BINARY tests (``@pytest.mark.skipif`` when ``claude`` is not on
  PATH): drive the actual CLI with trivial prompts, mirroring the manual
  protocol probes this connector's design was built from. No new pytest
  marker is registered (``pyproject.toml`` only registers ``replay``);
  ``skipif`` needs none.
"""

from __future__ import annotations

import queue
import shutil
import sys
import threading
import time

import pytest

from okto_nexus.domain.harness import HarnessCommand, HarnessEvent, HarnessSession
from okto_nexus.errors import OktoNexusError
from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector

_HAS_REAL_CLAUDE = shutil.which("claude") is not None
requires_real_claude = pytest.mark.skipif(
    not _HAS_REAL_CLAUDE, reason="requires the real `claude` CLI on PATH"
)


# --------------------------------------------------------------------------- #
# Fake `claude -p --input-format stream-json --output-format stream-json`
# --------------------------------------------------------------------------- #
# A single parametrisable stdlib script so every scenario shares one code
# path (less risk of the fake silently diverging from the real protocol
# shape). Scenario is selected via the FAKE_CC_SCENARIO env var:
#
#   basic                  - normal turns, echoes "echo:<content>".
#   crash_early_interrupt  - if an interrupt control_request arrives BEFORE
#                             this turn's content_block_start, reproduces the
#                             real CLI's fatal exit(1) after
#                             result:error_during_execution. This exists to
#                             prove the connector's OWN gate never lets that
#                             request reach the child in the first place;
#                             the scenario is a safety net, not the primary
#                             assertion.
#   garbage_line            - emits one non-JSON stdout line before the
#                             normal turn 1 sequence.
#   die_without_result       - exits(2) immediately on the first turn with no
#                             result event at all (simulated abrupt death).
#   slow_start               - sleeps before emitting message_start/
#                             content_block_start, widening the unsafe
#                             interrupt window so a test can deterministically
#                             land an interrupt attempt inside it.
#   shape_drifted_mid_turn    - emits a syntactically-valid, top-level-type-
#                             recognised but internally shape-drifted
#                             ``stream_event`` (``"event": "oops"``, a string
#                             where the connector expects a dict) in the
#                             middle of an otherwise normal turn, then
#                             continues with the normal completion sequence.
#                             Reproduces a real-world "unknown internal
#                             shape" hazard distinct from `garbage_line`
#                             (which is not even valid JSON).
#   eof_without_exit         - closes BOTH stdout and stderr (hitting EOF
#                             on the reader threads) but then sleeps far
#                             past _EXIT_WAIT_TIMEOUT_S without exiting -
#                             the process is genuinely still alive when
#                             _finish()'s proc.wait() times out.
_FAKE_CLAUDE_SCRIPT = r"""
import json, os, select, sys, time

scenario = os.environ.get("FAKE_CC_SCENARIO", "basic")
session_id = "fake-native-session-id"
generating = False

def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

# --------------------------------------------------------------------- #
# Single unbuffered reader over fd 0.
#
# The mid-generation window below used to poll readiness with
# ``select.select([sys.stdin], ...)`` (kernel-level, on the raw fd) and
# then read with ``sys.stdin.readline()`` (CPython's own buffered
# ``TextIOWrapper``, layered on top of that same fd). Those two are NOT
# the same buffer: if two lines land in the pipe before the child's next
# read syscall - exactly what happens here, since the test writes an
# ordinary ``send_turn`` immediately followed by an ``interrupt`` -
# ``readline()`` can slurp BOTH into its internal buffer in one syscall
# but hand back only the first. The first line (not a control_request)
# gets deferred and the loop goes back to ``select()`` - which now
# reports the kernel-level pipe as EMPTY forever, even though a complete,
# already-read ``control_request`` line is sitting unread in
# ``TextIOWrapper``'s private buffer. Depending on OS/process scheduling,
# that a landing coincidence happens often enough to flake this suite
# (reproduced independently of any timing budget - see
# test_ordinary_send_turn_while_generating_does_not_desync_the_generating_flag).
# The fix is structural, not a timing tweak: read fd 0 with ``os.read``
# ONLY, through ONE shared line buffer, everywhere in this script (both
# the mid-generation window and the top-level loop) - so a line can never
# be stranded in a buffer nothing else looks at.
_stdin_buf = ""
_stdin_eof = False

def _fill_stdin_buf():
    global _stdin_buf, _stdin_eof
    chunk = os.read(0, 65536)
    if chunk == b"":
        _stdin_eof = True
    else:
        _stdin_buf += chunk.decode("utf-8", errors="replace")

def _pop_buffered_line():
    global _stdin_buf
    idx = _stdin_buf.find("\n")
    if idx == -1:
        return None
    line, _stdin_buf = _stdin_buf[: idx + 1], _stdin_buf[idx + 1 :]
    return line

def _drain_eof_remainder():
    global _stdin_buf
    if _stdin_buf:
        remainder, _stdin_buf = _stdin_buf, ""
        return remainder
    return ""

def read_line_blocking():
    # Block (no timeout) until one full line is available, or return "" on
    # EOF. Always goes through the ONE shared buffer above.
    while True:
        line = _pop_buffered_line()
        if line is not None:
            return line
        if _stdin_eof:
            return _drain_eof_remainder()
        _fill_stdin_buf()

def read_line_within(timeout_s):
    # Non-blocking-with-budget poll: returns a full line if one is already
    # buffered or arrives within timeout_s (select-gated - never a busy
    # spin), "" on EOF, or None if nothing arrived in the budget. Same
    # shared buffer - a line that arrives here and isn't a control_request
    # is left for a LATER caller (deferred_lines below), never silently
    # owned by a buffer another reader can't see.
    line = _pop_buffered_line()
    if line is not None:
        return line
    if _stdin_eof:
        return _drain_eof_remainder()
    ready, _, _ = select.select([0], [], [], timeout_s)
    if not ready:
        return None
    _fill_stdin_buf()
    line = _pop_buffered_line()
    if line is not None:
        return line
    if _stdin_eof:
        return _drain_eof_remainder()
    return None

if scenario == "garbage_line":
    sys.stdout.write("not json at all\n")
    sys.stdout.flush()

if scenario == "die_without_result":
    # Consume nothing useful; die as soon as any input arrives.
    read_line_blocking()
    sys.stderr.write("simulated abrupt death\n")
    sys.stderr.flush()
    sys.exit(2)

if scenario == "eof_without_exit":
    # Consume the turn, then close BOTH streams at the raw OS fd level
    # (both reader threads hit genuine EOF - _finish() runs) but never
    # actually exit the process: sleeps far past _EXIT_WAIT_TIMEOUT_S with
    # stdin left open. This is what `_finish`'s proc.wait(timeout=...) is a
    # backstop against. NOTE: `sys.stdout.close()`/`sys.stderr.close()`
    # (the TextIOWrapper level) do NOT reliably release the pipe's write
    # end promptly on every platform - verified empirically (macOS/CPython
    # 3.13: EOF was NOT observed by the parent until full process exit).
    # `os.close(fd)` on the raw fd does.
    read_line_blocking()
    sys.stdout.flush()
    sys.stderr.flush()
    os.close(1)
    os.close(2)
    time.sleep(30)
    os._exit(0)  # never reached within the test's own bound

def handle_control_request(msg):
    # Answers a control_request; returns True iff it was an honoured interrupt.
    req = msg.get("request") or {}
    req_id = msg.get("request_id")
    subtype = req.get("subtype")
    if subtype == "interrupt":
        if scenario == "crash_early_interrupt" and not generating:
            emit({"type": "control_response", "response": {"subtype": "success", "request_id": req_id, "response": {"still_queued": []}}})
            emit({"type": "result", "subtype": "error_during_execution", "session_id": session_id, "result": ""})
            sys.exit(1)
        emit({"type": "control_response", "response": {"subtype": "success", "request_id": req_id, "response": {"still_queued": []}}})
        emit({"type": "result", "subtype": "error_during_execution", "session_id": session_id, "result": ""})
        return True
    emit({"type": "control_response", "response": {"subtype": "error", "request_id": req_id, "error": "Unsupported control request subtype: " + str(subtype)}})
    return False

deferred_lines = []  # lines read-but-not-consumed by the mid-generation select loop below

def next_raw_line():
    if deferred_lines:
        return deferred_lines.pop(0)
    return read_line_blocking()

while True:
    raw = next_raw_line()
    if raw == "":
        break  # EOF - stdin closed, matches `for raw in sys.stdin`'s natural end
    raw = raw.strip()
    if not raw:
        continue
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        sys.stderr.write("Error parsing streaming input line\n")
        sys.stderr.flush()
        sys.exit(1)

    mtype = msg.get("type")

    if mtype == "control_request":
        generating = False
        handle_control_request(msg)
        continue

    if mtype != "user":
        # Unknown top-level type: silently ignored, matching the real CLI.
        continue

    content = (msg.get("message") or {}).get("content")
    if content is None:
        sys.stderr.write("Error: Expected message role 'user', got 'undefined'\n")
        sys.exit(1)

    emit({"type": "system", "subtype": "init", "session_id": session_id})
    generating = False
    if scenario == "slow_start":
        time.sleep(0.5)
    generating = True
    emit({"type": "stream_event", "event": {"type": "message_start"}})
    emit({"type": "stream_event", "event": {"type": "content_block_start"}})

    interrupted = False
    if scenario == "slow_start":
        # A real generating WINDOW (not just a delay before it): poll stdin
        # with select for up to ~2s so a control_request sent while this
        # turn is "in flight" has a genuine chance to land mid-turn and be
        # honoured inline - mirroring the real CLI's documented behaviour
        # (control_request answered synchronously during an in-flight turn,
        # module docstring) - rather than only ever being visible on the
        # NEXT top-level `for raw in sys.stdin` iteration, which would make
        # a mid-generation interrupt structurally impossible to simulate.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            raw2 = read_line_within(0.05)
            if raw2 is None:
                continue
            if raw2 == "":
                sys.exit(0)  # stdin closed mid-generation: exit like the real CLI's clean path.
            raw2 = raw2.strip()
            if not raw2:
                continue
            try:
                msg2 = json.loads(raw2)
            except json.JSONDecodeError:
                sys.stderr.write("Error parsing streaming input line\n")
                sys.exit(1)
            if msg2.get("type") == "control_request":
                if handle_control_request(msg2):
                    interrupted = True
                    generating = False
                break
            # Any other top-level type arriving mid-generation (e.g. an
            # ordinary queued send_turn racing an interrupt): the real CLI
            # strictly defers it to run AFTER the current turn (module
            # docstring) - DEFER it back into the main read loop (via
            # `deferred_lines`) rather than dropping it, so a test can
            # exercise ">1 turn genuinely outstanding" without losing the
            # second turn's content.
            deferred_lines.append(raw2)

    if not interrupted:
        text = "echo:" + str(content)
        if scenario == "shape_drifted_mid_turn":
            emit({"type": "stream_event", "event": "oops"})
        emit({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}})
        emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}})
        emit({"type": "stream_event", "event": {"type": "content_block_stop"}})
        emit({"type": "result", "subtype": "success", "session_id": session_id, "result": text})
        generating = False

sys.exit(0)
"""


def _connector(scenario: str, **env_overrides: str) -> ClaudeCodeStreamConnector:
    env = {"FAKE_CC_SCENARIO": scenario, **env_overrides}
    return ClaudeCodeStreamConnector(
        binary=sys.executable,
        argv=("-u", "-c", _FAKE_CLAUDE_SCRIPT),
        env=env,
    )


def _drain_until(
    events_iter, predicate, *, timeout_s: float = 10.0
) -> list[HarnessEvent]:
    """Collect events from ``events_iter`` until ``predicate`` matches one.

    Uses a background thread + blocking ``next()`` with an overall wall-clock
    budget so a connector bug that hangs the iterator fails the test instead
    of the test suite itself. Deliberately NOT a sleep-poll loop over the
    connector's own queue - only a coarse outer safety timer for the test.
    """
    import queue as _queue
    import threading as _threading

    out: _queue.Queue = _queue.Queue()

    def _pump():
        try:
            for event in events_iter:
                out.put(("event", event))
                if predicate(event):
                    out.put(("done", None))
                    return
            out.put(("exhausted", None))
        except Exception as exc:  # pragma: no cover - surfaced via assertion below
            out.put(("error", exc))

    t = _threading.Thread(target=_pump, daemon=True)
    t.start()

    collected: list[HarnessEvent] = []
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"timed out waiting for matching event; collected so far: {collected}")
        try:
            kind, payload = out.get(timeout=remaining)
        except _queue.Empty:
            raise AssertionError(f"timed out waiting for matching event; collected so far: {collected}") from None
        if kind == "event":
            collected.append(payload)
        elif kind == "done":
            return collected
        elif kind == "exhausted":
            raise AssertionError(f"events() exhausted before predicate matched; collected: {collected}")
        elif kind == "error":
            raise payload


# --------------------------------------------------------------------------- #
# Capabilities / construction
# --------------------------------------------------------------------------- #
def test_capabilities_match_adr_0004_d7a_mapping():
    connector = _connector("basic")
    caps = connector.capabilities
    assert caps.send_only is False
    assert caps.steer_timing == "IMMEDIATE"
    assert caps.interrupt_requires_settle_wait is False
    assert caps.multiplexes_sessions is False
    assert caps.observes_session_end is True


def test_start_returns_starting_session_with_minted_id():
    connector = _connector("basic")
    session = connector.start(owning_agent_id="agent_test")
    try:
        assert isinstance(session, HarnessSession)
        assert session.session_id.startswith("hsess_")
        assert session.harness_kind == "claude_code"
        assert session.owning_agent_id == "agent_test"
        assert session.status == "STARTING"
        assert session.capabilities is connector.capabilities
    finally:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
        list(connector.events())


def test_start_twice_raises_conflict():
    connector = _connector("basic")
    session = connector.start(owning_agent_id="agent_test")
    try:
        with pytest.raises(OktoNexusError) as exc_info:
            connector.start(owning_agent_id="agent_test")
        assert exc_info.value.code == "CONFLICT"
    finally:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
        list(connector.events())


def test_send_before_start_raises_conflict():
    connector = _connector("basic")
    fake_session = HarnessSession(
        session_id="hsess_doesnotexist",
        harness_kind="claude_code",
        owning_agent_id="agent_test",
        status="STARTING",
        capabilities=connector.capabilities,
        started_at="2026-01-01T00:00:00.000000Z",
    )
    with pytest.raises(OktoNexusError) as exc_info:
        connector.send(fake_session, HarnessCommand(session_id=fake_session.session_id, verb="send_turn", payload={"content": "hi"}))
    assert exc_info.value.code == "CONFLICT"


def test_send_wrong_session_id_rejected():
    connector = _connector("basic")
    session = connector.start(owning_agent_id="agent_test")
    other = HarnessSession(
        session_id="hsess_someone_else",
        harness_kind="claude_code",
        owning_agent_id="agent_test",
        status="STARTING",
        capabilities=connector.capabilities,
        started_at="2026-01-01T00:00:00.000000Z",
    )
    try:
        with pytest.raises(OktoNexusError) as exc_info:
            connector.send(other, HarnessCommand(session_id=other.session_id, verb="send_turn", payload={"content": "hi"}))
        assert exc_info.value.code == "VALIDATION_ERROR"
    finally:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
        list(connector.events())


def test_send_turn_requires_content_payload():
    connector = _connector("basic")
    session = connector.start(owning_agent_id="agent_test")
    try:
        with pytest.raises(OktoNexusError) as exc_info:
            connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={}))
        assert exc_info.value.code == "VALIDATION_ERROR"
    finally:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
        list(connector.events())


# --------------------------------------------------------------------------- #
# Turn lifecycle / event mapping (fake binary)
# --------------------------------------------------------------------------- #
def test_single_turn_maps_turn_started_then_turn_completed():
    connector = _connector("basic")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "hello"}))

    events = _drain_until(connector.events(), lambda e: e.kind == "turn_completed")

    kinds = [e.kind for e in events]
    assert kinds[0] == "turn_started"
    assert kinds[-1] == "turn_completed"
    assert all(e.harness_kind == "claude_code" for e in events)
    assert all(e.session_id == session.session_id for e in events)  # Nexus-minted id, not native

    completed = events[-1]
    assert completed.payload["subtype"] == "success"
    assert completed.payload["interrupted_by_connector"] is False

    deltas = [e for e in events if e.kind == "output_delta"]
    assert any("echo:hello" in (d.payload.get("text") or "") for d in deltas)

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(connector.events())


def test_second_turn_reuses_same_nexus_session_id():
    connector = _connector("basic")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "one"}))
    _drain_until(connector.events(), lambda e: e.kind == "turn_completed")

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "two"}))
    events = _drain_until(connector.events(), lambda e: e.kind == "turn_completed")
    assert all(e.session_id == session.session_id for e in events)
    completed = events[-1]
    assert "echo:two" in completed.payload["result"]

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(connector.events())


def test_unparseable_stdout_line_surfaced_not_dropped_and_does_not_hang():
    connector = _connector("garbage_line")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "hello"}))

    events = _drain_until(connector.events(), lambda e: e.kind == "turn_completed")
    error_events = [e for e in events if e.kind == "error" and e.native_event == "unparseable_stdout_line"]
    assert len(error_events) == 1
    assert error_events[0].payload["raw"] == "not json at all"
    # And the connector kept going afterwards - turn still completed.
    assert events[-1].kind == "turn_completed"

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(connector.events())


def test_shape_drifted_stdout_line_is_surfaced_not_fatal_to_the_reader():
    """Defect (journal wf_de1d2ad9-17f, line 17, CRITICAL): a syntactically
    valid JSON line with a shape-drifted internal field (e.g.
    ``{"type":"stream_event","event":"oops"}`` - a string where the
    connector's handlers expect a dict) used to raise an uncaught
    AttributeError INSIDE per-line dispatch, silently killing the stdout
    reader thread (Python swallows the exception in a bare thread target).
    ``_finish()`` then ran with the child still genuinely alive: two back-
    to-back 10s timeouts (stderr join, then ``proc.wait``) before it
    fabricated a ``process_exit``/session-end signal the connector never
    actually observed, dropped the turn's real eventual result forever, and
    leaked the child process.

    Uses a 15s ``_drain_until`` budget - short enough that the pre-fix ~20s
    double-timeout path fails this test rather than merely making it slow.
    """
    connector = _connector("shape_drifted_mid_turn")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "hello"}))

    events = _drain_until(connector.events(), lambda e: e.kind == "turn_completed", timeout_s=15.0)

    dispatch_errors = [e for e in events if e.kind == "error" and e.native_event == "stdout_dispatch_error"]
    assert len(dispatch_errors) == 1, f"expected exactly one dispatch-error event, got: {events}"
    assert "oops" in dispatch_errors[0].payload["raw"]

    # The reader thread survived: the turn's REAL, subsequent completion is
    # not lost, and no fabricated process_exit/session-end event appears.
    assert not any(e.kind == "error" and e.native_event in ("process_exit", "reader_eof_without_confirmed_exit") for e in events)
    completed = events[-1]
    assert completed.kind == "turn_completed"
    assert completed.payload["subtype"] == "success"
    assert "echo:hello" in completed.payload["result"]

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(connector.events())


def test_child_death_without_result_surfaces_error_then_ends_cleanly():
    connector = _connector("die_without_result")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "hello"}))

    events = list(connector.events())  # bounded: the fake script exits fast.
    assert events, "expected at least the diagnostic error event"
    error_events = [e for e in events if e.kind == "error" and e.native_event == "process_exit"]
    assert len(error_events) == 1
    assert error_events[0].payload["exit_code"] == 2
    assert "simulated abrupt death" in error_events[0].payload["stderr_tail"]


def test_events_called_twice_both_return_after_close_not_just_one():
    """Cross-cutting defect class (see two sibling connectors' reviews in
    the same journal): a single-consumption shutdown sentinel (one ``None``
    pushed once into the shared queue by ``_finish()``) can only ever be
    observed by ONE ``events()`` caller. Whichever generator happens to
    consume that sentinel returns; any OTHER live generator - a second call
    to ``events()``, or the same caller invoking it twice - is left blocked
    forever on an unbounded ``Queue.get()`` with nothing left to receive,
    since nothing is ever pushed again.

    Reproduced deterministically: open two generators before the child
    exits, let the first drain to completion (consuming whatever sentinel
    exists), then assert the second ALSO returns - via a background thread
    with a bounded ``join()`` so a real hang fails this test in seconds
    rather than wedging the suite.
    """
    connector = _connector("basic")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))

    it1 = connector.events()
    it2 = connector.events()

    list(it1)  # drains to exhaustion - single-threaded, so this runs first and fully

    result: dict[str, object] = {}

    def _drain_second() -> None:
        result["events"] = list(it2)

    t = threading.Thread(target=_drain_second, daemon=True)
    t.start()
    t.join(timeout=10.0)
    assert not t.is_alive(), (
        "second events() call hung - single-consumption shutdown sentinel "
        "regression (see module docstring / harness/pi.py reference fix)"
    )
    assert result.get("events") == []


def test_finish_never_fabricates_process_exit_when_child_is_still_alive():
    """Covers the OTHER half of defect 1's why_it_matters (journal
    wf_de1d2ad9-17f, line 17, CRITICAL) via a DIFFERENT route than the
    reviewer's own repro: their mechanism was a dispatch error killing the
    reader thread outright, which is no longer reachable at all once
    :meth:`_pump_stdout`'s per-line guard is in place (see
    test_shape_drifted_stdout_line_is_surfaced_not_fatal_to_the_reader) -
    the loop never aborts early any more. This test instead reaches the
    SAME ``_finish`` branch the honest way: genuine raw-fd EOF on both
    stdout/stderr while the child process itself is still alive (verified
    empirically that ``sys.stdout.close()`` at the TextIOWrapper level does
    NOT reliably release the pipe's write end promptly on this platform -
    ``os.close(fd)`` does; see the ``eof_without_exit`` fake scenario).
    Either way, ``_finish`` must not FABRICATE a ``process_exit``/
    session-end signal it never actually observed - ``proc.poll()`` proves
    the child is still alive at exactly that moment - and must say so
    honestly and kill the leaked child rather than abandoning it.

    Explicitly bounded (not a bare ``list(events())``): a background thread
    with a hard ``join(timeout=25.0)``, so a regression that removes
    ``_finish``'s own internal backstop fails this test in seconds instead
    of hanging the suite - the same pattern as
    test_events_called_twice_both_return_after_close_not_just_one.
    """
    connector = _connector("eof_without_exit")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "hello"}))

    result: dict[str, object] = {}

    def _drain() -> None:
        result["events"] = list(connector.events())

    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    t.join(timeout=25.0)
    assert not t.is_alive(), "events() did not terminate - _finish's internal backstop appears to have regressed"

    events = result["events"]
    honest_events = [e for e in events if e.kind == "error" and e.native_event == "reader_eof_without_confirmed_exit"]
    assert len(honest_events) == 1, f"expected exactly one honest EOF-without-exit event, got: {events}"
    assert honest_events[0].payload["was_still_running_before_kill"] is True
    assert not any(e.kind == "error" and e.native_event == "process_exit" for e in events), (
        "must never fabricate process_exit while the child is provably still alive"
    )

    # The leaked child was actually killed, not abandoned.
    assert connector._proc is not None
    assert connector._proc.poll() is not None, "child process was left running (leaked)"


def test_end_closes_stdin_and_events_iterator_exhausts_cleanly():
    connector = _connector("basic")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))

    # events() must terminate (sentinel), not hang, and with no error event
    # for a clean exit(0).
    events = list(connector.events())
    assert all(not (e.kind == "error" and e.native_event == "process_exit") for e in events)


# --------------------------------------------------------------------------- #
# Interrupt safety gate (fake binary) - the crash-avoidance behaviour is the
# most important thing this connector does; test it directly rather than
# only via the real binary.
# --------------------------------------------------------------------------- #
def test_interrupt_in_unsafe_window_is_deferred_not_forwarded():
    """The 'crash_early_interrupt' fake would kill the child if an interrupt
    reached it before content_block_start. Firing interrupt() immediately
    after send_turn (before any stream_event can possibly have arrived)
    proves the connector's own gate keeps the child alive - the interrupt
    never reaches the fake at all.
    """
    connector = _connector("crash_early_interrupt")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "hello"}))
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))

    events = _drain_until(connector.events(), lambda e: e.kind == "turn_completed")
    assert not any(e.kind == "error" and e.native_event == "process_exit" for e in events)
    deferred = [e for e in events if e.native_event == "interrupt_deferred_unsafe_window"]
    assert len(deferred) == 1
    assert deferred[0].payload["interrupt_degraded"] is True
    completed = events[-1]
    assert completed.payload["subtype"] == "success"  # turn ran to completion, uninterrupted

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(connector.events())


def test_interrupt_after_generation_started_is_forwarded_and_marks_interrupted():
    connector = _connector("slow_start")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "hello"}))

    # Wait for the connector to actually observe generation start before
    # interrupting - this is the safe window (the fake's 0.5s sleep before
    # message_start makes this reliable without a race).
    for event in connector.events():
        if event.native_event == "stream_event:content_block_start":
            break
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))

    events = _drain_until(connector.events(), lambda e: e.kind == "turn_completed")
    completed = events[-1]
    assert completed.payload["subtype"] == "error_during_execution"
    assert completed.payload["interrupted_by_connector"] is True
    assert completed.kind == "turn_completed"  # not "error" - deliberate interrupt, not a failure

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(connector.events())


class _StubStdin:
    """Minimal stand-in for ``Popen.stdin`` - only ``write``/``flush`` are
    touched by ``_write_json``/``_end``, so nothing else needs modelling."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.closed = False

    def write(self, s: str) -> None:
        self.lines.append(s)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _StubProc:
    def __init__(self) -> None:
        self.stdin = _StubStdin()


def _wired_connector() -> ClaudeCodeStreamConnector:
    """A connector with just enough internal state hand-wired to exercise
    the pure in-memory command/result-handling logic without a subprocess -
    ``_request_interrupt``/``_handle_result`` never touch anything but
    ``_proc.stdin`` (write path) and ``self._session`` (event stamping)."""
    connector = ClaudeCodeStreamConnector(binary=sys.executable, argv=("-c", "pass"))
    connector._proc = _StubProc()  # type: ignore[assignment]
    connector._session = HarnessSession(
        session_id="hsess_test",
        harness_kind="claude_code",
        owning_agent_id="agent_test",
        status="STARTING",
        capabilities=connector.capabilities,
        started_at="2026-01-01T00:00:00.000000Z",
    )
    return connector


def test_request_interrupt_marks_the_head_pending_turn_not_the_tail():
    """Defect (journal wf_de1d2ad9-17f, line 17): ``_request_interrupt``
    used to mark ``_pending_turns[-1]`` (the newest, not-yet-started entry)
    while ``_handle_result`` always resolves oldest-first via ``popleft()``.
    Whenever more than one turn is outstanding (two ordinary ``send_turn``
    calls before the first resolves - nothing forbids this), those two ends
    disagreed about which pending entry an interrupt belongs to: the
    genuinely-interrupted HEAD turn's belated result was misclassified as
    ``error`` and the untouched TAIL turn's later, unrelated genuine failure
    was misclassified as ``turn_completed`` / ``interrupted_by_connector``.

    This reproduces the bug deterministically with no subprocess/threading:
    seed two outstanding turns, request one interrupt (as ``_interrupt()``
    would once it observes generation has started), then resolve both in
    FIFO order and assert the interrupt landed on the turn actually being
    interrupted (the head), not the tail.
    """
    from collections import deque

    connector = _wired_connector()
    connector._pending_turns = deque([False, False])  # two turns outstanding
    connector._turn_in_flight = True
    connector._turn_generating.set()  # safe window: real interrupt path

    connector._interrupt()

    # Belated results arrive in the order the turns were queued (FIFO,
    # single-threaded child - see _pending_turns's docstring): turn 1 (the
    # one actually interrupted) resolves first, turn 2 (never interrupted,
    # a genuine unrelated failure) resolves second.
    connector._handle_result({"subtype": "error_during_execution"})
    connector._handle_result({"subtype": "error_during_execution"})

    events = []
    while not connector._events.empty():
        events.append(connector._events.get())

    kinds = [e.kind for e in events]
    interrupted_flags = [e.payload["interrupted_by_connector"] for e in events]
    assert kinds == ["turn_completed", "error"], (
        "turn 1 (actually interrupted) must be classified turn_completed; "
        f"turn 2 (unrelated failure) must be classified error - got {kinds}"
    )
    assert interrupted_flags == [True, False]


def test_write_lock_contention_raises_instead_of_blocking_forever():
    """Audit finding (STANDING REQUIREMENT: every blocking wait has a
    timeout and raises a clear error on expiry): ``_write_json``/``_end``
    used to take ``self._write_lock`` with a bare ``with`` - an unbounded
    acquire. If a write ever got stuck holding it (e.g. genuinely blocked
    on a full stdin pipe because the child stopped reading), every OTHER
    caller of ``send()`` would then wedge forever with no way to observe
    or recover from it - a silent hang, worse than a crash (module
    docstring's own framing, echoed in the task brief).

    Reproduced deterministically: hold the lock from another thread for
    longer than the bounded timeout, then assert a concurrent write raises
    a clear ``OktoNexusError`` rather than blocking past it.
    """
    connector = _wired_connector()
    connector._write_lock.acquire()
    try:
        result: dict[str, object] = {}

        def _attempt_write() -> None:
            try:
                connector._write_json({"type": "user", "message": {"role": "user", "content": "x"}})
            except OktoNexusError as exc:
                result["error"] = exc

        t = threading.Thread(target=_attempt_write, daemon=True)
        t.start()
        t.join(timeout=15.0)
        assert not t.is_alive(), "write lock acquire hung past its bounded timeout"
        assert isinstance(result.get("error"), OktoNexusError)
        assert result["error"].code == "INTERNAL_ERROR"
    finally:
        connector._write_lock.release()


def test_interrupt_with_no_turn_in_flight_is_a_safe_no_op():
    connector = _connector("basic")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "still alive"}))

    events = _drain_until(connector.events(), lambda e: e.kind == "turn_completed")
    assert events[-1].payload["subtype"] == "success"

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(connector.events())


# --------------------------------------------------------------------------- #
# steer() - mid-turn redirect (ADR 0004 D7a "steer_timing=IMMEDIATE" claim).
# Verified empirically (2026-09-20 probe of claude 2.1.278) that
# `system/init` does NOT fire until a turn's content is actually written to
# stdin - it is a per-turn signal, never a bare process-start one. Both
# scenarios below therefore always send_turn before touching the events
# iterator, matching that verified behaviour (and matching the fake's own
# `for raw in sys.stdin` shape, which emits nothing until it has a line to
# read).
# --------------------------------------------------------------------------- #
def test_steer_after_generation_started_interrupts_current_turn_then_runs_new_one():
    connector = _connector("slow_start")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "first"}))

    it = connector.events()
    for event in it:
        if event.native_event == "stream_event:content_block_start":
            break
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="steer", payload={"content": "steered"}))

    first_turn = _drain_until(it, lambda e: e.kind == "turn_completed")
    assert first_turn[-1].payload["subtype"] == "error_during_execution"
    assert first_turn[-1].payload["interrupted_by_connector"] is True

    second_turn = _drain_until(it, lambda e: e.kind == "turn_completed")
    assert second_turn[-1].payload["subtype"] == "success"
    assert "echo:steered" in second_turn[-1].payload["result"]

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(it)


def test_steer_in_unsafe_window_is_deferred_and_degrades_to_a_queued_turn():
    """Mirrors test_interrupt_in_unsafe_window_is_deferred_not_forwarded:
    firing steer() immediately after send_turn (before generation can
    possibly have started) proves the connector never forwards a real
    interrupt into the fatal race window - it only queues the new content,
    exactly the "Known, deliberate degradation" the module docstring
    describes for steer.
    """
    connector = _connector("crash_early_interrupt")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "first"}))
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="steer", payload={"content": "steered"}))

    events = _drain_until(connector.events(), lambda e: e.kind == "turn_completed")
    assert not any(e.kind == "error" and e.native_event == "process_exit" for e in events)
    deferred = [e for e in events if e.native_event == "steer_interrupt_deferred_unsafe_window"]
    assert len(deferred) == 1
    # Defect (journal wf_de1d2ad9-17f, line 17, major): the declared
    # steer_timing=IMMEDIATE capability had no port-legal, closed-
    # vocabulary way for a supervisor to learn about this documented
    # exception (EVENT_KINDS has no dedicated kind and the port is frozen -
    # cannot add one). Partial fix: a stable, always-present payload flag a
    # supervisor can branch on without native_event string-matching.
    assert deferred[0].payload["steer_timing_degraded"] is True
    assert deferred[0].payload["declared_steer_timing"] == "IMMEDIATE"
    assert deferred[0].payload["effective_steer_timing"] == "NEXT_TURN_BOUNDARY"

    completed = events[-1]
    assert completed.payload["subtype"] == "success"
    # The FIRST turn's own content ("first") - not the degraded steer text -
    # since the unsafe-window degrade path never interrupts, so "first" runs
    # to completion before "steered" is even queued behind it.
    assert "echo:first" in completed.payload["result"]

    second = _drain_until(connector.events(), lambda e: e.kind == "turn_completed")
    assert second[-1].payload["subtype"] == "success"
    assert "echo:steered" in second[-1].payload["result"]

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(connector.events())


def test_ordinary_send_turn_while_generating_does_not_desync_the_generating_flag():
    """Defect (adversarial recheck, MAJOR, new): ``_send_turn`` used to call
    ``self._turn_generating.clear()`` UNCONDITIONALLY, even when it is
    queuing an ORDINARY second turn behind one that is already, genuinely
    generating. ``_turn_generating`` is meant to track whether the HEAD
    turn (the one actually running right now) has started producing
    output - that is what the interrupt safety gate in ``_interrupt()``/
    ``_steer()`` reads to decide whether a real ``control_request`` is safe
    to forward. Clearing it here has nothing to do with the head turn: it
    only reflects that the NEW (tail) turn hasn't started yet. The bug
    silently defeats a SUBSEQUENT interrupt: the connector believes no turn
    is generating, degrades the interrupt to a documented no-op, and the
    turn that is genuinely running is never actually interrupted.

    Reproduced with the real multi-turn shape this connector exists for:
    send turn 1, wait for the connector to observe it has started
    generating (``stream_event:content_block_start``), send an ORDINARY
    second turn while turn 1 is still in flight (nothing in the port
    forbids this - it is the normal multi-turn path), THEN interrupt.
    Correct behaviour: the interrupt is forwarded for real (turn 1 is
    genuinely generating) and turn 1's belated result is classified
    ``turn_completed``/``interrupted_by_connector=True`` - never deferred
    as an "unsafe window" no-op.
    """
    connector = _connector("slow_start")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "first"}))

    it = connector.events()
    for event in it:
        if event.native_event == "stream_event:content_block_start":
            break

    # Turn 1 is now genuinely generating (_turn_generating is set). An
    # ORDINARY second send_turn queued behind it must not desync that flag.
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "second"}))
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))

    first_turn = _drain_until(it, lambda e: e.kind == "turn_completed")
    deferred = [e for e in first_turn if e.native_event == "interrupt_deferred_unsafe_window"]
    assert not deferred, (
        "interrupt was deferred as 'unsafe window' even though turn 1 was "
        "genuinely generating - _send_turn desynchronised _turn_generating "
        "by clearing it for a queued (tail) turn instead of the head turn"
    )
    assert first_turn[-1].payload["subtype"] == "error_during_execution"
    assert first_turn[-1].payload["interrupted_by_connector"] is True

    second_turn = _drain_until(it, lambda e: e.kind == "turn_completed")
    assert second_turn[-1].payload["subtype"] == "success"
    assert second_turn[-1].payload["interrupted_by_connector"] is False
    assert "echo:second" in second_turn[-1].payload["result"]

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    for _ in it:
        pass


def test_interrupt_with_a_second_turn_already_queued_behind_resolves_fifo_correctly():
    """Coverage gap (journal wf_de1d2ad9-17f, line 17, major finding): no
    prior test ever left >1 turn genuinely outstanding in ``_pending_turns``
    at the moment ``_request_interrupt()`` marks an entry - the existing
    steer tests only ever have a single pending entry at that exact moment
    (``_steer()`` appends its OWN new entry only AFTER calling
    ``_request_interrupt()``, so ``[-1]`` and ``[0]`` were indistinguishable
    there). This is a full connector-integration reproduction of the shape
    the marking-bug fix (see
    ``test_request_interrupt_marks_the_head_pending_turn_not_the_tail`` for
    the isolated logic-only version) must hold under: an ordinary
    ``interrupt()`` while a SECOND, ordinary ``send_turn`` is already queued
    behind the first - nothing in ``send()``/the port forbids this.
    """
    connector = _connector("slow_start")
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "first"}))
    # Queue a SECOND turn immediately, BEFORE turn 1 has even started
    # generating - matching the review's exact failure_scenario ordering.
    # _pending_turns is genuinely [False, False] (length 2) at the moment
    # interrupt() below marks an entry; the fake's mid-generation select
    # loop defers (not drops) this queued line until turn 1 resolves,
    # mirroring the real CLI's documented strict-queueing behaviour.
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "second"}))

    it = connector.events()
    for event in it:
        if event.native_event == "stream_event:content_block_start":
            break
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))

    first_turn = _drain_until(it, lambda e: e.kind == "turn_completed")
    assert first_turn[-1].payload["subtype"] == "error_during_execution"
    assert first_turn[-1].payload["interrupted_by_connector"] is True

    second_turn = _drain_until(it, lambda e: e.kind == "turn_completed")
    assert second_turn[-1].payload["subtype"] == "success"
    assert second_turn[-1].payload["interrupted_by_connector"] is False
    assert "echo:second" in second_turn[-1].payload["result"]

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    for _ in it:
        pass


@requires_real_claude
def test_real_claude_interrupt_with_a_second_turn_already_queued_behind():
    """Real-CLI counterpart of the fake-level test above - closes the other
    half of the coverage gap (no test, fake OR real, ever exercised the FIFO
    ordering claim against the actual binary). Asserts only on
    ``interrupted_by_connector`` and session survival, never on exact model
    text, per the suite's existing real-binary convention.
    """
    connector = ClaudeCodeStreamConnector()
    session = connector.start(owning_agent_id="agent_test")
    connector.send(
        session,
        HarnessCommand(
            session_id=session.session_id,
            verb="send_turn",
            payload={"content": "Write the numbers 1 to 30, one per line, nothing else. Do not stop early."},
        ),
    )

    it = connector.events()
    for event in it:
        if event.native_event in ("stream_event:message_start", "stream_event:content_block_start"):
            break
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "reply with the single word: second"}),
    )

    first_turn = _drain_until(it, lambda e: e.kind == "turn_completed", timeout_s=30)
    assert first_turn[-1].payload["interrupted_by_connector"] is True

    second_turn = _drain_until(it, lambda e: e.kind == "turn_completed", timeout_s=30)
    assert second_turn[-1].payload["interrupted_by_connector"] is False
    assert "second" in second_turn[-1].payload["result"].lower()

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    remaining = list(it)
    assert not any(e.kind == "error" and e.native_event == "process_exit" for e in remaining)


# --------------------------------------------------------------------------- #
# No-polling proof: a blocking Queue.get() wakes immediately on publish,
# never on a fixed interval (D1: no SleepPollWaiter anywhere in this path).
# --------------------------------------------------------------------------- #
#: How long the real connector's events() may take to deliver the first
#: event after send_turn. Tight enough that ANY meaningfully poll-based
#: implementation fails it (see the in-test control below, which proves
#: this - not just asserts a number and hopes), loose enough to absorb
#: local-subprocess IPC jitter for a genuinely blocking implementation.
_PROMPT_DELIVERY_BOUND_S = 0.2


class _SleepPollEventsConnector(ClaudeCodeStreamConnector):
    """A connector that reimplements ``events()`` as a DELIBERATE sleep-poll
    loop - exactly the anti-pattern D1 forbids and this module's own
    ``events()`` must never be. Exists ONLY as a control in
    ``test_events_iterator_delivers_promptly_not_on_a_poll_interval``, to
    prove ``_PROMPT_DELIVERY_BOUND_S`` actually discriminates a poll-based
    implementation from a genuinely blocking one - the exact honesty gap a
    prior version of this test had (it used a 1.0s bound that a
    sub-second, e.g. 900ms, poll interval would also have satisfied).
    """

    _POLL_PERIOD_S = 0.3

    def events(self):  # type: ignore[override]
        while True:
            time.sleep(self._POLL_PERIOD_S)
            drained_any = False
            while True:
                try:
                    item = self._events.get_nowait()
                except queue.Empty:
                    break
                drained_any = True
                yield item
            if not drained_any and self._closed_event.is_set():
                return


def test_events_iterator_delivers_promptly_not_on_a_poll_interval():
    """``system/init`` (this connector's ``turn_started`` signal) does NOT
    fire at bare process start - verified empirically against the real
    ``claude`` 2.1.278 binary (2026-09-20 stream-json probe): it is a
    PER-TURN event, only emitted once a turn's content has actually been
    written to stdin. The fake script mirrors this (nothing is emitted
    until its ``for raw in sys.stdin`` loop has a line to read), so
    ``next(it)`` is only ever called AFTER ``send_turn`` below - calling it
    before would block forever on both the fake and the real binary.

    Test-honesty fix (journal wf_de1d2ad9-17f, line 17, minor): the
    previous version of this test asserted ``t_first < 1.0`` - loose enough
    that a hypothetical sub-second sleep-poll implementation (e.g. a 900ms
    interval) would ALSO have satisfied it, so passing proved nothing about
    polling specifically. This version first runs the identical measurement
    through :class:`_SleepPollEventsConnector`, a deliberately poll-based
    ``events()``, and requires THAT to exceed the bound below - proving the
    bound discriminates - before asserting the real connector stays under
    it.
    """
    poll_connector = _SleepPollEventsConnector(
        binary=sys.executable, argv=("-u", "-c", _FAKE_CLAUDE_SCRIPT), env={"FAKE_CC_SCENARIO": "slow_start"}
    )
    poll_session = poll_connector.start(owning_agent_id="agent_test")
    poll_it = poll_connector.events()
    t0 = time.monotonic()
    poll_connector.send(poll_session, HarnessCommand(session_id=poll_session.session_id, verb="send_turn", payload={"content": "hi"}))
    poll_first = next(poll_it)
    poll_latency = time.monotonic() - t0
    assert poll_first.kind == "turn_started"
    assert poll_latency > _PROMPT_DELIVERY_BOUND_S, (
        f"control (deliberately poll-based events()) delivered the first "
        f"event in {poll_latency:.3f}s, under the {_PROMPT_DELIVERY_BOUND_S}s "
        "bound - the bound below would not actually catch a poll-based "
        "implementation; widen _SleepPollEventsConnector._POLL_PERIOD_S"
    )
    poll_connector.send(poll_session, HarnessCommand(session_id=poll_session.session_id, verb="end"))
    for _ in poll_it:
        pass

    connector = _connector("slow_start")  # 0.5s gap before the first real event
    session = connector.start(owning_agent_id="agent_test")

    it = connector.events()
    t0 = time.monotonic()
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "hi"}))
    # first event after send_turn is turn_started (system:init)
    first = next(it)
    t_first = time.monotonic() - t0
    assert first.kind == "turn_started"
    assert t_first < _PROMPT_DELIVERY_BOUND_S, (
        f"first event took {t_first:.3f}s to arrive - the control above "
        f"proves a poll-based events() would exceed {_PROMPT_DELIVERY_BOUND_S}s "
        "here, so this looks like polling, not a genuine blocking wait"
    )

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    for _ in it:
        pass


# --------------------------------------------------------------------------- #
# Real-binary tests (skipped when `claude` is not on PATH)
# --------------------------------------------------------------------------- #
@requires_real_claude
def test_real_claude_single_trivial_turn():
    connector = ClaudeCodeStreamConnector()
    session = connector.start(owning_agent_id="agent_test")
    connector.send(
        session,
        HarnessCommand(
            session_id=session.session_id,
            verb="send_turn",
            payload={"content": "reply with the single word: ok"},
        ),
    )
    events = _drain_until(connector.events(), lambda e: e.kind == "turn_completed", timeout_s=60)
    # NOT necessarily events[0]: verified empirically (2026-09-20, this same
    # environment) that a machine with SessionStart hooks configured emits
    # `system:hook_started`/`system:hook_response` (mapped to `tool_activity`
    # per the module docstring's event-vocabulary port-gap note) BEFORE
    # `system:init` on the very first turn of a process. turn_started is
    # still guaranteed to occur before turn_completed, just not first.
    assert any(e.kind == "turn_started" for e in events[:-1])
    completed = events[-1]
    assert completed.payload["subtype"] == "success"
    assert "ok" in completed.payload["result"].lower()

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    remaining = list(connector.events())
    assert not any(e.kind == "error" and e.native_event == "process_exit" for e in remaining)


@requires_real_claude
def test_real_claude_two_turns_share_session_and_process_survives():
    connector = ClaudeCodeStreamConnector()
    session = connector.start(owning_agent_id="agent_test")
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "reply with the single word: one"}),
    )
    first = _drain_until(connector.events(), lambda e: e.kind == "turn_completed", timeout_s=60)
    assert "one" in first[-1].payload["result"].lower()

    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "reply with the single word: two"}),
    )
    second = _drain_until(connector.events(), lambda e: e.kind == "turn_completed", timeout_s=60)
    assert "two" in second[-1].payload["result"].lower()
    assert second[0].kind == "turn_started"  # system:init re-fired for turn 2

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    list(connector.events())


@requires_real_claude
def test_real_claude_steer_interrupts_in_flight_turn_and_runs_new_one_immediately():
    """Coverage gap (adversarial recheck, MAJOR): no test - fake OR real -
    ever called ``send()`` with ``verb='steer'`` against the real ``claude``
    binary, so the connector's declared ``steer_timing=IMMEDIATE`` (module
    docstring, ``__init__``) was never actually verified for the ``steer``
    verb itself, only inferred from separately verified ``interrupt``
    behaviour.

    Empirically established against ``claude`` 2.1.278 (manual probe,
    2026-09-20, same shape as this test): ``steer`` sent once the first
    turn has started generating (``content_block_start`` observed) lands a
    real ``control_request``/``interrupt`` almost instantly (~15ms in the
    probe - a ``control_response:success`` followed immediately by the
    interrupted turn's ``result:error_during_execution``), and the new,
    steered content then runs as the very next turn on the SAME process/
    session with no settle delay needed. This is genuine IMMEDIATE
    redirection, not a bare queued line landing only at the next turn
    boundary (that would be NEXT_TURN_BOUNDARY, not IMMEDIATE - see the
    module docstring's "steer_timing=IMMEDIATE achievable via interrupt-
    then-resend" note) - so the declared capability is honest, not a
    capability lie, for this (safe-window) path. The one documented
    exception (the unsafe-window degrade, where steer falls back to a
    queued NEXT_TURN_BOUNDARY-like line) is covered separately by
    ``test_steer_in_unsafe_window_is_deferred_and_degrades_to_a_queued_turn``
    on the fake binary - the race window is sub-second and not reliably
    reproducible against the real binary without artificially slowing it.
    """
    connector = ClaudeCodeStreamConnector()
    session = connector.start(owning_agent_id="agent_test")
    connector.send(
        session,
        HarnessCommand(
            session_id=session.session_id,
            verb="send_turn",
            payload={"content": "Write the numbers 1 to 40, one per line, nothing else. Do not stop early."},
        ),
    )

    it = connector.events()
    for event in it:
        if event.native_event in ("stream_event:message_start", "stream_event:content_block_start"):
            break

    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="steer", payload={"content": "reply with the single word: steered"}),
    )

    first_turn = _drain_until(it, lambda e: e.kind == "turn_completed", timeout_s=30)
    assert not any(e.native_event == "steer_interrupt_deferred_unsafe_window" for e in first_turn), (
        "steer degraded to the unsafe-window queued-turn fallback instead of "
        "a real interrupt - the first turn was already observed generating, "
        "so this must be the genuine IMMEDIATE path"
    )
    assert first_turn[-1].payload["interrupted_by_connector"] is True
    assert first_turn[-1].payload["subtype"] == "error_during_execution"

    second_turn = _drain_until(it, lambda e: e.kind == "turn_completed", timeout_s=30)
    assert second_turn[-1].payload["interrupted_by_connector"] is False
    assert second_turn[-1].payload["subtype"] == "success"
    assert "steered" in second_turn[-1].payload["result"].lower()

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    remaining = list(it)
    assert not any(e.kind == "error" and e.native_event == "process_exit" for e in remaining)


@requires_real_claude
def test_real_claude_interrupt_after_generation_start_survives_and_reprompts_immediately():
    connector = ClaudeCodeStreamConnector()
    session = connector.start(owning_agent_id="agent_test")
    connector.send(
        session,
        HarnessCommand(
            session_id=session.session_id,
            verb="send_turn",
            payload={"content": "Write the numbers 1 to 30, one per line, nothing else. Do not stop early."},
        ),
    )

    it = connector.events()
    for event in it:
        if event.native_event in ("stream_event:message_start", "stream_event:content_block_start"):
            break

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))
    interrupted_result = _drain_until(it, lambda e: e.kind == "turn_completed", timeout_s=30)
    assert interrupted_result[-1].payload["interrupted_by_connector"] is True

    # No settle wait: reprompt immediately (interrupt_requires_settle_wait=False).
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "reply with the single word: alive"}),
    )
    revived = _drain_until(it, lambda e: e.kind == "turn_completed", timeout_s=30)
    assert "alive" in revived[-1].payload["result"].lower()

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    remaining = list(it)
    assert not any(e.kind == "error" and e.native_event == "process_exit" for e in remaining)


@requires_real_claude
def test_real_claude_end_verb_drains_and_exits_cleanly():
    connector = ClaudeCodeStreamConnector()
    session = connector.start(owning_agent_id="agent_test")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    events = list(connector.events())  # must terminate, not hang
    assert not any(e.kind == "error" and e.native_event == "process_exit" for e in events)


@requires_real_claude
def test_real_claude_interrupt_targets_head_turn_with_two_outstanding():
    """Real-CLI coverage for the fix in ``_request_interrupt`` (journal
    wf_de1d2ad9-17f, line 17, critical defect): two ordinary ``send_turn``
    calls issued before either resolves leave TWO outstanding turns: this
    is exactly the scenario the old ``_pending_turns[-1]`` bug needed and
    the fake-only test suite never exercised (flagged as its own gap in the
    same review). Verified manually against this real binary during review
    (2026-09-20, claude 2.1.278): two turns queued back-to-back, interrupted
    once the first starts generating, resolve in FIFO order - turn 1
    (interrupted) first with ``interrupted_by_connector=True``, turn 2
    (untouched) second with ``success`` - proving the interrupt landed on
    the turn actually running, not the one merely queued behind it.
    """
    connector = ClaudeCodeStreamConnector()
    session = connector.start(owning_agent_id="agent_test")
    connector.send(
        session,
        HarnessCommand(
            session_id=session.session_id,
            verb="send_turn",
            payload={"content": "Write the numbers 1 to 40, one per line, nothing else. Do not stop early."},
        ),
    )
    connector.send(
        session,
        HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "reply with the single word: two"}),
    )

    it = connector.events()
    for event in it:
        if event.native_event in ("stream_event:message_start", "stream_event:content_block_start"):
            break
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))

    first = _drain_until(it, lambda e: e.kind == "turn_completed", timeout_s=60)
    assert first[-1].payload["interrupted_by_connector"] is True
    assert first[-1].payload["subtype"] == "error_during_execution"

    second = _drain_until(it, lambda e: e.kind == "turn_completed", timeout_s=60)
    assert second[-1].payload["interrupted_by_connector"] is False
    assert second[-1].payload["subtype"] == "success"
    assert "two" in second[-1].payload["result"].lower()

    connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))
    remaining = list(it)
    assert not any(e.kind == "error" and e.native_event == "process_exit" for e in remaining)
