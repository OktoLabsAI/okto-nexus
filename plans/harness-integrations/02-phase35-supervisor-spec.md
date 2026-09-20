# Phase 3.5 — Supervisor wiring specification

- Design authority: [ADR 0004](../../docs/design/0004-harness-integrations.md) D1, D3, D8, D9, D10
- Status: specification. Not implemented.
- Precondition: all four connectors committed and adversarially verified.

This exists so the implementing agents share one shape. Every name below is a proposal to be
checked against the repo's actual conventions before use — read `adapters/inbound/mcp/tools/` and
`adapters/inbound/http/routes.py` first and MATCH what is there rather than importing this
document's guesses wholesale.

## S3.5.1 — Package consolidation (do this FIRST, alone)

The repo's convention for multi-file outbound adapters is a package: `embedding/`, `file/`,
`sqlite/`, `sharedmd/`, `telemetry/`, `tokenizer/`. Only trivial single-file adapters are flat
(`clock.py`, `waiter.py`).

Two connectors were written flat by agents who could not see each other:

    adapters/outbound/harness_codex.py        -> adapters/outbound/harness/codex.py
    adapters/outbound/harness_claude_code.py  -> adapters/outbound/harness/claude_code_stream.py

Already correct: `harness/pi.py`, `harness/claude_code_attach.py`.

Move with `git mv`, update every import in the same commit, re-run the four connector suites.
This is pure motion — no behaviour change, and it lands before any wiring so later diffs are
readable.

## S3.5.2 — The supervisor (D1: in-process with `serve`)

Lives in the application layer. Owns:

- a registry of live `HarnessSession`s keyed by session id
- one connector instance per live session
- the in-memory subscriber registry that fans events out to consumers
- lifecycle: open, close, and reaping on child death

The SQLite write is DURABILITY ONLY and must never be the notification path. `SleepPollWaiter`
must not appear anywhere in the harness path — this is checked structurally by RES-A3/SYS-06, not
by timing.

Consumes the frozen port (`HarnessConnector`, `HarnessSubscriberRegistry`). Does NOT modify it.

### Failure isolation (non-negotiable, D8)

Phase 3 established that a connector's characteristic failure is "looks alive, delivers nothing"
(three of four shipped a defect of that class). The supervisor must therefore assume:

- a connector can wedge without raising
- a child can die without the connector noticing promptly
- a harness declared at boot can fail to start

Requirements: one harness failing NEVER takes down `serve` or another harness; a failed boot-time
start is reported and skipped; every supervisor-side wait is bounded.

## S3.5.3 — Surface (D9: MCP tools AND HTTP routes, full parity)

`tests/test_http_parity.py` enforces that the stdio and HTTP tool surfaces stay identical. Every
tool below MUST exist on both. No exemption is taken.

Proposed MCP tools (match existing naming style — `agent_register`, `session_open`,
`handoff_claim` — before finalising):

| Tool | Purpose |
|---|---|
| `harness_list` | available harness kinds and their declared capabilities |
| `harness_open` | open a session for a kind; returns the session id |
| `harness_send` | send a turn to a live session |
| `harness_steer` | steer, honouring the declared `steer_timing` |
| `harness_interrupt` | interrupt the in-flight turn |
| `harness_close` | end a session, reap the child |
| `harness_status` | session state, capabilities, liveness |
| `harness_events` | read persisted events for a session (replay/debug) |

Capabilities must be reported from the connector's OWN declaration, so a caller can see that
cc-socks is `send_only` with `steer_timing=None` rather than discovering it by failure.

HTTP routes mirror these under `/api/v1/harness/...`, following the shapes already in `routes.py`.

## S3.5.4 — Persistence (D10: durable events + notable messages)

New migration `029_harness_sessions_and_events.sql`. Two tables, shaped to the existing repo
conventions in `src/okto_nexus/migrations/`:

- `harness_sessions` — id, kind, owning agent id, status, capabilities snapshot, timestamps
- `harness_events` — id, session id, kind (the normalised vocabulary), native_event (verbatim),
  payload, thread_id, turn_id, occurred_at, sequence

`native_event` is stored VERBATIM. It is the audit trail that lets a session be replayed to
demonstrate push delivery after the fact — which is what makes the no-polling claim checkable
rather than a one-shot wire trace.

Notable events (turn completion above all) are ALSO delivered as messages through the existing
per-recipient inbox (ADR 0001), so the existing target grammar addresses harnesses with no new
delivery concept. The connector's registered Agent is the sender.

REG-07 (migration applies cleanly from empty, and is idempotent) is IN SCOPE.

## S3.5.5 — Registration (D3)

Each live harness session registers as an ordinary Agent via the existing `nxs_` key path, so
`direct` / `capability` / `role` / `tag` routing works with no new mechanism. Do not invent a
second credential scheme; `poll_tokens` (EPT) is for detached pollers and is the wrong fit.

## Exit criteria

- Package consolidated; all four connector suites green.
- `serve` boots with harness support; `GET /api/v1/info` reflects it.
- `test_http_parity.py` green with the new tools on both surfaces.
- `test_import_boundary.py` green — transport stays in adapters.
- Migration applies from empty and is idempotent.
- Full suite green against the running reference with zero regressions.
- A harness can be opened, sent to, and closed through BOTH the MCP and HTTP surfaces, against a
  REAL running `okto-nexus serve` on a real socket — not an in-process TestClient.

Only then does Phase 4 begin.
