---
title: "ADR 0002 — Design-review hardening (concurrency, observability, MCP surface, inbox, presence, trust, retention)"
status: Accepted
date: 2026-06-10
references: ADR 0001 (message inbox delivery)
---

# ADR 0002 — Design-review hardening

## Status

**Accepted.** All decisions below are implemented on top of the V2 inbox
delivery model of [ADR 0001](0001-message-inbox-delivery.md). The findings are
numbered **M1–M11** after the adversarial design review that produced them
(reviewed as deployed at baseline `49120d1`).

## Context

V2 (ADR 0001) shipped a correct delivery *model* with several latent defects in
its *execution*: write transactions that could die mid-flight under WAL
contention, an observability chain with three independent breaks (events that
no consumer could ever see), an MCP surface that could block a single-threaded
agent harness by default, an inbox whose "cheap read" tools took the writer
lock, three divergent parsers for the same routing-target grammar, three
unreconciled notions of "is this agent present", zero authentication on
mutating verbs, and a store that grows forever. The operating constraints are
unchanged: **N processes (MCP stdio servers + CLI followers) over a single
SQLite file in WAL mode**, hexagonal layering, and **LLM agents as the only
consumers** — every error must be prescriptive enough for an agent to repair
its own call.

## Decisions

### D1 (M1) — Write transactions take the lock up front; contention is retryable

`SqliteUnitOfWork` (in `adapters/outbound/sqlite/connection.py`) now opens
**`BEGIN IMMEDIATE` by default** (`write=True`): the WAL write lock is acquired
at `BEGIN`, where `busy_timeout` actually applies, so a read-then-write
sequence can never die mid-transaction with `SQLITE_BUSY_SNAPSHOT` (the failure
mode `busy_timeout` does *not* cover). Read-only scopes opt out with
`write=False` (deferred `BEGIN`; WAL readers never queue behind writers).
Lock/busy contention is surfaced as `DB_ERROR` with **`details.retryable:
true`** and a message telling the caller to retry the same call — agents branch
on the flag, never on message text. The one-time WAL conversion of a fresh
database gets a short bounded retry (concurrent bootstraps race it outside
`busy_timeout`). Migrations apply each pending version in its **own
`BEGIN IMMEDIATE` transaction**, re-checking the ledger under the write lock,
so concurrent bootstraps are safe and a ledger newer than the package fails
closed.

### D2 (M2) — The observability chain is repaired end to end

Four independent breaks, one consequence (events nobody could see), all fixed:

1. **`stream=None` means ALL streams.** `EventRepo.list_after(stream=None)`
   selects every stream (the unit-test fake had drifted from the SQLite
   adapter; `tests/test_ports_contract.py` now runs the same contract suite
   against both implementations so fake-drift fails the build).
2. **Session lifecycle events are observable.** `session.opened` /
   `session.heartbeat` / `session.closed` are emitted on the canonical
   **`workspace`** stream with `visibility="public"` and no routing target.
   (They previously used an internal `"session"` stream with
   `visibility="workspace"` — neither value is in the canonical vocabulary, so
   the events were invisible to every consumer.)
3. **The emit path is fail-closed.** `validate_emit_vocabulary`
   (`domain/events.py`) rejects any out-of-vocabulary `stream`/`visibility`
   (and a blank `type`) at write time with `INTERNAL_ERROR` — nothing
   unreachable is ever persisted. Producer bugs surface immediately instead of
   silently poisoning the log.
4. **The sender always sees its own events (sender carve-out).**
   `can_agent_see_event` treats `actor_agent_id == agent_id` as visible —
   eligibility never excludes an actor from its own audit trail (ADR 0001:
   "you have a delivery row *or you are the sender*").

### D3 (M3) — The MCP surface is safe by default

- **Object-shaped parameters are annotated `Any`** (`target`, `payload`,
  pagination inputs) and validated by `require_json_object_param`
  (`envelope.py`) plus the application layer — a wrong type returns the
  canonical `VALIDATION_ERROR` envelope, never a second (SDK/pydantic) error
  grammar. `handoff_create.payload` accepts any JSON value and round-trips it
  opaquely.
- **`event_wait` defaults to a non-blocking snapshot.** `timeout_seconds`
  omitted/`0`/`null` performs a single scan with no sleep (same default as
  `handoff_list_available`); blocking is an explicit opt-in (`> 0`, clamped to
  the configured ceiling). A single-threaded agent harness is never parked by
  default.
- **Removed tools answer `MIGRATED`, permanently.** The S3 clean break
  (`message_get` / `message_list` / `message_wait`) is backed by parameterless
  shims that always return `ok:false, code=MIGRATED` with
  `details.replacements` naming the exact replacement calls — a pinned client
  gets prescriptive guidance instead of an opaque "Unknown tool".
- **`nexus_info` makes staleness detectable.** It reports
  `{package_version, schema_version, surface_revision}`;
  `SURFACE_REVISION` (in `server.py`) is bumped on **every** change to tool
  names/parameters/defaults/semantics, so an agent whose cached schemas
  disagree with observed behaviour has a one-call diagnosis.

### D4 (M4 + M8) — Inbox: read-only reads, tunable leases, a dead letter, stable history

- **`inbox_peek` / `inbox_count` / `inbox_history` / `message_status` are
  strictly READ-ONLY** (`unit_of_work(write=False)`): polling between turns
  never takes the WAL writer lock. Expired in-flight leases are *projected* as
  `unread` at read time — never swept by a read.
- **`inbox_pull` claims are recipient-scoped**: a pull takes `unread` rows plus
  *your own* lease-expired redeliveries, atomically, into in-flight.
- **Caller-tunable leases.** `inbox_pull(lease_seconds=…)` sizes the in-flight
  lease to the expected turn (clamped 10–3600 s; default
  `inbox_lease_ttl_seconds`, 300 s); **`inbox_extend`** renews in-flight leases
  mid-turn, all-or-nothing with a per-message reason on failure.
- **Poison messages park instead of looping.** Migration
  `006_inbox_delivery_hardening.sql` adds `attempts`; a delivery claimed
  `DEFAULT_MAX_DELIVERY_ATTEMPTS` (5) times without an ack moves to the
  **`parked`** lane (dead letter) — visible to the recipient via
  `inbox_peek(include_parked=true)` and to the sender via `message_status`,
  never redelivered again, never counted as `unread`.
- **`inbox_history` is keyset-paginated** (opaque cursor pinned to the last row
  seen): acks landing between pages can no longer duplicate or hide items.
  Legacy numeric offset cursors are rejected with a prescriptive
  `VALIDATION_ERROR`.
- **`message_status`** gives the sender the per-recipient effective lane
  (`unread`/`delivered`/`read`/`parked` + `attempts`) so "recipient seems
  silent" is answered by observation, not by re-sending.

### D5 (M9) — One grammar for targets (and one for pagination)

`domain/targets.py` is now the **single source of truth for the routing-target
grammar**: every slice that accepts, stores, or evaluates a `target` (message
send validation, handoff descriptors, routing eligibility/visibility) parses it
through `validate_target` / `coerce_target` / `normalize_strategy`. A target
accepted on one write path can never be rejected — or silently reinterpreted —
on another. The grammar also hardened: `mixed` requires a **non-empty** `rules`
list, a null/blank sub-rule is rejected (it would silently resolve to a covert
broadcast), and a `broadcast` nested in a `mixed` is rejected everywhere
(messages *and* handoffs). Pagination input parsing (`normalize_cursor` /
`clamp_limit`) likewise moved to `domain/base.py` as the shared grammar for
every slice (integer-string cursors/limits are accepted uniformly), and
timestamps are pinned to one canonical fixed-width UTC form — `iso_plus`
refuses to compute a lease from a non-canonical base, because lease expiry
compares timestamps lexicographically.

### D6 (M6) — Presence is one predicate; broadcasts never silently drop anyone

`session_is_present` (`application/identity.py`) is the **single presence
predicate**: persisted status `active` AND last heartbeat within
`presence_ttl_seconds` (default 1800 s). It reconciles the three previously
divergent notions (stored status, derived `stale`, agent `last_seen_at`). Both
consumers use exactly this function:

- **`IdentityService.list_present`** — the single presence read: the sessions
  listed are exactly the broadcast audience.
- **The message broadcast audience** — a bare `broadcast`/no-target
  `message_create` fans out to the workspace's **present** participants only.
  Agents excluded because every active session of theirs has a stale heartbeat
  are surfaced **explicitly** to the sender in `excluded_stale` plus a
  `warning` — exclusion is never silent (the D1b critique rule of ADR 0001,
  extended to staleness).

Sessions silent past `session_reap_seconds` (default 86400 s) are
**opportunistically closed** (reason `stale`) by `session_open` /
`session_heartbeat` — dead sessions stop accumulating state forever, still with
no background thread.

### D7 (M10) — Trust: `open`/`strict` modes with a per-session secret

`session_open` returns a server-generated **`session_secret`** (uuid4, stored
by migration `007_session_secret.sql`, returned **only** at open time). The
sensitive verbs — `message_create`, `handoff_claim`/`complete`/`reject`,
`inbox_pull`/`ack`/`extend` — are gated by `NexusConfig.trust_mode`:

- **`open`** (default): credentials optional, **but a supplied
  `session_secret` is always validated** — a wrong credential is never
  ignored (a bare `session_id` keeps its legacy attribution-only meaning).
- **`strict`**: `session_id` + `session_secret` are required and must match an
  open session belonging to the acting agent.

Enforcement is `verify_session_credentials` / `SessionTrustGuard`
(`application/identity.py`), run in its own read-only transaction before the
verb executes; errors are prescriptive (missing credentials name
`session_open` as the fix; a mismatch states which check failed without
echoing the stored secret). This is **cooperative authentication** — it stops
impersonation between well-behaved local agents, not a hostile process with
file access to `nexus.db`.

### D8 (M7) — Retention: terminal lanes age out, everything live is untouchable

`RetentionService.prune` (`application/retention.py`) enforces configured
windows — events 30 d, `read` deliveries 14 d, `closed` sessions 7 d
(`OKTO_NEXUS_RETENTION_*_KEEP_DAYS`; overridable per call) — under hard safety
invariants: **only terminal lanes are eligible**. `unread`/`delivered`/`parked`
deliveries, `active`/`stale` sessions, and ALL handoffs/tasks/messages/
channels/agents/workspaces/artifacts are never deleted regardless of age (the
lane predicates are baked into the adapters' SQL). Deletes run in bounded
batches (500 rows), each in its own write transaction, so the writer lock is
held briefly. Two entry points:

- **`okto-nexus admin prune`** — operator CLI (`adapters/inbound/cli/admin.py`)
  with `--dry-run` (count only), `--vacuum` (compact the file; deletes alone
  leave free pages), and per-window overrides. Scope is the **whole store**
  (every workspace shares one `nexus.db`; the inbox is global) —
  `--project-root` only anchors/validates the call.
- **`auto_prune_on_start`** (default `false`) — an opportunistic, bounded
  reaper at server startup (at most 4 batches per table), best-effort by
  design: a failure is reported to stderr and startup proceeds.

### D9 (M5) — Blocking is an adapter concern: the `Waiter` port

The application layer no longer holds any blocking primitive (no `time.sleep`
anywhere in `application/`). Long-poll waiting (`event_wait`,
`handoff_list_available`) goes through the **`Waiter` port**
(`application/ports.py`); the V1 adapter is `SleepPollWaiter`
(`adapters/outbound/waiter.py`): sleep at the configured poll cadence, and
between sleeps probe SQLite's **`PRAGMA data_version`** (a cheap, cached,
read-only, cross-process change counter via `ConnectionFactory.data_version`).
The caller's SELECT is re-run **only when some process committed a write** —
not once per interval. The probe fails **open towards delivery**: a degraded
probe reports a change after one interval, so the regular read path surfaces
the real `DB_ERROR` (or succeeds); a broken probe can never absorb a write or
park a caller past its timeout. A future **SSE/notify transport replaces only
this adapter** (block on a notification instead of sleeping) — same port, zero
change to the application layer.

### D10 (M11) — Residual point fixes

The review's closing batch of smaller defects, applied with this hardening
(each with a behavioural regression test):

- `shared.md` is the workspace-**public** view: the routing target of a
  non-`public` handoff is redacted as `[private]` instead of rendered raw.
- `os.replace` of `shared.md` gets a short bounded retry on Windows (a
  concurrent swap of the same destination can transiently fail with a sharing
  violation; POSIX is atomic already).
- The `tail` follower resolves `--from latest` in O(1) via `latest_cursor`
  (an indexed `MAX(event_id)`), replacing the page-walk that made startup
  O(log size).
- `message_create` flags `workspace_created: true` when a send materialises a
  brand-new workspace row (additive key; absent in the steady state).
- The adapter-level env knobs (`inbox_lease_ttl_seconds`,
  `session_stale_ttl_seconds`, `max_event_limit`, `max_shared_md_events`) moved
  from ad-hoc `os.environ` reads with silent fallbacks into `NexusConfig`,
  parsed **fail-closed** at startup (an invalid value is a `CONFIG_ERROR`, not
  a silently-applied default).
- The `tail` follower gains **opt-in resume** (`--cursor-file` — atomic
  checkpoint after every non-empty window; a crash re-emits at most one window,
  at-least-once like the inbox) and becomes a **passive observer** (it never
  stamps `last_seen_at`, so a detached monitor cannot keep an idle agent's
  liveness signal eternally fresh).

**Companion surface (same wave).** The "events are observability, not
delivery" principle (D2) also closes the handoff outcome gap: handoff
**outcome persistence** (`handoffs.result` / `handoffs.rejected_reason`,
migration `008`), **`handoff_get`** (read status/outcome by id —
creator/claimant always; others gated by visibility), **`handoff_cancel`**
(creator-only `OPEN → CANCELLED` retraction; `CANCELLED` becomes a produced
status), the D1b create-time policy for handoffs (`direct` to an unregistered
agent → `NOT_FOUND`; pool target matching 0 agents → explicit
`eligible_count`/`warning`), and **inbox notifications** for directed handoffs
and for the creator on complete/reject (`notified` in the responses). Full
reference in the README's Handoffs sections.

## Consequences

- **Positive.** No mid-transaction `SQLITE_BUSY` deaths; transient contention
  is machine-actionable (`retryable: true`). Every emitted event is reachable
  by some consumer, by construction. A default-configured agent harness can
  never be blocked or fed a second error grammar. Inbox polling is lock-free;
  poison messages cannot loop forever; senders can observe delivery instead of
  re-sending. One target grammar ends accept/reject drift between slices.
  Broadcast exclusions are explicit; impersonation requires file access, not
  just a tool call. The store's growth is boundable. The SSE migration path is
  a single adapter swap.
- **Negative / trade-offs.** `message_deliveries` carries more mutable state
  (`attempts`); `strict` trust requires every client to thread
  `session_id`+`session_secret` through sensitive calls; retention defaults to
  **off** (`auto_prune_on_start=false`), so an unmaintained store still grows
  until an operator prunes; the `data_version` probe holds one extra (read-only)
  connection per process; presence-bounded broadcasts mean an alive-but-silent
  agent (heartbeat older than 30 min) misses broadcasts — mitigated by the
  generous TTL and the explicit `excluded_stale` report.
- **Surface.** `SURFACE_REVISION` is `5` after this hardening (2 = post-S3
  safe-by-default surface; 3 = unified target/pagination grammar; 4 =
  presence + trust parameters; 5 = `event_get`/`event_wait` `stream`
  description aligned with `VALID_STREAMS` — the removed `task` stream is no
  longer advertised). All additions are backwards-compatible
  (new optional parameters / additive response keys); the only breaking change
  remains ADR 0001's S3 removal, which the `MIGRATED` shims keep prescriptive.

## References

- [ADR 0001 — Message inbox delivery](0001-message-inbox-delivery.md)
  (the V2 model this hardening operates on).
- Finding markers `M1`–`M10` are preserved as comments/test names in the
  codebase (e.g. `tests/test_ports_contract.py` for M2,
  `tests/test_tools_surface.py` for M3, `tests/test_inbox_service.py` for
  M4+M8, `tests/test_presence_trust.py` for M6+M10, `tests/test_retention.py`
  for M7).
