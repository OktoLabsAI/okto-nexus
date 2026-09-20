# EV-CC-005 — RES-B1..3, RES-C1..3, Claude Code stream-json connector

Captured: 2026-09-20, this session. Module under test:
`src/okto_nexus/adapters/outbound/harness/claude_code_stream.py` (FROZEN — read-only, unchanged).

## RES-B1 — domain-invalid-but-syntactically-valid message surfaced, reader continues (PASS, existing)

The test plan's own example shapes (`empty method`, `params` as a JSON array) are JSON-RPC 2.0
vocabulary specific to Codex's `app-server` protocol — stream-json has no `method`/`params`
envelope at all, so there is no literal analogue. The mapped equivalent for THIS wire format,
already covered: a line that IS valid JSON, IS a recognised top-level `"type"`, but has an
internally shape-drifted field the handler assumes is a dict
(`{"type":"stream_event","event":"oops"}` — a string where `_handle_stream_event` calls `.get()`
on it). This is domain-invalid in exactly the sense RES-B1 means (distinct from, and NOT caught by,
the `json.JSONDecodeError` guard in `_handle_stdout_line`, which is a different, already-covered
class).

`test_shape_drifted_stdout_line_is_surfaced_not_fatal_to_the_reader` (existing, unchanged) —
PASSED: the malformed line is surfaced as `error`/`stdout_dispatch_error` (not silently dropped),
and the reader loop CONTINUES — the turn's real, subsequent `turn_completed` is not lost, and no
fabricated `process_exit`/session-end event appears in between.

## RES-B2 — a reader thread exiting for ANY reason signals shutdown to EVERY consumer (PASS, existing + structural)

Structural guarantee: `_pump_stdout`'s entire body is one `try/finally: self._finish()`
(`claude_code_stream.py:692-707`) — the `finally` covers not just the per-line dispatch guard
(`except Exception` inside the loop, line 700) but the `for raw_line in self._proc.stdout:` loop
construct itself, so ANY exit from this method — normal EOF, an exception escaping the per-line
guard somehow, or anything else — reaches `_finish()`, which unconditionally ends with
`self._closed_event.set()` (line 786). `_closed_event` is a `threading.Event`, readable from any
thread, checked by every live/future `events()` call on its next `queue.Empty` (at most
`_EVENTS_POLL_S=1.0`s later) — not a single-consumption sentinel (that was the pre-fix design this
module's own docstring at lines 433-439 describes replacing).

Behavioural proof, both existing, unchanged:
* `test_events_called_twice_both_return_after_close_not_just_one` — two `events()` callers, both
  terminate after the child exits (RES-A1, and by extension the "EVERY consumer" half of B2 for the
  clean-exit path).
* `test_finish_never_fabricates_process_exit_when_child_is_still_alive` — reader thread hits raw-fd
  EOF (an unusual exit reason — stdout/stderr closed but the child genuinely still alive) — proves
  `_finish()` still runs and still signals shutdown (bounded `thread.join(timeout=25.0)`), even on
  this non-standard exit path, and does not fabricate a dishonest `process_exit`.

Caveat, stated plainly: RES-A2 (EV-CC-004) shows shutdown signalling reaching every consumer is NOT
the same guarantee as every consumer having received every EVENT — a consumer that lost events to
a race with another concurrent `events()` caller still gets the shutdown signal on time; it just
already lost data before that point. RES-B2 itself (the shutdown-signal guarantee) holds; it is
RES-A2 (fan-out) that does not.

## RES-B3 — no cleanup path contains an unbounded wait (PASS, structural)

`_finish()` (the sole cleanup path, run by the stdout reader thread's `finally`,
`claude_code_stream.py:726-786`) contains exactly three blocking calls, all bounded by
`_EXIT_WAIT_TIMEOUT_S=10.0`:

    739:  self._stderr_thread.join(timeout=_EXIT_WAIT_TIMEOUT_S)
    745:  exit_code = proc.wait(timeout=_EXIT_WAIT_TIMEOUT_S)          # first attempt
    763:  proc.wait(timeout=_EXIT_WAIT_TIMEOUT_S)                       # after proc.kill(), best-effort

The third (line 763) is wrapped in its own `try/except (OSError, subprocess.TimeoutExpired): pass`
— even if the KILL doesn't reap in time, `_finish()` does not block further; it falls through to
`self._closed_event.set()` (line 786) regardless, so a pathological double-timeout still cannot
leave `events()` callers hanging past roughly `2 * _EXIT_WAIT_TIMEOUT_S` (~20s worst case, matching
the module's own comment at line 528-532 of the docstring referencing this exact bound in
`test_shape_drifted_stdout_line_is_surfaced_not_fatal_to_the_reader`'s own commentary on the
pre-fix behaviour). No other method in the module is a "cleanup path" — `_end()` only closes stdin
(non-blocking at the Python level; see RES-A3 for the disclosed residual on the write syscall
itself) and does not wait for the child.

## RES-C1 — the fake's wire behaviour is justified against CAPTURED BYTES, cited by file/section

No captured-bytes artifact existed for this connector before this session (the evidence directory
had `EV-PI-001-raw_capture*.log` for pi but nothing equivalent for claude-code-stream — the
existing fake script's shapes were justified only by prose docstrings claiming empirical
verification, not by a committed raw trace). **New this session**:
`EV-CC-003-stream-json-raw_capture.log` (see `EV-CC-003-int-wire-trace-and-lifecycle.md`) — a real,
committed, timestamped raw wire trace against `claude` 2.1.278, four turns, one interrupt, one
clean close.

Field-by-field justification, fake (`_FAKE_CLAUDE_SCRIPT` in the test file) vs. captured real bytes
(`EV-CC-003-stream-json-raw_capture.log`):

| Shape | Fake emits | Real binary emits (captured, line refs in the raw log) | Match |
|---|---|---|---|
| Turn start signal | `{"type":"system","subtype":"init","session_id":...}` | line 7: `{"type":"system","subtype":"init","cwd":...,"session_id":...,"tools":[...]}` | Same envelope (`type`/`subtype`/`session_id`); fake omits `cwd`/`tools`, both `tool_activity`-mapped fields the connector never reads |
| Generation start | `{"type":"stream_event","event":{"type":"message_start"}}`, then `{"type":"content_block_start"}` | lines 11-12: identical two-event sequence, `message_start` then `content_block_start` | Exact match, same order |
| Text delta | `{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":...}}}` | line 13: byte-identical shape | Exact match |
| Final assistant message | `{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":...}]}}` | line 14: same top-level shape (real adds `model`/`id`/`usage`/etc., all `tool_activity`/ignored fields the connector's `_handle_assistant` only reads `message.content[].text` from) | Match on the fields the connector reads |
| Result (success) | `{"type":"result","subtype":"success","session_id":...,"result":...}` | line 20: same `type`/`subtype`/`session_id`/`result` fields present (plus extra cost/usage fields, unread) | Match on read fields |
| Result (interrupted) | `{"type":"result","subtype":"error_during_execution",...}` | raw log line 50 (run captured for RES-C2 below): `"subtype":"error_during_execution"` present, byte-identical on the field the connector branches on | Match |
| Interrupt request/ack | `{"type":"control_request","request":{"subtype":"interrupt"}}` -> `{"type":"control_response","response":{"subtype":"success",...}}` | see RES-C2 below | Match |
| Malformed-input fatal exit | fake's `die_without_result`/`garbage_line` scenarios: non-zero exit / non-JSON line | `EV-CC-003-malformed-outbound-real.py` real run: non-JSON stdin line -> real CLI exit(1), stderr `"Error parsing streaming input line ... SyntaxError"` | Confirms the FATAL-exit behaviour class the fake's `die_without_result` scenario stands in for (exact stderr text differs; the connector never reads stderr content programmatically, only stores a tail for diagnostics, so this is immaterial to connector logic) |

**One divergence found and disclosed, and it is the Class C pattern itself, not a mere gap**: the
fake NEVER reproduces the real binary's `end()`-immediately-after-`interrupt()` exit(1) behaviour
documented as a new finding under INT-06 (`EV-CC-003-int-wire-trace-and-lifecycle.md`) — the fake's
main loop always falls through to a plain `sys.exit(0)` on EOF regardless of whether the most
recent turn was interrupted. This exact sequence — interrupt, drain to `turn_completed`, `end()`,
drain again, with NO further turn in between — **is already walked** by an EXISTING, currently
PASSING test: `test_interrupt_after_generation_started_is_forwarded_and_marks_interrupted`
(fake-binary) ends with precisely `connector.send(..., verb="end"); list(connector.events())`
directly after the interrupted turn completes, no intervening turn. What is missing is any
assertion on the resulting exit behaviour (`list(connector.events())`'s return value is discarded,
uninspected) — so the fake's exit(0) vs the real binary's exit(1) sits unasserted inside a GREEN
test. This is precisely the Class C pattern EV-REV-002 names ("a mock that contradicts captured
reality... manufactures false confidence... exactly how a green suite ships a hang" — here not a
hang, but a silently-wrong exit code the fake happens to make invisible): the fake's behaviour was
never wrong enough to fail anything, because the one test that walks this exact sequence never
looked. Per the Class C rule ("the FAKE is corrected FIRST... the resulting failures are the proof
the defect was real and hidden"), this fake would need updating to emit `exit(1)` on this sequence
before that existing test could actually catch the divergence — not done here (frozen module task
boundary is the connector, not the test fixture's fidelity, and rule 2 counsels reporting over
fixing); reported here so it is not silently reconciled.

## RES-C2 — fake emits the REAL ordering for the interrupt path (PASS, existing + new real capture)

Fake's `crash_early_interrupt`/`slow_start` scenarios encode: interrupt in the unsafe pre-generation
window -> `control_response:success` THEN `result:error_during_execution` THEN `exit(1)` (fatal);
interrupt in the safe window (after `content_block_start`) -> same ack-then-result order, but the
process and session SURVIVE. Real capture (`EV-CC-003-stream-json-raw_capture.log`, turn 3,
5.1199s-5.1263s): `control_response:success` observed immediately after the `content_block_delta`
already in flight, `result:subtype=error_during_execution` immediately after that, turn 3 marked
complete, turn 4 (an ordinary next turn) runs successfully on the SAME session — matches the fake's
safe-window ordering exactly (ack, then result, then process/session survive).

Existing tests already assert on this ordering against BOTH fake and real:
`test_interrupt_after_generation_started_is_forwarded_and_marks_interrupted` (fake) and
`test_real_claude_interrupt_after_generation_start_survives_and_reprompts_immediately` (real,
re-run this session, PASSED — see EV-CC-003).

## RES-C3 — fakes can FAIL, not only succeed (PASS, existing)

Four distinct failure-capable scenarios already exist in `_FAKE_CLAUDE_SCRIPT`, each exercised by a
dedicated test:
* `die_without_result` — abrupt `exit(2)` with no `result` at all
  (`test_child_death_without_result_surfaces_error_then_ends_cleanly`).
* `garbage_line` — a non-JSON stdout line before the normal sequence
  (`test_unparseable_stdout_line_surfaced_not_dropped_and_does_not_hang`).
* `crash_early_interrupt` — reproduces the real CLI's fatal early-interrupt race
  (`test_interrupt_in_unsafe_window_is_deferred_not_forwarded`,
  `test_steer_in_unsafe_window_is_deferred_and_degrades_to_a_queued_turn`).
* `eof_without_exit` — closes both pipes at the raw-fd level but never actually exits, forcing
  `_finish()`'s own internal backstop
  (`test_finish_never_fabricates_process_exit_when_child_is_still_alive`).

All four are genuine failure injections the connector must survive, not scenarios that only ever
succeed — confirmed by reading each scenario's branch in `_FAKE_CLAUDE_SCRIPT` (test file,
lines 171-310) and its corresponding assertion.

## Commands run this session

    timeout 300 uv run python -m pytest -q tests/test_harness_claude_code_connector.py
    -> 33 passed in 83.59s

    timeout 60 uv run ruff check .
    -> All checks passed!

    timeout 30 python3 EV-CC-003-malformed-outbound-real.py   (RES-C1 real-binary corroboration; see EV-CC-003)
