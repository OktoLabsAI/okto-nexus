# Okto Nexus

**Local Agent Coordination Bus** — a local-only [MCP](https://modelcontextprotocol.io)
stdio server that lets multiple AI coding agents coordinate on a shared project:
register identities, open sessions, exchange messages on channels, hand off work
with atomic single-winner claiming, publish artifacts, and tail an append-only
event log — entirely on one machine, backed by a single SQLite database, with
**zero network surface**.

Okto Nexus is the coordination substrate for a *team* of agents operating in the
same repository. Instead of talking to a cloud service or a message broker, every
agent speaks to the same local MCP server; all state lives in one SQLite file in
WAL mode, which is the single source of truth. Every coordinated entity is scoped
to a deterministic `workspace_id` derived from the project path, so two agents
pointed at the same real directory automatically share one coordination space —
and never see another workspace's data.

---

## Table of Contents

1. [Highlights](#highlights)
2. [Architecture](#architecture)
3. [Requirements & Installation](#requirements--installation)
4. [Configuration](#configuration)
5. [Running It / MCP Client Setup](#running-it--mcp-client-setup)
6. [Core Concepts](#core-concepts)
7. [Tool Reference](#tool-reference)
8. [Data Model](#data-model)
9. [Response Envelope & Error Catalog](#response-envelope--error-catalog)
10. [Operations](#operations)
11. [Troubleshooting](#troubleshooting)
12. [Example Flow](#example-flow)
13. [Testing](#testing)
14. [Project Layout](#project-layout)
15. [Limitations (V1 Non-Goals)](#limitations-v1-non-goals)
16. [Roadmap](#roadmap)
17. [License](#license)

---

## Highlights

- **Local-first, zero network surface.** MCP over **stdio** only. No HTTP, no
  sockets, no auth server, no cloud. The MCP host launches the `okto-nexus`
  command and talks to it through stdin/stdout.
- **SQLite WAL is the single source of truth.** One file (`~/.okto_nexus/nexus.db`
  by default). No in-memory cache, broker, or external store. Every connection
  enforces WAL + foreign keys + a busy timeout.
- **Deterministic workspace isolation.** `workspace_id = sha256(realpath(project_root))`.
  The client passes `project_root`; the server computes the hash. Every read and
  write is scoped to one workspace — the deliberate cross-workspace surfaces are
  the global-admin `workspace_list` and the global `agent_list`/`agent_get`/
  `capability_list` (agents are global identities).
- **Three ways to reach an agent, two delivery semantics.** Direct message
  (1:1, preferred), handoff (one *free* worker claims), or broadcast (disseminate
  info / open-ended discovery, last resort) — **pub/sub fan-out** for messages vs
  **competing-consumers** for handoffs. Peers and skills are discoverable
  (`agent_list` / `agent_get` / `capability_list`). See
  *[How agents communicate](#how-agents-communicate)*.
- **Append-only, monotonic event log.** A single global `events` table with a
  gapless `INTEGER AUTOINCREMENT` `event_id`. State mutations and their audit
  events commit in the **same transaction** (atomic).
- **Cursor pagination + long-polling without threads.** `event_get` /
  `event_wait` (and `handoff_list_available`) tail the log with cursors and an
  optional long-poll bounded by a configured ceiling — no sockets, threads, or
  subscriptions. Waiting goes through a **`Waiter` port** whose V1 adapter
  sleep-polls gated by a cheap `PRAGMA data_version` probe: the log is
  re-scanned only when some process actually committed a write (a future
  SSE/notify transport swaps in at the same port).
- **Durable per-agent inbox with at-least-once delivery (ADR 0001).** Messages
  fan out to a global inbox at send time; pulled messages are leased
  (caller-tunable, renewable via `inbox_extend`) and redelivered if unacked;
  poison messages park in a dead-letter lane after 5 attempts; `inbox_peek` /
  `inbox_count` / `inbox_history` / `message_status` are strictly read-only.
- **Cooperative trust + bounded growth (ADR 0002).** `trust_mode=strict`
  requires a per-session `session_secret` on every sensitive verb (in `open`
  mode a supplied secret is still validated); `okto-nexus admin prune` (and the
  opt-in `auto_prune_on_start`) enforce retention windows over terminal lanes
  only — live state is never deleted.
- **Atomic single-winner handoffs with leases.** Claiming is one conditional
  `UPDATE` (no TOCTOU race). Abandoned work returns to the pool via opportunistic
  lease expiry evaluated on access — no background reaper.
- **Routing / visibility / eligibility as pure functions.** Six target
  strategies, three visibilities; *seeing* is orthogonal to *claiming*.
- **Workspace-contained artifacts.** Inline (`text`/`json`/`markdown`) or
  by-reference (`file` + `path`), with strict path-containment checks that reject
  any path escaping the workspace root.
- **Deterministic human-readable view.** `shared_md_render` writes a four-section
  `shared.md` snapshot via atomic overwrite — never a source of truth, never read
  back.
- **Hexagonal architecture with an enforced import boundary.** `domain/` and
  `application/` are stdlib-only and may never import `sqlite3` or `mcp` (a test
  fails the build otherwise).
- **Closed, normative error catalog.** Exactly **18** error codes; no exception
  ever crosses the adapter boundary — anything unexpected normalizes to
  `INTERNAL_ERROR`. Transient WAL contention carries `details.retryable: true`
  so agents can branch without parsing messages.
- **Fail-closed bootstrap.** Config → home dir → DB connections → migrations →
  repos/emitter → tool auto-discovery, strictly ordered; any failure aborts.

---

## Architecture

Okto Nexus is a **hexagonal (ports & adapters)** application. Dependencies point
strictly **inward**: adapters depend on application ports; the application depends
on the domain; the domain depends on nothing but the standard library.

```
            INBOUND ADAPTER                              OUTBOUND ADAPTERS
  ┌──────────────────────────────┐            ┌────────────────────────────────┐
  │ adapters/inbound/mcp         │            │ adapters/outbound/sqlite       │
  │   server.py  (FastMCP, stdio)│            │   connection.py  (PRAGMAs/UoW) │
  │   tools/*  register(srv,deps)│            │   migrations.py  (runner)      │
  └──────────────┬───────────────┘            │   *_repo.py  (Sqlite*Repo)     │
                 │  depends on                │ adapters/outbound/file/store   │
                 │  (Protocols)               │ adapters/outbound/sharedmd     │
                 ▼                            │ adapters/outbound/clock        │
        ┌────────────────────────────────────┴──────────┐  │ implements ports
        │            APPLICATION (ports.py)              │◄─┘
        │  Clock · UnitOfWork · ConnectionFactory        │
        │  WorkspaceRepo · AgentRepo · SessionRepo       │   dependencies point
        │  EventRepo · EventEmitter · ChannelRepo        │   INWARD ↑↑
        │  MessageRepo · TaskRepo · HandoffRepo          │
        │  ArtifactRepo · FileStore · Repos              │
        └────────────────────┬───────────────────────────┘
                             ▼ depends on
        ┌────────────────────────────────────────────────┐
        │   DOMAIN (models, ids, routing, events, …)      │
        │   pure, stdlib-only, no I/O                      │
        └────────────────────────────────────────────────┘

  Import boundary enforced by tests/test_import_boundary.py:
  domain/ and application/ MUST NOT import  sqlite3  or  mcp.
```

**Layers**

- **`domain/`** — entity dataclasses and pure helpers (`ids`, `routing`,
  `events`, `messages`, `handoff`, `artifacts`, `models`, `base`). No I/O; never
  imports `sqlite3` or `mcp`.
- **`application/`** — `typing.Protocol` (`@runtime_checkable`) **ports** that are
  the seams of the hexagon, plus the use-case services. Inbound depends on the
  ports; outbound implements them. The concrete SQLite connection type is
  referenced as `Any` to keep this layer free of `sqlite3`.
- **`adapters/inbound/mcp/`** — the `FastMCP` stdio server and the auto-discovered
  tool modules. The MCP SDK is imported **lazily** (only inside `create_server` /
  `main`), so importing the package never requires the SDK.
- **`adapters/outbound/`** — SQLite repos, the workspace file store, the
  `shared.md` renderer, and `SystemClock`. These are the only places that import
  `sqlite3`.

**SQLite WAL as source of truth.** Each connection opens with
`isolation_level=None` (driver autocommit; transactions are explicit
`BEGIN`/`COMMIT`/`ROLLBACK`), `row_factory = sqlite3.Row`, and the three
mandatory PRAGMAs: `journal_mode=WAL`, `foreign_keys=ON`, and
`busy_timeout={busy_timeout_ms}`. A `SqliteUnitOfWork` opens **`BEGIN
IMMEDIATE`** on entry by default (`write=True`): the WAL write lock is acquired
up front, where `busy_timeout` applies, so a read-then-write sequence inside
the transaction can never die mid-way with `SQLITE_BUSY_SNAPSHOT`. Read-only
scopes pass `write=False` (deferred `BEGIN`; readers never queue behind
writers). The UoW commits on clean exit, rolls back on exception, always closes
the connection, and never suppresses exceptions. Failure to open/configure a
connection → `DB_ERROR`; lock/busy contention → `DB_ERROR` with
`details.retryable: true` (retry the same call).

**Fail-closed bootstrap (ordered).** `bootstrap()` in `server.py`:

1. `load_config(env, argv)` — resolve config (`CONFIG_ERROR` on bad input).
2. `ConnectionFactory(config)` — ensure `home_dir` exists (`mkdir(parents=True, exist_ok=True)`).
3. Configured SQLite connections via the factory.
4. `MigrationRunner(factory).apply()` — apply pending migrations (idempotent;
   `MIGRATION_ERROR` on failure).
5. `build_repos(clock)` + tool registration — **only** after the store is
   migrated and healthy.

`main()` catches `OktoNexusError` from bootstrap, prints
`[okto-nexus] bootstrap failed: {code}: {message}` to stderr, and returns exit
code `1`. If the `mcp` SDK is missing in `create_server`, it catches the
`ImportError`, prints an install hint, and returns `1`. On success it runs the
stdio server and returns `0`. The first argv token selects the mode: `tail`
dispatches to the NDJSON event-log follower and `admin` to the operator
maintenance commands (see [Operations](#operations)); anything else runs the
MCP server. With `auto_prune_on_start=true`, startup additionally runs one
bounded, best-effort retention pass (a failure is reported to stderr and
startup proceeds).

**Auto-discovery of tools.** `register_tools(server, deps)` iterates every module
under `okto_nexus.adapters.inbound.mcp.tools` (via `pkgutil.iter_modules` +
`importlib.import_module`); each module participates by exposing
`def register(server, deps) -> None`. `build_repos` is the **single composition
root** for persistence — it instantiates one concrete per port plus the shared
`SqliteEventEmitter` *before* any tool registers, so every slice reuses one
coherent backing store (each slice's own wiring is idempotent).

**Enforced import boundary.** `tests/test_import_boundary.py` AST-parses every
`.py` under `domain/` and `application/` and fails the suite if any `import` /
`from` names the `sqlite3` or `mcp` root (relative imports are always allowed).

---

## Requirements & Installation

- **Python:** `>= 3.11`.
- **Runtime dependencies:** `mcp >= 1.0`, `pydantic >= 2`.
- **Dev extra:** `pytest >= 8`.
- **Build backend:** `setuptools >= 68` (`src/` layout).
- **Console script entry point:** `okto-nexus = okto_nexus.adapters.inbound.mcp.server:main`.

Clone, create a virtual environment, and install editable with the dev extras.

**PowerShell (Windows):**

```powershell
git clone <repo-url> okto_nexus
cd okto_nexus
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

**Bash (macOS / Linux):**

```bash
git clone <repo-url> okto_nexus
cd okto_nexus
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the `okto-nexus` console script (the MCP stdio server). If the
`mcp` SDK is missing at runtime, `main()` exits `1` with the hint:
`pip install 'mcp>=1.0'` (or `pip install okto-nexus`).

Package: `okto-nexus` v`0.1.0` — *Okto Nexus - Local Agent Coordination Bus (MCP
stdio server)* · author Okto Labs · license Proprietary.

---

## Configuration

All settings live under the `OKTO_NEXUS_*` namespace. Precedence is strict:
**CLI flag > environment variable > default**. The CLI parser accepts both
`--flag value` and `--flag=value`. Invalid input (unparseable integer, value
below the minimum, out-of-vocabulary enum/boolean, unknown flag, unexpected
positional argument, or a flag with no value) fails closed with `CONFIG_ERROR` —
**never** a silently-applied default. Path values have `~` expanded; if
`OKTO_NEXUS_DB_PATH` is unset it is derived from the home directory.

| Environment variable | CLI flag | Default | Min | Description |
|---|---|---|---|---|
| `OKTO_NEXUS_HOME` | `--home` | `~/.okto_nexus` | — | Server home directory. Created idempotently at bootstrap. |
| `OKTO_NEXUS_DB_PATH` | `--db-path` | `{home}/nexus.db` | — | SQLite database file. Derived from `home` when unset. |
| `OKTO_NEXUS_BUSY_TIMEOUT_MS` | `--busy-timeout-ms` | `5000` | `0` | `PRAGMA busy_timeout` (ms) applied to every connection. |
| `OKTO_NEXUS_POLL_INTERVAL_MS` | `--poll-interval-ms` | `200` | `1` | Poll interval (ms) for waits / long-poll loops. |
| `OKTO_NEXUS_MAX_WAIT_TIMEOUT_SECONDS` | `--max-wait-timeout-seconds` | `30` | `0` | Ceiling (s) for blocking long-poll operations. |
| `OKTO_NEXUS_HANDOFF_LEASE_TTL_SECONDS` | `--handoff-lease-ttl-seconds` | `300` | `1` | TTL (s) of a claimed handoff's lease. |
| `OKTO_NEXUS_MAX_INLINE_BYTES` | `--max-inline-bytes` | `65536` | `1` | Inclusive ceiling (UTF-8 bytes) for inline content. |
| `OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS` | `--inbox-lease-ttl-seconds` | `300` | `1` | Default in-flight lease (s) for pulled inbox deliveries (per-pull override: `lease_seconds`). |
| `OKTO_NEXUS_SESSION_STALE_TTL_SECONDS` | `--session-stale-ttl-seconds` | `60` | `1` | Read-time threshold (s) after which a session's heartbeat reads `stale`. |
| `OKTO_NEXUS_PRESENCE_TTL_SECONDS` | `--presence-ttl-seconds` | `1800` | `1` | Presence window (s): a session is PRESENT (in the broadcast audience) only while its heartbeat is this fresh. |
| `OKTO_NEXUS_SESSION_REAP_SECONDS` | `--session-reap-seconds` | `86400` | `1` | Sessions silent past this (s) are opportunistically closed by `session_open`/`session_heartbeat`. |
| `OKTO_NEXUS_MAX_SHARED_MD_EVENTS` | `--max-shared-md-events` | `1000` | `1` | Hard ceiling for `shared_md_render`'s `limit_events`. |
| `OKTO_NEXUS_MAX_EVENT_LIMIT` | `--max-event-limit` | `1000` | `1` | Hard ceiling for the `limit` page size on `event_get` / `event_wait`. |
| `OKTO_NEXUS_TRUST_MODE` | `--trust-mode` | `open` | — | One of `open`, `strict`. `strict` requires `session_id` + `session_secret` on the sensitive verbs; `open` validates a supplied secret but does not require one. |
| `OKTO_NEXUS_RETENTION_EVENTS_KEEP_DAYS` | `--retention-events-keep-days` | `30` | `0` | Retention window (days) for the event log (prune-eligible past it). |
| `OKTO_NEXUS_RETENTION_READ_DELIVERIES_KEEP_DAYS` | `--retention-read-deliveries-keep-days` | `14` | `0` | Retention window (days) for acknowledged (`read`) deliveries. |
| `OKTO_NEXUS_RETENTION_CLOSED_SESSIONS_KEEP_DAYS` | `--retention-closed-sessions-keep-days` | `7` | `0` | Retention window (days) for `closed` sessions. |
| `OKTO_NEXUS_AUTO_PRUNE_ON_START` | `--auto-prune-on-start` | `false` | — | Boolean (`true/1/yes/on` / `false/0/no/off`). Run one bounded, best-effort retention pass at server startup. |

Retention only ever deletes **terminal** lanes (events past their window,
`read` deliveries, `closed` sessions) — see [Operations](#operations).
`load_config(env, argv=None)` is the single entry point and depends only on the
stdlib + `okto_nexus.errors` (it imports neither `mcp` nor `sqlite3`).

---

## Running It / MCP Client Setup

Okto Nexus speaks MCP over **stdio**. Register it with any MCP host that launches
stdio servers (e.g. Claude Desktop's `claude_desktop_config.json`) by pointing
the host at the `okto-nexus` command:

```json
{
  "mcpServers": {
    "okto-nexus": {
      "command": "okto-nexus",
      "env": {
        "OKTO_NEXUS_HOME": "~/.okto_nexus",
        "OKTO_NEXUS_HANDOFF_LEASE_TTL_SECONDS": "300",
        "OKTO_NEXUS_MAX_WAIT_TIMEOUT_SECONDS": "30"
      }
    }
  }
}
```

If `okto-nexus` is not on the host's `PATH`, point `command` at the venv entry
point instead — for example `/path/to/.venv/bin/okto-nexus`, or on Windows
`C:\\path\\to\\.venv\\Scripts\\okto-nexus.exe`. Any `OKTO_NEXUS_*` variable from
the [Configuration](#configuration) tables can be supplied via `env`; the
`NexusConfig` settings may alternatively be passed as CLI flags via an `args`
array (e.g. `"args": ["--max-inline-bytes", "131072"]`).

A successful `list_tools` from the client proves the store was migrated and all
tools registered (the bootstrap is fail-closed and ordered).

---

## Core Concepts

### How agents communicate

Everything below is the conceptual model; each idea maps to concrete tools.
Agents are **global identities** that coordinate **inside a workspace** (the
client passes `project_root`, the server derives the `workspace_id`). Three ways
to reach one another sit on top of **two delivery semantics** plus a **discovery**
layer.

**Two delivery semantics — the core distinction.**

| Semantics | Tool | Who receives | Use when |
|---|---|---|---|
| **Pub/sub fan-out** | `message_create` | **every eligible agent** can read it (a copy for all) | zero-or-many agents may legitimately read/act |
| **Competing consumers** | `handoff_create` | every eligible agent **sees** it, but only the **first** `handoff_claim` wins (others get `HANDOFF_ALREADY_CLAIMED`); an abandoned claim's lease expires and it returns to the pool | exactly **one free** agent should do the work |

A message is *information broadcast to those allowed to see it*; a handoff is *a
unit of work exactly one worker takes*. (Seeing is not acting — see
*[Routing / visibility / eligibility](#routing--visibility--eligibility)*: an item
can be visible to the whole workspace while only its target may claim it.)

**Discovery — who is out there?**

- **Structured registry:** `agent_list` (every agent + `role`/`capabilities`/`last_seen_at`),
  `agent_get` (one agent's details + last interaction), `capability_list` (which
  capabilities exist and who advertises them). Use these to find an `agent_id`, a
  role, or a capability **before** addressing.
- **Semantic discovery (broadcast a question):** when the answer is *not* in the
  registry — *"who owns application X?"*, *"who is impacted by change Y in
  XYZ?"* — broadcast an open question; only the relevant agents answer, and they
  reply **directly** to you.

**The three modes, in preference order (most targeted, least noise → least):**

1. **Direct message — the default.** `message_create` with
   `target={"strategy":"direct","agent_id":"<recipient>"}`. Most efficient, no
   spurious work. **Always reply directly** to whoever messaged you (target their
   `from_agent_id`) unless you deliberately mean to broadcast or hand off.
   *Examples:* answering a question, acknowledging, a 1:1 follow-up, returning a
   result to the requester.
2. **Handoff — when exactly one free agent should take the work.**
   `handoff_create` with a capability / role / broadcast target. Every eligible
   agent sees it; the first to `handoff_claim` owns it; the lease (TTL) returns
   abandoned work to the pool. *Example:* "OCR this scan" →
   `target={"strategy":"capability","capability":"ocr"}` (find the capability
   with `capability_list` first); one free OCR worker claims and completes. See
   *[Handoffs & leases](#handoffs--leases)*.
3. **Broadcast — last resort.** `message_create` with **no** `target`. Two valid
   uses: **(a) disseminate** instructive/contextual info to everyone
   (announcements, conventions, status, shared decisions); **(b) discovery** (the
   open questions above). **Never broadcast actionable "do X" requests** — an
   undirected ask can trigger **unwanted parallel work** (every eligible agent may
   act on it). Once discovery finds the owner, switch to a direct message (or a
   handoff for dispatchable work). A broadcast reaches the workspace's
   **present** participants — sessions with a heartbeat within
   `presence_ttl_seconds` (default 30 min); agents excluded for staleness are
   reported back to the sender in `excluded_stale` (never dropped silently).

**Addressing — the target strategies (shared by messages *and* handoffs).** The
`target` object decides *who is eligible*. Omitting it means broadcast.

| You want to reach… | `strategy` | `target` shape |
|---|---|---|
| one named agent | `direct` | `{"strategy":"direct","agent_id":"…"}` |
| anyone with a skill | `capability` | `{"strategy":"capability","capability":"ocr"}` (string, or a list = *any-of*) |
| anyone in a role | `role` | `{"strategy":"role","role":"reviewer"}` |
| everyone in the workspace | `broadcast` | `{"strategy":"broadcast"}` *(or omit `target`)* |
| several rules at once (OR) | `mixed` | `{"strategy":"mixed","rules":[ … ]}` |
| one agent now, a pool later | `direct_with_fallback` | `{"strategy":"direct_with_fallback","agent_id":"…","fallback_after_seconds":N,"fallback":<sub-target>}` |

Exact match rules (case-sensitivity, the inclusive fallback boundary) are in
*[Routing / visibility / eligibility](#routing--visibility--eligibility)*.

**Three independent axes — do not conflate them.**

| Axis | Set by | Decides |
|---|---|---|
| **Target** (routing) | `target` strategy | *who is eligible* to receive / claim |
| **Visibility** | `visibility` (`public` / `eligible` / `private`) | *who may see* it (messages default: `eligible` if targeted, else `public`; handoffs require it explicitly) |
| **Channel** | `channel_id` | *where it is filed* — an organizational label only |

**Channels are labels, not access boundaries.** There is no membership or ACL:
any agent in the workspace can read and post to **any** channel, and the channel
**never** decides who receives a message (the `target` does). Only `general` is
seeded; create the rest with `channel_create` (idempotent by name), discover them
with `channel_list`. When **listening**, **omit `channel_id`** to cover the whole
workspace across all channels — narrowing to one channel can make you miss
messages directed to you elsewhere. See *[Channels & messages](#channels--messages)*.

**Your inbox — how you receive messages (ADR 0001).** Messages addressed to you
are **delivered to your global inbox** and stay there until you read them — no
cursor, no index, regardless of which workspace they were sent in. Between turns,
`inbox_count` (cheap check); if `unread > 0`, `inbox_pull` returns them with their
body (leased), then `inbox_ack` once handled. Unacked messages are **redelivered**
(at-least-once). `inbox_peek` is a non-destructive look; `inbox_history` is the
read archive. After sending something that expects a reply, just check your inbox
on a later turn. `event_get`/`event_wait`/`okto-nexus tail` are for **observing**
the bus, not for receiving your own messages. See
*[Message delivery & the inbox](#message-delivery--the-inbox)*.

**Concept → tool quick map.**

| Goal | Tools |
|---|---|
| Discover agents / roles / capabilities | `agent_list`, `agent_get`, `capability_list` |
| Send a 1:1 message | `message_create` (`direct` target) |
| Broadcast info / ask an open question | `message_create` (no target) |
| Receive / read your messages | `inbox_count`, `inbox_pull`, `inbox_ack`, `inbox_peek`, `inbox_history` |
| Organize messages by topic | `channel_create`, `channel_list` |
| Dispatch work to one free worker | `handoff_create`, `handoff_list_available`, `handoff_claim`, `handoff_complete`, `handoff_reject`, `handoff_cancel`, `handoff_get` |
| Observe the whole bus | `event_get`, `event_wait`, `okto-nexus tail` |
| Identity & presence | `agent_register`, `session_open`/`session_heartbeat`/`session_close` |

### Workspace isolation

Each project is a coordinated *workspace* identified by a deterministic hash of
its real on-disk path:

```
workspace_id = sha256( realpath(project_root) ).hexdigest().lower()   # 64 hex chars
```

The **client** passes `project_root`; the **server** computes the hash — clients
never send a raw `workspace_id` (except `shared_md_render`, which takes the
already-resolved id). `resolve_realpath` uses `os.path.realpath(project_root, strict=True)`,
so symlinks are resolved and the path must exist; an empty, broken, or
nonexistent path → `WORKSPACE_UNRESOLVED`. There is **never** a fallback to a
shared/default workspace. `workspace_resolve` additionally requires the path to
be absolute (`VALIDATION_ERROR` otherwise) before attempting the realpath.

Every use case resolves the `workspace_id` up front and scopes all reads/writes
to it. Operations that take an entity id distinguish three cases:

- id exists nowhere → `NOT_FOUND`;
- id exists **in another** workspace → `WORKSPACE_MISMATCH` (never leaks the other
  workspace's row);
- id in the correct workspace → ok.

The cross-workspace reads are `workspace_list` (global-admin) and the global
`agent_list`/`agent_get`/`capability_list` (agents are global identities); every
workspace/session read stays scoped. Because `workspace_id` is a pure
function of `realpath`, identity is reproducible and aliasing-proof (two paths
with the same real target collide on purpose), with no client-side coordination.

### Identity: agents vs sessions

There are two distinct identity layers:

| Concept | What it is | Scope |
|---|---|---|
| `agent_id` | A **logical, global** agent identity (role + capabilities + metadata) | Global — *not* workspace-scoped |
| `session_id` | A **live instance** of an agent operating inside a workspace | Bound immutably to `(agent_id, workspace_id)` |

- **`agent_register`** upserts the logical identity by `agent_id`; re-registering
  updates `role` / `capabilities` / `metadata` without changing the id. It is
  independent of sessions and workspaces.
- **`session_open`** creates a session whose `session_id` is **assigned by the
  server** (`ses…`), bound to `(agent_id, workspace_id)`; both the workspace and
  the agent must already exist (`NOT_FOUND` otherwise), and a workspace is
  required (`WORKSPACE_REQUIRED`). The response includes a per-session
  **`session_secret`** (uuid4, returned **only** here — keep it): in
  `trust_mode=strict` the sensitive verbs (`message_create`,
  `handoff_claim`/`complete`/`reject`, `inbox_pull`/`ack`/`extend`) require
  `session_id` + `session_secret`, and in `open` mode a supplied secret is
  always validated (a wrong credential is never ignored).

**Session status is derived, not persisted as truth.** `session_heartbeat`
advances `last_heartbeat_at` and reports a derived status. *Stale* is computed at
read time: an `active` session whose last heartbeat is older than the stale TTL
(default **60 s**, via `OKTO_NEXUS_SESSION_STALE_TTL_SECONDS`) is reported as
`stale`, while its row stays `active`. `session_close` is **idempotent**: the
first call sets `status='closed'` + `closed_at` and emits `session.closed`; a
second call is a no-op (keeps the original `closed_at`, does not re-emit).

**Presence is one predicate.** A session is *present* iff its persisted status
is `active` **and** its last heartbeat is within `presence_ttl_seconds`
(default **30 min**). `IdentityService.list_present` is the single presence
read, and the **message broadcast audience uses the exact same predicate** —
a session listed as present is exactly a session that would receive a
broadcast, so "who is present" has one answer bus-wide. Heartbeat regularly:
agents whose every active session has gone heartbeat-stale are excluded from
broadcasts (surfaced to the sender in `excluded_stale`). There is still no
background thread, but `session_open` / `session_heartbeat` **opportunistically
reap** sessions silent past `session_reap_seconds` (default **24 h**, closed
with reason `stale`) — dead sessions that never called `session_close` stop
accumulating state forever.

> Session events (`session.opened` / `session.closed`) are emitted on the
> canonical **`workspace`** stream with `visibility="public"` and no routing
> `target`, so they ARE observable via `event_get` / `event_wait` like
> message/artifact events. (Historically they used an internal `"session"`
> stream with `visibility="workspace"` — neither value is in the canonical
> vocabularies, so those events were invisible to every consumer; the emit
> path now rejects out-of-vocabulary values fail-closed.)

### Event log + streams + long-polling

`events` is a single, global, **append-only** log. `event_id` is
`INTEGER PRIMARY KEY AUTOINCREMENT`; under the WAL single-writer it is **globally
monotonic**, never reused, never altered (no `UPDATE`/`DELETE` exists for the
log). Each event is assigned **inside** the transaction of the slice that emits
it (atomic coupling via `EventEmitter.emit`).

**Streams are semantic filters, not physical partitions:**

```
VALID_STREAMS = { workspace, agent, task, handoff }
```

`validate_stream` rejects anything else with `INVALID_STREAM` *before* any scan.
Note that `message.created` and `artifact.created` are published on the
**`workspace`** stream (the base observable stream) so consumers of `event_get` /
`event_wait` can actually see them; handoff events go on the `handoff` stream.

`event_get` is a non-blocking, cursor-paginated read:

- `cursor` is the **last `event_id` consumed**; the scan selects `event_id > cursor`
  (`normalize_cursor`: integer ≥ 0, `bool` rejected).
- `filters` keys are enumerated `{type, agent_id, task_id, handoff_id}` (equality,
  combined with **AND**); `task_id`/`handoff_id` come from the payload (not
  columns in V1).
- **Visibility** (`can_agent_see_event`) is applied in the application layer, so
  `next_cursor` advances past **every** examined event (filtered or not-visible) —
  nothing already scanned is re-returned.
- Returns `{events, next_cursor, has_more, timed_out: false}`. `has_more` is true
  iff a matched + visible event exists strictly beyond the page (via a
  `batch_size = limit + 1` probe). A "poisoned" event (malformed visibility/target)
  is treated as **not-visible**, so one bad event never wedges the stream.

`event_wait` is `event_get` plus a bounded wait on the **`Waiter` port** (no
socket/thread/subscription): it scans **before** waiting, so a non-empty first
page returns immediately (`timed_out=false`); on timeout it returns
`events:[]`, the **entry cursor unchanged**, and `timed_out=true`. The V1
waiter (`SleepPollWaiter`) sleeps in `poll_interval_ms` steps and, between
sleeps, probes SQLite's `PRAGMA data_version` (a cheap cross-process change
counter) — the log is **re-scanned only when some process committed a write**,
never once per interval; a degraded probe fails open (re-scan after one
interval, so the read path surfaces any real error). Clamps: `limit`
`None`→default, `<1` or non-int → `VALIDATION_ERROR`, above max → pinned to
max; `timeout_seconds` `None`→ceiling at the service layer (the MCP tool
defaults it to `0` = snapshot), `<= 0` → a single `event_get` with no sleep,
else `min(timeout, ceiling)`.

### Monitoring patterns (background follower)

These patterns are for **observing** the bus (audit/monitoring) — to *receive
messages addressed to you*, use your [inbox](#message-delivery--the-inbox), not
these. `event_wait` is a **blocking** long-poll: with `timeout_seconds > 0` the
call parks the caller's turn until an event arrives or the timeout expires. Pick
the mode that fits your harness so it is never forced to block:

- **Background follower (recommended).** If your harness can spawn a detached
  process, run the CLI follower and treat each NDJSON line as a notification —
  the agent loop stays free, idle cost ~0. It is the layer-clean replacement for
  reading `nexus.db` directly (visibility/routing stay enforced):

  ```bash
  okto-nexus tail --project-root <path> --agent-id <you> --from latest \
      --exclude-agent <you>          # drop your own echo
  ```

- **In-loop, no background.** Call with `timeout_seconds=0` for a **non-blocking
  snapshot** (single scan, no sleep) and poll between turns, advancing
  `cursor` → `next_cursor`. Don't use a long timeout if you can't park the turn.

- **Targeted wait.** A short `timeout_seconds` (e.g. 30) is fine to await the
  reply to a message you just sent, accepting the block.

Four things a real monitor must handle — the `tail` follower does all of them:

- **Own echo.** The follower emits *every* visible event, including the caller's
  own, so a naive monitor reacts to itself. `--exclude-agent <you>` drops them
  **client-side** (the `event_wait` filter is equality-only, so exclusion can't
  be server-side); `--from-agent <x>` includes a single author **server-side**.
- **Transient locks.** A momentary WAL lock surfaces as `DB_ERROR`; the follow
  loop retries those with bounded backoff (counter reset on each successful poll)
  while failing fast on terminal errors and surfacing a transient that won't
  clear. The cursor is not advanced across a failed poll, so no event is skipped.
- **Resume across restarts.** `--cursor-file PATH` (opt-in; the consumer owns
  the path) checkpoints the cursor atomically after every non-empty window; on
  restart an existing file precedes `--from`, a corrupted file fails closed
  (`CONFIG_ERROR`). A crash between flush and persist re-emits at most one
  window — at-least-once, coherent with the inbox lease/ack model.
- **Passive presence.** The follower never stamps the agent's `last_seen_at`
  (unlike the MCP `event_get`/`event_wait` tools), so a detached monitor cannot
  keep an otherwise-idle agent's liveness signal eternally fresh.

> The block is a property of the current **stdio** long-poll. The roadmap's
> SSE/HTTP transport would replace polling with server **push** (no blocking, no
> busy-wait), at which point the background-follower workaround becomes optional.

### Channels & messages

Channels are **lightweight organizational labels, not access boundaries**: there
is no membership or ACL, so every agent in the workspace can read and post to any
channel, and a channel never decides *who receives* a message — that is the
message `target` (see *Routing*). Only **`general`** is seeded per workspace
(idempotently, the first time `channel_list` touches it — no write path seeds it);
agents create any other channel they need with **`channel_create`** (idempotent
by name), so the bus is not pinned to a single purpose. A channel only **tags** a
message; it does not gate delivery (you **receive** messages through your
[inbox](#message-delivery--the-inbox), not by channel).

`message_create` requires non-empty `from_agent_id`, `subject`, and `body`
(`VALIDATION_ERROR` otherwise), enforces a **64 KB inclusive** inline limit on
`subject`/`body` (`CONTENT_TOO_LARGE` beyond), accepts `artifacts` only as a
**list of `artifact_id` references** (never inline blobs), validates `target`
against the shared routing schema, and supports threading via
`parent_message_id` (the parent must exist in the same workspace — and, when a
channel is set, the same channel — else `NOT_FOUND`). It then resolves the
recipient set and **fans out one inbox delivery per recipient** (see
*[Message delivery & the inbox](#message-delivery--the-inbox)*). The message row,
its deliveries, and the `message.created` event commit in the **same unit of
work**; the event goes on the `workspace` stream with `visibility = "eligible" if
target else "public"` for observability.

### Message delivery & the inbox

Receiving a message is **not** a log scan (V1's cursor model is gone, ADR 0001).
At send time `message_create` resolves the **recipient set** and writes one
**delivery row per recipient** into that recipient's **global inbox** — keyed by
`agent_id`, so a direct message reaches you in any workspace (the message keeps a
`workspace_id` only as context). The append-only event log still records
`message.created` for observability/`tail`; it is no longer the delivery channel.

**Recipient resolution** (`domain/inbox.py`, reusing `is_agent_eligible`):
`direct`/`capability`/`role`/`mixed` resolve against the **global** agent
registry; a bare top-level `broadcast` (and a no-target message) is **bounded to
the sender's workspace** — its **present** participants (sessions whose
heartbeat is within `presence_ttl_seconds`; the same single predicate
`list_present` uses) — and excludes the sender. Agents excluded because every
active session of theirs is heartbeat-stale are reported **explicitly** in
`excluded_stale` + a `warning` — reach them with a `direct` message (delivered
regardless of presence). A `direct` target naming an unregistered agent is
`NOT_FOUND` (the whole send rolls back); a group target matching nobody
succeeds with `recipients: []` + a `warning` (never a silent drop).
`direct_with_fallback` and a `broadcast` nested in a `mixed` are rejected
(`VALIDATION_ERROR`) — they would broadcast globally; model timed escalation
as a **handoff**.

**Index-free lanes, at-least-once, with a dead letter.** Each delivery moves
`unread` → `delivered` (in-flight, leased) → `read` (history). `inbox_pull`
atomically claims your claimable deliveries (unread + your own lease-expired
redeliveries) into in-flight and returns them with their body — no cursor;
`inbox_extend` renews the lease mid-turn; `inbox_ack` settles them into history;
an **unacked** in-flight delivery whose lease elapses is **redelivered** (exactly
the handoff lease mechanic), and a delivery that exhausts its claim attempts is
**`parked`** (dead-letter — visible via `inbox_peek(include_parked=true)` for the
recipient and `message_status` for the sender). `inbox_count`/`inbox_peek` are
**READ-ONLY** (no sweep — expired leases are *projected* as `unread` at read
time) and are the cheap between-turns check; `inbox_history` is the read
archive (keyset-paginated). This is the durable, lossless replacement for the
V1 cursor/`message_wait` model.

### Routing / visibility / eligibility

Eligibility/visibility live in `domain/routing.py`; the target **grammar**
(shape validation) lives in **`domain/targets.py`** — the *single source of
truth* every slice parses through (message send validation, handoff
descriptors, routing), so a target accepted on one write path can never be
rejected or silently reinterpreted on another. All are **total, deterministic,
I/O-free** functions. Malformed input → `VALIDATION_ERROR`; a well-formed rule
that simply does not match → `False` (not an error). Grammar constraints worth
knowing: `mixed` requires a **non-empty** `rules` list, a null/blank sub-rule
is rejected (it would silently resolve to a covert broadcast), and a
`broadcast` nested in a `mixed` is rejected everywhere — use a bare top-level
`{"strategy": "broadcast"}` instead.

**Six target strategies** (`is_agent_eligible`) — discriminator `strategy`/`kind`,
case-insensitive, `-`/space normalized to `_`:

| Strategy | Rule |
|---|---|
| `direct` | `agent_id == target.agent_id` (exact, opaque ids) |
| `capability` | capability held by the agent — exact, **case-sensitive** (string = membership; list = *any-of*); `preferred` is advisory only |
| `role` | `agent.role == target.role` (exact, **case-sensitive**) |
| `broadcast` | every agent in the workspace is eligible |
| `mixed` | union/**OR** of `target.rules` (each a sub-target); short-circuits on first match |
| `direct_with_fallback` | the direct agent is **always** eligible; after `now >= created_at + fallback_after_seconds` (**inclusive**, monotonic) the `fallback` (default broadcast) also becomes eligible |

An absent/blank `target` means **no restriction** → broadcast (everyone
eligible). `direct_with_fallback` requires valid `created_at` and `now`.

**Three visibilities** (`can_agent_see_event`), layered over eligibility and
**strictly workspace-isolated** (agent and item must share the same
`workspace_id`, both present, else `False`):

| Visibility | Who sees it |
|---|---|
| `public` | any agent in the same workspace |
| `eligible` | only agents `is_agent_eligible` approves |
| `private` | eligible-only; for non-`direct` targets, `private == eligible` (never widens beyond the eligible set) |

Default when the log's `visibility` is null: **`public`**. **Sender
carve-out:** the item's actor (`actor_agent_id`) always sees its own event —
eligibility never excludes a sender from its own audit trail (ADR 0001:
"you have a delivery row *or you are the sender*"). The emit path is
**fail-closed** (`validate_emit_vocabulary`): an out-of-vocabulary
`stream`/`visibility` (or a blank `type`) is rejected with `INTERNAL_ERROR`
before anything persists, so no event can ever be written that no consumer
could read.

**Claimability ≠ visibility.** *Seeing is not acting.* An item can be `public`
(visible to the whole workspace) while only its target may claim it. So even a
universally visible handoff still checks `is_agent_eligible` on claim and, if it
fails, returns `NOT_ELIGIBLE_TO_CLAIM`.

### Handoffs & leases

Status set: `OPEN`, `CLAIMED`, `COMPLETED`, `REJECTED`, `CANCELLED`.
(`IN_PROGRESS`, `BLOCKED`, `EXPIRED` are reserved for forward-compat, with no
producer.)

```
(none)  --create-->            OPEN
OPEN    --claim-->             CLAIMED
OPEN    --reject (direct)-->   REJECTED
OPEN    --cancel (creator)-->  CANCELLED
CLAIMED --complete (owner)-->  COMPLETED
CLAIMED --reject (owner)-->    REJECTED
CLAIMED --expire_old_leases--> OPEN
```

`COMPLETED` / `REJECTED` / `CANCELLED` are **terminal**; any transition off
this table → `INVALID_TRANSITION`. On `handoff_create`, `visibility` is
**mandatory and explicit** (missing/invalid → `VALIDATION_ERROR`). Owner rules:
`complete` only by `claimed_by` (`NOT_OWNER`) and only from `CLAIMED`; `reject`
by the owner of a `CLAIMED`, **or** by the `direct` target of an as-yet-unclaimed
`OPEN`; `cancel` only by the **creator** (`from_agent_id`) and only while `OPEN`
(a `CLAIMED` handoff is resolved by its claimant, or cancel it after the lease
expires and it reopens).

**Create-time recipient policy (D1b, mirrors `message_create`).** A `direct`
target naming an **unregistered** agent is a hard `NOT_FOUND` (full rollback —
a typo'd handoff must not sit `OPEN` forever; use `direct_with_fallback` for an
agent that will register later). A pool target
(capability/role/mixed/broadcast/`direct_with_fallback`) matching **zero**
currently-registered agents succeeds with `eligible_count: 0` + an explicit
`warning` — never silent, never fatal (eligibility is lazily re-evaluated at
claim time, so a later registrant can still claim; `handoff_cancel` retracts a
mistake).

**Outcome persistence + inbox notifications.** A directed handoff
(`direct`/`direct_with_fallback` naming a registered agent) lands one synthetic
notification in the named agent's **inbox** in the same transaction
(`notified` in the response) — the wakeup needs no polling; claiming still
happens via `handoff_claim`. `handoff_complete` persists `result` (and
`handoff_reject` persists `rejected_reason`) **on the handoff row** and
notifies the creator's inbox with the outcome. **`handoff_get`** is the
creator's path to a finished handoff's status/result by id — terminal handoffs
leave `handoff_list_available`, and lifecycle events are observability, not
delivery.

**Atomic claim — single winner, no TOCTOU.** Claiming is one conditional `UPDATE`:

```sql
UPDATE handoffs
   SET status='CLAIMED', claimed_by=?, lease_expires_at=?, updated_at=?
 WHERE handoff_id=? AND status='OPEN' AND workspace_id=?
```

`rowcount == 1` → winner (no select-then-update, no race). `rowcount == 0` →
reload to classify: present in workspace → `HANDOFF_ALREADY_CLAIMED`; present in
another → `WORKSPACE_MISMATCH`; else `NOT_FOUND`. No event is emitted on the
failure path. Before the `UPDATE`, the service still gates eligibility
(`NOT_ELIGIBLE_TO_CLAIM`).

**Leases (TTL) and opportunistic expiry.** On claim,
`lease_expires_at = now + handoff_lease_ttl_seconds`. `expire_old_leases` runs
**opportunistically** before `handoff_list_available` and `handoff_claim` (no
background job). Threshold is strict: `lease_expires_at < now` expires;
`== now` does not. Expiring reopens `CLAIMED → OPEN` (clearing
`claimed_by`/`lease_expires_at`, again via a conditional `UPDATE`) and emits
`handoff.expired` in the same transaction — returning abandoned work to the pool
without a dedicated reaper. `handoff_list_available` returns the `OPEN` handoffs
that are **visible *and* eligible** to the caller, paginated, with optional
long-poll (same waiter-gated mechanics and snapshot-by-default as `event_wait`).

**Trust.** `handoff_claim` / `handoff_complete` / `handoff_reject` are
sensitive verbs: in `trust_mode=strict` they require `session_id` +
`session_secret` (from `session_open`); in `open` mode the credentials are
optional but a supplied secret is always validated.

### Artifacts & path safety

Type whitelist (closed, case-insensitive): `{file, text, json, markdown}`.
Inline limit is **64 KB inclusive** (`ensure_within_inline_limit` measures UTF-8
byte length; `<= 65536` accepted, one byte over → `CONTENT_TOO_LARGE` with a hint
to store as `artifact_type='file'` + `path`). For `json`, well-formedness is
validated *after* the size ceiling (so a giant JSON is rejected by size, not an
expensive parse).

**Path containment** (`adapters/outbound/file/store.py`): every `path` reference
is checked with

```
resolved = realpath( join(root_real, relative_path) )
contained = commonpath([normcase(root), normcase(resolved)]) == normcase(root)
```

`commonpath` + `realpath` catch `..` escapes, external absolute paths, and
symlinks whose real target leaves the root → `PATH_OUTSIDE_WORKSPACE`; `normcase`
covers case-insensitive filesystems (Windows), and a `ValueError` (e.g. different
drives) counts as not-contained. A `path` supplied alongside `content` must still
be contained — escaping fails the whole put.

Other invariants: `artifact_id` is server-assigned (`art…`) and immutable;
`artifact.created` is emitted in the same UoW on the `workspace` stream with
`visibility="public"`; size is the content byte length (inline) or `os.path.getsize`
(path — a **stat**, never a read). `artifact_get` returns `NOT_FOUND` for an
unknown or other-workspace id (no leak); a `stored=path` artifact returns **only
path + metadata**, never the referenced file's bytes.

### shared.md — a derived view

`shared_md_render` writes a per-workspace, human-readable view at
`{home}/workspaces/{workspace_id}/shared.md`. The `workspace_id` must be 64-hex
lowercase (`VALIDATION_ERROR` otherwise; `WORKSPACE_REQUIRED` if absent;
`NOT_FOUND` if well-formed but nonexistent). It is **never a source of truth** —
SQLite (WAL) is the only truth, and this module only *produces* the file (the
system never reads it back). The renderer writes a temp file in the same
directory and `os.replace`s it over `shared.md` (**atomic overwrite** — no
observer sees a partial file; an FS failure → `RENDER_ERROR` with no partial
left behind).

Four fixed-order sections: (1) relevant agents / active sessions, (2) open tasks,
(3) open handoffs, (4) recent events (**newest-first** by descending `event_id`,
capped by `limit_events`, default 50, ceiling 1000). The read is a single
read-only transaction over committed state and embeds no wall-clock, so two
renders over the same state are **byte-identical**. `shared.md` is the
workspace-**public** view: the routing target of a non-`public` handoff
(`eligible`/`private`) is redacted as `[private]` instead of rendered raw, and
handoff payloads are never rendered.

---

## Tool Reference

**35 MCP tools** — 34 across seven slices, auto-discovered from
`adapters/inbound/mcp/tools/`, plus the server-level `nexus_info`. Every tool
returns the canonical envelope (success `{ok:true,data}` / failure
`{ok:false,error}`); the `@tool_envelope` decorator guarantees no exception
crosses the boundary. Consequently **every tool may also return
`INTERNAL_ERROR`** (and `DB_ERROR` when a SQLite repo fails) in addition to the
codes listed below.

#### `nexus_info`
Report the server's versions — call it when behaviour seems to disagree with
your cached tool schemas.
- **Request:** none.
- **Data:** `{package_version, schema_version, surface_revision}` —
  `surface_revision` increments on every change to the tool surface
  (names/parameters/defaults/semantics); `schema_version` is the highest
  applied DB migration; `package_version` is the installed distribution
  version (`"dev"` for a source checkout).
- **Errors:** none specific (boundary `INTERNAL_ERROR`/`DB_ERROR` only).

### Identity & Workspace

#### `workspace_resolve`
Resolve `project_root` to its deterministic `workspace_id` and upsert the
workspace row.
- **Request:** `project_root: str` (required); `display_name: str | None` (default `None`).
- **Data:** `{workspace_id, display_name, root_realpath, created_at, last_seen_at}`.
- **Errors:** `VALIDATION_ERROR` (missing/empty or non-absolute `project_root`),
  `WORKSPACE_UNRESOLVED` (unresolvable realpath).

#### `workspace_list`
GLOBAL-ADMIN — enumerate **all** workspaces (a deliberately cross-workspace
surface, alongside the global `agent_list`/`agent_get`).
- **Request:** none.
- **Data:** `{workspaces: [{workspace_id, display_name, root_realpath, created_at, last_seen_at}, …]}`.
- **Errors:** none specific (boundary `INTERNAL_ERROR`/`DB_ERROR` only).

#### `agent_register`
Upsert a logical, global agent identity; re-registering updates
role/capabilities/metadata.
- **Request:** `agent_id: str` (required); `role: str | None`; `capabilities: Any`; `metadata: Any` (all default `None`).
- **Data:** `{agent_id, role, capabilities, metadata, created_at, updated_at, last_seen_at}`.
- **Errors:** `VALIDATION_ERROR` (missing `agent_id`; or capabilities/metadata
  not JSON-serializable), `CONTENT_TOO_LARGE` (capabilities/metadata inline >
  `max_inline_bytes`).

> **`last_seen_at` (presence).** Every agent-attributed operation stamps the
> agent's `last_seen_at` (best-effort; a no-op for an unregistered actor): the
> identity ops (`agent_register`, `session_*`), `message_create`, the inbox ops
> (`inbox_pull`/`inbox_ack`), the handoff mutations
> (`create`/`claim`/`complete`/`reject`), and `event_get`/`event_wait`. Surfaced
> by `agent_list` and `agent_get`.

#### `agent_list`
Enumerate **all** registered agents (global; the agent-discovery surface for
addressing — find an `agent_id` before a direct message / directed handoff).
- **Request:** none.
- **Data:** `{agents: [{agent_id, role, capabilities, metadata, created_at, last_seen_at}, …]}`,
  ordered by `created_at`. `last_seen_at` is the agent's most recent action
  (`null` if it never acted).
- **Errors:** none specific (boundary `INTERNAL_ERROR`/`DB_ERROR` only).

#### `agent_get`
Return one agent's full details, including `last_seen_at` (its latest interaction).
- **Request:** `agent_id: str` (required).
- **Data:** `{agent_id, role, capabilities, metadata, created_at, last_seen_at}`.
- **Errors:** `VALIDATION_ERROR` (missing `agent_id`), `NOT_FOUND` (no such agent).

#### `capability_list`
GLOBAL — enumerate the distinct capabilities advertised across all registered
agents (discovery for capability-targeted addressing: know a capability exists
and who would match it before a `target: {strategy:"capability"}`).
- **Request:** none.
- **Data:** `{capabilities: [{capability, agent_count, agents:[…]}, …]}`, sorted
  by `capability` (and `agents` sorted per capability). Normalised exactly as
  capability routing matches: a flag-mapping keeps truthy keys, a list/string is
  its set; a falsey flag or blank name is excluded (so the advertised set equals
  the addressable set).
- **Errors:** none specific (boundary `INTERNAL_ERROR`/`DB_ERROR`). Malformed
  capabilities are rejected at `agent_register`, so a stored value always
  normalises cleanly here.

#### `session_open`
Open a session bound immutably to `(agent_id, workspace_id)`; server assigns
`session_id` (`ses…`) **and a per-session `session_secret`** (uuid4, returned
ONLY here — keep it for the sensitive verbs). Emits `session.opened` and
opportunistically reaps the workspace's sessions silent past
`session_reap_seconds`.
- **Request:** `agent_id: str` (required); `workspace_id: str | None` (default
  `None`, but **required in practice**); `metadata: Any` (default `None`).
- **Data:** `{session_id, agent_id, workspace_id, status:"active", started_at, last_heartbeat_at, session_secret}`.
- **Errors:** `WORKSPACE_REQUIRED`, `VALIDATION_ERROR` (missing `agent_id`;
  non-serializable metadata), `CONTENT_TOO_LARGE` (metadata inline), `NOT_FOUND`
  (workspace or agent nonexistent). No row created on failure.

#### `session_heartbeat`
Advance `last_heartbeat_at` and report derived status (`active`/`stale`). Emits
`session.heartbeat`. Heartbeating keeps you **present** (in the broadcast
audience, window `presence_ttl_seconds`) and clear of the opportunistic
stale-session reaper (which this call also runs for the workspace's long-dead
sessions).
- **Request:** `session_id: str` (required); `workspace_id: str | None` (default
  `None`; if given, membership is validated).
- **Data:** `{session_id, status, last_heartbeat_at}`.
- **Errors:** `VALIDATION_ERROR` (missing `session_id`), `NOT_FOUND`,
  `WORKSPACE_MISMATCH`. No mutation on failure.

#### `session_close`
Close a session (idempotent); repeating returns ok and stays `closed`. Only the
transition to `closed` emits `session.closed`.
- **Request:** `session_id: str` (required); `workspace_id: str | None` (default `None`).
- **Data:** `{session_id, agent_id, workspace_id, status:"closed", started_at, last_heartbeat_at, closed_at}`.
- **Errors:** `VALIDATION_ERROR` (missing `session_id`), `NOT_FOUND`, `WORKSPACE_MISMATCH`.

### Events & Polling

> Valid streams: `{workspace, agent, task, handoff}`. Valid `filters` keys
> (equality, AND-combined): `{type, agent_id, task_id, handoff_id}`. Each event:
> `{event_id, workspace_id, stream, type, payload, actor_agent_id, task_id, handoff_id, created_at}`.
> `limit` defaults to 100, max 1000 (override `OKTO_NEXUS_MAX_EVENT_LIMIT`).

#### `event_get`
Non-blocking, cursor-paginated read of the workspace event log (filters +
visibility applied before the envelope).
- **Request:** `project_root: str` (required); `agent_id: str` (required);
  `stream: str` (required); `cursor: int | None` (`None`→0); `limit: int | None`
  (`None`→100); `filters: dict | None` (default `None`).
- **Data:** `{events: [...], next_cursor: int, has_more: bool, timed_out: false}`.
- **Errors:** `WORKSPACE_REQUIRED` (missing `project_root`), `INVALID_STREAM`,
  `VALIDATION_ERROR` (missing `agent_id`; non-int/negative cursor; non-int/`<1`
  limit; non-mapping filters or unknown key), `WORKSPACE_UNRESOLVED`. Precedence:
  `WORKSPACE_REQUIRED` → `INVALID_STREAM` → `VALIDATION_ERROR` → `WORKSPACE_UNRESOLVED`.

#### `event_wait`
Read the event log; optionally long-poll until the first non-empty page or the
timeout (clamped to the configured ceiling), without socket/thread.
- **SAFE BY DEFAULT:** `timeout_seconds` omitted, `0` or `null` is an immediate
  **non-blocking snapshot** (single scan, no sleep). Blocking is an explicit
  opt-in: `timeout_seconds > 0` parks the caller's turn until an event arrives
  or the timeout expires (clamped to `max_wait_timeout_seconds`).
- **Request:** same as `event_get` + `timeout_seconds: int | None` (default `0`).
- **Data:** `{events: [...], next_cursor: int, has_more: bool, timed_out: bool}`.
  On timeout: `events:[]`, `next_cursor` = entry cursor, `timed_out: true`.
- **Errors:** same as `event_get` + `VALIDATION_ERROR` (non-int `timeout_seconds`;
  `bool` rejected).

### Channels & Messages

> Seeded channels per workspace: only `general` (agents create the rest with
> `channel_create`). Channels are organizational labels, not access boundaries —
> they never decide who receives a message (the `target` does). **Reading a
> message is the [Inbox](#inbox--message-delivery-adr-0001) slice's job** —
> `message_create` only sends; the per-recipient `inbox_*` tools receive.

#### `message_create`
Persist the message, **resolve its recipients and fan one inbox delivery per
recipient**, and emit `message.created` — all in the same (atomic) transaction.
- **Request:** `project_root: str` (required); `from_agent_id: str` (required);
  `subject: str` (required); `body: str` (required); `channel_id: str | None`;
  `from_session_id: str | None` (REQUIRED with `session_secret` in
  `trust_mode=strict`); `target: dict | None`; `artifacts: list[str] | None`;
  `parent_message_id: str | None`; `session_secret: str | None` (validated
  whenever supplied; required in `strict`) (all default `None`).
- **Data:** message shape **+** `event_id`, `recipients: [...]`, `delivered_count`,
  an optional `warning` (group target matched nobody, or agents were excluded
  for staleness), an optional `excluded_stale: [...]` (agents whose every
  active session has a heartbeat older than `presence_ttl_seconds` — they will
  NOT receive this broadcast; reach them with a `direct` message), and an
  optional `workspace_created: true` (present **only** when the send
  materialised a brand-new `workspaces` row; absent in the steady state —
  additive key, existing clients unaffected). Recipient resolution:
  `direct`/`capability`/`role`/`mixed` → the **global** registry;
  bare `broadcast`/no-target → this workspace's **present participants**
  (active sessions with a fresh heartbeat; the sender is excluded from group
  targets).
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing/empty from_agent_id/subject/body; malformed target; `direct_with_fallback`
  or a `broadcast` nested in `mixed`; artifacts not a list; missing credentials
  in `trust_mode=strict`), `CONTENT_TOO_LARGE` (subject/body >
  `max_inline_bytes`), `NOT_FOUND` (channel, parent message, unknown
  session_id, or a **`direct` target that is not a registered agent**),
  `NOT_OWNER` (session_secret mismatch, or session belongs to another agent),
  `INTERNAL_ERROR`.

### Inbox — message delivery (ADR 0001)

> The inbox is **global** (keyed by `agent_id`): a direct message reaches you in
> any workspace. Lanes per recipient: `unread` → `delivered` (in-flight, leased) →
> `read` (history), plus `parked` (dead-letter). At-least-once: an unacked pull
> is **redelivered** after the lease (`OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS`,
> default 300); a delivery claimed 5 times (`DEFAULT_MAX_DELIVERY_ATTEMPTS`)
> without an ack is **parked** instead of redelivered. `limit` defaults to 50,
> max 200. `inbox_peek` / `inbox_count` / `inbox_history` / `message_status` are
> **READ-ONLY** (`unit_of_work(write=False)` — polling never takes the WAL
> writer lock); only `pull`/`ack`/`extend` write. The three writers are
> sensitive verbs: in `trust_mode=strict` they require `session_id` +
> `session_secret` (from `session_open`); in `open` mode a supplied secret is
> still validated (`NOT_OWNER` on mismatch).

#### `inbox_pull`
Atomically claim your claimable deliveries (`unread` + your own lease-expired
redeliveries) into in-flight and return them **with their body**; index-free
(no cursor).
- **Request:** `agent_id: str` (required); `limit: int | None`;
  `lease_seconds: int | None` (size the lease for long turns; clamped to
  10–3600, default = lease TTL); `session_id: str | None` +
  `session_secret: str | None` (trust credentials — required in `strict`).
- **Data:** `{messages: [{delivery_id, message_id, status, delivered_at, lease_expires_at, read_at, from_agent_id, workspace_id, channel_id, subject, body, target, artifacts, created_at}, …], count}`.
- **Note:** a delivery on its 5th claim is parked (dead-letter) instead of
  returned; parked rows consume slots of THAT claim's `limit`, so a pull that
  parks poison messages may return fewer items — the next pull brings the rest.
- **Errors:** `VALIDATION_ERROR` (missing `agent_id`; non-positive `limit`;
  non-int/`bool` `lease_seconds`; missing credentials in `strict`),
  `NOT_FOUND`/`NOT_OWNER` (bad trust credentials).

#### `inbox_ack`
Move messages to history (read), freeing the queue. Idempotent by `message_id`.
- **Request:** `agent_id: str` (required); `message_ids: str | list[str]`
  (required); `session_id: str | None` + `session_secret: str | None` (trust
  credentials — required in `strict`).
- **Data:** `{acknowledged: int}` (rows transitioned). **Errors:**
  `VALIDATION_ERROR`, `NOT_FOUND`/`NOT_OWNER` (bad trust credentials).

#### `inbox_extend`
Renew the lease on messages you pulled but have not finished handling (long
turns), avoiding duplicate redelivery.
- **Request:** `agent_id: str` (required); `message_ids: str | list[str]`
  (required); `extend_seconds: int` (required; clamped to 10–3600); `session_id`
  + `session_secret` (trust credentials — required in `strict`). New lease =
  now + `extend_seconds`.
- **Data:** `{extended: int, lease_expires_at: str}`.
- **All-or-nothing:** if ANY id is not currently in-flight for you (never
  pulled / lease already expired / already acknowledged / parked) the call
  fails with a per-message reason and **nothing** is extended.
- **Errors:** `VALIDATION_ERROR`.

#### `inbox_peek`
READ-ONLY view of pending (`unread` + in-flight): nothing is leased, moved, or
swept — an in-flight delivery whose lease elapsed is *shown* as `unread` (its
effective lane, computed at read time).
- **Request:** `agent_id: str` (required); `limit: int | None`;
  `include_parked: bool` (default `false` — `true` also surfaces the
  dead-letter lane).
- **Data:** `{messages: [...], count}`. **Errors:** `VALIDATION_ERROR`.

#### `inbox_count`
READ-ONLY lane sizes `{unread, in_flight, read}`; an elapsed in-flight lease is
*counted* as `unread` (effective lane) without sweeping it. Parked deliveries
are excluded — inspect them with `inbox_peek(include_parked=true)`.
- **Request:** `agent_id: str` (required). **Errors:** `VALIDATION_ERROR`.

#### `inbox_history`
The `read` archive, newest-first, **keyset-paginated** (READ-ONLY): the opaque
cursor pins the page boundary to the last row seen, so acks between pages never
duplicate/hide items.
- **Request:** `agent_id: str` (required); `cursor: str | None` (**opaque** —
  pass back `next_cursor` verbatim; legacy numeric offset cursors are rejected
  with a prescriptive `VALIDATION_ERROR`); `limit: int | None`.
- **Data:** `{messages: [...], next_cursor: str | None, has_more: bool}`.
- **Errors:** `VALIDATION_ERROR`.

#### `message_status`
Sender-side observability (READ-ONLY): track a message you SENT instead of
re-sending when a recipient seems silent.
- **Request:** `message_id: str` (required — as returned by `message_create`).
- **Data:** `{message_id, deliveries: [{recipient, status, attempts, read_at}, …], count}`
  where `status` is the per-recipient **effective** lane: `unread` (queued, or
  lease expired awaiting redelivery), `delivered` (in flight), `read`
  (acknowledged), `parked` (dead-lettered after exhausting attempts).
- **Errors:** `VALIDATION_ERROR` (missing `message_id`), `NOT_FOUND`.

#### `channel_create`
Create a channel by name — **idempotent by name** (creating an existing name
returns it). Channels are organizational labels, not ACLs.
- **Request:** `project_root: str` (required); `name: str` (required — trimmed,
  ≤ 64 chars, no control characters, unique per workspace).
- **Data:** `{channel: {channel_id, workspace_id, name, created_at}, created: bool}`
  (`created: false` when the name already existed).
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (blank/overlong name or control characters).

#### `channel_list`
Return the workspace's channels (idempotently seeds the `general` default first).
- **Request:** `project_root: str` (required).
- **Data:** `{channels: [{channel_id, workspace_id, name, created_at}, …]}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`.

#### `message_get` / `message_list` / `message_wait` (migration shims)
Removed in S3 and kept as **permanent shims**: each always answers
`ok:false` with `code=MIGRATED` and a prescriptive message naming the exact
replacement call (`details.replacements` lists the new tools;
`details.removed_in: "S3"`). The shims declare no parameters, so every legacy
call shape lands on the guidance instead of failing schema validation.
Replacements: `message_get` → `inbox_pull`/`inbox_peek`/`inbox_history` (or
`event_get` for bus traffic); `message_list` → `inbox_peek`/`inbox_history`/
`event_get`; `message_wait` → `inbox_count` polling + `inbox_pull` (or
`event_wait` for explicit blocking).

### Handoffs

> Status: `OPEN`/`CLAIMED`/`COMPLETED`/`REJECTED`/`CANCELLED`. Visibilities:
> `{private, eligible, public}`. Target strategies:
> `{direct, capability, role, broadcast, mixed, direct_with_fallback}`.
> `handoff_list_available` `limit` defaults to 100, max 500. The mutating
> verbs `claim`/`complete`/`reject`/`cancel` are trust-gated (`session_id` +
> `session_secret` required in `trust_mode=strict`).

#### `handoff_create`
Create an `OPEN` handoff (validating target/visibility/limit) and emit
`handoff.created`. The `payload` (inline request body / work content) is stored
**with the row** and returned by `handoff_list_available`/`handoff_claim`, so a
worker reads the work without correlating the `handoff.created` event — pass an
`artifact_id` reference for large content. A `direct` target must name a
**registered** agent (else `NOT_FOUND`, full rollback) and lands an inbox
notification for it; a pool target matching 0 agents succeeds with an explicit
warning. After creating, poll `handoff_get` for the outcome.
- **Request:** `project_root: str` (required); `from_agent_id: str` (required);
  `target: Any` (required — descriptor with `strategy` + per-strategy fields);
  `visibility: str` (required — one of `{private, eligible, public}`);
  `payload: Any` (any JSON value — a string round-trips byte-for-byte, a
  non-string is stored/returned as opaque JSON text); `session_id: str | None`
  (default `None`).
- **Data:** `{handoff_id, workspace_id, status:"OPEN", created_at}` **+** for a
  directed target an optional `notified: [agent_id]` (the inbox notification
  landed); for pool targets `eligible_count` and, when it is `0`, an explicit
  `warning` (the handoff stays `OPEN` for later registrants — retract a
  mistake with `handoff_cancel`).
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing from_agent_id; missing/malformed target or unknown strategy/missing
  field; missing/unknown visibility), `NOT_FOUND` (`direct` target naming an
  unregistered agent), `CONTENT_TOO_LARGE` (payload inline).

#### `handoff_list_available`
Expire stale leases, then list `OPEN` handoffs visible **and** eligible to the
caller (paginated, with optional long-poll).
- **Request:** `project_root: str` (required); `agent_id: str` (required);
  `cursor: str | None` (`None`→0); `limit: int | None` (`None`→100);
  `timeout_seconds: int | None` (`None`→0 = no long-poll; clamped to
  `max_wait_timeout_seconds`).
- **Data:** `{handoffs: [{handoff_id, status, target, visibility, from_agent_id, payload, created_at}, …], next_cursor: str | None, has_more: bool, timed_out: bool}`. Each entry carries the `payload` so a worker can triage before claiming.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing agent_id; non-int/negative cursor; non-int/`<=0`/`bool` limit;
  non-numeric/negative/`bool` timeout_seconds).

#### `handoff_claim`
Atomically claim an `OPEN` handoff (single winner); expires leases first and gates
on eligibility. Emits `handoff.claimed`.
- **Request:** `project_root: str` (required); `handoff_id: str` (required);
  `agent_id: str` (required); `session_id: str | None` +
  `session_secret: str | None` (trust credentials — required in
  `trust_mode=strict`; a supplied secret is validated even in `open`).
- **Data:** `{handoff_id, workspace_id, status:"CLAIMED", claimed_by, lease_expires_at, payload}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing handoff_id/agent_id; missing credentials in `strict`), `NOT_FOUND`,
  `WORKSPACE_MISMATCH`, `NOT_ELIGIBLE_TO_CLAIM`, `HANDOFF_ALREADY_CLAIMED`,
  `NOT_OWNER` (bad trust credentials).

#### `handoff_complete`
Owner-only transition `CLAIMED → COMPLETED`. Emits `handoff.completed`,
**persists `result` on the row** (read it back with `handoff_get`), and
notifies the creator's inbox with the outcome.
- **Request:** `project_root: str` (required); `handoff_id: str` (required);
  `agent_id: str` (required); `result: Any` (default `None` — string verbatim,
  non-string as opaque JSON text); `session_id` + `session_secret` (trust
  credentials — required in `strict`).
- **Data:** `{handoff_id, status:"COMPLETED"}` + optional `notified: [creator]`
  (absent when the creator is unregistered or is the completing agent itself).
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing ids; non-serializable result; missing credentials in `strict`),
  `CONTENT_TOO_LARGE` (result inline), `NOT_FOUND`, `WORKSPACE_MISMATCH`,
  `INVALID_TRANSITION` (status ≠ CLAIMED), `NOT_OWNER` (agent_id ≠ claimed_by;
  or bad trust credentials).

#### `handoff_reject`
Reject: owner `CLAIMED → REJECTED` or direct-target `OPEN → REJECTED`. Emits
`handoff.rejected`, **persists `rejected_reason` on the row** (read it back
with `handoff_get`), and notifies the creator's inbox.
- **Request:** `project_root: str` (required); `handoff_id: str` (required);
  `agent_id: str` (required); `reason: str | None` (default `None`); `session_id`
  + `session_secret` (trust credentials — required in `strict`).
- **Data:** `{handoff_id, status:"REJECTED"}` + optional `notified: [creator]`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing ids; non-serializable reason; missing credentials in `strict`),
  `CONTENT_TOO_LARGE` (reason inline), `NOT_FOUND`, `WORKSPACE_MISMATCH`,
  `INVALID_TRANSITION` (terminal/invalid state), `NOT_OWNER` (non-owner of
  CLAIMED; non-direct-target of OPEN; or bad trust credentials).

#### `handoff_cancel`
Creator-only transition `OPEN → CANCELLED` — retract a handoff nobody should
take anymore (e.g. created with a pool target that matched zero agents). Emits
`handoff.cancelled` (the optional `reason` rides the event payload).
- **Request:** `project_root: str` (required); `handoff_id: str` (required);
  `agent_id: str` (required — must be the creator); `reason: str | None`
  (default `None`); `session_id` + `session_secret` (trust credentials —
  required in `strict`).
- **Data:** `{handoff_id, status:"CANCELLED"}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing ids; missing credentials in `strict`), `CONTENT_TOO_LARGE` (reason
  inline), `NOT_FOUND`, `WORKSPACE_MISMATCH`, `NOT_OWNER` (caller is not the
  creator; or bad trust credentials), `INVALID_TRANSITION` (CLAIMED — resolved
  by its claimant, or cancel after the lease expires; or already terminal).

#### `handoff_get`
Read ONE handoff by id — the creator's path to a finished handoff's outcome
(status, claimant, payload, `result`/`rejected_reason`). Runs opportunistic
lease expiry first, so an elapsed claim reads as `OPEN` again. READ access: the
creator and the claimant always may; any other agent is gated by the handoff's
visibility (the same predicate as `handoff_list_available`).
- **Request:** `project_root: str` (required); `handoff_id: str` (required);
  `agent_id: str` (required).
- **Data:** `{handoff_id, workspace_id, status, from_agent_id, target, visibility, claimed_by, lease_expires_at, payload, result, rejected_reason, created_at, updated_at}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing ids), `NOT_FOUND`, `WORKSPACE_MISMATCH`, `NOT_OWNER` (not
  creator/claimant and not admitted by visibility).

### Artifacts

> Types: `{file, text, json, markdown}` (case-insensitive). `stored ∈ {inline, path}`.

#### `artifact_put`
Register a `file`/`text`/`json`/`markdown` artifact in the resolved workspace and
emit `artifact.created` in the same transaction.
- **Request:** `project_root: str` (required); `artifact_type: str` (required);
  `name: str | None`; `path: str | None`; `content: str | None`; `metadata: Any`
  (all default `None`). Requires at least one of `path` or `content`.
- **Data:** `{artifact_id, workspace_id, artifact_type, stored, size_bytes, created_at}`
  (+ `path` when `stored="path"`).
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing/non-whitelisted artifact_type; neither path nor content; non-string
  content; malformed JSON when type=`json`; non-serializable metadata),
  `CONTENT_TOO_LARGE` (content inline > `max_inline_bytes`, inclusive),
  `PATH_OUTSIDE_WORKSPACE` (path escapes the workspace root).

#### `artifact_get`
Retrieve an artifact by id within the resolved workspace; a `stored=path` artifact
returns only path + metadata (never the file's bytes).
- **Request:** `project_root: str` (required); `artifact_id: str` (required).
- **Data:** `{artifact_id, workspace_id, artifact_type, stored, size_bytes, metadata, created_at}`
  + `content` (if `inline`) **or** `path` (if `path`).
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing artifact_id), `NOT_FOUND` (unknown or other-workspace id — no leak).

### shared.md

#### `shared_md_render`
Render the workspace's human-readable `shared.md` (atomic overwrite at
`{home}/workspaces/{workspace_id}/shared.md`), four deterministic sections.
- **Request:** `workspace_id: str` (required — 64-char lowercase hex);
  `limit_events: int` (default 50; must be 1..max, max default 1000 via
  `OKTO_NEXUS_MAX_SHARED_MD_EVENTS`).
- **Data:** `{path, workspace_id, bytes_written, sections_rendered, limit_events, generated_at}`.
- **Errors:** `WORKSPACE_REQUIRED` (missing/empty workspace_id), `VALIDATION_ERROR`
  (non-hex-64 workspace_id; non-positive-int/`bool`/out-of-range limit_events),
  `NOT_FOUND` (well-formed but nonexistent), `DB_ERROR` (SQLite read failure),
  `RENDER_ERROR` (atomic-write failure).

---

## Data Model

SQLite is the single source of truth. **Workspace invariant:** every coordinated
entity carries `workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id)` —
except `schema_migrations`, `workspaces` (the root itself), and `agents` (global,
unscoped identities). Timestamps are UTC ISO-8601 `TEXT`; JSON-ish columns
(`payload`, `capabilities`, `metadata`, `artifacts`, `target`) are `TEXT`.
`workspace_id = sha256(realpath(root))`.

| Table | PK | `workspace_id`? | Key columns | FKs / UNIQUE / indexes |
|---|---|---|---|---|
| `schema_migrations` | `version INTEGER` | no | `applied_at` | ledger of applied migrations |
| `workspaces` | `workspace_id TEXT` | is the root | `display_name`, `root_realpath`, `created_at`, `last_seen_at` | — |
| `agents` | `agent_id TEXT` | **no** (global) | `role`, `capabilities`, `metadata`, `created_at`, `last_seen_at` (migr. 004) | — |
| `sessions` | `session_id TEXT` | yes | `agent_id`, `status`, `started_at`, `last_heartbeat_at`, `closed_at` (migr. 002), `session_secret` (migr. 007) | FK→`agents`, FK→`workspaces`; idx `(workspace_id,status)`, `(workspace_id,agent_id)` |
| `events` | `event_id INTEGER AUTOINCREMENT` | yes | `stream`, `type`, `actor_agent_id`, `payload`, `visibility`, `target`, `created_at` | append-only/immutable; FK→`workspaces`; idx `(workspace_id,event_id)`, `(workspace_id,stream,event_id)` |
| `channels` | `channel_id TEXT` | yes | `name`, `created_at` | FK→`workspaces`; **UNIQUE(workspace_id,name)**; idx `(workspace_id,name)` |
| `messages` | `message_id TEXT` | yes | `from_agent_id`, `channel_id`, `from_session_id`, `target`, `subject`, `body`, `artifacts`, `parent_message_id`, `created_at` | FK→`workspaces`, FK→`channels`, self-FK→`messages`; idx `(workspace_id,created_at)`, `(workspace_id,channel_id,created_at)` |
| `message_deliveries` (migr. 005/006) | `delivery_id TEXT` | **no** (global inbox) | `message_id`, `recipient_agent_id`, `status` (`unread`/`delivered`/`read`/`parked`), `delivered_at`, `lease_expires_at`, `read_at`, `attempts` (migr. 006), `created_at` | FK→`messages`, FK→`agents`; **UNIQUE(message_id,recipient_agent_id)**; idx `(recipient_agent_id,status)`, `(status,lease_expires_at)`, keyset idx `(recipient_agent_id,status,read_at DESC,delivery_id DESC)` |
| `tasks` | `task_id TEXT` | yes | `title`, `description`, `status`, `created_by`, `created_at` | FK→`workspaces`; idx `(workspace_id,status)` |
| `handoffs` | `handoff_id TEXT` | yes | `task_id`, `from_agent_id`, `target`, `visibility`, `status`, `claimed_by`, `lease_expires_at`, `payload` (migr. 003), `result` + `rejected_reason` (migr. 008), `created_at`, `updated_at` | FK→`workspaces`, FK→`tasks`; idx `(workspace_id,status)`, `(workspace_id,target,status)` |
| `artifacts` | `artifact_id TEXT` | yes | `artifact_type`, `name`, `path`, `content`, `size_bytes`, `content_type`, `created_at` | FK→`workspaces`; idx `(workspace_id,artifact_type)` |

**Migrations** (shipped inside the package at `src/okto_nexus/migrations/`).
`001_core.sql` defines the core schema; `002_session_close.sql`,
`003_handoff_payload.sql`, and `004_agent_last_seen.sql`
are forward-only `ALTER TABLE … ADD COLUMN` migrations (adding `sessions.closed_at`,
`handoffs.payload`, and `agents.last_seen_at`); `005_message_deliveries.sql` adds
the global `message_deliveries` inbox table (ADR 0001);
`006_inbox_delivery_hardening.sql` adds `message_deliveries.attempts` (backs the
`parked` dead-letter lane) and the keyset history index;
`007_session_secret.sql` adds `sessions.session_secret` (the trust credential,
ADR 0002); `008_handoff_result.sql` adds `handoffs.result` +
`handoffs.rejected_reason` (terminal-outcome persistence behind `handoff_get`).
The runner discovers `migrations/NNN_*.sql` (regex `^(\d+)_.*\.sql$`), orders by
numeric version, and applies each pending one in its **own** `BEGIN IMMEDIATE`
transaction, recording `(version, applied_at)` in `schema_migrations` —
**durable per migration**: a failure in migration N keeps 1..N-1 committed
(forward-only by design; there is no all-or-nothing bootstrap rollback). The
ledger is re-checked under the write lock, so concurrent bootstraps are safe,
and a ledger version newer than the package knows fails closed. The statement
splitter is line-based (blank and `--` lines dropped; a statement boundary is a
line whose content ends in `;`) — so `;` may not be embedded in literals.
`apply()` is idempotent (returns `[]` when already current); any failure →
best-effort `ROLLBACK` of the failing migration + `MIGRATION_ERROR`.

---

## Response Envelope & Error Catalog

Every tool returns a canonical envelope; `data` and `error` are mutually
exclusive.

**Success** — `ok(data)`:

```json
{ "ok": true, "data": { "session_id": "ses-123", "status": "active" } }
```

`data=None` becomes `{}` — the `data` key is always a present mapping.

**Failure** — `err(code, message, details?)`:

```json
{
  "ok": false,
  "error": {
    "code": "WORKSPACE_REQUIRED",
    "message": "No workspace was provided.",
    "details": { "field": "workspace_id" }
  }
}
```

`details` appears only when truthy.

**The `tool_envelope` decorator** is the single choke point of the inbound
adapter — it guarantees no exception crosses the boundary:

- a handler returning a dict that already has an `ok` key passes through unchanged;
- any other mapping is wrapped by `ok(...)`; a non-mapping value becomes
  `ok({"result": value})`;
- an `OktoNexusError` becomes its `to_error_dict()` failure envelope;
- **any other exception** becomes `INTERNAL_ERROR` with
  `details.exception = type(exc).__name__`.

**Closed catalog of 18 error codes** (`errors.py`, a frozen, normative
`frozenset`; each serializes as its own string value):

| Code | Meaning |
|---|---|
| `WORKSPACE_REQUIRED` | Operation needs a workspace and none was provided. |
| `WORKSPACE_UNRESOLVED` | Workspace could not be resolved from context (bad/broken path). |
| `WORKSPACE_MISMATCH` | Entity belongs to a different workspace than requested. |
| `VALIDATION_ERROR` | Invalid input / payload validation failure. |
| `NOT_FOUND` | Target entity (session, task, handoff, …) does not exist. |
| `NOT_OWNER` | Actor is not the owner of the entity it tried to mutate. |
| `INVALID_TRANSITION` | State transition not allowed by the state machine. |
| `INVALID_STREAM` | Invalid/unknown event stream. |
| `HANDOFF_ALREADY_CLAIMED` | Handoff already claimed (lease still valid). |
| `NOT_ELIGIBLE_TO_CLAIM` | Caller is not eligible to claim the handoff. |
| `CONTENT_TOO_LARGE` | Inline content exceeds `max_inline_bytes`. |
| `PATH_OUTSIDE_WORKSPACE` | Resolved path escapes the workspace root. |
| `CONFIG_ERROR` | Invalid configuration (flag/env/value) at bootstrap. |
| `MIGRATION_ERROR` | Failure locating/applying migrations. |
| `DB_ERROR` | Failure opening/configuring the SQLite connection. |
| `RENDER_ERROR` | Failure rendering an output/representation. |
| `MIGRATED` | Tool was removed/renamed; the shim's message points at the replacement tool. |
| `INTERNAL_ERROR` | Catch-all for unexpected (unmapped) failures. |

`to_envelope_error(exc)` normalizes any exception: `OktoNexusError` verbatim,
everything else → `INTERNAL_ERROR` with *"An unexpected internal error occurred."*.

**Transient failures carry `details.retryable: true`.** SQLite lock/busy
contention (another process briefly holds the write lock) surfaces as
`DB_ERROR` with `details.retryable = true` and a message telling the caller to
simply retry the same call; the flag is absent on non-transient failures, so
agents can branch on it without parsing messages.

---

## Operations

Operator-facing concerns of a long-running bus: the CLI subcommands, retention,
trust, and the presence/staleness windows. (All knobs are in
[Configuration](#configuration); design rationale in
`docs/design/0002-design-review-hardening.md`.)

### CLI subcommands

The `okto-nexus` entry point dispatches on its first argument:

| Invocation | What it does |
|---|---|
| `okto-nexus [flags]` | Run the MCP stdio server (the default). |
| `okto-nexus tail …` | Follow the workspace event log as NDJSON (the background-monitor pattern — see [Monitoring patterns](#monitoring-patterns-background-follower)). |
| `okto-nexus admin prune …` | Enforce the retention windows and print a JSON report. |

Unrecognised flags on `tail`/`admin` (e.g. `--home`, `--db-path`) are forwarded
verbatim to the same fail-closed bootstrap the server uses, so config
precedence (CLI > env > default) is identical everywhere.

### Retention (`admin prune` / `auto_prune_on_start`)

The store is append-mostly by design — without pruning, `nexus.db` grows
without bound. `RetentionService.prune` deletes rows older than their window
under hard safety invariants:

- **Only terminal lanes are eligible:** events past `retention_events_keep_days`
  (default 30 d), `read` deliveries past
  `retention_read_deliveries_keep_days` (14 d), `closed` sessions past
  `retention_closed_sessions_keep_days` (7 d).
- **Never deleted, regardless of age:** `unread`/`delivered`/`parked`
  deliveries, `active`/`stale` sessions, and ALL handoffs, tasks, messages,
  channels, agents, workspaces and artifacts.
- **Bounded batches** (500 rows each, one write transaction per batch) keep the
  WAL writer lock brief; concurrent agents keep flowing.

```bash
# Count first (deletes nothing, skips --vacuum):
okto-nexus admin prune --project-root <path> --dry-run

# Enforce the configured windows and compact the file:
okto-nexus admin prune --project-root <path> --vacuum

# Override a window for this run only:
okto-nexus admin prune --project-root <path> --events-keep-days 7
```

Scope is the **whole store** — every workspace shares one `nexus.db` and the
inbox is global; `--project-root` only anchors/validates the call. Deletes
alone leave free pages inside the file; only `--vacuum` shrinks it on disk.
`auto_prune_on_start=true` additionally runs one bounded, incremental pass at
server startup (at most 4 batches per table; best-effort — a failure is
reported to stderr and startup proceeds; backlog converges across restarts or
via a full `admin prune`).

### Trust mode

`trust_mode=open` (default) keeps the cooperative posture: the sensitive verbs
(`message_create`, `handoff_claim`/`complete`/`reject`,
`inbox_pull`/`ack`/`extend`) accept optional credentials, but a **supplied**
`session_secret` is always validated — a wrong credential is never ignored.
`trust_mode=strict` requires `session_id` + `session_secret` (returned once by
`session_open`) on every sensitive verb. This is **cooperative
authentication**: it stops accidental/sloppy impersonation between local
agents, not a hostile process that can read `nexus.db` directly. Sessions
opened before the trust upgrade have no stored secret — close and reopen them.

### Presence & staleness windows

Three read-time windows govern session liveness (no background threads):

| Window | Default | Effect when exceeded |
|---|---|---|
| `session_stale_ttl_seconds` | 60 s | Session *reports* `stale` (row stays `active`). |
| `presence_ttl_seconds` | 30 min | Session leaves the **broadcast audience** (sender sees `excluded_stale`). |
| `session_reap_seconds` | 24 h | Session is opportunistically **closed** by the next `session_open`/`session_heartbeat` in the workspace. |

---

## Troubleshooting

Symptoms an agent (or its operator) actually meets, and the prescriptive fix:

- **`DB_ERROR` with `details.retryable: true`** — transient WAL contention
  (another process briefly held the write lock). Retry the **same call** after
  a short backoff (~0.5–2 s). The flag is absent on real failures — never
  retry those blindly. The `tail` follower retries transients itself with
  bounded backoff and never advances the cursor across a failed poll.
- **`MIGRATED` error** — you called a tool removed in S3 (`message_get`,
  `message_list`, `message_wait`). The error's `details.replacements` names the
  exact replacement calls (`inbox_*`, `event_get`/`event_wait`); switch to
  them — do **not** retry the old call.
- **Behaviour disagrees with your cached tool schemas** — call `nexus_info` and
  compare `surface_revision` with what you cached; it increments on every
  change to tool names/parameters/defaults/semantics. (MCP hosts typically
  don't re-discover tools mid-session — reconnect to refresh.)
- **A recipient seems silent** — don't re-send. `message_status(message_id)`
  shows the per-recipient lane: `unread` (not pulled yet, or lease expired and
  awaiting redelivery), `delivered` (in flight), `read` (acked), `parked`
  (dead-lettered after 5 unacked claims — inspect via
  `inbox_peek(include_parked=true)` on the recipient side).
- **Your broadcast reached fewer agents than expected** — check the response's
  `excluded_stale`: those agents' sessions are heartbeat-stale (older than
  `presence_ttl_seconds`). Reach them with a `direct` message (delivered
  regardless of presence) and remind them to `session_heartbeat`.
- **You keep receiving the same message** — you pulled it but never
  `inbox_ack`ed it before the lease elapsed (at-least-once redelivery). Ack
  what you finish; for long turns size the lease (`inbox_pull(lease_seconds=…)`)
  or renew it (`inbox_extend`).
- **`VALIDATION_ERROR`/`NOT_OWNER` on a sensitive verb** — the server runs
  `trust_mode=strict` (or you supplied a wrong secret in `open` mode). Pass
  the `session_id` + `session_secret` returned by **your own** `session_open`;
  a pre-upgrade session has no secret — open a new one.
- **`WORKSPACE_MISMATCH`** — the entity exists but belongs to another
  workspace. Check the `project_root` you are passing; workspace identity is
  `sha256(realpath(project_root))`, so two different paths to the same real
  directory are the *same* workspace, and different directories never share
  entities.

---

## Example Flow

A realistic two-agent coordination, all over the canonical
`{"ok": true, "data": …}` envelope. This mirrors the live MCP client in
[`scripts/live_client.py`](scripts/live_client.py), which spawns the **real**
server over the **real** stdio transport (a fresh `OKTO_NEXUS_HOME` temp dir) and
drives the full flow as any third-party MCP host would. The end-to-end smoke test
`tests/test_e2e_smoke.py` exercises the same path in-process.

1. **`workspace_resolve(project_root)`** → deterministic `workspace_id` (+ upserts
   the `workspaces` row).
2. **`agent_register(agent_id="builder", role="builder", capabilities=["py"])`** and
   a second `reviewer` agent.
3. **`session_open(agent_id="builder", workspace_id=…)`** → emits `session.opened`
   and returns a `session_secret` (keep it — required on the sensitive verbs in
   `trust_mode=strict`); **`session_heartbeat(session_id=…)`** keeps it `active`
   **and present** (in the broadcast audience).
4. **`message_create(project_root, from_agent_id="builder", subject, body, target={"strategy":"direct","agent_id":"reviewer"})`** →
   persists the message, fans an inbox delivery to `reviewer`, and emits
   `message.created` in the **same** transaction (the response carries `event_id`,
   `recipients`, `delivered_count`). The reviewer receives it with
   **`inbox_pull(agent_id="reviewer")`** → `inbox_ack(...)` — no cursor, any
   workspace. List channels with `channel_list` (only `general` is seeded — create
   others with `channel_create`).
5. **`event_wait(project_root, agent_id="reviewer", stream="workspace", cursor=0)`** →
   the reviewer observes `message.created` (cursor-paginated, visibility-filtered,
   long-poll bounded by `max_wait_timeout_seconds`).
6. **`handoff_create(project_root, from_agent_id="builder", target={"strategy":"direct","agent_id":"reviewer"}, visibility="public")`** →
   an `OPEN` handoff + `handoff.created` on the `handoff` stream.
7. **`handoff_list_available(project_root, agent_id="reviewer")`** →
   **`handoff_claim(handoff_id, agent_id="reviewer")`** (atomic single-winner,
   lease TTL applied) → **`handoff_complete(handoff_id, agent_id="reviewer")`** →
   `handoff.claimed` then `handoff.completed`.
8. **`artifact_put(project_root, artifact_type="text", content=…)`** (inline,
   `<= 64 KB`) and **`artifact_put(…, artifact_type="markdown", path="notes.md")`**
   (a workspace-contained path reference) → each emits `artifact.created`;
   **`artifact_get(artifact_id)`** round-trips the inline content + metadata.
9. **`shared_md_render(workspace_id)`** → atomically (over)writes the derived,
   four-section view at `{home}/workspaces/{workspace_id}/shared.md`.

Throughout, the append-only `events` table accumulates `session.opened`,
`message.created`, `handoff.created`, `handoff.claimed`, `handoff.completed`, and
`artifact.created` with global, gapless, monotonic `event_id`s.

Run the live client with the venv interpreter:

```powershell
.\.venv\Scripts\python.exe scripts\live_client.py
```

---

## Testing

The suite has **650+ tests** (`pytest`, `testpaths=["tests"]`, `pythonpath=["src"]`).

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

```bash
.venv/bin/python -m pytest -q
```

Notable coverage:

- **`tests/test_import_boundary.py`** — AST-parses every module under `domain/`
  and `application/` and fails if any imports the `sqlite3` or `mcp` root, keeping
  the hexagonal layering intact.
- **`tests/test_e2e_smoke.py`** — an in-process end-to-end smoke of the full
  coordination flow.
- **`tests/test_ports_contract.py`** — runs the same contract suite against the
  SQLite `EventRepo` *and* the unit-test fake, so fake-drift (the M2 root
  cause) fails the build.
- **`tests/test_connection.py` / `tests/test_migrations.py`** — the
  `BEGIN IMMEDIATE` concurrency contract, retryable `DB_ERROR`, and the
  per-migration transaction/ledger discipline.
- **`tests/test_tools_surface.py` / `tests/test_tool_schemas.py`** — the
  safe-by-default MCP surface (snapshot defaults, `MIGRATED` shims,
  `nexus_info`, one error grammar) asserted at behaviour and schema level.
- **`tests/test_presence_trust.py`** — the single presence predicate,
  `excluded_stale`, session reap, and the `open`/`strict` trust contract.
- **`tests/test_retention.py`** — terminal-lane-only pruning invariants,
  bounded batches, dry-run, and the `admin prune` CLI.
- **`scripts/live_client.py`** — a real out-of-process MCP stdio client (not a
  unit test) that initializes, lists tools, and drives the whole flow against a
  freshly migrated temp store; a successful `list_tools` already proves the store
  was migrated before any tool became callable.
- Per-slice unit tests: `test_identity`, `test_events`, `test_messages`,
  `test_message_delivery`, `test_inbox_service`, `test_handoff`,
  `test_artifacts`, `test_routing`, `test_targets`, `test_shared_md`,
  `test_tail`, `test_config`.

---

## Project Layout

```
okto_labs_okto_nexus/
├─ pyproject.toml                 # package metadata, deps, console script, pytest config
├─ docs/design/
│  ├─ 0001-message-inbox-delivery.md      # ADR: global inbox, lease/ack at-least-once
│  └─ 0002-design-review-hardening.md     # ADR: this hardening (M1–M11)
├─ scripts/
│  └─ live_client.py              # real MCP stdio client exercising the full flow
├─ src/okto_nexus/
│  ├─ config.py                   # NexusConfig + load_config (CLI > env > default, fail-closed)
│  ├─ errors.py                   # ErrorCode (18), OktoNexusError, retryable DB_ERROR helpers
│  ├─ envelope.py                 # ok()/err() + @tool_envelope + require_json_object_param
│  ├─ migrations/                 # NNN_*.sql shipped inside the package (001..008)
│  ├─ domain/                     # pure, stdlib-only
│  │  ├─ ids.py · routing.py · targets.py (single target grammar) · events.py
│  │  ├─ messages.py · inbox.py · handoff.py · artifacts.py · models.py · base.py
│  ├─ application/                # ports (Protocols) + use-case services
│  │  ├─ ports.py                 # incl. the Waiter port (blocking seam)
│  │  ├─ identity.py · events.py · messages.py · inbox.py
│  │  ├─ handoff.py · artifacts.py · shared_md.py · retention.py
│  └─ adapters/
│     ├─ inbound/
│     │  ├─ mcp/
│     │  │  ├─ server.py          # FastMCP stdio server + fail-closed bootstrap + nexus_info
│     │  │  └─ tools/             # auto-discovered register(server, deps) modules
│     │  │     ├─ identity.py · events.py · messages.py · inbox.py
│     │  │     ├─ handoff.py · artifacts.py · shared_md.py
│     │  └─ cli/
│     │     ├─ tail.py            # NDJSON event-log follower (okto-nexus tail)
│     │     └─ admin.py           # operator maintenance (okto-nexus admin prune)
│     └─ outbound/
│        ├─ sqlite/               # connection (IMMEDIATE UoW), migrations runner, *_repo
│        ├─ waiter.py             # SleepPollWaiter (data_version-gated long-poll)
│        ├─ file/store.py         # workspace-contained file store (path safety)
│        ├─ sharedmd/renderer.py  # atomic shared.md writer
│        └─ clock.py              # SystemClock
└─ tests/                         # 650+ tests incl. import boundary, contracts, e2e smoke
```

---

## Limitations (V1 Non-Goals)

- **Local only:** no HTTP / SSE / WebSocket transport — MCP over stdio only.
- **Cooperative trust, not real auth:** `trust_mode=strict` requires a
  per-session `session_secret` on the sensitive verbs, which stops
  impersonation *between cooperative local agents* — but secrets are stored in
  plaintext in `nexus.db`, so trust is still bounded by who can read the file /
  launch the process. No multi-tenant security.
- **No cloud sync / multi-host:** coordination is bounded by a single SQLite file
  on one machine.
- **No background threads:** session staleness, presence, handoff/inbox lease
  expiry, session reaping, and (opt-in) startup pruning are all
  derived/opportunistic at access time — there is no scheduler. Corollary:
  retention defaults to off, so an unmaintained store grows until an operator
  runs `okto-nexus admin prune` (or enables `auto_prune_on_start`).
- **No UI:** interaction is via MCP tools only.
- **Not vendor-specific:** any MCP host that launches stdio servers works; there
  is no integration tied to a particular vendor.
- **Inline content cap:** 65536 UTF-8 bytes (inclusive); larger payloads must be
  stored by `path` as `artifact_type='file'`.

---

## Roadmap

Post-V1 ideas (non-binding):

- **Streamable HTTP / SSE transport** alongside stdio, for remote/multi-host
  coordination and **push** instead of polling. The seam is already in place:
  the `Waiter` port isolates all blocking in one outbound adapter
  (`SleepPollWaiter`), so an SSE/notify waiter — and push delivery of inbox
  notifications — swaps in without touching the application layer (ADR 0002).
- **Richer streams & consumers:** make more event categories consumable, with
  finer-grained filtering and tailing.
- **Tasks surface:** the `tasks` table exists in the schema; expose task
  create/transition tools and wire them into handoffs.
- **Reserved handoff states:** activate `IN_PROGRESS` / `BLOCKED` / `CANCELLED` /
  `EXPIRED` with explicit producers.
- **Optional background reaper:** proactive session/lease expiry and continuous
  retention as an opt-in daemon (today both are opportunistic at access time —
  session reap, lease sweeps, and bounded startup pruning already exist).

---

## License

Proprietary © Okto Labs. All rights reserved. See `pyproject.toml`
(`license = { text = "Proprietary" }`). Replace this section with the project's
chosen license terms before any external distribution.
