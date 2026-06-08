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
applied, all repositories and the event emitter are wired, and only then are the
tools auto-discovered and registered.

Example client config (`claude_desktop_config.json` / any MCP host that launches
stdio servers):

```json
{
  "mcpServers": {
    "okto-nexus": {
      "command": "okto-nexus",
      "env": {
        "OKTO_NEXUS_HOME": "~/.okto_nexus"
      }
    }
  }
}
```

If `okto-nexus` is not on the host's `PATH`, point `command` at the venv entry
point (e.g. `/path/to/.venv/bin/okto-nexus`, or on Windows
`C:\\path\\to\\.venv\\Scripts\\okto-nexus.exe`). Any `OKTO_NEXUS_*` variable (see
the table below) can be supplied via `env`, or as CLI flags in an `args` array.

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

## Tools (18)

Auto-discovered from `adapters/inbound/mcp/tools/` and registered on the live
FastMCP server. Every tool returns the canonical envelope.

| Slice | Tools |
|---|---|
| Identity | `workspace_resolve`, `agent_register`, `session_open`, `session_heartbeat` |
| Events | `event_get`, `event_wait` |
| Messages | `message_create`, `message_get`, `message_list`, `channel_list` |
| Handoffs | `handoff_create`, `handoff_list_available`, `handoff_claim`, `handoff_complete`, `handoff_reject` |
| Artifacts | `artifact_put`, `artifact_get` |
| shared.md | `shared_md_render` |

Most tools are workspace-scoped and take `project_root` (the server derives the
`workspace_id`); `shared_md_render` takes the resolved `workspace_id` directly.
The coordination event streams readable via `event_get`/`event_wait` are
`workspace`, `agent`, `task`, and `handoff`; message and artifact history is read
through `message_list` / `artifact_get`.

## Example flow

A real end-to-end flow (exercised by `tests/test_e2e_smoke.py`), all over the
canonical `{"ok": true, "data": ...}` envelope:

1. `workspace_resolve(project_root)` → deterministic `workspace_id` (+ upserts
   the `workspaces` row).
2. `agent_register(agent_id="builder", role="builder", capabilities=["py"])` and
   a second `reviewer` agent.
3. `session_open(agent_id="builder", workspace_id=...)` → `session.opened` event;
   `session_heartbeat(session_id=...)` keeps it `active`.
4. `message_create(project_root, from_agent_id="builder", subject, body)` →
   persists the message and emits `message.created` in the **same** transaction
   (the response carries the assigned `event_id`). Read it back with
   `message_get` / `message_list`; list seeded channels with `channel_list`.
5. `handoff_create(project_root, from_agent_id="builder",
   target={"strategy": "broadcast"}, visibility="public")` → an `OPEN` handoff +
   `handoff.created` on the `handoff` stream.
6. `event_get(project_root, agent_id="reviewer", stream="handoff")` /
   `event_wait(...)` observe `handoff.created` (cursor-paginated, visibility
   filtered, long-poll bounded by `max_wait_timeout_seconds`).
7. `handoff_list_available` → `handoff_claim(handoff_id, agent_id="reviewer")`
   (atomic single-winner, lease TTL applied) → `handoff_complete(...)` →
   `handoff.claimed` then `handoff.completed`.
8. `artifact_put(project_root, artifact_type="text", content=...)` (inline, must
   be ≤ 64 KB) and `artifact_put(..., artifact_type="markdown", path="notes.md")`
   (a workspace-contained path reference) → each emits `artifact.created`.
9. `artifact_get(artifact_id)` round-trips the inline content + metadata.
10. `shared_md_render(workspace_id)` atomically (over)writes the derived,
    four-section human-readable view at
    `{home}/workspaces/{workspace_id}/shared.md`.

Throughout, the append-only `events` table accumulates `session.opened`,
`message.created`, `handoff.created`, `handoff.claimed`, `handoff.completed`, and
`artifact.created` with global, gapless, monotonic `event_id`s.

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
