# 0004 — Harness Integrations: native bidirectional sessions

- Status: Proposed
- Date: 2026-09-20
- Branch: `feature/harness-integrations`
- Supersedes: nothing. Extends the delivery model of [0001](0001-message-inbox-delivery.md).

## Context

Nexus today has no push transport to an external process.

- `adapters/inbound/http/stream.py:1-8` — `GET /api/v1/stream` is SSE, but publication is
  "the bounded 1s poll from TR7 (the in-process push notifier is the F4 Waiter upgrade)".
- `adapters/outbound/waiter.py` — `SleepPollWaiter` polls `PRAGMA data_version` between sleeps.
  This is the entire notification primitive in the system today.
- `application/ports.py:108-109` — "A future push transport (SSE/HTTP notify, as promised in the
  server instructions) replaces it".
- No websocket, no webhook sender, no outbound push adapter exists anywhere in `src/`.

`domain/targets.py` is a routing-audience grammar (`direct`, `capability`, `role`, `tag`,
`broadcast`, `mixed`, `direct_with_fallback`) resolved against `Agent` rows. It is NOT a transport
extension point: `Agent` (`domain/models.py:31-63`) has no harness-type field, and nothing in the
domain models *how* to reach a participant.

We want three harnesses — Claude Code, Codex, Pi — to hold native, bidirectional, non-polling
sessions with the hub.

## Decisions

### D1 — The harness supervisor runs in-process with `okto-nexus serve`

Harness events land in an in-memory subscriber registry and are pushed straight to the connected
peer. The SQLite write is for durability, not for notification.

**Consequence: the F4 push-transport rewrite is NOT in scope.** `SleepPollWaiter` stays on the
pre-existing `event_wait` / `handoff_list_available` long-poll paths, which this feature does not
touch. Had the supervisor been a separate process, the DB would be the only shared channel and the
1s poll would become load-bearing, forcing F4 first.

Rejected alternative: separate supervisor process. Better blast-radius isolation (a wedged `pi`
child cannot take down the hub), but materially larger scope.

### D2 — One thin per-harness connector reconciles the topology asymmetry

Two natural shapes exist and they conflict:

- **Nexus-as-parent** (Pi, Codex): the hub spawns a child and owns its pipes; push is free.
- **Nexus-as-server** (Claude Code): the peer dials in; the hub needs a server-side down-channel.

A thin per-harness *connector* attaches INTO Nexus (satisfying the harness-initiated requirement)
and internally owns its own `pi`/`codex` child pipes. One uniform shape covers all three targets.

Without this, one of the three targets would not fit whichever single shape we picked.

### D3 — Connectors authenticate with the existing `nxs_` agent key

A connector registers via `agent_register` and carries the full key. Target routing
(`direct`/`capability`/`role`/`tag`) then works for free against the existing registry.

Rejected: the existing `poll_tokens` EPT scheme — designed for detached *pollers*, a semantic
mismatch for a push connection. Rejected: inventing a third credential scheme.

### D4 — Pi is consumed as an event stream, not via the polling facade

`pi-delegate` v0.10.0 polls (`pi_conversation_status` looping) only because MCP tools cannot push.
Nexus has no such constraint. We consume the raw LF-framed JSON-lines event stream off the child's
stdout directly.

Wire format, quoted from `pi-companion.mjs:637-652`:

    Command envelope:  {"id"?, "type": "<verb>", ...}
    Response envelope: {"type":"response","command":"<verb>","success":bool,"data"?,"error"?}
    Strict LF framing: buffer raw chunks, split on "\n", carry any partial trailing fragment

Spawn: `spawn("pi", ["--mode","rpc","--session-id",name])` (`pi-mcp-server.mjs:349`).
Verified locally: `pi` 0.85.1 at `/opt/homebrew/bin/pi`; `--mode <text|json|rpc>` and `--session-id`
confirmed present in `pi --help`.

Reusable prior art: `spawnManaged`, `rpcRoundtrip`, `newlineFramed`, the channel registry
(`spawnChannel`/`getChannel`/`killChannel`/`enforceCap`), lock helpers.
Claude-Code-specific glue to drop: plugin manifest, `.mcp.json`, slash-command markdown,
`${CLAUDE_PLUGIN_ROOT}` paths.

### D5 — Codex is validated against the LAN box, NOT Z.ai (corrected 2026-09-20)

The original decision named Z.ai GLM-5.3. **That is empirically impossible** and was corrected
before any code was written.

Codex 0.144.6 rejects the Chat Completions wire format at config-load time:

    Error loading config.toml: `wire_api = "chat"` is no longer supported.
    How to fix: set `wire_api = "responses"` in your provider config.
    More info: https://github.com/openai/codex/discussions/7782

Z.ai implements Chat Completions only:
- `https://api.z.ai/api/coding/paas/v4/chat/completions` -> `200`
- `https://api.z.ai/api/coding/paas/v4/responses` -> `404`

Live failure, captured verbatim:

    {"type":"error","message":"Reconnecting... 1/5 (unexpected status 404 Not Found:
     ... url: https://api.z.ai/api/coding/paas/v4/responses)"}
    {"type":"turn.failed","error":{"message":"unexpected status 404 Not Found: ..."}}

This is a hard protocol gate, not a credential or config nit. Any provider lacking a
Responses-API-shaped `/responses` endpoint cannot back codex 0.144.6 at all.

**Codex is therefore backed by the LAN box** `http://192.168.31.152:8123/v1`, model
`qwen3.8-flash`, which does serve `/responses` (verified `200`). Proven end-to-end in both
machine-readable modes, returning `"text":"ok"`. Scratch provider config:

    model_provider = "lanqwen"
    base_url  = "http://192.168.31.152:8123/v1"
    env_key   = "LANQWEN_API_KEY"
    wire_api  = "responses"

The `.222` box is reserved for a running benchmark and MUST NOT be touched.
Z.ai credentials remain in the gitignored `.secrets/harness.env` for non-codex use.

### D6 — Codex is driven via `codex app-server` (JSON-RPC 2.0)

`codex proto` does NOT exist in 0.144.6; `app-server` is its successor. `codex exec --json`
streams events but is single-shot per process, so it cannot satisfy the bidirectional
requirement. `app-server` is the only mode that keeps one long-lived connection across
multiple threads and turns.

Proven live over one stdio connection:

    -> initialize -> thread/start -> turn/start
    <- turn/started, item/started, item/agentMessage/delta, item/completed, turn/completed

Envelope: standard JSON-RPC 2.0. Requests carry `id` + `method` + `params`; responses echo
`id` with `result` or `error`; server->client notifications have NO `id`. Every async event
carries `threadId` + `turnId`, so one connection demuxes concurrent threads.

Mid-session control available: `turn/interrupt`, `turn/steer`, `thread/inject_items`,
`thread/resume`, `thread/fork`.

Unattended operation: `-a never -s danger-full-access`. With `approvalPolicy = "never"` no
approval round-trips are emitted (confirmed empirically — the live turn completed with zero).

Risks: the entire `app-server` surface is marked `[experimental]`; method and field names can
change between versions with no deprecation guarantee. Pin the codex version and re-run
`codex app-server generate-json-schema` on every upgrade to diff for protocol drift.
Threads are per-process — a `turn/start` against a `threadId` from an exited process fails
with `-32600 thread not found`, so the connector must persist enough state to call
`thread/resume` rather than assume in-memory thread survival.

### D7 — Claude Code: TWO substrates (amended 2026-09-20, supersedes the MCP-notification plan)

The original D7 proposed custom MCP `notifications/claude/*` push, on the strength of the
Discord plugin precedent. **That substrate was tested and ELIMINATED** (EV-CC-002): proven
negative across headless-HTTP, headless-stdio and interactive-HTTP, with the spike server
patched to declare `capabilities.experimental['claude/channel']` exactly as the Discord plugin
does. The notification is sent and the channel is open; it is simply never rendered into model
context. Discord's delivery must use host-side wiring not exposed to arbitrary MCP servers.

Two substrates ship, covering two genuinely different use cases:

**D7a — `claude -p` stream-json (PRIMARY).** Nexus spawns and owns the session:

    claude -p --output-format stream-json --input-format stream-json --verbose

Proven on v2.1.278: one process held across two turns 8s apart, stable `session_id`, both
answered, process alive until stdin closed. Documented, supported, stable flag surface. Same
shape as pi `--mode rpc` and codex `app-server`, so it reuses the connector pattern.

**D7b — `cc-socks` injection (ATTACH).** For a session the user ALREADY has open, which D7a
structurally cannot reach. Transport: `/tmp/cc-socks/<pid>.sock`, one per INTERACTIVE session
(`claude -p` sessions have none). Wire format is newline-delimited JSON with a REQUIRED auth
line first:

    {"type":"auth","token":"<peerToken>"}
    {"type":"user","message":{"role":"user","content":"..."}}

Auth: per-session bearer token at `~/.claude/sessions/<pid>.<hash>.key` (0600), PLUS kernel
`SO_PEERCRED`/`LOCAL_PEERPID` verification of the connecting process. Registry backing
`ListAgents` is `~/.claude/sessions/<pid>.json`.

Proven first-hand (EV-CC-001): a pure-stdlib Python client, no plugin/MCP/hook, delivered a
marked message into this feature's own orchestrating session.

**Known limit:** Nexus can send INTO sessions but CANNOT appear AS a peer in another session's
`ListAgents`. Those registry files are written only by Claude Code itself; there is no socket
RPC to inject an entry.

**Risk accepted deliberately:** `cc-socks` is an undocumented private protocol and can break on
any Claude Code release with no deprecation notice. This is why D7a is primary: if D7b breaks,
the core feature survives and only the attach-to-existing-session capability is lost. D7b must
therefore be isolated behind the same connector port as everything else, degrade gracefully,
and never be on the critical path of the other two harnesses.

Security: content injected via D7b renders to the model as a peer message, so it is a
prompt-injection surface. Pushed content must be treated by the receiver as untrusted data and
must not be able to pose as system authority.

### D8 — Harness sessions start BOTH ways: declared at boot AND on demand

`serve` reads a config listing harnesses to bring up at launch, AND an operator/agent can open a
session on demand through the API. Both paths converge on the same connector lifecycle.

Consequence, and it is a real cost: a harness declared at boot can wedge startup if its child
misbehaves. Boot-time startup MUST therefore be failure-isolated — a harness that fails to come
up is reported and skipped, never fatal to `serve`. This is directly informed by Phase 3: three of
four connectors shipped a defect class whose signature is "looks alive, delivers nothing", so boot
must assume a connector can fail in exactly that way.

### D9 — The harness surface lands on BOTH MCP tools and HTTP routes, at full parity

`tests/test_http_parity.py` already enforces that the stdio and HTTP tool surfaces stay identical.
Harnesses become first-class alongside agents and handoffs rather than a dashboard-only side
channel. No parity exemption is taken.

### D10 — Harness output is BOTH a durable event record AND, when notable, a message

- The full native event stream is persisted for replay and debugging, preserving fidelity to what
  the harness actually emitted (`native_event` is carried verbatim — see EV-INF-002).
- Notable events — turn completion above all — are ALSO surfaced as messages through the existing
  per-recipient inbox (ADR 0001), so the existing target grammar (`direct` / `capability` /
  `role` / `tag`) addresses harnesses with no new delivery concept.

This is the largest of the three options and requires a `029_*.sql` migration for the event table.
REG-07 (migration applies cleanly from empty and is idempotent) is therefore IN SCOPE, not struck.

Rationale for accepting the extra scope: the durable stream is what makes the no-polling claim
auditable after the fact. Without it, an SYS-05 wire trace is a one-shot artifact; with it, any
session can be replayed to show push delivery. The evidence requirement effectively demands it.

## Constraints this feature must respect

- `tests/test_http_parity.py` enforces the stdio and HTTP tool surfaces stay identical — any new
  harness tool must land on BOTH surfaces.
- `tests/test_import_boundary.py` — transport code lives in adapters; any `HarnessSession` domain
  concept must be stdlib-only (no `sqlite3`, no `mcp`).
- New tables require a `029_*.sql` migration; migrations apply at bootstrap before tools register.
- `tests/test_serve_lock.py` / the `serve` lock file — any test booting a real server must handle it.
- No test in the repo binds a real socket today (`test_http_api.py` uses an in-process TestClient).
  A fixture that boots `okto-nexus serve` on an ephemeral port, waits for readiness and tears down
  is a prerequisite for every piece of DoD evidence, and is built BEFORE the adapters.

## Open questions

- Whether Nexus's Streamable-HTTP `/mcp` mount propagates custom server-initiated notifications
  the way the Discord plugin's stdio transport does. Under active spike; decides D7 vs. its
  stream-json fallback.
- Codex `app-server` reconnection/resume semantics after a dropped stdio pipe (only `thread/resume`
  exists as a request method; threads do not survive the process).
- Approval-response correlation in `app-server` uses `callId`, not the JSON-RPC `id`. The schema
  was inspected but no approval round-trip was fired over the wire (the proven run used
  `approvalPolicy = "never"`). Needs verification IF we ever run with approvals on.
