# Okto Nexus

**Local Agent Coordination Bus** — a local-only [MCP](https://modelcontextprotocol.io)
stdio server that lets multiple AI coding agents coordinate on a shared project:
exchange messages, hand off work, track tasks, and observe an append-only event
log — all within a single machine, with **zero network surface**.

## Purpose

Okto Nexus is the coordination substrate for a team of agents working in the
same repository. It provides channels & messages, tasks & handoffs, artifacts,
sessions, and a monotonic event stream so agents can stay in sync without
talking to a cloud service.

## SQLite WAL is the single source of truth

All state lives in a single SQLite database at `~/.okto_nexus/nexus.db`, opened
in **WAL** mode. Every connection enforces:

- `PRAGMA journal_mode=WAL`
- `PRAGMA foreign_keys=ON`
- `PRAGMA busy_timeout=5000`

There is no in-memory cache, message broker, or external store. The append-only
`events` table (global, monotonic `event_id` assigned inside the writing
transaction) is the canonical history. Every coordinated entity is scoped by a
`workspace_id` (`NOT NULL` + FK), and there is no cross-workspace access.

### Workspace identity

`workspace_id = sha256(realpath(project_root)).hexdigest()` (lowercase hex).
The **client** passes `project_root`; the **server** computes the hash. An
unresolvable path (e.g. a broken symlink) yields `WORKSPACE_UNRESOLVED`; a
missing `project_root` on a coordinated operation yields `WORKSPACE_REQUIRED`.

## Architecture (hexagonal)

```
domain/        pure model + identity (no I/O, no sqlite3, no mcp)
application/   ports (Protocols) the slices implement
adapters/
  inbound/mcp/    MCP stdio server + auto-discovered tools
  outbound/sqlite/ connection factory, migrations, repos
  outbound/file/   workspace-contained filesystem access
  outbound/sharedmd/ shared-markdown rendering
```

Dependencies point **inward**. `domain/` and `application/` never import the
MCP SDK or `sqlite3` (enforced by `tests/test_import_boundary.py`).

## Setup (MCP stdio)

Install (editable, with dev extras):

```bash
pip install -e ".[dev]"
```

Run the server (console script):

```bash
okto-nexus
```

Register it with an MCP-capable client by pointing the client at the
`okto-nexus` command over **stdio**. Bootstrap is fail-closed: config is
resolved, the home dir is created, the database is opened, migrations are
applied, and only then are tools registered.

## Configuration (`OKTO_NEXUS_*`)

Precedence: **CLI flag > environment variable > default**.

| Setting | Env var | CLI flag | Default |
|---|---|---|---|
| Home directory | `OKTO_NEXUS_HOME` | `--home` | `~/.okto_nexus` |
| Database path | `OKTO_NEXUS_DB_PATH` | `--db-path` | `{home}/nexus.db` |
| Busy timeout (ms) | `OKTO_NEXUS_BUSY_TIMEOUT_MS` | `--busy-timeout-ms` | `5000` |
| Poll interval (ms) | `OKTO_NEXUS_POLL_INTERVAL_MS` | `--poll-interval-ms` | `200` |
| Max wait timeout (s) | `OKTO_NEXUS_MAX_WAIT_TIMEOUT_SECONDS` | `--max-wait-timeout-seconds` | `30` |
| Handoff lease TTL (s) | `OKTO_NEXUS_HANDOFF_LEASE_TTL_SECONDS` | `--handoff-lease-ttl-seconds` | `300` |
| Max inline bytes | `OKTO_NEXUS_MAX_INLINE_BYTES` | `--max-inline-bytes` | `65536` |

Invalid values fail closed with `CONFIG_ERROR`.

## Response envelope & errors

Every tool returns a canonical envelope:

- success: `{"ok": true, "data": {...}}`
- failure: `{"ok": false, "error": {"code", "message", "details"?}}`

`data` and `error` are mutually exclusive. Error `code` is one of the **closed
catalogue of 17 codes** (`WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`,
`WORKSPACE_MISMATCH`, `VALIDATION_ERROR`, `NOT_FOUND`, `NOT_OWNER`,
`INVALID_TRANSITION`, `INVALID_STREAM`, `HANDOFF_ALREADY_CLAIMED`,
`NOT_ELIGIBLE_TO_CLAIM`, `CONTENT_TOO_LARGE`, `PATH_OUTSIDE_WORKSPACE`,
`CONFIG_ERROR`, `MIGRATION_ERROR`, `DB_ERROR`, `RENDER_ERROR`,
`INTERNAL_ERROR`). Unexpected failures normalise to `INTERNAL_ERROR`; no
exception ever crosses the adapter boundary.

## Agent instructions

> _Placeholder — domain slices will document the per-tool agent guidance here
> (how an agent should register, claim handoffs, post messages, etc.)._

## Example flow

> _Placeholder — to be filled by the slices: register agent → open session →
> create task → publish handoff → another agent claims it → exchange messages →
> attach artifacts → tail the event stream._

## Known limitations (V1)

- **Local only**: no HTTP/SSE/WebSocket, no auth, no cloud, no multi-host.
- **Single machine**: coordination is bounded by one SQLite file.
- No background reaper/scheduler; lease expiry is evaluated on access.
- No UI; interaction is via MCP tools only.
- Inline content is capped at 65536 UTF-8 bytes (inclusive); larger payloads
  must be stored by path.

## Roadmap

- Domain slices: workspace/agent/session, events, channels/messages, tasks,
  handoffs, artifacts, shared-markdown rendering.
- Richer event filtering and long-poll tailing.
- Optional remote transport and multi-host coordination (post-V1).

## Development

```bash
pip install -e ".[dev]"
pytest
```

The import-boundary test guarantees the hexagonal layering stays intact.
