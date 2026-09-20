# EV-CX-001 — Codex (H-CX) INT cases: raw wire captures + connector proof

Captured: 2026-09-20. Backend: LAN box `http://192.168.31.152:8123/v1`, model `qwen3.8-flash`,
`wire_api=responses` (ADR 0004 D5). `codex-cli 0.144.6` (`/opt/homebrew/bin/codex`).
`192.168.31.222` was never touched. `CODEX_HOME` was a fresh temp dir per capture, never
`~/.codex/config.toml`.

Two evidence tiers, both real (no mocks/TestClient):

1. **Raw wire captures** — a standalone stdlib script drives the real `codex app-server` binary
   directly over stdio (bypassing `CodexAppServerConnector` entirely) and logs every line with a
   `time.monotonic()` offset and a `>>`/`<<` direction tag. This is what proves the *protocol*
   facts (ordering, timing, error shapes) independent of this repo's own connector code.
   Capture script: `capture.py` (not committed — scratchpad-only per the task's evidence-file
   convention; the captured *output* below is the artifact).
2. **The connector itself**, run live against the same backend:
   `OKTO_NEXUS_CODEX_LIVE=1 timeout 180 uv run python -m pytest -q
   tests/test_harness_codex_connector.py::test_live_against_real_codex_lan_box` → **1 passed in
   10.10s**. This is the only piece of evidence that exercises `CodexAppServerConnector` (not just
   the raw protocol) against the real binary.

Raw captures committed alongside this file:
- `EV-CX-001-raw_capture_turn.jsonl` — initialize → thread/start → turn/start → turn/completed
- `EV-CX-001-raw_capture_interrupt.jsonl` — same, but fires `turn/interrupt` mid-turn
- `EV-CX-001-raw_capture_thread_not_found.jsonl` — a thread started under one process, then a
  **fresh** `app-server` process started against the SAME `CODEX_HOME`/thread id

## INT-01 — spawn and handshake

`capture_turn.jsonl` lines 1–2 (`t=0.0023` → `t=0.0825`): `>> initialize` answered `<< {"id":1,
"result":{...}}` in 80ms. Ready state reached.

Also proven through the actual connector, not just the raw wire: `test_live_against_real_codex_lan_box`
calls `CodexAppServerConnector().start(...)`, which performs the identical `initialize` →
`thread/start` handshake internally — **1 passed**, cited above.

## INT-02 — single turn

`capture_turn.jsonl`: `>> turn/start` (`id:3`) at `t=1.1219`, trivial prompt `"reply with the
single word: ok"`. Completed response: `<< item/agentMessage/delta {"delta":"ok"}` at `t=46.115`,
`<< turn/completed` at `t=46.8318`. The connector-level equivalent (`test_live_against_real_codex_
lan_box`) asserts `"pong" in deltas.lower()` for the prompt `"Reply with exactly the single word:
pong"` — **passed**.

Note on latency: the ~45s gap between the turn starting and the model's first token is backend
inference time on a LAN box shared by several concurrently running agents this session (task's own
"MACHINE IS LOADED" note), not a defect — the direct HTTP check below shows the backend itself
answers in 2.6s when uncontended:

    curl -s -X POST http://192.168.31.152:8123/v1/responses ... -> HTTP:200 TIME:2.587414

## INT-03 — event stream fidelity (no ordering loss, unmapped events surfaced)

`capture_turn.jsonl` (34 lines total) shows the full native sequence in strict arrival order, with
NO gaps or reordering: `initialize` → `thread/started` → 3× `mcpServer/startupStatus/updated` →
`turn/started` → `warning` → `thread/status/changed` → more `mcpServer/startupStatus/updated` →
`hook/started`/`hook/completed` (a codex CLI plugin hook, unrelated to Nexus) → `item/started`/
`item/completed` (echoing the user message) → [45s of real inference] → `item/started` →
`item/reasoning/summaryPartAdded` → `item/reasoning/summaryTextDelta` → `item/completed` →
`item/started` → `item/agentMessage/delta` → `item/completed` → `thread/tokenUsage/updated` →
`account/rateLimits/updated` → `hook/started`/`hook/completed` → `thread/status/changed` →
`turn/completed`.

Several of these native methods (`mcpServer/startupStatus/updated`, `hook/started`,
`hook/completed`, `warning`, `thread/status/changed`, `thread/tokenUsage/updated`,
`account/rateLimits/updated`, `item/reasoning/*`) are NOT in `_EVENT_KIND_BY_METHOD`
(`adapters/outbound/harness/codex.py` lines 119–141) and fall to `_DEFAULT_EVENT_KIND =
"tool_activity"` — coarsened, never dropped: `native_event` still carries the real method string
verbatim (module mismatch note 3, already disclosed in the module's own docstring). Confirmed
structurally: every method name observed in this real capture has an entry, or falls into the
documented default bucket, in `_EVENT_KIND_BY_METHOD`/`_DEFAULT_EVENT_KIND` — none is silently
discarded before reaching `HarnessEvent.native_event`.

## INT-04 — NO-POLLING PROOF (the DoD's core claim)

Directly from `capture_turn.jsonl`, with real timestamps. Between the client's `>> turn/start`
(`id:3`, `t=1.1219`) and the server's `<< turn/completed` (`t=46.8318`) — a **45.71-second** window
— the full list of CLIENT-INITIATED (`>>`) lines is:

    (none)

Every one of the 27 lines in that window is server-pushed (`<<`). Machine-checked, not
eyeballed:

    $ python3 -c "
    import json
    lines = [json.loads(l) for l in open('EV-CX-001-raw_capture_turn.jsonl')]
    start = next(l['t'] for l in lines if l['dir']=='>>' and l['msg'].get('method')=='turn/start')
    end   = next(l['t'] for l in lines if l['msg'].get('method')=='turn/completed')
    between = [l for l in lines if start < l['t'] <= end]
    outbound = [l for l in between if l['dir']=='>>']
    print('window_s=', round(end-start,3), 'total_lines=', len(between), 'client_initiated=', len(outbound))
    "
    window_s= 45.71 total_lines= 27 client_initiated= 0

`client_initiated=0` is the proof: zero requests were sent by the client while waiting for the
turn to complete. All 27 events arrived by push. This is a raw-wire fact, independent of this
repo's connector code.

## INT-05 — steer, real ordering semantics

Not captured live in this pass (budget was spent on the interrupt/thread-not-found captures below,
judged higher-value per the task's defect-class priorities). D6's documented steer timing for codex
is `STEER_TIMING_IMMEDIATE` (unlike Pi's `NEXT_TURN_BOUNDARY`) — `capabilities.steer_timing ==
STEER_TIMING_IMMEDIATE` is asserted by the EXISTING `test_capabilities_match_adr_d6` (cited, not
new). The connector's own steer wire-shape (`turn/steer` with `expectedTurnId` + `threadId`) is
exercised against a protocol-faithful fake by the EXISTING
`test_steer_and_interrupt_use_the_tracked_turn_id`:

    $ timeout 60 uv run python -m pytest -q tests/test_harness_codex_connector.py::test_steer_and_interrupt_use_the_tracked_turn_id
    1 passed

**Gap, disclosed rather than hidden:** whether codex's real `app-server` accepts a `turn/steer`
immediately (no settle wait) the way `interrupt_requires_settle_wait=False` implies was NOT
verified against the live binary in this pass — matching the module's own mismatch note 6, which
flags this as unverified. A real steer capture (mirroring `capture_interrupt` below) would close
this gap; not done here due to time budget.

## INT-06 — interrupt, correct settle signal

`EV-CX-001-raw_capture_interrupt.jsonl`: a long-running prompt ("count slowly from 1 to 200...")
was started, `turn/started` observed at `t=1.1341`, then `>> turn/interrupt` sent at `t=1.6373`
(0.5s after the turn started, before any model output — the backend's ~45s inference latency,
demonstrated above, meant no content had streamed yet). Real response, in arrival order:

    +0.1061s << {"id": 4, "result": {}}
    +0.1061s << {"method": "thread/status/changed"}
    +0.1061s << {"method": "turn/completed", "turn": {"status": "interrupted"}}

The `turn/interrupt` RPC result and `turn/completed` (with `status: "interrupted"`) arrive at the
SAME wire timestamp, 106ms after the interrupt was sent, with no separate/later settle
notification. This matches `interrupt_requires_settle_wait=False` (D6, `capabilities.py`): unlike
Pi (which delivers `agent_settled` as a distinct signal the caller must wait for separately before
it is safe to send again — EV-REV-003), codex's own ack IS effectively the settle signal.

**Caveat, disclosed:** this capture interrupted BEFORE any content had streamed (backend latency
meant no `item/agentMessage/delta` had arrived yet), not a genuine mid-stream cancel. A
mid-content-stream interrupt capture (waiting ~45s for the first delta, then interrupting) was not
run in this pass — the backend's real inference latency made that prohibitively slow to repeat
safely within the task's command-timeout discipline. The captured behaviour (immediate,
same-tick ack+completion) is still real and directly informs RES-C2 below.

## INT-07 — session persistence: codex threads do NOT survive the process

`EV-CX-001-raw_capture_thread_not_found.jsonl`: a thread was started under one `app-server`
process (`thread_id = 01a0bfdb-ea4d-73c3-96f9-f595741c2831`), that process was terminated, and a
FRESH `app-server` process was spawned against the SAME `CODEX_HOME`. `>> turn/start` against the
old thread id (`t=2.1127`) returned, verbatim:

    << {"id": 4, "error": {"code": -32600, "message": "thread not found: 01a0bfdb-ea4d-73c3-96f9-f595741c2831"}}

Confirms ADR 0004 D6's documented claim exactly, byte-for-byte (`-32600`, `"thread not found: "` +
id) — not asserted from prose, captured. `thread/resume` (the documented recovery path) was not
additionally exercised in this pass; the negative case (no silent recovery, no hang) is the part
this task asked to prove and is proven above.

## INT-08 — error edges (malformed input, unknown verb, abrupt child death)

All three sub-cases are EXISTING tests in `tests/test_harness_codex_connector.py`, run and cited
here rather than duplicated:

    $ timeout 60 uv run python -m pytest -q tests/test_harness_codex_connector.py -k \
        "malformed_line or child_death or missing_binary or empty_method or array_params or unknown_server_request"
    7 passed

(the `-k` filter also incidentally caught `test_two_concurrent_events_consumers_are_both_signalled_
on_child_death`, a NEW test written for RES-B2 — see EV-CX-002; harmless overlap, not double
counted below.)

- `test_malformed_line_is_surfaced_and_stream_continues` — non-JSON line, reader keeps draining.
- `test_child_death_surfaces_process_exited_and_stops_cleanly` — `os._exit(7)` mid-turn, `events()`
  terminates cleanly within 15s, `process/exited` surfaced as `kind="error"`.
- `test_missing_binary_raises_config_error_not_raw_oserror` — unresolvable binary → classified
  `OktoNexusError(CONFIG_ERROR)`, not a raw `FileNotFoundError`.
- `test_empty_method_notification_does_not_wedge_the_reader_thread`,
  `test_array_params_notification_does_not_wedge_the_reader_thread` — JSON-RPC-legal,
  domain-invalid shapes; reader thread survives and keeps delivering (these ARE also RES-B1's two
  required shapes; see EV-CX-002).
- `test_unknown_server_request_gets_method_not_found_reply` — a server→client REQUEST codex is not
  implemented for gets `-32601`, never left hanging.

No hang in any of the six INT-08 sub-cases. All bounded by the tests' own timeouts (10–15s), never
unbounded.

## Summary

| Case | Status | Evidence |
|---|---|---|
| INT-01 | PASSED | raw capture + `test_live_against_real_codex_lan_box` |
| INT-02 | PASSED | raw capture + `test_live_against_real_codex_lan_box` |
| INT-03 | PASSED | raw capture, event-kind mapping check |
| INT-04 | PASSED | raw capture, `client_initiated=0` machine-checked |
| INT-05 | PARTIAL | capabilities + fake-based ordering test cited; live steer capture NOT taken (disclosed gap) |
| INT-06 | PASSED (with caveat) | raw capture; interrupt fired pre-content-stream, disclosed |
| INT-07 | PASSED | raw capture, verbatim `-32600` |
| INT-08 | PASSED | 6 existing tests cited, run and green |
