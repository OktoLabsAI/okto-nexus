# Harness Integrations — Test Plan

- Branch: `feature/harness-integrations`
- Design authority: [ADR 0004](../../docs/design/0004-harness-integrations.md)
- Evidence root: `docs/harness-integrations/evidence/`
- Status: specification (Phase 4 not yet executed)

## Evidence rule

Every case below produces a file under `docs/harness-integrations/evidence/<case-id>-*.md`
containing the exact command run and its REAL captured output. A case with no evidence file is
not passed, it is unrun. Mocks, stubs, in-process TestClient calls and synthetic fixtures do not
satisfy any case in the SYS, INT or UAT suites — those run against a real `okto-nexus serve` on a
real socket with the real harness binaries.

## Harness matrix

| Id | Harness | Substrate | Backend |
|---|---|---|---|
| H-PI | Pi 0.85.1 | `pi --mode rpc`, LF-framed JSON lines over stdio | per `~/.pi/agent/settings.json`, NOT `.222` |
| H-CX | Codex 0.144.6 | `codex app-server`, JSON-RPC 2.0 over stdio | LAN `.152:8123/v1`, `qwen3.8-flash`, `wire_api=responses` |
| H-CC | Claude Code 2.1.278 | `claude -p` stream-json (primary) | own auth |
| H-CA | Claude Code 2.1.278 | `cc-socks` injection (attach) | n/a, send-only |

`192.168.31.222` is reserved for a running benchmark and must not receive inference from any case.

## INT — Integration suite (one harness, real binary, no hub)

Each connector against its real harness, in isolation.

- INT-01 `{H}` spawn and handshake: connector starts the binary and reaches ready state.
- INT-02 `{H}` single turn: send a trivial prompt, receive a completed response.
- INT-03 `{H}` event stream fidelity: every native event maps to a `HarnessEvent` with no loss
  of ordering; unmapped native events are surfaced, never silently dropped.
- INT-04 `{H}` **no-polling proof**: show the full wire trace of a turn. Events must arrive with
  ZERO client-initiated requests between the prompt and the completion. This is the DoD's core
  claim and is proven per-harness, with timestamps, not asserted.
- INT-05 `{H}` steer: mid-turn steering takes effect, with the harness's real ordering semantics
  documented (Pi delivers at the NEXT turn boundary, not immediately).
- INT-06 `{H}` interrupt: abort cuts the in-flight turn; the reprompt waits for the correct
  settle signal before being sent. Wrong ordering here is a known hang source.
- INT-07 `{H}` session persistence: where supported, a turn survives a reconnect
  (codex `thread/resume`; pi `--session-id`). Codex threads do NOT survive the process
  (`-32600 thread not found`) — the case asserts the documented behaviour, not a wish.
- INT-08 `{H}` error edges: malformed input, unknown verb, and abrupt child death are handled
  without hanging or crashing the supervisor.

Applies to H-PI, H-CX, H-CC. H-CA runs a reduced set (INT-01, INT-02, INT-08) because it is
send-only with no ack.

## SYS — System suite (real hub, all harnesses attached at once)

- SYS-01 Hub boots with harness support enabled; `GET /api/v1/info` reflects it.
- SYS-02 All connectors attach to one running hub simultaneously and appear as registered agents.
- SYS-03 Hub -> harness: a message routed via the existing target grammar reaches each harness.
- SYS-04 Harness -> hub: output from each harness lands in the hub as a durable record.
- SYS-05 **End-to-end no-polling**: a full round trip per harness with the wire trace showing
  push in both directions and no polling loop anywhere in the path.
- SYS-06 `SleepPollWaiter` is NOT in the harness path (D1). Asserted structurally, not by timing.
- SYS-07 Durability: the SQLite write is a side effect of delivery, never its trigger. Killing
  the subscriber does not lose the record; killing the DB write does not block the push.
- SYS-08 Isolation: one harness child dying does not take down the hub or the other two.
- SYS-09 Concurrency: two harnesses active simultaneously do not cross-talk; events demux
  correctly by session.
- SYS-10 Clean shutdown: hub stop terminates every child, leaving no orphans (`ps` evidence).

## REG — Regression suite

- REG-01 Full pre-existing suite green. Baseline EV-REG-000 = **1610 passed, 2 skipped**;
  after the Phase 1 fixture = **1613 passed, 2 skipped**. Final count must equal the running
  reference plus exactly the newly added tests, with zero pre-existing failures.
- REG-02 `tests/test_http_parity.py` green — any new tool exists on BOTH stdio and HTTP surfaces.
- REG-03 `tests/test_import_boundary.py` green — domain/application import neither `sqlite3` nor
  `mcp`; harness transport code lives only in adapters.
- REG-04 `tests/test_serve_lock.py` green — the fixture and connectors respect the serve lock.
- REG-05 Replay suite green — golden NDJSON re-export still byte-identical.
- REG-06 `ruff check .` clean on ruff defaults, with no config added.
- REG-07 Migration applies cleanly from an empty DB and is idempotent (only if a `029_*.sql` is
  actually introduced; if no new table is needed, this case is struck, not silently skipped).

## RES — Resilience suite (added 2026-09-20 after Phase 3 adversarial review)

These exist because three defect CLASSES recurred across connectors written independently by
different agents, and every one of them was invisible to a passing test suite. See
`docs/harness-integrations/evidence/EV-REV-002-full-defect-register.md`.

All three share one failure signature: **the transport stops delivering events while appearing
alive.** No exception reaches the supervisor, no process dies, nothing is logged. For a feature
whose entire DoD is push delivery, that is the worst possible failure — a connector that has
silently stopped pushing is indistinguishable from a harness with nothing to say.

Every case below runs per connector `{H}` and MUST be bounded so a regression fails in seconds
rather than wedging CI.

### Class A — one-shot shutdown signalling / unbounded blocking waits

- RES-A1 `{H}` `events()` called TWICE returns both times; the second call does not hang.
- RES-A2 `{H}` two CONCURRENT `events()` consumers each receive the FULL stream. They must not
  split it. (Pi failed exactly this: thread A got all 17 events, thread B got zero.)
- RES-A3 `{H}` every blocking wait has a timeout. Verified by grepping the module for
  `Queue.get`, lock `acquire`, `join`, `proc.wait`, socket `recv`/`connect`, `select` and
  asserting each carries a bound. A structural check, not a timing check.
- RES-A4 `{H}` a FAILED `start()` still leaves `events()` terminable. (Pi failed this: the error
  path closed the transport but not the connector, so `events()` looped forever.)

### Class B — unguarded per-line dispatch in the reader thread

- RES-B1 `{H}` a syntactically valid but DOMAIN-INVALID message is surfaced as an error event and
  the reader loop CONTINUES. Not merely a `JSONDecodeError` — that one is already caught
  everywhere. Use the shapes that actually broke things: an empty `method`, and `params` as a
  JSON array (JSON-RPC 2.0 permits it).
- RES-B2 `{H}` a reader thread that exits for ANY reason signals shutdown to EVERY consumer.
- RES-B3 `{H}` no cleanup path contains an unbounded wait. (Codex failed this: an unguarded
  `finally` called `proc.wait()` with no timeout while the child was still healthy, wedging the
  thread forever and stopping stdout drainage — a pipe-fill deadlock.)

### Class C — the fake contradicts the captured protocol

- RES-C1 `{H}` every fake server's wire behaviour is justified against CAPTURED BYTES from the
  real binary, cited by evidence file and section. Ordering, envelope shape, and which messages
  carry correlation ids must all match.
- RES-C2 `{H}` for any connector with an interrupt/abort path, the fake emits the REAL ordering.
  (Pi's fake emitted the abort ack BEFORE the settle; pi really emits settle FIRST. The classic
  hang sat unprotected behind a green test.)
- RES-C3 `{H}` fakes can FAIL, not only succeed: reject an auth line, close mid-message, die
  mid-turn. A fake that only ever succeeds cannot fail a test even if the connector's notion of
  success is meaningless.

Procedure when a fake is found to diverge: correct the FAKE first, re-run the existing tests, and
record which now fail. Those failures are the evidence the defect was real and hidden.

## UAT — User Acceptance suite (run as a user, transcripts captured)

- UAT-01 An operator attaches a Pi session to the hub and holds a two-turn conversation.
- UAT-02 An operator attaches a Codex session and holds a two-turn conversation.
- UAT-03 An operator attaches a Claude Code session (stream-json) and holds a two-turn
  conversation.
- UAT-04 An operator injects a message into a Claude Code session they ALREADY have open
  (`cc-socks`), and it appears in that session. This is the capability stream-json cannot provide.
- UAT-05 An operator addresses a harness through the EXISTING target grammar
  (`direct` / `capability` / `role` / `tag`) rather than a harness-specific API — proving
  harnesses are first-class agents, not a bolted-on side channel.
- UAT-06 Graceful degradation: with `cc-socks` unavailable (simulating a Claude Code update
  breaking the undocumented protocol), the primary path still works and the failure is reported
  clearly rather than hanging. This case exists because D7b's breakage risk was accepted
  deliberately.
- UAT-07 An operator reads the harness documentation and completes a first attach without
  needing to read source code.

## Exit criteria for merge to `main`

All INT, SYS, REG and UAT cases pass with committed evidence. Any struck case carries a written
justification in this file. No case is marked passed on the strength of a unit test alone.
