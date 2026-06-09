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
10. [Example Flow](#example-flow)
11. [Testing](#testing)
12. [Project Layout](#project-layout)
13. [Limitations (V1 Non-Goals)](#limitations-v1-non-goals)
14. [Roadmap](#roadmap)
15. [License](#license)

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
- **Append-only, monotonic event log.** A single global `events` table with a
  gapless `INTEGER AUTOINCREMENT` `event_id`. State mutations and their audit
  events commit in the **same transaction** (atomic).
- **Cursor pagination + long-polling without threads.** `event_get` /
  `event_wait` (and `handoff_list_available`) tail the log with cursors and an
  optional poll-and-sleep long-poll bounded by a configured ceiling — no sockets,
  threads, or subscriptions.
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
- **Closed, normative error catalog.** Exactly **17** error codes; no exception
  ever crosses the adapter boundary — anything unexpected normalizes to
  `INTERNAL_ERROR`.
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
`busy_timeout={busy_timeout_ms}`. A `SqliteUnitOfWork` opens a `BEGIN` on entry,
commits on clean exit, rolls back on exception, always closes the connection, and
never suppresses exceptions. Failure to open/configure a connection → `DB_ERROR`.

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
stdio server and returns `0`.

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
below the minimum, unknown flag, unexpected positional argument, or a flag with
no value) fails closed with `CONFIG_ERROR`. Path values have `~` expanded; if
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

**Adapter-level env knobs** (resolved in the inbound adapter, *not* part of
`NexusConfig`, env-only — no CLI flag):

| Environment variable | Default | Description |
|---|---|---|
| `OKTO_NEXUS_SESSION_STALE_TTL_SECONDS` | `60` | Read-time threshold after which a session's last heartbeat is reported as `stale`. |
| `OKTO_NEXUS_MAX_EVENT_LIMIT` | `1000` | Hard ceiling for the `limit` page size on `event_get` / `event_wait`. |
| `OKTO_NEXUS_MAX_SHARED_MD_EVENTS` | `1000` | Hard ceiling for `shared_md_render`'s `limit_events`. |

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
  required (`WORKSPACE_REQUIRED`).

**Session status is derived, not persisted as truth.** `session_heartbeat`
advances `last_heartbeat_at` and reports a derived status. *Stale* is computed at
read time: an `active` session whose last heartbeat is older than the stale TTL
(default **60 s**, via `OKTO_NEXUS_SESSION_STALE_TTL_SECONDS`) is reported as
`stale`, while its row stays `active` — there is no background reaper in V1.
`session_close` is **idempotent**: the first call sets `status='closed'` +
`closed_at` and emits `session.closed`; a second call is a no-op (keeps the
original `closed_at`, does not re-emit).

> Session events are emitted on an internal `"session"` stream with
> `visibility="workspace"`, which is **not** among the consumable streams or
> canonical visibilities — i.e. they are internal audit only, deliberately *not*
> observable via `event_get` / `event_wait` (unlike message/artifact events).

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

`event_wait` is `event_get` plus a poll-and-sleep loop (no socket/thread/
subscription): it scans **before** sleeping, so a non-empty first page returns
immediately (`timed_out=false`); on timeout it returns `events:[]`, the **entry
cursor unchanged**, and `timed_out=true`. Clamps: `limit` `None`→default, `<1` or
non-int → `VALIDATION_ERROR`, above max → pinned to max; `timeout_seconds`
`None`→ceiling, `<= 0` → a single `event_get` with no sleep, else
`min(timeout, ceiling)`; polling steps by `poll_interval_ms`.

### Monitoring patterns (background follower)

`event_wait` / `message_wait` are **blocking** long-polls: with
`timeout_seconds > 0` the call parks the caller's turn until an event/message
arrives or the timeout expires. Pick the mode that fits your harness so it is
never forced to block:

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

Two things a real monitor must handle — the `tail` follower does both:

- **Own echo.** The follower emits *every* visible event, including the caller's
  own, so a naive monitor reacts to itself. `--exclude-agent <you>` drops them
  **client-side** (the `event_wait` filter is equality-only, so exclusion can't
  be server-side); `--from-agent <x>` includes a single author **server-side**.
- **Transient locks.** A momentary WAL lock surfaces as `DB_ERROR`; the follow
  loop retries those with bounded backoff (counter reset on each successful poll)
  while failing fast on terminal errors and surfacing a transient that won't
  clear. The cursor is not advanced across a failed poll, so no event is skipped.

> The block is a property of the current **stdio** long-poll. The roadmap's
> SSE/HTTP transport would replace polling with server **push** (no blocking, no
> busy-wait), at which point the background-follower workaround becomes optional.

### Channels & messages

Three channels are **seeded per workspace** —
`general`, `architecture`, `code-review` — created idempotently the first time a
workspace is touched by `channel_list` or a coordinated write (`_seed_channels`
only creates the missing ones).

`message_create` requires non-empty `from_agent_id`, `subject`, and `body`
(`VALIDATION_ERROR` otherwise), enforces a **64 KB inclusive** inline limit on
`subject`/`body` (`CONTENT_TOO_LARGE` beyond), accepts `artifacts` only as a
**list of `artifact_id` references** (never inline blobs), validates `target`
against the shared routing schema, and supports threading via
`parent_message_id` (the parent must exist in the same workspace — and, when a
channel is set, the same channel — else `NOT_FOUND`). The message row and the
`message.created` event commit in the **same unit of work**; the event goes on the
`workspace` stream with `visibility = "eligible" if target else "public"`.

`message_get` / `message_list` are workspace-scoped and honor routing visibility:
a directed message the viewer is not eligible to see is indistinguishable from
nonexistent (`NOT_FOUND` on get, omitted from list). `list` orders by insertion
(= `event_id` order) with offset pagination.

### Routing / visibility / eligibility

All in `domain/routing.py` — **total, deterministic, I/O-free** functions.
Malformed input → `VALIDATION_ERROR`; a well-formed rule that simply does not
match → `False` (not an error).

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

Default when the log's `visibility` is null: **`public`**.

**Claimability ≠ visibility.** *Seeing is not acting.* An item can be `public`
(visible to the whole workspace) while only its target may claim it. So even a
universally visible handoff still checks `is_agent_eligible` on claim and, if it
fails, returns `NOT_ELIGIBLE_TO_CLAIM`.

### Handoffs & leases

V1 status set: `OPEN`, `CLAIMED`, `COMPLETED`, `REJECTED`. (`IN_PROGRESS`,
`BLOCKED`, `CANCELLED`, `EXPIRED` are reserved for forward-compat, with no
producer in V1.)

```
(none)  --create-->            OPEN
OPEN    --claim-->             CLAIMED
OPEN    --reject (direct)-->   REJECTED
CLAIMED --complete (owner)-->  COMPLETED
CLAIMED --reject (owner)-->    REJECTED
CLAIMED --expire_old_leases--> OPEN
```

`COMPLETED` / `REJECTED` are **terminal**; any transition off this table →
`INVALID_TRANSITION`. On `handoff_create`, `visibility` is **mandatory and
explicit** (missing/invalid → `VALIDATION_ERROR`). Owner rules: `complete` only by
`claimed_by` (`NOT_OWNER`) and only from `CLAIMED`; `reject` by the owner of a
`CLAIMED`, **or** by the `direct` target of an as-yet-unclaimed `OPEN`.

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
long-poll.

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
renders over the same state are **byte-identical**.

---

## Tool Reference

**24 MCP tools** across six slices, auto-discovered from
`adapters/inbound/mcp/tools/`. Every tool returns the canonical envelope (success
`{ok:true,data}` / failure `{ok:false,error}`); the `@tool_envelope` decorator
guarantees no exception crosses the boundary. Consequently **every tool may also
return `INTERNAL_ERROR`** (and `DB_ERROR` when a SQLite repo fails) in addition
to the codes listed below.

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
> identity ops (`agent_register`, `session_*`), `message_create`, the handoff
> mutations (`create`/`claim`/`complete`/`reject`), and `event_get`/`event_wait`
> (so `message_wait` is covered via the long-poll). Surfaced by `agent_list` and
> `agent_get`.

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
`session_id` (`ses…`). Emits `session.opened`.
- **Request:** `agent_id: str` (required); `workspace_id: str | None` (default
  `None`, but **required in practice**); `metadata: Any` (default `None`).
- **Data:** `{session_id, agent_id, workspace_id, status:"active", started_at, last_heartbeat_at}`.
- **Errors:** `WORKSPACE_REQUIRED`, `VALIDATION_ERROR` (missing `agent_id`;
  non-serializable metadata), `CONTENT_TOO_LARGE` (metadata inline), `NOT_FOUND`
  (workspace or agent nonexistent). No row created on failure.

#### `session_heartbeat`
Advance `last_heartbeat_at` and report derived status (`active`/`stale`). Emits
`session.heartbeat`.
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
Long-poll: `event_get` in a loop until the first non-empty page or the timeout
(clamped to the configured ceiling), without socket/thread.
- **Request:** same as `event_get` + `timeout_seconds: int | None`
  (`None`→`max_wait_timeout_seconds`; `<= 0`→single `event_get`, no sleep).
- **Data:** `{events: [...], next_cursor: int, has_more: bool, timed_out: bool}`.
  On timeout: `events:[]`, `next_cursor` = entry cursor, `timed_out: true`.
- **Errors:** same as `event_get` + `VALIDATION_ERROR` (non-int `timeout_seconds`;
  `bool` rejected).

### Channels & Messages

> Seeded channels per workspace: `general`, `architecture`, `code-review`.
> `message_list` `limit` defaults to 50, max 200. Message shape:
> `{message_id, workspace_id, channel_id, from_agent_id, from_session_id, target, subject, body, artifacts, parent_message_id, created_at}`.

#### `message_create`
Persist the message and emit `message.created` in the same (atomic) transaction.
- **Request:** `project_root: str` (required); `from_agent_id: str` (required);
  `subject: str` (required); `body: str` (required); `channel_id: str | None`;
  `from_session_id: str | None`; `target: dict | None`; `artifacts: list[str] | None`;
  `parent_message_id: str | None` (all default `None`).
- **Data:** message shape **+** `event_id`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing/empty from_agent_id/subject/body; malformed target; artifacts not a
  list or empty item), `CONTENT_TOO_LARGE` (subject/body > `max_inline_bytes`),
  `NOT_FOUND` (channel or parent message), `INTERNAL_ERROR` (EventEmitter not wired).

#### `message_get`
Read a single message, workspace-scoped and visibility-filtered.
- **Request:** `project_root: str` (required); `message_id: str` (required);
  `agent_id: str | None` (default `None` = no visibility filter).
- **Data:** message shape.
- **Errors:** `VALIDATION_ERROR` (missing `message_id`), `WORKSPACE_REQUIRED`,
  `WORKSPACE_UNRESOLVED`, `NOT_FOUND` (nonexistent, other workspace, or
  not-visible — indistinguishable).

#### `message_list`
List workspace messages ordered by `event_id`, cursor-paginated and
visibility-filtered.
- **Request:** `project_root: str` (required); `channel_id: str | None`;
  `cursor: int | None` (`None`→0); `limit: int | None` (`None`→50);
  `agent_id: str | None` (`None` = no visibility filter).
- **Data:** `{messages: [...], next_cursor: int | None, has_more: bool}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (non-int cursor; non-int limit).

#### `message_wait`
Long-poll for new messages, **materialised with body** — collapses
`event_wait` → parse → `message_get` into one call. Reuses `event_wait` under
the hood (filtered to `message.created` on the `workspace` stream) and re-checks
visibility per message. **Blocking** — see *Monitoring patterns*.
- **Request:** `project_root: str` (required); `agent_id: str` (required, scopes
  visibility); `channel_id: str | None`; `cursor: int | None` (the **`event_id`**
  cursor, not the `message_list` offset); `limit: int | None`;
  `timeout_seconds: int | None` (`<= 0` → non-blocking snapshot).
- **Data:** `{messages: [...], next_cursor: int, has_more: bool, timed_out: bool}`.
  Cursor semantics are inherited from `event_wait` (a non-empty page advances
  past every scanned event; on timeout the entry cursor is returned unchanged).
- **Errors:** same as `event_wait` (`WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`,
  `VALIDATION_ERROR` for `agent_id`/cursor/limit/timeout), plus `INTERNAL_ERROR`
  (no `EventWaiter` wired).

#### `channel_list`
Return the workspace's seeded channels (idempotently seeds them first).
- **Request:** `project_root: str` (required).
- **Data:** `{channels: [{channel_id, workspace_id, name, created_at}, …]}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`.

### Handoffs

> Status: `OPEN`/`CLAIMED`/`COMPLETED`/`REJECTED`. Visibilities:
> `{private, eligible, public}`. Target strategies:
> `{direct, capability, role, broadcast, mixed, direct_with_fallback}`.
> `handoff_list_available` `limit` defaults to 100, max 500.

#### `handoff_create`
Create an `OPEN` handoff (validating target/visibility/limit) and emit
`handoff.created`. The `payload` (inline request body / work content) is stored
**with the row** and returned by `handoff_list_available`/`handoff_claim`, so a
worker reads the work without correlating the `handoff.created` event — pass an
`artifact_id` reference for large content.
- **Request:** `project_root: str` (required); `from_agent_id: str` (required);
  `target: Any` (required — descriptor with `strategy` + per-strategy fields);
  `visibility: str` (required — one of `{private, eligible, public}`);
  `payload: str | None`; `session_id: str | None` (default `None`). *(The use case
  accepts `task_id`, but the tool does not expose it.)*
- **Data:** `{handoff_id, workspace_id, status:"OPEN", created_at}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing from_agent_id; missing/malformed target or unknown strategy/missing
  field; missing/unknown visibility), `CONTENT_TOO_LARGE` (payload inline).

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
  `agent_id: str` (required); `session_id: str | None` (default `None`).
- **Data:** `{handoff_id, workspace_id, status:"CLAIMED", claimed_by, lease_expires_at, payload}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing handoff_id/agent_id), `NOT_FOUND`, `WORKSPACE_MISMATCH`,
  `NOT_ELIGIBLE_TO_CLAIM`, `HANDOFF_ALREADY_CLAIMED`.

#### `handoff_complete`
Owner-only transition `CLAIMED → COMPLETED`. Emits `handoff.completed`.
- **Request:** `project_root: str` (required); `handoff_id: str` (required);
  `agent_id: str` (required); `result: Any` (default `None`).
- **Data:** `{handoff_id, status:"COMPLETED"}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing ids; non-serializable result), `CONTENT_TOO_LARGE` (result inline),
  `NOT_FOUND`, `WORKSPACE_MISMATCH`, `INVALID_TRANSITION` (status ≠ CLAIMED),
  `NOT_OWNER` (agent_id ≠ claimed_by).

#### `handoff_reject`
Reject: owner `CLAIMED → REJECTED` or direct-target `OPEN → REJECTED`. Emits
`handoff.rejected`.
- **Request:** `project_root: str` (required); `handoff_id: str` (required);
  `agent_id: str` (required); `reason: str | None` (default `None`).
- **Data:** `{handoff_id, status:"REJECTED"}`.
- **Errors:** `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `VALIDATION_ERROR`
  (missing ids; non-serializable reason), `CONTENT_TOO_LARGE` (reason inline),
  `NOT_FOUND`, `WORKSPACE_MISMATCH`, `INVALID_TRANSITION` (terminal/invalid state),
  `NOT_OWNER` (non-owner of CLAIMED; or non-direct-target of OPEN).

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
| `agents` | `agent_id TEXT` | **no** (global) | `role`, `capabilities`, `metadata`, `created_at` | — |
| `sessions` | `session_id TEXT` | yes | `agent_id`, `status`, `started_at`, `last_heartbeat_at`, `closed_at` (migr. 002) | FK→`agents`, FK→`workspaces`; idx `(workspace_id,status)`, `(workspace_id,agent_id)` |
| `events` | `event_id INTEGER AUTOINCREMENT` | yes | `stream`, `type`, `actor_agent_id`, `payload`, `visibility`, `target`, `created_at` | append-only/immutable; FK→`workspaces`; idx `(workspace_id,event_id)`, `(workspace_id,stream,event_id)` |
| `channels` | `channel_id TEXT` | yes | `name`, `created_at` | FK→`workspaces`; **UNIQUE(workspace_id,name)**; idx `(workspace_id,name)` |
| `messages` | `message_id TEXT` | yes | `from_agent_id`, `channel_id`, `from_session_id`, `target`, `subject`, `body`, `artifacts`, `parent_message_id`, `created_at` | FK→`workspaces`, FK→`channels`, self-FK→`messages`; idx `(workspace_id,created_at)`, `(workspace_id,channel_id,created_at)` |
| `tasks` | `task_id TEXT` | yes | `title`, `description`, `status`, `created_by`, `created_at` | FK→`workspaces`; idx `(workspace_id,status)` |
| `handoffs` | `handoff_id TEXT` | yes | `task_id`, `from_agent_id`, `target`, `visibility`, `status`, `claimed_by`, `lease_expires_at`, `created_at`, `updated_at` | FK→`workspaces`, FK→`tasks`; idx `(workspace_id,status)`, `(workspace_id,target,status)` |
| `artifacts` | `artifact_id TEXT` | yes | `artifact_type`, `name`, `path`, `content`, `size_bytes`, `content_type`, `created_at` | FK→`workspaces`; idx `(workspace_id,artifact_type)` |

**Migrations.** `migrations/001_core.sql` defines the core schema;
`002_session_close.sql` is forward-only (`ALTER TABLE sessions ADD COLUMN closed_at TEXT;`).
The runner discovers `migrations/NNN_*.sql` (regex `^(\d+)_.*\.sql$`), orders by
numeric version, applies unregistered ones inside **one** explicit transaction,
and records `(version, applied_at)` in `schema_migrations`. The statement splitter
is line-based (blank and `--` lines dropped; a statement boundary is a line whose
content ends in `;`) — so `;` may not be embedded in literals. `apply()` is
idempotent (returns `[]` when already current); any failure → best-effort
`ROLLBACK` + `MIGRATION_ERROR`.

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

**Closed catalog of 17 error codes** (`errors.py`, a frozen, normative
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
| `INTERNAL_ERROR` | Catch-all for unexpected (unmapped) failures. |

`to_envelope_error(exc)` normalizes any exception: `OktoNexusError` verbatim,
everything else → `INTERNAL_ERROR` with *"An unexpected internal error occurred."*.

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
3. **`session_open(agent_id="builder", workspace_id=…)`** → emits `session.opened`;
   **`session_heartbeat(session_id=…)`** keeps it `active`.
4. **`message_create(project_root, from_agent_id="builder", subject, body)`** →
   persists the message and emits `message.created` in the **same** transaction
   (the response carries the assigned `event_id`). Read it back with `message_get`
   / `message_list`; list seeded channels with `channel_list`.
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

The suite has **262 tests** (`pytest`, `testpaths=["tests"]`, `pythonpath=["src"]`).

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
- **`scripts/live_client.py`** — a real out-of-process MCP stdio client (not a
  unit test) that initializes, lists tools, and drives the whole flow against a
  freshly migrated temp store; a successful `list_tools` already proves the store
  was migrated before any tool became callable.
- Per-slice unit tests: `test_identity`, `test_events`, `test_messages`,
  `test_handoff`, `test_artifacts`, `test_routing`, `test_shared_md`.

---

## Project Layout

```
okto_labs_okto_nexus/
├─ pyproject.toml                 # package metadata, deps, console script, pytest config
├─ migrations/
│  ├─ 001_core.sql                # core schema (workspaces, agents, sessions, events, …)
│  └─ 002_session_close.sql       # forward-only ALTER: sessions.closed_at
├─ scripts/
│  └─ live_client.py              # real MCP stdio client exercising the full flow
├─ src/okto_nexus/
│  ├─ config.py                   # NexusConfig + load_config (CLI > env > default)
│  ├─ errors.py                   # ErrorCode (17), OktoNexusError, to_envelope_error
│  ├─ envelope.py                 # ok()/err() + @tool_envelope boundary decorator
│  ├─ domain/                     # pure, stdlib-only
│  │  ├─ ids.py · routing.py · events.py · messages.py
│  │  ├─ handoff.py · artifacts.py · models.py · base.py
│  ├─ application/                # ports (Protocols) + use-case services
│  │  ├─ ports.py
│  │  ├─ identity.py · events.py · messages.py
│  │  ├─ handoff.py · artifacts.py · shared_md.py
│  └─ adapters/
│     ├─ inbound/mcp/
│     │  ├─ server.py             # FastMCP stdio server + fail-closed bootstrap
│     │  └─ tools/                # auto-discovered register(server, deps) modules
│     │     ├─ identity.py · events.py · messages.py
│     │     ├─ handoff.py · artifacts.py · shared_md.py
│     └─ outbound/
│        ├─ sqlite/               # connection, migrations, *_repo, event emitter
│        ├─ file/store.py         # workspace-contained file store (path safety)
│        ├─ sharedmd/renderer.py  # atomic shared.md writer
│        └─ clock.py              # SystemClock
└─ tests/                         # 262 tests incl. import boundary + e2e smoke
```

---

## Limitations (V1 Non-Goals)

- **Local only:** no HTTP / SSE / WebSocket transport — MCP over stdio only.
- **No auth / multi-tenant security:** identities are cooperative, not
  authenticated; trust is bounded by who can launch the process.
- **No cloud sync / multi-host:** coordination is bounded by a single SQLite file
  on one machine.
- **No background workers:** session staleness and handoff lease expiry are
  derived/opportunistic at read time — there is no scheduler or reaper.
- **No UI:** interaction is via MCP tools only.
- **Not vendor-specific:** any MCP host that launches stdio servers works; there
  is no integration tied to a particular vendor.
- **Inline content cap:** 65536 UTF-8 bytes (inclusive); larger payloads must be
  stored by `path` as `artifact_type='file'`.

---

## Roadmap

Post-V1 ideas (non-binding):

- **Streamable HTTP transport** alongside stdio, for remote/multi-host
  coordination.
- **Richer streams & consumers:** make more event categories consumable, with
  finer-grained filtering and tailing.
- **Tasks surface:** the `tasks` table exists in the schema; expose task
  create/transition tools and wire them into handoffs.
- **Reserved handoff states:** activate `IN_PROGRESS` / `BLOCKED` / `CANCELLED` /
  `EXPIRED` with explicit producers.
- **Optional background reaper:** proactive session/lease expiry as an opt-in.

---

## License

Proprietary © Okto Labs. All rights reserved. See `pyproject.toml`
(`license = { text = "Proprietary" }`). Replace this section with the project's
chosen license terms before any external distribution.
