---
title: "ADR 0001 — Message inbox delivery (per-recipient lanes, global addressing)"
status: Accepted
date: 2026-06-09
supersedes: cursor-based message delivery (V1)
---

# ADR 0001 — Message inbox delivery

## Status

**Accepted.** Decisions D1–D3 and sub-decisions S1–S3 are all settled by the
product owner (see *Resolved sub-decisions*). Ready for the phased
implementation.

## Context — two failures of the V1 model

In V1 a message is an **append-only event** filtered at *read* time by
`workspace_id` + visibility + a per-reader **cursor**. "Receiving" a message is a
log scan. Two real failures follow:

1. **Workspace is a hard delivery wall.** Messages/events are strictly
   workspace-scoped (`can_view_message` requires identical `workspace_id`), yet
   **agents are global**. To DM a global agent the sender must first discover
   *which workspace the recipient is in* and post there. Observed bug: an agent
   addressed `target = {direct, agent_id: B}` but posted in **its own**
   workspace; B lives in another workspace, so the message was accepted
   (`ok:true`) and **silently never delivered**. Two defects in one: a needless
   workspace survey, and a silent zero-recipient send.

2. **Index-based retrieval is fragile.** Each reader tracks its own cursor over
   the global log. Lose the cursor, use the wrong index, or restart, and you
   **silently miss** messages. There is no per-recipient "still unread" state;
   `tail --from latest` only shows what is new from that point on.

Both have the same root cause: **delivery is lazy and reader-driven (log + cursor)
instead of a durable per-recipient inbox.**

## Decision

Separate two concepts V1 fused together:

| V1 (fused) | V2 (separated) |
|---|---|
| The event log **is** the delivery channel | **Event log** = observability/audit spine. Unchanged. `event_get`/`event_wait`/`tail` keep *watching* the bus. |
| "Receiving" = scan the log by workspace + visibility + cursor | **Per-agent inbox** = guaranteed delivery. Each intended recipient gets a durable entry that stays until they pull and acknowledge it. |

### D1 — Global per-agent inbox; workspace becomes context, not a wall

Direct/targeted messages address a **global `agent_id`** and are delivered to that
agent's **global inbox**, regardless of which workspace anyone is in. The message
still carries a `workspace_id` as **optional context** (threading, `shared.md`),
but delivery **no longer consults the workspace**. Channels, handoffs, events and
`shared.md` stay workspace-scoped — the project scope is a feature there.

> Result: to reach an agent you address the agent, not a workspace. The
> "workspace survey" disappears.

### D1b — No silent zero-recipient sends (the critique rule)

`message_create` resolves the **recipient set at send time** and reports it. A send
that would reach nobody is surfaced, never silently `ok`:

- `direct` to an **unknown** `agent_id` (no registered match) → **`NOT_FOUND`**
  (the whole unit of work rolls back; no message/delivery/event persists).
- `capability` / `role` / `broadcast` / `mixed` that match **0 agents** → the
  response still succeeds but carries `recipients: []` and an explicit
  `warning` (delivered to nobody) — **S2: success-with-warning, never silent**.
- Every successful send returns `recipients: [...]` and `delivered_count` so the
  sender always knows who actually got it.
- **Unsafe targets are rejected up front (`VALIDATION_ERROR`)** by
  `assert_deliverable_message_target`: `direct_with_fallback` (a time-based
  strategy that cannot fire eagerly — model timed escalation as a handoff) and a
  `broadcast`/`direct_with_fallback` **nested inside a `mixed`** (it would
  broadcast against the global registry). A bare top-level `broadcast` is allowed
  and stays workspace-bounded.

### D2 — Explicit ack, at-least-once (lease + redelivery)

Two lanes per recipient, addressed **without an index**:

- **`unread`** — written at send time; stays available until pulled.
- **`delivered`** (in-flight) — `inbox_pull` returns the unread set, flips them to
  `delivered`, and stamps a `lease_expires_at`. If the agent crashes before
  acknowledging, the lease expires and the entry returns to `unread`
  (**redelivery**), exactly like a handoff lease.
- **`read`** (history) — `inbox_ack` moves entries to `read`, freeing the queue.
  Ack is **idempotent by `message_id`**: it transitions any of the recipient's
  `unread`/`delivered` rows for those messages to `read` (so an ack that races a
  lease re-opening, or an ack of a peeked-but-unpulled message, still settles
  cleanly) and is a no-op for already-`read` or foreign ids. Content stays
  queryable as history; "moving to history" marks state, never deletes.

The inbox is to a message what the **claim/lease is to a handoff** — same
mechanics, minus the competition (every recipient has its own copy of state).

### D3 — Send-time fan-out to inboxes for every target

`direct`, `capability`, `role`, `broadcast`, `mixed` resolve their matching agents
**at send time** and write one inbox entry per recipient. Recipient resolution is
**point-in-time**: an agent that registers *after* the send does **not** receive
it. The event log still records `message.created` for observability, so late
joiners (and auditors) can still *see that it happened* via the log, even though
it is not in their inbox.

**`direct_with_fallback` is not a message target.** It is a lazy, *time-based*
strategy whose fallback is re-evaluated at *read* time — meaningless under eager
send-time delivery (and its `0`-delay form would broadcast against the global
registry). `assert_deliverable_message_target` rejects it (and a `broadcast`
nested in a `mixed`) with `VALIDATION_ERROR`. The strategy stays fully meaningful
for **handoffs** (lazily re-evaluated on `handoff_list_available` / claim);
senders who want timed escalation should model it as a handoff.

**S1 — audience scope of group targets.** `direct` is global (D1).
`capability` / `role` (and `mixed`) resolve against the **global** agent registry
(every agent advertising the skill/role, anywhere). A bare top-level `broadcast`
(and a no-target message) is **bounded to the sender's workspace** — its
**active-session participants** (the implicit scope is the sender's `project_root`;
there is no explicit `workspace_id`/`channel_id` scope field). This caps the blast
radius without a survey: a broadcast never reaches the whole bus. A `broadcast`
nested inside a `mixed` (which would resolve globally) is rejected (see D1b).

## Design

### Data model

New table (not workspace-scoped — the inbox is global):

```sql
-- migration 005_message_deliveries.sql
CREATE TABLE IF NOT EXISTS message_deliveries (
    delivery_id        TEXT PRIMARY KEY,            -- 'del_…'
    message_id         TEXT NOT NULL REFERENCES messages(message_id),
    recipient_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    status             TEXT NOT NULL,               -- 'unread' | 'delivered' | 'read'
    delivered_at       TEXT,                        -- when last pulled (lease start)
    lease_expires_at   TEXT,                        -- redelivery threshold
    read_at            TEXT,                        -- when acked into history
    created_at         TEXT NOT NULL,
    UNIQUE (message_id, recipient_agent_id)
);
CREATE INDEX IF NOT EXISTS idx_deliveries_inbox
    ON message_deliveries (recipient_agent_id, status);
CREATE INDEX IF NOT EXISTS idx_deliveries_lease
    ON message_deliveries (status, lease_expires_at);   -- Phase-2 lease sweep
```

`messages.workspace_id` stays `NOT NULL` (the **sender's** context); what changes
is that message **visibility/delivery for recipients no longer gates on
workspace** — it gates on "you have a delivery row (or you are the sender)."

### Tools

| Tool | Purpose | State change |
|---|---|---|
| `message_create` (changed) | resolve recipients at send time, write deliveries, emit `message.created`. Returns `{message_id, event_id, recipients:[…], delivered_count, warning?}` | inserts `unread` deliveries |
| `inbox_pull(agent_id, limit?)` | the index-free "give me my messages": returns unread (materialised), flips to `delivered`, sets lease | `unread → delivered` |
| `inbox_ack(agent_id, message_ids)` | move the recipient's entries for those messages to history (idempotent by message_id) | `unread`/`delivered → read` |
| `inbox_peek(agent_id, limit?)` | view unread/in-flight WITHOUT consuming; sweeps expired leases first | reopens expired leases |
| `inbox_count(agent_id)` | `{unread, in_flight, read}` counts; sweeps expired leases first | reopens expired leases |
| `inbox_history(agent_id, cursor?)` | the read lane (paginated) | none |

**Wakeup signal — deferred (the log is workspace-scoped, the inbox is global).**
The original plan emitted a `message.delivered` event on the recipient's `agent`
stream as an edge-trigger. But the event log is **strictly workspace-isolated**
(`can_agent_see_event`), while the inbox is **global** (D1): a recipient
operating in a *different* workspace than the sender would never see that wakeup
event. So Phase 2 does **not** emit a wakeup event. Recipients check their
durable global inbox directly — `inbox_count` / `inbox_peek` between turns, then
`inbox_pull`. The inbox being durable, nothing is lost by polling; a future
SSE/HTTP push transport (roadmap) replaces polling with server push without
relying on the workspace-scoped log. `message.created` is still emitted on the
sender's `workspace` stream for in-workspace observability/`tail`.

### What stays vs changes

- **Stays:** event log + `event_get`/`event_wait`/`tail` (observability);
  channels, handoffs, artifacts, `shared.md` (workspace-scoped). `message.created`
  still emitted on the `workspace` stream — so **workspace-level message
  observability (incl. body) survives via the log**, not a dedicated tool. The
  `messages` table also stays (storage; `inbox_*` joins it to materialise bodies).
- **Changes / removed (S3 — replace all message reading with the inbox):**
  `message_create` resolves recipients + writes deliveries. `message_wait`,
  `message_list`, and `message_get` are **REMOVED** (breaking). ALL message
  reading goes through `inbox_*` (`pull`/`peek`/`count`/`history`); cross-workspace
  / observer reads use the event log. This is a clean break, not a transition
  window.

### Validation / critique rules (D1b made concrete)

1. `direct` target whose `agent_id` is not a registered agent → reject the send.
2. Any send returns the resolved `recipients` and `delivered_count`; a sender can
   assert delivery instead of hoping.
3. A group send (`capability`/`role`/`mixed`/`broadcast`) matching 0 agents →
   `recipients: []` + explicit `warning` — never a silent success (**S2**).
4. A bare top-level `broadcast` (and a no-target message) is implicitly bounded to
   the sender's workspace **active-session participants** (sender excluded). The
   blast radius is capped without any explicit scope field; an empty workspace
   yields the rule-3 warning, **not** an error.
5. `direct_with_fallback`, and a `broadcast`/`direct_with_fallback` **nested in a
   `mixed`**, are rejected with `VALIDATION_ERROR`
   (`assert_deliverable_message_target`) — they would broadcast globally (**S1**).

## Resolved sub-decisions

- **S1 — Group audience scope.** `capability`/`role`/`mixed` resolve against the
  global registry. A bare top-level `broadcast` (and no-target) is bounded to the
  sender's workspace active-session participants — the blast radius is capped by
  the sender's `project_root`, not an explicit scope field. Constructions that
  would broadcast globally (`direct_with_fallback`; a `broadcast` nested in a
  `mixed`) are rejected with `VALIDATION_ERROR`. (`channel_id`-scoped broadcast is
  not implemented; channels are organizational labels with no membership.)
- **S2 — Zero-recipient (group targets).** Success **with explicit warning**
  (`recipients: []`, `warning`), never silent. (Direct-unknown stays a hard error.)
- **S3 — V1 cursor tools.** **Replace all message reading with the inbox.**
  `message_wait`, `message_list`, `message_get` are removed; `inbox_*` is the sole
  message-reading surface; the event log carries observer/cross-workspace reads.

## Phased implementation plan (once S1–S3 are settled)

1. **Schema + domain:** migration `005`, delivery model + pure recipient-resolution
   (reuse `is_agent_eligible`), lease/redelivery rules (reuse handoff lease logic).
2. **Application:** `MessageService.create` writes deliveries + the wakeup event;
   new `InboxService` (`pull`/`ack`/`peek`/`count`/`history`) with opportunistic
   lease expiry (mirroring `expire_old_leases`).
3. **Adapter tools:** `inbox_*` tools (Pulse-style param docs); `message_create`
   response gains `recipients`/`delivered_count`/`warning`.
4. **Docs:** README "How agents communicate" gains the inbox lanes; deprecate the
   cursor-for-delivery guidance in the server instructions.
5. **Tests:** delivery fan-out, at-least-once redelivery on lease expiry, ack →
   history, zero-recipient critique, global cross-workspace delivery, concurrent
   pull safety.

## Consequences

- **Positive:** reachability decoupled from workspace; no silent drops; robust
  index-free retrieval with at-least-once; delivery auditable (the `recipients`
  set is recorded). Reuses proven handoff lease mechanics.
- **Negative / trade-offs:** send-time fan-out means **late joiners miss**
  group/broadcast messages (accepted, D3); a new mutable projection
  (`message_deliveries`) sits beside the immutable log; `broadcast` blast radius
  needs bounding (S1).
