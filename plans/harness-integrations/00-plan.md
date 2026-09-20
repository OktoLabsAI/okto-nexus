# Harness Integrations — Delivery Plan

- Branch: `feature/harness-integrations` (no commit to `main` until fully validated)
- Design authority: [ADR 0004](../../docs/design/0004-harness-integrations.md)
- Status: Phases 0, 1 and 2 COMPLETE (port frozen: `domain/harness.py` +
  `HarnessConnector`/`HarnessSubscriberRegistry` in `application/ports.py`,
  commit `b0db60b`); Phase 3 (connectors, one agent each) next
- Last updated: 2026-09-20

## Definition of Done (verbatim from the request)

Nexus running with native (no-polling) integrations into all three harnesses, plus
system-level, integration-level, regression and User Acceptance test cases, each with
indisputable evidence.

"Indisputable evidence" is operationalised here as: the exact command run, its real captured
output, committed under `docs/harness-integrations/evidence/`, produced against a REAL running
`okto-nexus serve` on a real socket with REAL harness binaries. Mocks, stubs and in-process
TestClient calls do not count toward the DoD gate.

## Substrates (settled, see ADR 0004)

| Target | Substrate | Direction | Proven |
|---|---|---|---|
| Pi | `pi --mode rpc`, LF-framed JSON lines over child stdio | push/push | prior art, v0.85.1 live |
| Codex | `codex app-server`, JSON-RPC 2.0 over stdio | push/push | live turn completed |
| Claude Code | `claude -p` stream-json (primary) + `cc-socks` inject (attach) | push/push | both proven; MCP-notification eliminated |

Claude Code candidate ranking, to be settled by Phase 0 spikes:
1. `/tmp/cc-socks/<pid>.sock` — native per-session unix socket. No plugin, no MCP, no mount.
   Cleanest if externally speakable. UNDOCUMENTED private protocol: breakage risk.
2. Custom MCP `notifications/claude/*` push over the existing `/mcp` mount. Supported, shipped
   pattern (Anthropic's own Discord plugin). Proven over stdio; HTTP leg under spike.
3. `claude -p --input-format stream-json --output-format stream-json --verbose`. Empirically
   proven, but couples Nexus to owning a subprocess per session.

## Phases

### Phase 0 — Close the Claude Code substrate question (COMPLETE)

- S0.1 Spike: does the Streamable-HTTP `/mcp` mount propagate custom server-initiated
  notifications the way stdio does? (running)
- S0.2 Spike: reverse-engineer `/tmp/cc-socks/<pid>.sock` — wire format, method set, registry
  source, auth, and whether an external non-Claude process can send a message that lands as a
  `<cross-session-message>`. (running)
- S0.3 Decide the substrate. Record as ADR 0004 D7 amendment, with the stability tradeoff stated
  explicitly. A supported-but-clunkier path beats an elegant undocumented one for a shipped
  product feature unless the user rules otherwise.

Exit: D7 amended and committed.

### Phase 1 — Evidence infrastructure (COMPLETE)

No test in this repo binds a real socket today (`test_http_api.py` uses an in-process
TestClient). Without this, no DoD evidence is producible.

- S1.1 A pytest fixture that boots real `okto-nexus serve` on an ephemeral port, waits for
  readiness, yields a base URL, and tears down. Must cooperate with the `serve` lock file
  (`tests/test_serve_lock.py` is the reference for its semantics) and use an isolated
  `OKTO_NEXUS_HOME` so it never touches `~/.okto_nexus/nexus.db`.
- S1.2 An evidence harness that captures command + raw stdout/stderr to
  `docs/harness-integrations/evidence/<case-id>.log`, so every DoD claim has a file behind it.
- S1.3 Regression baseline: full suite result recorded BEFORE any production code changes.

Exit: fixture green; baseline recorded.

### Phase 2 — Freeze the shared transport port (COMPLETE — see EV-INF-002)

Three connectors implementing against an unfrozen interface, all touching one registration
point on one branch, will collide. The port lands first, alone, reviewed.

Shape (stdlib-only, lives in `domain/` to satisfy `test_import_boundary.py`):

- `HarnessSession` — identity, lifecycle state, owning agent id.
- `HarnessEvent` — normalised inbound event from any harness (turn started/delta/completed,
  tool call, error), carrying the originating harness id and native event name.
- `HarnessCommand` — normalised outbound (send turn, steer, interrupt, end).
- A subscriber registry port for in-process push (D1), with the SQLite write as durability only.

Per-harness native envelopes are translated at the adapter edge, never in the domain.

Exit: port merged, `test_import_boundary.py` green, no adapter written yet.

### Phase 3 — Connectors (fan-out; one agent per connector) — IN REMEDIATION

Each owns one adapter module plus its own tests. Genuinely independent once Phase 2 lands.

- S3.1 Pi connector — reuse `spawnManaged`/`rpcRoundtrip`/`newlineFramed` semantics; LF framing;
  `turn/steer` and abort→reprompt ordering (must wait for the aborted turn's own settle).
- S3.2 Codex connector — `initialize` → `thread/start` → `turn/start`; demux on
  `threadId`+`turnId`; `-a never -s danger-full-access`; persist enough to `thread/resume`
  (threads do NOT survive the process: `-32600 thread not found`).
- S3.3 Claude Code connector — per Phase 0 verdict.

Any new tool must land on BOTH stdio and HTTP surfaces or `test_http_parity.py` fails.
Any new table needs a `029_*.sql` migration.

Exit: all four connectors green in isolation AND every adversarial-review defect closed
with a failing-first regression test. A green suite alone is explicitly NOT sufficient — all
four connectors had green suites while carrying critical defects.

### Phase 3.5 — Consolidation and supervisor wiring (BLOCKS PHASE 4)

- S3.5.1 Consolidate the connectors into the `adapters/outbound/harness/` package. The repo's
  convention for multi-file outbound adapters is a package (`embedding/`, `sqlite/`,
  `telemetry/`, `tokenizer/`); only trivial single-file adapters are flat (`clock.py`,
  `waiter.py`). Two connectors were written flat by agents unaware of the others and must move,
  with their imports updated in the same commit.
- S3.5.2 Wire the in-process supervisor into `serve` (D1): the subscriber registry, connector
  lifecycle, and registration of each connector as an Agent via the existing `nxs_` key path (D3).
- S3.5.4 Boot-time harness startup from config (D8), FAILURE-ISOLATED: a harness that fails to
  start is reported and skipped, never fatal to `serve`.
- S3.5.5 On-demand session open/close through the API (D8).
- S3.5.6 Surface on BOTH MCP tools and HTTP routes at full parity (D9) — no parity exemption.
- S3.5.7 Durable harness-event records plus message surfacing of notable events (D10). Requires a
  `029_*.sql` migration, so REG-07 is IN SCOPE.
- S3.5.3 Any new tool must land on BOTH the stdio and HTTP surfaces or `test_http_parity.py`
  fails. Any new table needs a `029_*.sql` migration; if none is needed, strike REG-07 explicitly.

### Phase 4 — Test campaign and evidence

Four suites, each with captured evidence:

- Integration: each connector against its real harness binary, in isolation.
- System: real `okto-nexus serve`, all three harnesses attached simultaneously, a message routed
  hub→harness and harness→hub for each, proving push in both directions with no polling.
- Regression: full pre-existing suite, diffed against the Phase 1 baseline. Zero regressions.
- UAT: the user-facing scenarios, run as a user would, transcripts captured.

No-polling is proven, not asserted: for each connector, show the event arriving with no
intervening status request on the wire.

Exit: all four suites green with committed evidence; then and only then, merge to `main`.

## Risks

- Codex `app-server` is `[experimental]`; pin the version, re-run
  `codex app-server generate-json-schema` on upgrade and diff for drift.
- `cc-socks` is undocumented and can change in any release.
- Z.ai cannot back Codex at all (no `/responses`); the LAN `.152` box is the only proven backend.
  `.222` is reserved for a running benchmark and must not be touched.
- A server pushing arbitrary notifications is a prompt-injection vector; pushed content must be
  hardened against posing as system authority, as the Discord plugin does.
