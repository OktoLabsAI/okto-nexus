# Harness integrations — operator guide

Nexus can hold native, bidirectional, non-polling sessions with four kinds of
coding-agent harness. This is the how-to for attaching one and using it from
the outside — MCP tools and the REST mirror only, no source reading required.

For *why* the feature is shaped this way, see
[`docs/design/0004-harness-integrations.md`](../design/0004-harness-integrations.md)
(the ADR — decision record, not a how-to). For proof that every claim below
was actually exercised against a real binary, see
[`docs/harness-integrations/evidence/EV-INDEX.md`](evidence/EV-INDEX.md), the
Phase 4 test campaign's own index of every case, its status and its evidence
file. That index was captured at commit `b661538`; this guide is written
against the current tree (`3963bd1` plus this run's fixes) and calls out
below exactly which of its FAILED rows are now fixed and which remain.

## The four harnesses

| `kind` | `substrate` | What it is | Who owns the process |
|---|---|---|---|
| `pi` | (none) | Pi 0.85.1, `pi --mode rpc` | Nexus spawns and owns the child |
| `codex` | (none) | Codex 0.144.6, `codex app-server` | Nexus spawns and owns the child |
| `claude_code` | `stream` (default) | Claude Code, `claude -p` stream-json | Nexus spawns and owns the child |
| `claude_code` | `attach` | Claude Code, `cc-socks` injection | An interactive session the **operator** already has open; Nexus injects into it |

`stream` and `attach` are two different capability sets under one `kind`, not
interchangeable — pick the one your use case actually needs. `stream` is the
primary, general-purpose path: open a session, hold a real conversation,
close it. `attach` exists only for the one thing `stream` structurally
cannot do — reach a Claude Code session the operator is already sitting in
— and pays for that with hard limits (see below).

Check what any (kind, substrate) combination actually supports before
relying on it:

```
harness_list
```

or

```
GET /api/v1/harness/kinds
```

Both return the same catalog, read live off each connector's own declared
`HarnessCapabilities` — never a hand-typed table, so it can't drift from the
code. Each entry looks like:

```json
{
  "kind": "pi",
  "substrate": null,
  "capabilities": {
    "send_only": false,
    "steer_timing": "NEXT_TURN_BOUNDARY",
    "interrupt_requires_settle_wait": true,
    "multiplexes_sessions": false,
    "observes_session_end": true
  }
}
```

- `send_only` — `true` means there is no ack, no reply channel, nothing to
  wait on. Only `claude_code`/`attach` sets this.
- `steer_timing` — `"IMMEDIATE"` (codex), `"NEXT_TURN_BOUNDARY"` (pi — a
  mid-turn steer is buffered until the *next* turn, not applied instantly),
  or `null` (steering unsupported at all on this transport).
- `interrupt_requires_settle_wait` — `true` for pi: its abort does not
  resolve synchronously, so a `harness_send`/`harness_steer` issued right
  after an interrupt can come back `CONFLICT` until the aborted turn's own
  settle event lands. Don't race it; poll `harness_get`/`harness_event_list`
  or just wait a beat and retry.
- `multiplexes_sessions` — `true` only for codex (one connector process
  demuxes many concurrent threads by `threadId`/`turnId`); `false`
  everywhere else (one process per session).
- `observes_session_end` — `false` for `attach`: Nexus injected into a
  session it didn't spawn, so it has no channel to learn when that session
  ends. That session's `HarnessSession.status` never legally reaches
  `ENDED` on its own.

## Backend safety — read this before your first `pi` or `codex` open

**Omitting `backend` on `harness_open` means the spawned child inherits
whatever model provider is already configured on the machine running
`okto-nexus serve` — not a choice Nexus made for you.** For `pi` specifically
that is the *operator's own* `~/.pi/agent/settings.json` `defaultProvider`.
On the machine this feature was built and tested on, that default resolves
to a LAN box reserved for an unrelated multi-day benchmark run — a real
example of a first `kind="pi"` open silently sending live inference
somewhere the operator never chose, on their own machine, using whatever
routing that machine's ambient CLI config already happens to point at.

Pass `backend` explicitly on every `harness_open` unless you specifically
want the ambient default:

```json
{
  "agent_id": "my_pi_session",
  "kind": "pi",
  "project_root": "/abs/path/to/project",
  "backend": {"provider": "zai", "model": "glm-5.3"}
}
```

The response always states which happened — never silently:

```json
{
  "session_id": "hsess_...",
  "...": "...",
  "backend": {
    "explicit": true,
    "applied": {"provider": "zai", "model": "glm-5.3"},
    "note": "backend override applied exactly as given."
  }
}
```

Omit `backend` and the `note` field spells out the inherited-default warning
instead of staying silent — read it before trusting the session.

**Supported `backend` fields are per-kind, not uniform:**

| `kind` | `substrate` | Supported `backend` fields |
|---|---|---|
| `pi` | — | `provider`, `model`, `extra_args`, `env` (argv overrides passed straight to the child) |
| `codex` | — | `env` only — codex's real provider/model/base-URL selection is `CODEX_HOME` pointing at a `config.toml`, read from the process environment, not a CLI flag |
| `claude_code` | `stream` | `env` only |
| `claude_code` | `attach` | none — rejected entirely; `attach` spawns nothing to configure |

A field a given kind doesn't support is a `VALIDATION_ERROR` naming the
supported set, never a silent no-op or a silent drop.

## Open a session

```
harness_open(
  agent_id="my_session",        # REQUIRED — the agent_id this session registers/upserts as
  kind="pi",                    # REQUIRED — pi | codex | claude_code
  project_root="/abs/path",     # REQUIRED — defines the workspace scope
  substrate=None,                # only meaningful for kind="claude_code"
  target_pid=None,               # only for claude_code/attach — see below
  backend=None,                  # see backend safety above
  role=None,
  metadata=None,
  notify_target=None,            # see "notable events as messages" below
)
```

REST mirror: `POST /api/v1/harness/sessions` with the same fields as a JSON
body (mutating REST harness routes are operator-only — the same trust model
as `POST /agents`; see the main [README's HTTP surfaces
section](../../README.md#http-surfaces-and-authentication)).

`harness_open` is bounded: a connector that wedges on startup raises
`INTERNAL_ERROR` after a start timeout rather than hanging the call forever.

Returns a `HarnessSession`:

```json
{
  "session_id": "hsess_323656deb61f40ad8649ec88a21225b7",
  "kind": "pi",
  "owning_agent_id": "my_session",
  "status": "RUNNING",
  "capabilities": {"...": "..."},
  "started_at": "...",
  "ended_at": null,
  "metadata": {},
  "backend": {"...": "..."}
}
```

Keep the `session_id` — every other harness call needs it.

### `claude_code`/`attach`: finding a `target_pid`

`attach` requires `substrate="attach"` and a `target_pid` (rejected as
`VALIDATION_ERROR` without one). That pid is **not** something `harness_open`
discovers for you — it must be the OS process id of an already-running,
*interactive* Claude Code session on the same machine. `claude -p`
(non-interactive) sessions have no registry entry and cannot be attached to.
Claude Code itself writes one registry file per interactive session at
`~/.claude/sessions/<pid>.json`; finding your target pid means locating that
file for the session you want to inject into (for example, the pid of the
`claude` process you already have a terminal open to). This guide does not
have a friendlier discovery mechanism to offer, because none exists on the
public surface today — see "known gaps" at the end.

## Send a turn, steer, interrupt

The payload shape is **harness-native and not uniform across connectors** —
check `harness_list`'s catalog entry for the kind before sending:

- `pi` and `codex` read `{"text": "<prompt>"}`
- both `claude_code` substrates (`stream` and `attach`) read
  `{"content": "<prompt>"}`

```
harness_send(session_id="hsess_...", payload={"text": "hello"})
```

`harness_send` never blocks for a reply — the answer arrives later as
harness events (subscribe out-of-band, or poll `harness_event_list`). REST
mirror: `POST /api/v1/harness/sessions/{id}/send`.

`harness_steer(session_id, payload)` — steers the in-flight turn. Rejected
with `VALIDATION_ERROR` if the connector's `steer_timing` is `null`
(`attach` has no steer verb at all — check `harness_list` first). Remember
pi buffers this to the *next* turn boundary rather than applying it
mid-turn; codex applies it immediately.

`harness_interrupt(session_id, payload=None)` — aborts the in-flight turn.
If `interrupt_requires_settle_wait` is `true` (pi), a send/steer issued
immediately after may come back `CONFLICT` until the aborted turn's settle
event lands — wait for it rather than retrying in a tight loop.

`harness_close(session_id)` — best-effort teardown (`send(end)` then
`close()`), always returns the final session state even if teardown failed.
Never hangs.

`harness_get(session_id)` — reads the live in-memory view if still tracked
(`live: true`), else the last durable row (`live: false` — a row left
`RUNNING` there is **not** proof the process is actually alive; nothing
resurrects a dead session's liveness signal after an unclean exit).

`harness_event_list(session_id, after_sequence=0, limit=200)` — durable,
sequenced replay of everything the session emitted, independent of
liveness. `native_event` carries the harness's own verbatim event name
(`"item/agentMessage/delta"`, `"turn.completed"`, ...) for traceability; the
normalized `kind` (`turn_started` / `output_delta` / `turn_completed` /
`tool_activity` / `error`) is what to branch logic on.

REST mirrors all of the above 1:1 under `/api/v1/harness/sessions/{id}/...`.

## Addressing a harness through the target grammar

**As of this run, the ordinary routing grammar — `direct` / `capability` /
`role` / `tag`, resolved by `message_create` exactly as it always has been —
does reach a live harness session's own turn input**, addressed at the
`agent_id` you passed to `harness_open`. This closes a gap that the Phase 4
campaign found and reported as a false claim (`EV-SYS-003`, `EV-UAT-05`,
`UAT-07`): earlier in this same run, the shipped tool description promised
this routing worked and it did not — `message_create` reported success while
the harness's own wire trace gained zero bytes. That gap has now been fixed
and independently re-verified against a real running hub and a real `pi`
child (`docs/harness-integrations/evidence/EV-SYS-003-FOLLOWUP-target-grammar-fix.md`);
`tests/test_harness_target_grammar.py` (11 tests, including one that proves
the two composition roots — the messages tool module and the harness tool
module — genuinely share the same in-process notifier in production wiring,
not just in a test double) is the regression guard.

What this gets you, and its real limits:

- It is a **best-effort hand-off, not guaranteed delivery**. The ordinary
  inbox delivery row is created exactly as it always was and is **never**
  mutated by the forward — it stays `unread` whether the forward to the
  harness succeeds or fails, and remains pullable through the normal
  `inbox_pull`/`inbox_ack` path regardless. `message_create`'s response
  still reports its own `delivered_count` based on the inbox write, which
  happened — it does **not** reflect whether the harness forward itself
  succeeded.
- Only reaches **live** sessions. If the session isn't open, there's no
  subscriber to forward to.
- Only `send_turn` rides this path — `steer`/`interrupt` are not
  forwardable this way. Use `harness_steer`/`harness_interrupt` with the
  explicit `session_id` for those.
- Bounded at 10 seconds on the calling thread (`message_create`'s own
  caller — an MCP tool call or HTTP request), the same non-polling
  `Thread.join(timeout)` shape `harness_open`/`harness_close` already use.
- **A message sent BY any currently-live harness's own agent is never
  forwarded into any live harness** — a deliberate cascade guard against two
  harnesses ping-ponging turns at each other forever (harness A's
  `turn_completed` becomes a message → forwarded into B as a turn → B's
  `turn_completed` becomes a message → forwarded into A → ...). If you
  intentionally want one harness to relay into another, address it with the
  explicit `session_id` via `harness_send` instead — that path doesn't go
  through this guard.
- Guaranteed delivery, an explicit steer/interrupt, or addressing a session
  that may not be live yet: use `harness_send`/`harness_steer`/
  `harness_interrupt` with the `session_id` `harness_open` returned instead
  of relying on the target grammar.

## Notable events also arrive as messages (D10)

Independent of the target-grammar fix above, `turn_completed` and `error`
events from any open session are *also* delivered as ordinary messages
through the existing per-recipient inbox, routed by `notify_target` (same
grammar as `message_create`/`handoff_create`). Default when `notify_target`
is omitted: `{"strategy": "broadcast"}` scoped to that session's own
workspace. This has worked since the feature's initial build; it is the
*output* direction, and is unaffected by the *input*-direction gap described
above.

## `claude_code`/`attach` (`cc-socks`): what it actually is

This substrate exists for exactly one thing `stream` cannot do: inject into
an interactive Claude Code session the operator already has open. Its real
limits, stated plainly because they are easy to assume away:

- **Send-only, no ack, no reply channel at all.** The connection is
  accepted with no synchronous acknowledgement. A `200`/success response
  from `harness_open` or `harness_send` means the message was handed to the
  socket, not that it was received or rendered into the target session.
- **`steer_timing` is `null` and `observes_session_end` is `false`.** There
  is no steer verb and no interrupt verb on this transport, and Nexus has no
  channel to learn when the target session ends — its `HarnessSession`
  never legally reaches `ENDED` on its own.
- **The wire protocol is undocumented and private to Claude Code.** It can
  change shape on any Claude Code release with no deprecation notice — this
  risk was accepted deliberately (ADR 0004 D7b), which is why `stream` is
  the primary substrate and `attach` is isolated behind the same connector
  port rather than being load-bearing for anything else.
- **Claude Code 2.1.278 gates cross-session inbound behind an operator
  approval prompt on the receiving end**, a finding from this campaign not
  in the original design (`EV-INDEX.md`, INT-02/H-CA). A `200` from
  `harness_send` does not by itself mean your message appeared in the
  target session's transcript — the receiving session's own operator may
  need to approve it first.
- **Content injected this way is a prompt-injection surface**, not just a
  delivery mechanism: it renders to the receiving model as an ordinary peer
  chat message. The connector wraps every outbound message in a banner
  naming Nexus and the sending agent as the source and stating the content
  is untrusted external data, not a system or user instruction — a
  best-effort textual convention, not a structural guarantee the receiving
  model is bound to honour.

### Graceful degradation when `cc-socks` breaks

If the target session's registry file is missing (simulating exactly what a
Claude Code update that changes or drops the registry would look like from
the connector's own point of view), `harness_open` fails **fast** — not a
timeout, not a hang:

```
POST /api/v1/harness/sessions  {"kind":"claude_code","substrate":"attach","target_pid":...}
-> 404 in ~13ms
{
  "ok": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "No Claude Code session registry at ~/.claude/sessions/<pid>.json.
                 The session may have ended, the pid may be wrong, or this is not
                 an interactive session (`claude -p` sessions have no registry
                 entry)."
  }
}
```

The primary path (`claude_code`/`stream`) is completely unaffected — it can
be opened on the same hub immediately after an `attach` failure. This was
verified directly (`docs/harness-integrations/evidence/EV-UAT-06-graceful-degradation.md`).

## Known gaps and limitations (as of this guide)

Read these before assuming a capability exists. Sourced from
`docs/harness-integrations/evidence/EV-INDEX.md`'s Phase 4 campaign findings,
with this run's own fixes applied on top and stated explicitly:

- **Fixed in this run** (were FAILED in `EV-INDEX.md`; each confirmed fixed
  by reading the actual code change and its own re-run evidence, not merely
  by a green suite count — see each connector's own evidence file for the
  re-run): pi's unbounded `proc.wait()` on the reader thread's exception
  path (RES-A3/B1/B3 — was a real hang risk on a malformed-but-syntactically
  -valid deeply nested JSON payload); the `claude_code`/`stream` connector's
  single-shared-queue fan-out split and its failed-`start()` termination gap
  (RES-A2/A4); codex's equivalent queue-split and termination-gap defects
  (RES-A2/A4, re-run 3× isolated, same PASS every time); codex's fake-server
  post-interrupt ordering divergence (RES-C2, fake now emits the real
  `turn/completed(interrupted)` ordering); codex's missing live-binary steer
  capture (INT-05, closed by `EV-CX-001-raw_capture_steer.jsonl` — a genuine
  mid-stream `turn/steer`, 0.1ms after the first content delta, accepted and
  honoured with no abort/interrupt cycle, confirming `STEER_TIMING_IMMEDIATE`
  live; that capture explicitly does **not** distinguish "the steer
  preempted the original stream" from "the model happened to stop there
  anyway" — a control run without the steer would be needed for that,
  disclosed as an open question in the evidence file itself, not asserted);
  and the target-grammar input-direction gap (SYS-03/UAT-05), covered above.
- **Still open, not touched by this run:** `claude_code`/`attach`'s
  `RES-A2` — two concurrent `events()` consumers on this connector
  **partition** a stream rather than each receiving the full broadcast
  (a deque split, not a duplication). It is not reachable through today's
  supervisor, which always drains a `send_only` connector's events
  synchronously through one caller, but it is a real, unguarded violation
  of the connector port's own contract if a second consumer is ever added.
- **`claude_code`/`attach` cannot discover its own `target_pid`.** As noted
  above, an operator has to already know which interactive session's pid
  they want and locate its registry file themselves; nothing on the public
  surface enumerates candidate pids.

Full case-by-case detail, including every PASSED/FAILED/NOT-APPLICABLE/UNRUN
row with its evidence file, lives in
[`docs/harness-integrations/evidence/EV-INDEX.md`](evidence/EV-INDEX.md).
That file is the Phase 4 snapshot (commit `b661538`); the "fixed in this
run" list above is this guide's own reconciliation against the current tree,
not a rewrite of that index.
