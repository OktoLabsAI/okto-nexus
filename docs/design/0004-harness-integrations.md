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

### D7 — Claude Code is driven via custom MCP server-initiated notifications

Anthropic's own shipped Discord plugin is the precedent. A long-lived MCP server pushes an
unsolicited server->client JSON-RPC notification the instant an external event arrives
(`external_plugins/discord/server.ts:875-884`):

    mcp.notification({
      method: 'notifications/claude/channel',
      params: { content, meta: { chat_id, message_id, user, ... } },
    })

Claude Code's MCP client accepts unsolicited notifications on a custom `notifications/claude/*`
namespace. Nexus already mounts an MCP app at `/mcp`, so this reuses the existing app with no
new process.

Hooks are rejected as the primary channel: every hook fires only at a fixed lifecycle boundary,
so it cannot deliver a Nexus-initiated message mid-turn or while idle. `SendMessage`/`ListAgents`
are rejected as unverified for external processes.

Fallback (empirically proven, v2.1.278): `claude -p --output-format stream-json
--input-format stream-json --verbose` holds one process across many turns on a stable
`session_id` — the same shape as pi `--mode rpc`.

OPEN: the Discord proof is over stdio. Whether Nexus's Streamable-HTTP `/mcp` mount propagates
custom notifications identically is under active spike. If it does not, D7 falls back to the
stream-json path above.

Security: a server pushing arbitrary notifications is a prompt-injection vector. The Discord
plugin hardens against message content posing as system authority; Nexus must do the same for
pushed content.

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
