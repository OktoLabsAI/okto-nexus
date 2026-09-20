# EV-CC-003 — INT-01..08, Claude Code stream-json connector (D7a)

Captured: 2026-09-20, this session (claude 2.1.278 on PATH, real binary throughout).
Module under test: `src/okto_nexus/adapters/outbound/harness/claude_code_stream.py` (FROZEN —
read-only for this task; no lines changed).
Test file: `tests/test_harness_claude_code_connector.py` (2 new tests added, see EV-CC-004/005 for
why; existing tests otherwise untouched).

## Scope note: INT does not require `real_server`

The plan (`plans/harness-integrations/01-test-plan.md`) headers the INT suite explicitly: **"one
harness, real binary, no hub"** / "Each connector against its real harness, in isolation." The
`real_server` fixture (`tests/conftest.py`) boots the HTTP hub and is the evidence vehicle for the
SYS suite (see `EV-SYS-001`), not INT. Every case below therefore drives
`ClaudeCodeStreamConnector` directly against the real `claude` binary — a real subprocess, real
pipes, no `okto-nexus serve` process, no TestClient, no mock — which satisfies the evidence rule's
"real ... binaries" bar without a hub in the loop.

## INT-01 — spawn and handshake

Real binary, connector-level, from the isolated pytest run below (`test_real_claude_single_trivial_turn`)
and the raw capture's first line:

    $ timeout 200 uv run python -m pytest -q -v tests/test_harness_claude_code_connector.py::test_real_claude_single_trivial_turn
    tests/test_harness_claude_code_connector.py::test_real_claude_single_trivial_turn PASSED
    1 passed in ...

Raw wire trace (`EV-CC-003-stream-json-raw_capture.log`, line 1-7):

    [  0.0000s] SPAWN claude -p --output-format stream-json --input-format stream-json --verbose --include-partial-messages
    [  0.0012s] WRITE {"type": "user", "message": {"role": "user", "content": "reply with the single word: ok"}}
    [  0.6111s] READ {"type":"system","subtype":"hook_started", ...}
    [  0.6690s] READ {"type":"system","subtype":"init","cwd":"...","session_id":"1aeeb6be-...", "tools":[...]}

`system`/`init` (mapped by the connector to `turn_started`) is the handshake/ready signal; it
arrives 0.669s after spawn, well inside `ClaudeCodeStreamConnector.start()`'s synchronous return
(the connector's `start()` never blocks for this — it returns `STARTING` immediately and the
reader threads observe `init` asynchronously, per `capabilities.observes_session_end=True`'s
design). Confirmed via the connector itself: `HarnessSession.status == "STARTING"` right after
`start()` returns (`test_start_returns_starting_session_with_minted_id`, existing, cited not
duplicated).

## INT-02 — single turn

`test_real_claude_single_trivial_turn` (existing, run above): sends `"reply with the single word:
ok"`, drains to `turn_completed`, asserts `payload["subtype"] == "success"` and `"ok" in
payload["result"].lower()`. PASSED against the real binary this session.

Raw capture corroborates end to end (turn 1, `EV-CC-003-stream-json-raw_capture.log` lines 1-21):
one `user` write, 18 native events read (verified by re-counting programmatically, see the
`awk` command under INT-04; `system:hook_started`×2, `system:hook_response`×2, `system:init`,
`system:informational`×3, `system:status`, `stream_event`×7 sub-kinds, `rate_limit_event`,
`assistant`, `result`), turn completes at 2.4466s.

## INT-03 — event stream fidelity (no ordering loss; unmapped events surfaced)

Native event types observed in the raw capture and how `_handle_stdout_line`
(`claude_code_stream.py:788-820`) maps each one — every one is accounted for, none silently
dropped, matching the module's "Event-vocabulary port gap" note (everything without a dedicated
`EVENT_KINDS` member becomes `tool_activity` with the real name preserved in `native_event`):

| Native `type`/`subtype` seen on the wire | Mapped `HarnessEvent.kind` | `native_event` |
|---|---|---|
| `system`/`hook_started`, `hook_response`, `informational`, `status` | `tool_activity` | `system:<subtype>` |
| `system`/`init` | `turn_started` | `system:init` |
| `stream_event`/`message_start`, `content_block_start` | `tool_activity` | `stream_event:<type>` |
| `stream_event`/`content_block_delta` (text_delta) | `output_delta` | `stream_event:content_block_delta` |
| `stream_event`/`content_block_stop`, `message_delta`, `message_stop` | `tool_activity` | `stream_event:<type>` |
| `assistant` | `output_delta` | `assistant` |
| `rate_limit_event` | `tool_activity` | `rate_limit_event` |
| `control_response` | `tool_activity` | `control_response:<subtype>` |
| `user` (post-interrupt synthetic echo) | `tool_activity` | `user_echo` |
| `result` | `turn_completed` or `error` | `result:<subtype>` |

No native event type appears in the raw capture with no row above — confirmed by reading the raw
log's every distinct `"type"`/`"subtype"` pair against `_handle_stdout_line`'s branches
(`claude_code_stream.py:798-820`) and the `else` branch (`tool_activity`, `f"unknown:{native_type}"`)
which exists precisely so a FUTURE unmapped type is still surfaced, never dropped (D2/INT-03).
Ordering is preserved because there is exactly one reader thread (`_pump_stdout`) processing
`self._proc.stdout` strictly in the order the child writes it, and one `queue.Queue` receiving
`_emit()` calls in that same call order — no reordering point exists in the module.

Fake-binary corroboration (existing, cited not duplicated): `test_single_turn_maps_turn_started_then_turn_completed`
asserts `kinds[0] == "turn_started"` and `kinds[-1] == "turn_completed"`;
`test_shape_drifted_stdout_line_is_surfaced_not_fatal_to_the_reader` proves an unrecognised
*internal* shape is surfaced as `error`/`stdout_dispatch_error`, never dropped.

## INT-04 — NO-POLLING PROOF

Full timestamped wire trace, `WRITE`/`MARK` lines only (from `EV-CC-003-stream-json-raw_capture.log`,
captured with `time.monotonic()` at each I/O event, script `EV-CC-003-raw_capture_script.py`,
command: `timeout 180 uv run python EV-CC-003-raw_capture_script.py`):

    [  0.0012s] WRITE turn1 prompt ("reply with the single word: ok")
    [  0.6111s..2.4466s] READ × 18 (system/stream_event/assistant/rate_limit/result)  <- ZERO writes in this window
    [  2.4466s] MARK turn1 complete
    [  2.4466s] WRITE turn2 prompt ("reply with the single word: still-alive")
    [  2.4744s..4.1608s] READ × 13                                                    <- ZERO writes in this window
    [  4.1609s] MARK turn2 complete
    [  4.1609s] WRITE turn3 prompt ("Write the numbers 1 to 40 ...")
    [  4.1871s..5.1199s] READ × 6 (system:status, stream_event:message_start observed last)
    [  5.1199s] WRITE control_request/interrupt   <- the ONE deliberate, client-initiated command
                                                       this trace issues mid-turn (not a poll: it
                                                       is the interrupt() verb under test, sent
                                                       exactly once, synchronously acked)
    [  5.1199s..5.1263s] READ × 6 (content_block_start/delta, control_response, assistant, user_echo, result)
    [  5.1263s] MARK turn3 (interrupted) complete
    [  5.1264s] WRITE turn4 prompt ("reply with the single word: revived")
    [  5.1519s..6.9606s] READ × 13                                                    <- ZERO writes in this window
    [  6.9606s] MARK turn4 complete
    [  6.9606s] WRITE <close stdin>
    [  7.4043s] MARK process exit_code=0

Read counts above generated programmatically, not hand-counted:

    $ awk '/WRITE|MARK/{if(n)print prev": "n; n=0; prev=$0; next} /READ/{n++} END{if(n)print prev": "n}' \
        EV-CC-003-stream-json-raw_capture.log
    ...: 18   (turn 1)
    ...: 13   (turn 2)
    ...: 6    (turn 3, before the interrupt write)
    ...: 6    (turn 3, after the interrupt write, through its result)
    ...: 13   (turn 4)

Every inbound event during an idle wait window has **zero** client-initiated requests between it
and the write that started the turn — the only writes on the whole trace are the four turn prompts
and the one deliberate interrupt, each logged with its own timestamp immediately adjacent to the
read that triggered it (the prompt) or the read it was deliberately racing (the interrupt, sent the
instant `content_block_start`/`message_start` was observed, not on a timer). This is the write-side
half of the proof; the read-side half (a genuinely blocking `Queue.get()`, not a sleep-poll) is
independently proven by `test_events_iterator_delivers_promptly_not_on_a_poll_interval` (existing,
cited not duplicated), which uses a **discriminating control** (`_SleepPollEventsConnector`, a
deliberately poll-based `events()`) to prove its `<0.2s` delivery bound actually distinguishes
push from poll, not just asserts a number.

Structural corroboration: `grep -n "\.get(\|\.acquire(\|\.join(\|\.wait(\|\.recv(\|\.connect(\|select\.\|proc\.wait"
src/okto_nexus/adapters/outbound/harness/claude_code_stream.py` finds exactly one blocking-queue
wait (`self._events.get(timeout=_EVENTS_POLL_S)`, line 443) and no `time.sleep()` anywhere outside
comments/docstrings (confirmed separately in EV-CC-004).

## INT-05 — steer, real ordering semantics

`test_real_claude_steer_interrupts_in_flight_turn_and_runs_new_one_immediately` (existing, run in
isolation this session):

    $ timeout 200 uv run python -m pytest -q -v tests/test_harness_claude_code_connector.py::test_real_claude_steer_interrupts_in_flight_turn_and_runs_new_one_immediately
    PASSED

Documented real ordering (module docstring, `claude_code_stream.py:76-91`, verified by this test):
`steer` is implemented as interrupt-then-resend. Sent once the head turn is observed generating, it
lands a real `control_request`/`interrupt` in well under 20ms, the interrupted turn resolves
`result:error_during_execution` immediately after, and the new content runs as the very next turn
on the SAME process/session with no settle delay — genuine `IMMEDIATE`, not
`NEXT_TURN_BOUNDARY`-only-in-disguise. The one documented exception (steer issued in the
sub-second "requesting" window before generation starts, where a real interrupt would be fatal to
the process) degrades to a queued next turn instead — covered by the existing fake-binary test
`test_steer_in_unsafe_window_is_deferred_and_degrades_to_a_queued_turn`.

## INT-06 — interrupt, correct settle signal

`test_real_claude_interrupt_after_generation_start_survives_and_reprompts_immediately` (existing,
run in isolation this session): PASSED. Confirms `interrupt_requires_settle_wait=False` for real —
a reprompt sent immediately after a safe-window interrupt (no artificial delay) is honoured
correctly, unlike Pi's abort/settle ordering.

Raw-capture corroboration (turn 3 above): `control_request`/`interrupt` written at 5.1199s,
`control_response:success` read at (line 47 of the raw log, same timestamp bucket), `result`
(`subtype:error_during_execution`) immediately after, turn 3 marked complete at 5.1263s — a ~6ms
round trip, no settle wait needed before turn 4's prompt is written at 5.1264s.

**New finding, minor (not a hang/crash — an honest-error-surfacing gap in the module's own claim)**:
calling `end()` **immediately** after `interrupt()`, with **no further turn** sent in between (a
gap neither the fake-binary nor the real-binary test suite covered before this session — every
existing interrupt test sends a follow-up turn, or ends only from an otherwise-idle connector),
produces a real, 3-for-3 reproducible non-zero exit:

    $ timeout 60 uv run python EV-CC-003-interrupt-then-end-real.py   # (script embedded below)
    EVT turn_completed result:error_during_execution
    EVT error process_exit {'exit_code': 1, 'stderr_tail': []}
    total remaining events: 7
    has process_exit error: True

Reproduced identically on 3/3 runs against the real binary this session (machine-loaded rule).
This contradicts the module docstring's blanket claim (`claude_code_stream.py:69-74`): "Closing
stdin drains any in-flight turn and then the process exits(0) cleanly ... this connector never
synthesises an 'ended' HarnessEvent." In this one narrow state — `end()` called while the most
recent turn's outcome was an interrupt, with no intervening ordinary turn — the real binary exits
1, and `_finish()` (correctly, per its own honesty design) reports it as `error`/`process_exit`
rather than a silent clean end. **This is not a hang, crash, or dropped event** — the connector
still terminates `events()` promptly and reports truthfully — but a supervisor issuing `end()`
right after `interrupt()` (a very plausible real usage: "abort and close this session") will see a
spurious error event on an intentional close. Verified this is specific to the
interrupt-then-immediate-end sequence, not a general post-interrupt state: turn 4 in the main raw
capture (an ORDINARY turn sent after the same interrupt, then `end()`) exits 0 cleanly (see the
`INT-04` trace above, exit_code=0). Reported per the task's rule 2 (frozen module; not fixed here).

Script used (`EV-CC-003-interrupt-then-end-real.py`, committed alongside this file):

```python
connector = ClaudeCodeStreamConnector()
session = connector.start(owning_agent_id="agent_test")
connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn",
    payload={"content": "Write the numbers 1 to 40, one per line, nothing else. Do not stop early."}))
it = connector.events()
for event in it:
    if event.native_event in ("stream_event:message_start", "stream_event:content_block_start"):
        break
connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))
connector.send(session, HarnessCommand(session_id=session.session_id, verb="end"))  # no turn in between
remaining = list(it)
```

## INT-07 — session persistence

**Positive half (verified, real binary)**: one process holds a stable `session_id` across MANY
turns. Raw capture: `session_id` is `1aeeb6be-01bd-43f8-8e8c-fbf452b3500a` on turn 1's `system:init`
and identical on turn 2's, 3's and 4's `system:init` (all four turns, same process). Also
`test_real_claude_two_turns_share_session_and_process_survives` (existing, PASSED in isolation this
session).

**Negative half, stated plainly (not a wish)**: this connector does **NOT** survive a process
restart. `claude --help` documents a `--resume <session-id>`/`-r`/`--session-id <uuid>` flag family
at the CLI level, but `ClaudeCodeStreamConnector._DEFAULT_ARGV` (`claude_code_stream.py:164-172`)
never passes any of them, and nothing in `start()` accepts or threads through a prior
`session_id` — `start()` always spawns a brand-new process with no resume argument. A
`ClaudeCodeStreamConnector` instance is `multiplexes_sessions=False`, one child for its whole
lifetime (`capabilities` docstring); if the child dies or `serve` restarts, there is no code path
in this connector back to the same `session_id`, unlike Codex's `thread/resume` (also documented as
NOT surviving process death, D4) or Pi's `--session-id` re-attach. This is a genuine capability gap
of this specific connector (not exercised because nothing in the frozen module attempts it), stated
here rather than left implicit.

## INT-08 — error edges

**Malformed input** (inbound, from the harness): existing fake-binary tests
`test_unparseable_stdout_line_surfaced_not_dropped_and_does_not_hang` (non-JSON line) and
`test_shape_drifted_stdout_line_is_surfaced_not_fatal_to_the_reader` (syntactically-valid,
internally shape-drifted JSON) — both PASS, both prove the reader loop survives and the turn's real
result is not lost. Cited, not duplicated.

**Malformed input** (outbound, what the real CLI does if ever written — the connector's own
`_require_content` prevents this path from ever being reached in practice, so this is a real-binary
probe of the documented hazard the module docstring calls out, not a connector-level test):

    $ timeout 30 python3 EV-CC-003-malformed-outbound-real.py
    exit_code: 1
    stderr: 'Error parsing streaming input line (type=unknown, 21 chars): SyntaxError\n'

Confirms the module docstring's claim verbatim (`claude_code_stream.py:58-66`): a non-JSON stdin
line makes the real CLI exit(1) immediately with a stderr diagnostic — exactly why `_send_turn`
validates `payload["content"]` before ever writing.

**Unknown command verb**: two NEW tests added this session (no prior test in this file exercised
this edge):
`test_unknown_verb_rejected_at_domain_layer_before_reaching_connector` (the PRIMARY gate —
`HarnessCommand.__post_init__`, frozen `domain/harness.py`, rejects an unknown verb before a
command object can even be constructed) and
`test_unknown_verb_backstop_at_connector_layer_if_domain_gate_is_bypassed` (the connector's OWN
backstop check at `claude_code_stream.py:399-404`, reached via a forged `HarnessCommand` built with
`object.__new__`/`object.__setattr__` to bypass the frozen dataclass's own validation — proving the
connector does not blindly trust the domain gate either). Both PASS:

    $ timeout 300 uv run python -m pytest -q tests/test_harness_claude_code_connector.py
    33 passed in 83.59s

**Abrupt child death**: existing fake-binary tests
`test_child_death_without_result_surfaces_error_then_ends_cleanly` (`exit(2)` mid-turn, no result
at all) and `test_finish_never_fabricates_process_exit_when_child_is_still_alive` (stdout/stderr
EOF while the child is genuinely still alive — proves `_finish()` never fabricates an end signal it
didn't observe, and actually kills the leaked child). Both PASS. Cited, not duplicated.

None of the above hangs: every test in this file that could hang uses a bounded
`thread.join(timeout=...)` pattern (see EV-CC-004 for the two cases, RES-A2/RES-A4, where that
bound was needed to catch a real hang rather than assume one away).

## Commands run this session (all bounded)

    timeout 200 uv run python -m pytest -q -v tests/test_harness_claude_code_connector.py::test_real_claude_single_trivial_turn tests/test_harness_claude_code_connector.py::test_real_claude_steer_interrupts_in_flight_turn_and_runs_new_one_immediately tests/test_harness_claude_code_connector.py::test_real_claude_interrupt_after_generation_start_survives_and_reprompts_immediately tests/test_harness_claude_code_connector.py::test_real_claude_two_turns_share_session_and_process_survives tests/test_harness_claude_code_connector.py::test_real_claude_end_verb_drains_and_exits_cleanly tests/test_harness_claude_code_connector.py::test_real_claude_interrupt_targets_head_turn_with_two_outstanding
    -> 6 passed in 24.65s

    timeout 300 uv run python -m pytest -q tests/test_harness_claude_code_connector.py
    -> 33 passed in 83.59s  (31 pre-existing + 2 new INT-08 tests)

    timeout 60 uv run ruff check .
    -> All checks passed!

    timeout 180 uv run python EV-CC-003-raw_capture_script.py   # -> EV-CC-003-stream-json-raw_capture.log
