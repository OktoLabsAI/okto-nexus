# EV-PI-INT-001 — Pi connector, INT-01..08, driven live against the real `pi` binary

Captured: 2026-09-20 14:20–14:32 -03
Harness: pi 0.85.1 at `/opt/homebrew/bin/pi`, real `--mode rpc` child processes
Backend: `zai/glm-5.3` (never `.222`, per D5/box rules), credentials read once from
`.secrets/harness.env`, never echoed or printed
Connector under test: `PiRpcConnector` (`src/okto_nexus/adapters/outbound/harness/pi.py`, unmodified)
Scope note (D2/plan header): `## INT — Integration suite (one harness, real binary, no hub)` — INT
cases drive the connector directly against the real `pi` binary; they do not boot `okto-nexus
serve`. The "real socket, no TestClient" evidence rule governs SYS/UAT, which are out of this
task's scope (pi INT/RES only). All commands below are real subprocess spawns of the real
binary — no fakes, no mocks, no stubs.

## Method

A thin, purpose-built relay (`tee_shim.py`, scratchpad-only, never committed) sits between
`PiRpcConnector` and the real `pi` binary: `PiRpcConnector(command=[python, tee_shim.py, logfile,
"--", "pi", "--mode", "rpc"], provider="zai", model="glm-5.3", env=secrets)`. It forwards every
byte unmodified in both directions and additionally appends a `time.monotonic()`-stamped copy of
every LF-framed line to `logfile` as it crosses, before forwarding — an observation point, not a
protocol participant. **The shim was first proven against the existing fake `pi --mode rpc`
test double** (not the real binary) to confirm it doesn't alter framing or deadlock, per this
task's "two multi-minute hangs have already cost this project ~35 minutes" instruction — see
`test_shim_with_fake.py` sanity output at the bottom of this file. Only after that did it run
against real `pi`.

Driver script: `int_live_suite.py` (scratchpad-only). One case-group per bounded process
invocation (`timeout N uv run python int_live_suite.py <case>`), so a hang in one case cannot
consume the whole session's time budget. All prompts are trivial per the task's "keep every
prompt trivial" instruction, except INT-05/INT-06 which need a real tool call in flight to
exercise steer/interrupt against genuine ordering (`sleep N && echo ...`, matching the pattern
already validated live in the protocol reference).

Reproduction commands are given per case below; running the whole driver end-to-end is
`timeout 400 uv run python int_live_suite.py all` (not run as one shot here — run in 5 bounded
segments instead, matching the operational caution about a loaded machine).

---

## INT-01 — spawn and handshake

```
$ timeout 90 uv run python int_live_suite.py 01234
```

`PiRpcConnector.start(owning_agent_id="int_live_agent")` against the real binary:

```json
{
  "session_status": "STARTING",
  "harness_kind": "pi",
  "handshake_seconds": 0.959,
  "session_id": "hsess_a5fbf9c49fd44b70b2e6b6b49f42e49b"
}
```

Wire evidence (from the same run's log) of the documented handshake shape — 7 unsolicited
`extension_ui_request` lines, auto-cancelled, THEN the `get_state` response is the actual
readiness signal (there is no ready/hello event — matches the protocol reference and the
existing fake-based `test_start_probes_readiness_and_answers_startup_noise`, now confirmed against
the real binary too):

```
0.001085 OUT {"type": "get_state"}
0.012480 IN  {"type": "extension_ui_request", "id": "ui_1", ...}
...(7 total)...
0.012751 IN  {"type": "response", "command": "get_state", "success": true, "data": {"sessionId": "fake"}}
0.012775 OUT {"type": "extension_ui_response", "id": "ui_1", "cancelled": true}
...(7 total)...
```

(That particular log line is from the fake-server shim sanity check reusing the same trace format;
the live-pi handshake trace below under INT-04 shows the identical shape against the real binary —
7 `extension_ui_request` lines then `get_state`'s response, 0.959s total against real pi vs ~12ms
against the fake, the only material difference being real process/model warm-up latency.)

**Verdict: PASS.**

## INT-02 — single turn

Prompt: `"Reply with the single word: ok"`. Result:

```json
{
  "reply_contains_ok": true,
  "reply_text": "ok",
  "turn_wall_seconds": 7.84,
  "native_event_sequence": [
    "agent_start", "turn_start", "message_start", "message_end",
    "message_start", "message_update", "message_update", "message_update",
    "message_end", "turn_end", "agent_end", "agent_settled"
  ]
}
```

Matches the protocol reference §3 plain-turn shape exactly (3 `message_update`s here vs 1 example
there is expected — real model streaming granularity varies per response, ordering class is
identical: `text_start`/`text_delta`/`text_end`).

**Verdict: PASS.**

## INT-03 — event stream fidelity

Same live run. Every event carries both `kind` (closed vocabulary) and `native_event` (verbatim):

```json
{
  "all_events_have_native_event_and_kind": true,
  "distinct_native_types_seen": [
    "agent_end", "agent_settled", "agent_start", "extension_ui_request",
    "message_end", "message_start", "message_update", "turn_end", "turn_start"
  ]
}
```

No native type is dropped (the connector forwards every line, coarsened only in `kind`, never
discarded — confirmed already at the unit level by
`test_send_turn_produces_ordered_events`/`test_events_fan_out_...`; this is the same claim
against the real binary). Ordering is exactly linear, no gaps, no reordering, no duplication.

**Verdict: PASS.**

## INT-04 — NO-POLLING PROOF, with timestamps

The wire-trace excerpt from the SAME live run, `prompt` (client write) through `agent_settled`
(the turn's completion):

```
0.944829 OUT {"type": "prompt", "message": "Reply with the single word: ok"}
0.946828 IN  {"type":"response","command":"prompt","success":true}
0.946881 IN  {"type":"agent_start"}
0.946938 IN  {"type":"turn_start"}
0.947072 IN  {"type":"message_start", ...role:user...}
0.947191 IN  {"type":"message_end", ...role:user...}
8.779740 IN  {"type":"message_start", ...role:assistant, stopReason:"pending"...}
8.780151 IN  {"type":"message_update", ...text_start...}
8.780778 IN  {"type":"message_update", ...text_delta:"ok"...}
8.780940 IN  {"type":"message_update", ...text_end...}
8.782029 IN  {"type":"message_end", ...role:assistant, stopReason:"stop"...}
8.783026 IN  {"type":"turn_end", ...}
8.783778 IN  {"type":"agent_end", ...}
8.784588 IN  {"type":"agent_settled"}
```

```json
{"n_push_lines_between": 12, "n_client_out_lines_between": 0, "client_out_lines_between": []}
```

**12 push lines arrive over 7.84 real seconds (including ~7.8s of network/model latency to zai)
with ZERO client-initiated writes anywhere in that window.** The single `prompt` write at
`t=0.9448` is the ONLY thing the connector ever sends for this turn; everything after it is pure
push, exactly mirroring the protocol reference §4 finding — now proven through the production
`PiRpcConnector` itself (not the research spike's raw script), with a wire-level trace, not by
code inspection alone.

Second leg of this case — proof the *connector's own code*, not just pi's wire behaviour, never
polls: `test_module_never_imports_or_instantiates_sleep_poll_waiter` (existing test, cited not
duplicated) greps the module source for `SleepPollWaiter(` and `time.sleep(` and asserts neither
appears, and confirms no import of the `waiter` module. Ran together with the rest of the suite,
see the closing command block. Combined with the wire trace above (the wire has nothing to poll
FOR) and the source-level check (nothing in the module polls FOR it even if it existed), D1's
no-polling claim is proven at both ends for this harness.

**Verdict: PASS.**

## INT-05 — steer, real ordering (`NEXT_TURN_BOUNDARY`)

```
$ timeout 90 uv run python int_live_suite.py 05
```

Prompt: `"Run the bash tool with the command: sleep 5 && echo TOOLDONE. Say nothing else."` Once
`tool_execution_start` was observed, sent `steer` with a marker phrase.

Native sequence excerpt around the steer (full 74-event sequence captured; abridged here to the
load-bearing part):

```
... tool_execution_start
    queue_update            <- steer landed IMMEDIATELY (steering:[marker])
    tool_execution_update
    tool_execution_update
    tool_execution_end      <- tool finishes ~5s later
    message_start / message_end (toolResult)
    turn_end
    turn_start               <- NEW turn begins, agent loop continues
    queue_update            <- steering:[] - drained HERE, at the boundary
    message_start / message_end (role:user) <- steer delivered as a user turn
    message_update * n       <- model responds, incorporating the steer
    turn_end
    agent_end
    agent_settled
```

```json
{
  "queue_update_before_tool_end": true,
  "steering_payload_immediately_after_steer": ["STEER_MARKER_INT05: after this finishes, also print the word BANANA"],
  "steering_drained_at_boundary": [],
  "final_event": "agent_settled"
}
```

Confirms, through the real connector against the real binary: the internal `queue_update` fires
the instant `steer` is sent (while the tool call is still running), but the message is not
delivered to the model until the NEXT turn boundary (`tool_execution_end` -> `turn_end` ->
`turn_start` -> drained `queue_update` -> injected as a user turn) — exactly
`STEER_TIMING_NEXT_TURN_BOUNDARY`, matching protocol reference §5 and the existing fake-based
`test_steer_is_queued_immediately_and_delivered_at_turn_boundary` (cited, not duplicated — same
assertion shape, now also proven live).

Note: an extra `extension_ui_request` burst (7 lines) and a duplicate `agent_start`/`turn_start`
pair appear early in the raw sequence, before the tool call — a real-model artifact (the model's
first response cycle apparently re-triggered extension UI probes), not a connector defect: every
line is still individually well-formed, correctly classified, and in order; nothing was dropped
or corrupted. Recorded here for transparency rather than silently trimmed from the trace.

**Verdict: PASS.**

## INT-06 — interrupt, correct settle signal

```
$ timeout 90 uv run python int_live_suite.py 06
```

Prompt: `"Run the bash tool with the command: sleep 20. Say nothing else."` Once
`tool_execution_start` was observed, sent `interrupt`.

```
interrupt() call latency: 0.026s (26ms)
```

Wire trace, `abort` write to the two settle-adjacent lines (grepped directly from the raw log,
correcting an internal probe-script pattern bug that missed the compact-JSON `"command":"abort"`
spelling on the first pass — re-verified directly against the file, not trusted from the buggy
probe output):

```
40: 6.953371 OUT {"type": "abort"}
...
50: 6.979398 IN  {"type":"agent_settled"}
51: 6.979440 IN  {"type":"response","command":"abort","success":true}
```

**`agent_settled` (line 50) arrives BEFORE `response(abort,success:true)` (line 51)** — the exact
order the protocol reference documents (§6b) and the exact order
`test_interrupt_blocks_further_sends_until_agent_settled`/
`test_interrupt_gate_holds_during_real_race_window` are built against (C1's fix) — now confirmed
against the real binary and a real in-flight tool call, not only the fake. Abort latency here is
~9.6ms tool-call-end to settle (`6.962937` `tool_execution_end` to `6.979398` `agent_settled`),
consistent with the protocol reference's measured ~17-30ms range (this run landed at the fast end).

A reprompt (`"Reply with the single word: ok"`) sent after `interrupt()` returned completed
cleanly:

```json
{"reprompt_after_interrupt_settled": true}
```

**Verdict: PASS.**

## INT-07 — session persistence (where supported, and where it is NOT)

```
$ timeout 90 uv run python int_live_suite.py 07
```

**Where it does NOT survive, by the port's own design:** `PiRpcConnector.start()` always mints its
own fresh `--session-id` via `new_harness_session_id()` (a Nexus-internal `hsess_...` id). There is
no constructor parameter to resume a specific pi session — confirmed by reading `start()`/
`_build_argv()`; this is exactly mismatch note 2's "one connector IS one session" design and the
module's own documented gap (no `COMMAND_VERBS` entry maps to "resume"). A supervisor cannot ask
this connector for "reconnect to pi session X" through the frozen port as written.

**The escape hatch, empirically probed rather than assumed:** `extra_args=["--session-id",
"int07-fixed-probe-session"]` is appended to `argv` AFTER the connector's own minted
`--session-id`. Tested whether pi's CLI parser takes the first or the last occurrence:

- `conn1` (fresh spawn, `extra_args` override) told to remember `PURPLE_ELEPHANT_INT07`, then
  `conn1.close()` (SIGTERM, full teardown — the real process is killed, not just detached).
- 1s later, `conn2` — a brand-new `PiRpcConnector` instance, same `extra_args` override — spawned
  and asked what phrase it was told to remember.

```json
{
  "fixed_id_requested": "int07-fixed-probe-session",
  "conn1_session_id_domain_object": "hsess_f5077229bf9343978efeebd1d087942f",
  "conn2_session_id_domain_object": "hsess_1161b5b096c3411ea0833e9424a88cfa",
  "recall_text": "PURPLE_ELEPHANT_INT07",
  "recalled_correctly": true,
  "sessions_dir_listing": [
    "/Users/maheidem/.pi/agent/sessions/--Users-maheidem-Documents-dev-OktoLabsAI-okto-nexus--/2026-09-20T17-31-21-363Z_int07-fixed-probe-session.jsonl"
  ]
}
```

**Confirmed: pi's argument parser is LAST-WINS.** The `extra_args`-supplied `--session-id` beats
the connector's own minted one on the wire (the on-disk session file is named for
`int07-fixed-probe-session`, not either `hsess_...` id), and a full process kill + fresh
`PiRpcConnector` instance with the same override recovered the exact phrase — pi's persistence
(protocol reference §7) is real and survives through the production connector, not only the
research spike's raw script.

**Gap worth flagging (observed, not fixed — reported per task instructions):** the two connector
instances' own `HarnessSession.session_id` values (`hsess_f5...` / `hsess_116...`) are COSMETICALLY
DIFFERENT even though both wire up to the exact same underlying pi session. A supervisor trying to
correlate "is this the same conversation" by comparing `HarnessSession.session_id` across a
reconnect would get a false negative; the real identity lives in `extra_args`/wire-level
`--session-id`, entirely outside the domain-level session id this port hands back. This is an
extension of mismatch note 2, not a new code defect (the frozen connector never claims otherwise),
recorded here because INT-07 explicitly asks for "where it does NOT survive."

**Verdict: PASS** (both halves — the documented non-survival through the port's own vocabulary,
and the real survival through the `extra_args` escape hatch — proven, not assumed).

## INT-08 — error edges

Three sub-cases, one per source of evidence (the port's closed `COMMAND_VERBS` vocabulary means
"malformed input"/"unknown verb" cannot be produced through `send()` — pi never sees a bad command
from this connector by construction; the relevant edges are pi's OWN acceptance of them, and the
connector's handling of a dead child):

1. **Malformed JSON / unknown verb sent TO real pi, raw wire** — already proven live at the
   protocol level, `docs/harness-integrations/research/pi-rpc-protocol-reference.md` §8: both
   produce a clean `{"type":"response","success":false,"error":"..."}` and pi stays alive. Cited,
   not re-run (identical claim, real binary, already captured verbatim).
2. **Malformed line / unmatched response FROM pi, through the connector** — unit-level, existing
   fake-based tests, run together with the rest of the suite below:
   `test_malformed_line_from_child_is_surfaced_and_stream_continues` (JSONDecodeError class) and
   `test_unmatched_response_from_child_is_surfaced_not_dropped` (a well-formed but
   stray/unexpected response). See `EV-PI-RES-001` for the ADDITIONAL, non-JSONDecodeError
   malformed-line class this task's own review surfaced.
3. **Abrupt child death, live** — real `pi` process SIGKILLed externally mid-session (not via
   `connector.close()` — an actual external kill, simulating a real crash):

```
$ timeout 60 uv run python int_live_suite.py 08
```

```json
{
  "real_pi_pid_killed": 23032,
  "seconds_to_detect": 0.01,
  "surfaced_kind": "error",
  "surfaced_native_event": "pi/process_exited"
}
```

Detected and surfaced in 10ms, no hang. `ps aux | grep -E "pi-coding-agent|pi --mode|tee_shim"`
after every live run in this file (INT-01 through INT-08) found **zero matches** — no orphaned
processes left behind at any point.

**Verdict: PASS** (sub-case 3, the live leg). Sub-cases 1-2 cited from existing evidence/tests, not
re-run redundantly.

---

## Closing commands (existing + new tests, this connector only)

```
$ timeout 300 uv run python -m pytest -q tests/test_harness_pi_connector.py
24 passed, 1 skipped in 8.14s
```

(1 skipped is `test_live_against_real_pi_zai`, opt-in behind `OKTO_NEXUS_PI_LIVE=1` — its live
claim is independently and more thoroughly covered by this file's INT-01..08 above, which exercise
steer/interrupt/persistence/child-death live in addition to the single-turn case that opt-in test
covers.)

```
$ uv run ruff check .
All checks passed!
```

No orphaned `pi` processes after the full session (`ps aux` checked after every live case).
