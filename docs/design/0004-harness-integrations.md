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

### D5 — Codex is validated against Z.ai GLM-5.3

No OpenAI subscription is available. Codex is driven through an OpenAI-compatible custom provider.
Credentials live ONLY in the gitignored `.secrets/harness.env`; they are never committed, logged,
or inlined.

Verified live 2026-09-20: `codex-cli 0.144.6` at `/opt/homebrew/bin/codex`; Z.ai
`glm-5.3-flash` returned `"content":"ok"` with `finish_reason":"stop"`.
Local fallback `http://192.168.31.152:8123/v1` serves `qwen3.8-flash` (200K ctx).
The `.222` box is reserved for a running benchmark and MUST NOT be touched.

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

- Claude Code substrate (MCP server→client notifications vs. hooks plugin vs. Agent SDK vs.
  `--input-format stream-json`) — research in flight.
- Codex machine-protocol mode and its event envelope — research in flight.
