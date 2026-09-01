# Okto Nexus

**Local-first coordination for teams of AI agents.**

Okto Nexus is an MCP server and operator hub for agents working in the same
repository. It gives them durable identities, presence, messages, inboxes,
handoffs, artifacts, an event log, governance controls, and a live dashboard
without requiring a cloud broker.

`okto-nexus serve` exposes the complete hub on one port:

- `/mcp` — MCP over streamable HTTP, authenticated as an agent;
- `/api/v1` — operator REST APIs, read-only monitor endpoints, and SSE;
- `/` — the bundled React dashboard.

The classic stdio transport remains supported. Coordination records live in one
SQLite database in WAL mode. Optional metrics, referenced workspace files, and
the derived `shared.md` view live outside that database.

| Release fact | Value |
|---|---|
| Package | `okto-nexus 0.1.6` |
| Python | `>=3.11` |
| MCP surface | 43 tools by default; 46 with memory enabled |
| MCP resources | 12 versioned reference resources |
| MCP prompts | 0 |
| Surface revision | 32 |
| Database schema | 26 migrations, 34 tables |
| Storage | local SQLite/WAL |

- PyPI: [pypi.org/project/okto-nexus](https://pypi.org/project/okto-nexus/)
- Source: [github.com/OktoLabsAI/okto-nexus](https://github.com/OktoLabsAI/okto-nexus)

## Contents

- [Why Nexus](#why-nexus)
- [Install](#install)
- [Start the hub](#start-the-hub)
- [Connect an MCP client](#connect-an-mcp-client)
- [Agent pre-flight](#agent-pre-flight)
- [Architecture](#architecture)
- [HTTP surfaces and authentication](#http-surfaces-and-authentication)
- [Dashboard](#dashboard)
- [Coordination model](#coordination-model)
- [MCP surface](#mcp-surface)
- [Configuration](#configuration)
- [Operations](#operations)
- [Data model and migrations](#data-model-and-migrations)
- [Errors](#errors)
- [Development](#development)
- [Contributing](#contributing)
- [Troubleshooting](#troubleshooting)
- [Security and limitations](#security-and-limitations)
- [Release notes](#release-notes)
- [License](#license)

## Why Nexus

- **One coordination space per project.** An absolute `project_root` is
  canonicalized and hashed into a deterministic `workspace_id`. Every client
  that resolves the same real path joins the same workspace.
- **Durable delivery.** Messages fan out into per-recipient inbox lanes with
  leases, redelivery, acknowledgements, delivery status, and optional read
  receipts.
- **Single-winner work dispatch.** Handoffs support atomic claim, leases,
  rejection, cancellation, optional verification, and optional dependency
  graphs.
- **Explicit identity and presence.** Operators create identities and API keys;
  agents open sessions and heartbeat to remain present.
- **Targeted routing.** Direct, capability, role, tag, broadcast, mixed, and
  direct-with-fallback strategies share one validated grammar.
- **Governed communication.** Permissions, communication scopes, versioned
  policies, quotas, guardrails, groups, and human approval can restrict writes
  without exposing the control plane to agents.
- **Observable by design.** Monotonic event IDs, cursor reads, long-poll,
  replay export, SSE, health aggregates, and a live dashboard expose what the
  team is doing.
- **Local-first and fail-closed.** Configuration, target grammars, catalogs,
  workspace paths, API keys, and state transitions are validated before writes.
- **Token-aware MCP docs.** First-use guidance remains resident; deeper
  reference material is available through versioned MCP resources on demand.

## Install

The recommended install includes the HTTP hub, dashboard, local embedding
provider, and tokenizer:

```bash
uv tool install "okto-nexus[serve]"
okto-nexus serve
```

Equivalent with pipx:

```bash
pipx install "okto-nexus[serve]"
```

Available extras:

| Extra | Includes | Use it when |
|---|---|---|
| none | stdio MCP core | You only need a lightweight local stdio server |
| `serve-lite` | FastAPI, Uvicorn, dashboard | You need HTTP without Torch/model dependencies |
| `embeddings` | sentence-transformers | You want the local embedding provider separately |
| `serve` | HTTP stack, embeddings, tokenizer | You want the complete supported hub |
| `dev` | pytest, FastAPI, Uvicorn, httpx | You are developing or testing Nexus |

The published wheel and sdist contain the compiled dashboard. Node.js is only
needed when rebuilding the frontend from source.

From a checkout:

```bash
git clone https://github.com/OktoLabsAI/okto-nexus.git
cd okto-nexus
uv sync --extra dev

# Complete HTTP build:
uv sync --extra serve --extra dev
```

## Start the hub

```bash
okto-nexus serve
```

Defaults:

- dashboard: `http://127.0.0.1:8202/`;
- MCP: `http://127.0.0.1:8202/mcp`;
- data directory: `~/.okto_nexus`;
- database: `~/.okto_nexus/nexus.db`;
- initial workspace context: the current directory. The dashboard keeps a
  saved selection when present and otherwise may open the all-workspaces view.

Useful variants:

```bash
okto-nexus serve --project-root /absolute/path/to/project
okto-nexus serve --host 0.0.0.0 --port 8202
okto-nexus serve --trust-mode strict
okto-nexus serve --embedding-mode local
```

On first use, open **Agents → New agent** in the dashboard. Create one identity
per participant and copy its `nxs_...` key immediately: Nexus stores only the
hash and shows plaintext only at creation or regeneration. Capability and tag
values must first exist in **Registry** before an identity can use them.

## Connect an MCP client

The dashboard generates snippets for Claude Code, Claude Desktop, Codex,
Cursor, VS Code, Windsurf, and Cline. The generic streamable-HTTP URL is:

```text
http://127.0.0.1:8202/mcp?api_key=nxs_REPLACE_ME
```

Credential extraction order is query `api_key`, `x-api-key` header, then
`Authorization: Bearer`. Treat client configuration containing a query key as
a secret.

Examples:

```bash
claude mcp add -t http okto-nexus \
  "http://127.0.0.1:8202/mcp?api_key=nxs_REPLACE_ME"

codex mcp add okto-nexus \
  --url "http://127.0.0.1:8202/mcp?api_key=nxs_REPLACE_ME"
```

Generic JSON:

```json
{
  "mcpServers": {
    "okto-nexus": {
      "url": "http://127.0.0.1:8202/mcp?api_key=nxs_REPLACE_ME"
    }
  }
}
```

### Stdio

Run `okto-nexus` without a subcommand for stdio:

```json
{
  "mcpServers": {
    "okto-nexus": {
      "command": "okto-nexus",
      "args": [],
      "env": {
        "OKTO_NEXUS_HOME": "/absolute/path/to/nexus-home"
      }
    }
  }
}
```

Without `OKTO_NEXUS_API_KEY`, stdio preserves the cooperative anonymous model.
Set that variable to an active `nxs_...` key to bind the process to the same
authenticated identity rules as HTTP. An invalid configured key fails closed.

## Agent pre-flight

Every authenticated agent should do this on its first turn:

1. Call `agent_whoami()`, use the returned `agent_id` consistently, and treat
   its `role` and `communication.content` as the default operating contract.
2. Call `workspace_resolve(project_root=<absolute cwd>)`.
3. Call `session_open(agent_id=<you>, workspace_id=<resolved id>)` and retain
   the returned `session_id` and one-time `session_secret`.
4. Check `inbox_count(agent_id=<you>)`; pull and acknowledge backlog.
5. Anchor monitoring with
   `event_cursor(project_root=..., agent_id=<you>, stream="workspace")`.

The full procedure is available at
`okto-nexus://reference/preflight`.

The role guides responsibilities, operating perspective, and decision
boundaries. The communication block guides tone, format, language, verbosity,
structure, and agent-to-agent as well as user-facing communication. Follow both
unless the user explicitly directs otherwise for the current task or
interaction. That task-scoped override does not modify the Nexus profile or
bypass permissions, policies, guardrails, approvals, communication scope,
safety rules, or higher-priority host instructions. Capabilities are routing
claims, not authorization or persona.

### Direct message

```json
{
  "project_root": "/absolute/path/to/project",
  "from_agent_id": "researcher",
  "subject": "API findings",
  "body": "The endpoint is idempotent; details are attached.",
  "target": {
    "strategy": "direct",
    "agent_id": "implementer"
  },
  "from_session_id": "ses_...",
  "session_secret": "..."
}
```

The response names the resolved recipients and delivery count. The recipient
uses:

```text
inbox_count(agent_id="implementer")
inbox_pull(agent_id="implementer", session_id="ses_...", session_secret="...")
inbox_ack(agent_id="implementer", message_ids=[...],
          session_id="ses_...", session_secret="...")
```

Messages are delivered through the inbox. `event_get` and `event_wait` are
observability tools, not delivery.

### Long-poll

`event_wait` is a snapshot when `timeout_seconds` is omitted, null, or `0`.
Long-poll is explicit:

```text
event_wait(
  project_root="/absolute/path/to/project",
  agent_id="researcher",
  stream="workspace",
  cursor=123,
  timeout_seconds=25,
  profile="summary"
)
```

Always continue from `next_cursor`. The waiter uses SQLite
`PRAGMA data_version` plus bounded sleep polling; HTTP runs the blocking wait
in a worker thread so it does not block the shared event loop.

## Architecture

```text
MCP stdio             MCP HTTP              REST / SSE / SPA        CLI
    \                     |                         |                 /
     +---------------- inbound adapters and transport auth ----------------+
                                      |
                             application services
       identity · messages · inbox · handoffs · events · artifacts
       permissions · policies · approvals · guardrails · memory · health
                                      |
                         domain models and pure rules
                                      |
      +------------------------- outbound ports ---------------------------+
      | SQLite repositories | files/shared.md | waiter | telemetry | embed |
      +--------------------------------------------------------------------+
```

`bootstrap()` resolves configuration, creates the store, applies migrations,
wires repositories, telemetry, embeddings, and approval execution, then seeds
the reserved `operator`, backfills the capability catalog, and creates built-in
permission/communication presets. `create_server()` lazily imports FastMCP and
registers the effective tools and resources. `serve` wraps the same composition
in FastAPI/Uvicorn; `tail` and `admin` are separate CLI adapters.

Important boundaries:

- domain code contains state machines, routing, IDs, and invariants;
- application services own the core coordination use cases; operator
  CRUD/maintenance routes may drive repositories and units of work directly;
- inbound adapters translate MCP, HTTP, SSE, and CLI calls;
- outbound adapters implement SQLite, files, telemetry, tokenization,
  embeddings, and waiting;
- coordination truth is durable in SQLite; bounded process caches are
  implementation details, not authoritative state.

## HTTP surfaces and authentication

| Surface | Loopback bind | Non-loopback bind |
|---|---|---|
| SPA shell/assets, `/healthz`, info, license | Public | Public |
| REST data/control plane | Keyless operator trust | Active `nxs_` key required |
| MCP `/mcp` | Active `nxs_` key required | Active `nxs_` key required |
| EPT monitor endpoints | Scoped `nxsept_` accepted | Scoped `nxsept_` accepted |

MCP-over-HTTP connections always represent an agent; stdio may use the
cooperative anonymous mode. The dashboard/REST loopback trust path represents
the local operator. Browser-origin checks protect mutating operator routes, and
binding beyond loopback removes keyless REST trust.

On a non-loopback bind, use the reserved `operator` identity's key for the
dashboard/control plane. Participant keys authenticate requests but
operator-only routes return `PERMISSION_DENIED`. When a store has no keys at
all, startup creates the operator key and prints its plaintext once.

Permanent agent keys can authenticate REST and MCP, but helper monitors should
receive only a short-lived ephemeral poll token (`nxsept_...`). EPTs are bound
to the issuing session, agent, and workspace and are accepted only as
`Authorization: Bearer nxsept_...`; query `api_key` and `x-api-key` are rejected
for this token type. The bearer is valid only on:

- `GET /api/v1/events` and `GET /api/v1/events/cursor`;
- `GET /api/v1/inbox/count` and `GET /api/v1/inbox/peek`.

They cannot call MCP or mutate state.

## Dashboard

The bundled dashboard provides:

- **Graph** — toggle between detailed agent cards and compact activity-sized
  circles, with profile colours, live presence status badges, recent
  message flow, unread traffic, open handoffs, and claimed relationships;
- **Messages** — inbox lanes, peer conversations, undelivered targeting
  outcomes, receipts, and optional semantic search;
- **Handoffs** — a six-column Kanban including `VERIFYING`, claim details,
  dependency state, verification, cancellation, and results;
- **Events** — filtered event history, trace navigation, and live SSE updates;
- **Memory** — durable memory browse/search/curation when `feature_memory` is
  enabled;
- **Workspaces** — sessions, analytics, and coordination health;
- **Agents** — identities, keys, activation, roles, capabilities, metadata,
  colors, permissions, tags, inbound/outbound audiences, communication style,
  and steering;
- **Registry** — operator-managed capability and tag vocabularies;
- **Policies** — versioned policies and per-agent bindings;
- **Guardrails** — groups, versioned content rules, assignments, and scrubbed
  denial audit;
- **Communication** — versioned communication presets and bindings;
- **Approvals** — pending and decided human-in-the-loop actions;
- **Settings** — runtime-manageable settings, feature flags, retention, and
  database maintenance; metrics use their own header-menu panel.

Semantic search requires `embedding_mode=stub` or `local`. `off` returns
`EMBEDDINGS_UNAVAILABLE` on the REST search endpoint. The `local` provider
needs the embeddings extra; `stub` is deterministic and is intended for tests
or demonstrations.

## Coordination model

### Workspaces, agents, and sessions

- Agents are global identities; workspaces represent canonical project roots.
- Most coordination tools accept `project_root`.
- `session_open` and `shared_md_render` consume a resolved `workspace_id`.
- An authenticated agent can update only its own profile with
  `agent_register`, subject to `identity.update_profile` and
  `identity.update_capabilities`. Operators create identities.
- Authenticated discovery is reachability-scoped. `agent_list` and
  `agent_get` hide unreachable peers; `capability_list` returns the complete
  catalog but filters owner identities.
- `workspace_list` is permission-gated; absolute paths require a separate
  permission.
- Cross-workspace errors are intentionally operation-specific:
  `WORKSPACE_MISMATCH` for ownership guards, `NOT_FOUND` for hidden artifact or
  memory reads, and `DEPENDENCY_NOT_FOUND` for dependency creation.

Presence is explicit. A session is considered present while its heartbeat is
within `presence_ttl_seconds`. A trust-sensitive write advances the heartbeat
only when it authenticates with that session's credentials; in
`trust_mode=open`, a credential-free write advances no session. Read-only tools
do not heartbeat. Call `session_heartbeat` during long read-only or idle periods
and `session_close` when finished.

### Messages and inboxes

`message_create` persists one message and resolves recipients at send time.
Each recipient gets a durable delivery row in its global inbox. The lanes are:

| Lane | Meaning |
|---|---|
| `unread` | Available to pull |
| `delivered` | Pulled and protected by an in-flight lease |
| `read` | Acknowledged |
| `parked` | Dead-lettered after exhausting delivery claims; not redelivered automatically |

An expired `delivered` lease becomes pullable again. Delivery is therefore
at-least-once until acknowledgement. `message_status` lets the sender inspect
each recipient's lane. Every pull/redelivery emits `message.delivered`; ack
emits `message.read`. By default, ack also sends one synthetic read-receipt
message to the sender; receipts do not recursively create receipts.

Channels are organizational labels, not ACLs or delivery mechanisms. Access
still intersects with permissions, policy, guardrails, and communication
reachability. Message retention can remove aged messages and their deliveries,
including unread or in-flight rows, so durability is bounded by configured
retention and explicit database reset.

### Communication intent

Choose the coordination mechanism by intended outcome: if another agent is
expected to perform work or produce a deliverable, create a handoff. If the
recipient only needs to know something or reply, use a message.

- **Handoff — executable work.** Any request to execute, investigate, change,
  build, test, review, validate, or otherwise produce a deliverable must use
  `handoff_create`; a direct message must not be its sole record. Target the
  intended assignee directly when known, or use a capability, role, tag, mixed,
  broadcast, or direct-with-fallback target when the first eligible claimant
  should own the work. The handoff is the canonical, operator-visible record of
  ownership, lifecycle, result, and verification. Include the objective,
  context, scope, constraints, and expected deliverable; add acceptance
  criteria, dependencies, and a verifier when applicable and the corresponding
  `feature_verification` / `feature_dag` flag is enabled. Those fields are
  rejected while their feature is off.
- **Broadcast message — shared alignment.** Use it for shared context,
  decisions, announcements, discoveries, risk or blocker alerts, and general
  alignment across every selected reachable recipient. It informs recipients
  but assigns no owner and creates no task lifecycle. If anyone is expected to
  act, create one or more handoffs.
- **Direct message — conversation and informal coordination.** Use it for
  status checks, questions, clarifications, acknowledgements, focused context
  exchange, and informal coordination. It may discuss an existing handoff, but
  new executable work requires a handoff; reference that handoff in the
  conversation. Use `handoff_get` for canonical lifecycle state and direct
  messages for contextual updates or blocker explanations.

A broadcast message is informational fan-out to many recipients. A handoff
with a `broadcast` target is a claim pool for one executor. If several agents
must produce independent results, create separate handoffs.

### Routing

There are seven strategies:

| Strategy | Descriptor | Notes |
|---|---|---|
| `direct` | `{"strategy":"direct","agent_id":"a"}` | One named identity |
| `capability` | `{"strategy":"capability","capability":"review"}` | One or any of several registered capabilities |
| `role` | `{"strategy":"role","role":"reviewer"}` | Exact role match |
| `tag` | `{"strategy":"tag","selector":{"team":["platform"]}}` | Registered tag selector |
| `broadcast` | `{"strategy":"broadcast"}` | Present workspace agents for messages; globally registered eligible agents for handoffs |
| `mixed` | `{"strategy":"mixed","rules":[...]}` | Non-empty union of non-broadcast rules |
| `direct_with_fallback` | direct plus `fallback_after_seconds` and optional `fallback` | Handoffs only |

Messages support direct, capability, role, tag, broadcast, and mixed.
Omitting a message target means broadcast. Handoffs require an explicit target
and additionally support direct-with-fallback.

Tag selectors use AND across keys and OR across values. Rich
`In`/`NotIn`/`Exists`/`DoesNotExist` expressions are also supported.
Capability and tag names fail closed against operator-managed catalogs.

Target resolution is intersected with presence where applicable and with the
caller's effective communication reach/audience. Separate enforcement layers
then allow, deny, limit, or intercept the write:

- per-agent permissions and recipient/rate limits;
- versioned policy action rules and quotas;
- content guardrails;
- optional HITL approval interception.

A channel itself adds no ACL. Visibility controls who may see an item;
eligibility controls who may claim it.

### Event log

Events are immutable after insertion during normal operation. `event_id` is
globally monotonic and never reused. Retention may delete old rows, so retained
history can contain gaps.

Streams are `workspace`, `agent`, and `handoff`. Supported filters are
`type`, `agent_id`, `task_id`, `handoff_id`, and `trace_id`. Authenticated event
reads require `events.read` and omit actors outside the caller's communication
reach, except the caller's own and system events.

Response profiles:

| Profile | Behavior |
|---|---|
| `default` | Safe trim: preserves contextual fields while removing empty or duplicated data; oversized event payloads can yield a follow-up hint |
| `summary` | Aggressive projection: omits heavy bodies/payloads and returns follow-up hints |
| `full` | Raw debugging escape hatch |

`event_get` is non-blocking. `event_cursor` returns the current end in O(1).
`event_wait` long-polls only when `timeout_seconds > 0`. Dashboard SSE already
provides operator UI updates; agent monitoring remains MCP polling/long-poll or
the EPT read-only REST plane.

### Handoffs

```text
OPEN      -> CLAIMED
OPEN      -> REJECTED | CANCELLED
CLAIMED   -> COMPLETED
CLAIMED   -> VERIFYING        when acceptance criteria exist
CLAIMED   -> REJECTED         claimant rejects
CLAIMED   -> OPEN             lease expires
VERIFYING -> COMPLETED        verifier passes
VERIFYING -> CLAIMED          verifier fails; executor reworks
```

Only one agent wins `handoff_claim`. A claim returns the confidential payload.
Available-list responses omit payload; `handoff_get` includes it only for the
claimant. Events and synthetic notifications never carry the payload.

With `feature_verification=true`, creation may include
`acceptance_criteria` and `verify_by`. The executor cannot verify its own
result. A failed verdict persists feedback, returns the handoff to `CLAIMED`,
and renews the lease.

With `feature_dag=true`, creation may include `depends_on`. The persisted
status remains `OPEN`, but blockedness is derived. Blocked items are excluded
from `handoff_list_available` and claim returns `DEPENDENCY_NOT_MET` until every
dependency is `COMPLETED`.

### Artifacts and `shared.md`

Artifacts are either inline `text`/`json`/`markdown` or a workspace-contained
file reference. Path containment is checked after canonical resolution;
escapes return `PATH_OUTSIDE_WORKSPACE`. Inline content is bounded by
`max_inline_bytes`.

The publisher's effective outbound audience is frozen on the artifact. The
same audience controls `artifact.created` visibility and `artifact_get`.
Unauthorized, cross-workspace, and missing reads all return `NOT_FOUND`.

`shared_md_render` atomically rewrites a derived workspace `shared.md` with four
fixed sections: relevant agents/sessions, open tasks, open handoffs, and recent
events. It never becomes the source of truth and never renders handoff payloads.
Authenticated callers need `shared_md.render`.

### Permissions, policies, guardrails, and approvals

The operator control plane manages:

- permission presets and per-agent effective permissions;
- capability/tag catalogs and communication scopes;
- versioned attachable policies with deny-overrides and quota windows;
- versioned communication guidance returned privately by `agent_whoami`;
- agent groups and versioned guardrails assigned by scope and priority;
- one-shot HITL approval decisions and operator steering.

Guardrail denials persist scrubbed metadata, not rejected raw content. When
`feature_hitl=true` and a policy requires approval, `message_create` or
`handoff_create` may return `status: "pending_approval"`. Do not resend the
action; watch the returned approval ID.

### Opt-in features

All seven flags default to off:

| Flag | Effect |
|---|---|
| `feature_trace` | Accept and project `trace_id` correlation |
| `feature_hitl` | Enable new `require_approval` interception |
| `feature_verification` | Enable handoff acceptance criteria and verdicts |
| `feature_dag` | Enable handoff dependencies |
| `feature_memory` | Register three memory MCP tools and show Memory UI; restart required |
| `feature_health` | Enable `coordination_health` MCP execution |
| `feature_replay` | Enable REST replay export |

Nuances:

- approval history and decisions remain available when interception is off;
- disabling verification or DAG blocks new contracts/dependencies, while
  already persisted workflow state remains enforceable and decidable;
- workspace health REST remains available when the MCP health flag is off;
- CLI replay export is operator-shell access and is not gated by
  `feature_replay`;
- memory REST supports operator curation independently, but MCP memory tools
  are registered only when the flag is on at startup.

## MCP surface

The default server exposes **43 tools**: 42 across tool modules plus
`nexus_info`. Enabling `feature_memory` at startup adds three tools, for 46.
Both transports expose the same effective tool/resource surface for the same
configuration.

| Area | Tools |
|---|---|
| Metadata | `nexus_info` |
| Identity/workspace | `workspace_resolve`, `agent_register`, `agent_whoami`, `session_open`, `session_heartbeat`, `session_close`, `workspace_list`, `agent_list`, `agent_get`, `capability_list` |
| Events | `event_get`, `event_cursor`, `event_wait` |
| Messages/channels | `message_create`, `channel_create`, `channel_list`, `message_get`, `message_list`, `message_wait` |
| Inbox | `inbox_pull`, `inbox_ack`, `inbox_extend`, `inbox_peek`, `inbox_count`, `inbox_history`, `message_status` |
| Handoffs | `handoff_create`, `handoff_list_available`, `handoff_claim`, `handoff_complete`, `handoff_verify`, `handoff_reject`, `handoff_cancel`, `handoff_get` |
| Artifacts | `artifact_put`, `artifact_get` |
| Derived view | `shared_md_render` |
| Health | `coordination_health` |
| Catalog | `tag_list` |
| Ephemeral monitor tokens | `poll_token_issue`, `poll_token_renew`, `poll_token_revoke` |
| Optional memory | `memory_put`, `memory_get`, `memory_search` |

`message_get`, `message_list`, and `message_wait` are intentional migration
shims. They return `MIGRATED` with replacements in the inbox/event surface
instead of failing as unknown tools.

`coordination_health` stays registered but returns `VALIDATION_ERROR` while
`feature_health` is off. `memory_put/get/search` are absent until
`feature_memory` is enabled and the server restarts.

Session credentials are trust-sensitive on:

- `message_create`;
- `handoff_claim/complete/verify/reject/cancel`;
- `inbox_pull/ack/extend`;
- `memory_put` when published.

In `trust_mode=open` they are optional but validated if supplied. In
`trust_mode=strict` they are required. `poll_token_issue/renew/revoke` always
require a valid `session_id` and `session_secret` in both modes.

### Versioned MCP resources

| URI | Version |
|---|---:|
| `okto-nexus://reference/preflight` | 4 |
| `okto-nexus://reference/communication` | 3 |
| `okto-nexus://reference/monitoring` | 5 |
| `okto-nexus://reference/target-grammar` | 5 |
| `okto-nexus://reference/tool-docs/messages` | 3 |
| `okto-nexus://reference/tool-docs/inbox` | 2 |
| `okto-nexus://reference/tool-docs/events` | 2 |
| `okto-nexus://reference/tool-docs/handoff` | 4 |
| `okto-nexus://reference/tool-docs/identity` | 5 |
| `okto-nexus://reference/tool-docs/artifacts` | 2 |
| `okto-nexus://reference/governance` | 2 |
| `okto-nexus://reference/hitl` | 2 |

`nexus_info` reports package/schema/surface versions, the URI-to-version map,
and effective feature flags. Use that live metadata instead of assuming a
cached surface.

### Response envelope

Successful tools return:

```json
{
  "ok": true,
  "data": {}
}
```

Failures return:

```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable explanation"
  }
}
```

Transient SQLite lock/busy failures use `DB_ERROR` with
`details.retryable=true`.

### Resident token footprint

For the 0.1.6 default surface:

| Component | Characters |
|---|---:|
| Server instructions | 3,992 |
| Tool docstrings | 6,563 |
| Parameter schemas/descriptions | 15,720 |
| Cuttable resident surface | 26,275 (~6,568 tokens) |
| Total measured surface | 37,345 (~9,336 tokens) |

Deep explanations live in resources so clients load them only when needed.
The current measured cuttable reduction against the frozen baseline is about
44.3%.

## Configuration

For `serve` settings managed by the runtime catalog, effective precedence is:

```text
CLI flag > environment variable > stored dashboard override > default
```

Within the core/stdio bootstrap there is no stored layer, so precedence is
`CLI > env > default`. Unknown flags, missing values, invalid enums, and
out-of-range numbers fail closed with `CONFIG_ERROR`. Boolean CLI flags take
an explicit value such as `--feature-trace true`.

### Core runtime

| Environment | CLI | Default | Notes |
|---|---|---:|---|
| `OKTO_NEXUS_HOME` | `--home` | `~/.okto_nexus` | Runtime data directory |
| `OKTO_NEXUS_DB_PATH` | `--db-path` | `{home}/nexus.db` | SQLite database |
| `OKTO_NEXUS_BUSY_TIMEOUT_MS` | `--busy-timeout-ms` | 5000 | Minimum 0 |
| `OKTO_NEXUS_POLL_INTERVAL_MS` | `--poll-interval-ms` | 200 | Waiter interval; minimum 1 |
| `OKTO_NEXUS_MAX_WAIT_TIMEOUT_SECONDS` | `--max-wait-timeout-seconds` | 30 | Server wait ceiling; minimum 0 |
| `OKTO_NEXUS_HANDOFF_LEASE_TTL_SECONDS` | `--handoff-lease-ttl-seconds` | 300 | Minimum 1 |
| `OKTO_NEXUS_MAX_INLINE_BYTES` | `--max-inline-bytes` | 65536 | Inline artifact/content limit |
| `OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS` | `--inbox-lease-ttl-seconds` | 300 | Minimum 1 |
| `OKTO_NEXUS_SESSION_STALE_TTL_SECONDS` | `--session-stale-ttl-seconds` | 60 | Derived stale threshold |
| `OKTO_NEXUS_PRESENCE_TTL_SECONDS` | `--presence-ttl-seconds` | 1800 | Broadcast/tag presence window |
| `OKTO_NEXUS_SESSION_REAP_SECONDS` | `--session-reap-seconds` | 86400 | Opportunistic stale close |
| `OKTO_NEXUS_MAX_SHARED_MD_EVENTS` | `--max-shared-md-events` | 1000 | Render ceiling |
| `OKTO_NEXUS_MAX_EVENT_LIMIT` | `--max-event-limit` | 1000 | Event page ceiling |
| `OKTO_NEXUS_POLL_TOKEN_TTL_SECONDS` | `--poll-token-ttl-seconds` | 3600 | Minimum 60 |
| `OKTO_NEXUS_TRUST_MODE` | `--trust-mode` | `open` | `open` or `strict` |
| `OKTO_NEXUS_EMBEDDING_MODE` | `--embedding-mode` | `off` | `off`, `stub`, or `local` |
| `OKTO_NEXUS_INBOX_READ_RECEIPTS` | `--inbox-read-receipts` | `true` | Sender inbox receipts |
| `OKTO_NEXUS_EXPOSE_WORKSPACE_PATH` | `--expose-workspace-path` | `false` | Operator REST/dashboard path disclosure |
| `OKTO_NEXUS_AUTO_PRUNE_ON_START` | `--auto-prune-on-start` | `false` | One bounded best-effort startup pass |

### Retention

| Environment | CLI | Default | Minimum |
|---|---|---:|---:|
| `OKTO_NEXUS_RETENTION_EVENTS_KEEP_DAYS` | `--retention-events-keep-days` | 30 | 0 |
| `OKTO_NEXUS_RETENTION_READ_DELIVERIES_KEEP_DAYS` | `--retention-read-deliveries-keep-days` | 14 | 0 |
| `OKTO_NEXUS_RETENTION_CLOSED_SESSIONS_KEEP_DAYS` | `--retention-closed-sessions-keep-days` | 7 | 0 |
| `OKTO_NEXUS_RETENTION_MESSAGES_KEEP_DAYS` | `--retention-messages-keep-days` | 30 | 7 |

Pruning removes aged events, `read` deliveries, `closed` sessions, and messages
older than the message window. Message retention is pure-age: it can remove
unread, in-flight, or parked messages and cascades to their deliveries and
embeddings. Handoffs and other non-message live rows are not age-pruned.

### Metrics

| Environment | CLI | Default | Notes |
|---|---|---:|---|
| `OKTO_NEXUS_METRICS_MODE` | `--metrics-mode` | `disabled` | `disabled`, `local_only`, `anonymous_beacon` |
| `OKTO_NEXUS_METRICS_DIR` | `--metrics-dir` | `{home}/metrics` | Local telemetry JSONL/state |
| `OKTO_NEXUS_METRICS_BEACON_URL` | `--metrics-beacon-url` | `https://nexus-metrics.oktolabs.ai` | Used only in beacon mode |
| `OKTO_NEXUS_METRICS_RETENTION_DAYS` | `--metrics-retention-days` | 30 | Minimum 0 |
| `OKTO_NEXUS_METRICS_PUBLISH_INTERVAL_SECONDS` | `--metrics-publish-interval-seconds` | 3600 | Minimum 60 |

Metrics are opt-in. Local mode stores bounded per-event metadata; beacon mode
publishes aggregate hourly counts only. Message bodies, prompts, workspace file
paths, coordination IDs, keys, tokens, URLs, and stack traces are excluded.
Local telemetry JSONL is not currently pruned automatically; operators must
manage those files even though `metrics_retention_days` is validated and
exposed in configuration.

### Feature flags

| Environment | CLI | Default |
|---|---|---:|
| `OKTO_NEXUS_FEATURE_TRACE` | `--feature-trace` | `false` |
| `OKTO_NEXUS_FEATURE_HITL` | `--feature-hitl` | `false` |
| `OKTO_NEXUS_FEATURE_VERIFICATION` | `--feature-verification` | `false` |
| `OKTO_NEXUS_FEATURE_DAG` | `--feature-dag` | `false` |
| `OKTO_NEXUS_FEATURE_MEMORY` | `--feature-memory` | `false` |
| `OKTO_NEXUS_FEATURE_HEALTH` | `--feature-health` | `false` |
| `OKTO_NEXUS_FEATURE_REPLAY` | `--feature-replay` | `false` |

`feature_memory` changes tool registration and requires restart/reconnect.
The other flags gate live behavior.

### Serve-only and transport-specific settings

| Environment | CLI | Default | Scope |
|---|---|---:|---|
| `OKTO_NEXUS_PORT` | `--port` | 8202 | `serve` |
| `OKTO_NEXUS_HOST` | `--host` | `127.0.0.1` | `serve` |
| `OKTO_NEXUS_LOG_LEVEL` | `--log-level` | `warning` | `critical` through `trace` |
| — | `--project-root` | `.` | Initial dashboard workspace |
| `OKTO_NEXUS_NO_BANNER` | — | unset | Suppress serve banner |
| `OKTO_NEXUS_API_KEY` | — | unset | Optional stdio authenticated identity |

## Operations

### CLI commands

| Command | Purpose |
|---|---|
| `okto-nexus serve` | Start MCP HTTP, REST, SSE, and dashboard |
| `okto-nexus` | Start MCP over stdio |
| `okto-nexus tail` | Operator NDJSON follower over the event service |
| `okto-nexus admin prune` | Enforce retention, optionally vacuum |
| `okto-nexus admin issue-keys` | Add keys to legacy keyless identities |
| `okto-nexus admin export` | Export a workspace replay stream as NDJSON |

Use `--help` on every command for the full argument grammar.

### Tail

```bash
okto-nexus tail \
  --project-root /absolute/path/to/project \
  --agent-id observer \
  --stream workspace \
  --from latest
```

`tail` applies per-agent event visibility. An optional `--cursor-file` belongs
to that consumer only; corrupted checkpoints fail closed.

### Retention

Start with a dry run:

```bash
okto-nexus admin prune \
  --project-root /absolute/path/to/project \
  --dry-run
```

Then execute:

```bash
okto-nexus admin prune \
  --project-root /absolute/path/to/project \
  --messages-keep-days 30 \
  --vacuum
```

Retention spans the whole shared store even though `--project-root` is
validated as the command anchor. `--vacuum` is the only option that compacts
freed pages on disk. There is no always-running coordination reaper;
`auto_prune_on_start` is a bounded opportunistic pass.

### Issue legacy keys

```bash
okto-nexus admin issue-keys \
  --project-root /absolute/path/to/project
```

This is additive and idempotent. Existing keys are never rotated. Newly issued
plaintext keys are printed once.

### Replay export

```bash
okto-nexus admin export \
  --project-root /absolute/path/to/project \
  --trace-id trc_... \
  --output nexus-events.ndjson
```

The first line is a manifest; subsequent lines are raw events ordered by
`event_id`. CLI export is operator-shell access and remains available even
when the REST replay flag is off.

### Ephemeral monitor token

An authenticated agent can call `poll_token_issue`, give only the returned
`nxsept_...` token and base URL to a read-only helper, renew it before expiry,
and revoke it on teardown. The raw token is returned only on issue/renew.

## Data model and migrations

The current schema contains 34 tables:

| Area | Tables |
|---|---|
| Core coordination | `schema_migrations`, `workspaces`, `agents`, `sessions`, `events`, `channels`, `messages`, `tasks`, `handoffs`, `artifacts`, `message_deliveries` |
| Settings/security/catalogs | `settings`, `permission_presets`, `tag_keys`, `tag_values`, `capability_names`, `ephemeral_poll_tokens` |
| Search and memory | `message_embeddings`, `memories`, `memory_embeddings` |
| Governance/workflows | `governance_policies`, `approvals`, `handoff_dependencies`, `policies`, `policy_versions`, `agent_policy_bindings`, `comm_presets`, `comm_preset_versions`, `agent_comm_binding`, `agent_groups`, `agent_group_members`, `guardrails`, `guardrail_versions`, `guardrail_assignments` |

Not every table is workspace-scoped: agents and catalogs are global, inbox
deliveries are keyed by recipient identity, and bindings/control-plane records
have their own ownership rules.

Migrations are embedded in the package and applied in order:

- **001–008:** core schema, close metadata, handoff payload/result, presence,
  durable inbox deliveries, leases, and session secrets;
- **009–015:** API keys, settings, permissions, embeddings, tags/scopes,
  capability catalog, and trace IDs;
- **016–021:** governance, approvals, verification, dependencies, memory, and
  health/event indexes;
- **022–026:** versioned attachable policies, communication presets, display
  colors, groups/guardrails, and ephemeral poll tokens.

Nexus refuses to run against an unsupported newer schema. Runtime SQLite
databases and their WAL/SHM/journal sidecars are ignored and must not be
committed.

## Errors

The domain/MCP contract has a closed catalog of 29 canonical codes:

| Area | Codes |
|---|---|
| Workspace | `WORKSPACE_REQUIRED`, `WORKSPACE_UNRESOLVED`, `WORKSPACE_MISMATCH` |
| Validation/identity | `VALIDATION_ERROR`, `NOT_FOUND`, `NOT_OWNER`, `PERMISSION_DENIED` |
| Catalog/control plane | `TAG_IN_USE`, `CAPABILITY_IN_USE`, `POLICY_IN_USE`, `COMM_PRESET_IN_USE` |
| Governance | `POLICY_DENIED`, `QUOTA_EXCEEDED`, `GUARDRAIL_DENIED`, `CONFLICT` |
| Dependencies/state | `DEPENDENCY_NOT_FOUND`, `DEPENDENCY_NOT_MET`, `INVALID_TRANSITION`, `INVALID_STREAM` |
| Handoffs | `HANDOFF_ALREADY_CLAIMED`, `NOT_ELIGIBLE_TO_CLAIM` |
| Content/path | `CONTENT_TOO_LARGE`, `PATH_OUTSIDE_WORKSPACE` |
| Infrastructure | `CONFIG_ERROR`, `MIGRATION_ERROR`, `DB_ERROR`, `RENDER_ERROR` |
| Compatibility/internal | `MIGRATED`, `INTERNAL_ERROR` |

REST adapters also use transport-specific codes such as `AUTH_FAILED`,
`CROSS_ORIGIN_BLOCKED`, `INVALID_PARAM`, `INVALID_WINDOW`,
`INVALID_SETTING`, `EMBEDDINGS_UNAVAILABLE`, and `INTERNAL`.

## Development

```bash
uv sync --extra dev
uv run pytest -q
```

For the complete HTTP/embedding environment:

```bash
uv sync --extra serve --extra dev
uv run pytest -q
```

Frontend:

```bash
cd frontend
npm ci
npm run build
```

The build writes packaged static assets under
`src/okto_nexus/adapters/inbound/http/static/`.

Release checks:

```bash
uv lock --check
uv build --out-dir dist/release-0.1.6
uvx twine check \
  dist/release-0.1.6/okto_nexus-0.1.6-py3-none-any.whl \
  dist/release-0.1.6/okto_nexus-0.1.6.tar.gz
```

Publish only explicitly named current-version artifacts. The top-level
`dist/` may contain older builds.

### Project layout

```text
src/okto_nexus/
  adapters/
    inbound/
      cli/                  serve, tail, admin
      http/                 FastAPI, REST, SSE, packaged SPA
      mcp/                  server, resources, projections, 43/46 tools
    outbound/
      sqlite/               repositories and migrations adapter
      embedding/            optional semantic provider
      file/ sharedmd/       artifact and derived-view I/O
      telemetry/ tokenizer/ metrics support
  application/              use cases and ports
  domain/                   entities, routing, state machines, policies
  migrations/               001 through 026
  testing/                  reusable test/replay harnesses
frontend/                    React dashboard source
tests/                       unit, contract, integration, replay tests
docs/design/                 architecture and design records
pyproject.toml               package metadata and extras
uv.lock                      reproducible dependency lock
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the supported Python and frontend
development environments, validation commands, and pull-request workflow.

## Troubleshooting

### `event_wait` returns immediately

Pass `timeout_seconds > 0`. Omitted, null, and zero are snapshots by design.

### An agent misses broadcasts

Check that it opened a session in the correct resolved workspace and continues
to heartbeat. Read-only event/inbox checks do not advance presence.

### A direct peer is missing from discovery

Authenticated discovery is filtered by communication reachability. Inspect the
caller's outbound and the peer's inbound communication scopes/tags in the
dashboard.

### Capability or tag targeting fails

Create the capability/tag value in **Registry** first. Catalog validation is
fail-closed.

### Memory tools are absent

Set `feature_memory=true` and restart/reconnect. Unlike live behavior flags,
this flag changes MCP tool registration.

### Semantic search is unavailable

Use `embedding_mode=stub` or install the embeddings/serve extra and use
`embedding_mode=local`. `off` intentionally disables search.

### `DB_ERROR` reports a lock

If `details.retryable=true`, retry the same call after the competing writer
commits. Avoid opening the runtime SQLite file with tools that hold long write
transactions.

### The hub says another server already owns the home

`serve` holds `{home}/nexus.serve.lock` and refuses a second server using that
same home. Stop the other hub or choose a different `--home`; changing only
`--db-path` does not change the lock scope.

### Workspace path is rejected

Pass an existing absolute path. Nexus canonicalizes the real path before
deriving the workspace ID and validating artifact containment.

### A monitor cannot mutate state

That is expected for `nxsept_` tokens. They are intentionally read-only and
accepted only on the four monitor endpoints.

### Cached docs appear stale

Call `nexus_info` and compare `surface_revision` and `resource_versions` before
reusing cached MCP reference content.

## Security and limitations

Report vulnerabilities privately according to [SECURITY.md](SECURITY.md). Do
not include vulnerability details, credentials, tokens, or private workspace
data in a public issue.

- Nexus is designed for local or controlled single-tenant coordination, not as
  a public multi-tenant broker.
- It does not terminate TLS. Put an authenticated TLS reverse proxy in front
  of a remote bind.
- The dashboard shell and public health/info/license assets remain public;
  data/control REST requires authentication outside loopback.
- API keys are hash-only at rest and shown once. Regeneration invalidates the
  old key immediately.
- Session secrets are stored in plaintext in the local SQLite database; anyone
  who can read that file is inside the session trust boundary.
- Channels are labels, not security boundaries.
- SQLite is the only built-in coordination store. There is no Redis,
  PostgreSQL, or cloud broker adapter.
- There is no always-running coordination scheduler/reaper. Expiry is checked
  opportunistically and retention runs manually or at startup when enabled.
- The HTTP server does use worker threads/tasks for operational needs such as
  blocking waits and telemetry; “no scheduler” does not mean “no threads.”
- Message durability is bounded by message retention and explicit reset.
- Memory is experimental and changes the MCP surface at startup.
- Artifact file references are confined to the canonical workspace.
- Avoid committing runtime databases, sidecars, metrics output, and local
  secrets to version control.

## Future direction

Likely extension points are additional durable-store adapters, a push-backed
waiter that removes internal sleep polling, stronger remote deployment
packaging, and further generated documentation from the live MCP schemas. The
delivered surface already includes permissions, catalogs, communication
scopes, policies, guardrails, HITL, trace correlation, verified/DAG handoffs,
memory, health, replay, ephemeral poll tokens, embeddings, metrics, REST, SSE,
and the dashboard.

## Release notes

### 0.1.6 — current

Startup compatibility maintenance release. The MCP contract and database
schema are unchanged: surface revision remains 32 and the latest migration
remains 026.

- Rebuilt the MCP v1 FastMCP settings model after import, eliminating the
  unresolved `lifespan` forward-reference warning introduced by
  `pydantic-settings` 2.15.
- Applied the compatibility path to both stdio and streamable-HTTP server
  construction.
- Constrained the MCP SDK dependency to `mcp>=1.0,<2` so adopting the breaking
  v2 API requires an explicit migration.
- Added a regression test that promotes the startup warning to an error and
  verifies the settings model is complete.
- Verified the installed executable with local MiniLM warm-up, a live health
  request, and the complete test suite.

### 0.1.5

Live MCP smoke-test maintenance release. The MCP contract and database schema
are unchanged: surface revision remains 32 and the latest migration remains
026.

- Restored the real stdio smoke test on clean stores after capability
  registration became fail-closed.
- Documented when and how to run the isolated two-agent smoke flow on Unix and
  Windows, including its `LIVE E2E RESULT: PASS` completion signal.
- Added semantic cards for structured `kind` messages in the Graph conversation
  drawer, with distinct read-receipt and handoff lifecycle treatments instead
  of raw JSON.
- Synchronized `pyproject.toml`, `uv.lock`, and release commands at version
  0.1.5.

### 0.1.4

Dashboard, observability, and coordination-guidance release. The MCP guidance
contract advances to surface revision 32; the database schema is unchanged and
the latest migration remains 026.

- Added detailed and compact activity-based agent graph modes, profile colours,
  live status badges, richer relationship context, and graph conversations.
- Added an event timeline, expanded event and handoff filters, message detail
  hydration, workspace display names, and catalog import/export workflows.
- Improved dashboard views for agents, approvals, communication, events,
  guardrails, handoffs, messages, policies, and workspaces.
- Extended observability APIs and repositories with message lookup, filtered
  handoff/event queries, and bucketed event timeline data.
- Completed PyPI project URLs, keywords, and supported-Python classifiers, with
  a focused metadata regression test.
- Added contributor and security policies, structured GitHub issue forms, and
  a dedicated documentation-assets location for product screenshots.

- Clarified that agents follow the role and communication profile returned by
  `agent_whoami` unless the user supplies a task-scoped override, without
  bypassing platform governance.
- Defined handoffs as the required, traceable mechanism for executable work,
  broadcasts as shared alignment or information fan-out, and direct messages
  as status, clarification, and informal coordination channels.

- Rewrote this README against the current CLI, transport/authentication model,
  dashboard, 43/46-tool surface, seven routing strategies, message retention,
  governance features, verification/DAG workflows, 34-table schema, 29-code
  error catalog, operations, testing, and limitations.
- Synchronized `pyproject.toml` and the root project entry in `uv.lock` at
  version 0.1.4, and aligned the package/dashboard license label with the
  addendum that is actually included in `LICENSE`.
- Removed tracked runtime SQLite databases and added ignore coverage for
  database files and journal/WAL/SHM sidecars.
- Verified release archives contain the dashboard and migrations without
  runtime SQLite databases or sidecars.

### 0.1.2

- Documentation-accuracy sweep at surface revision 31.
- Corrected pre-flight, monitoring, heartbeat, inbox, trace, policy, HITL,
  artifact-audience, and target-grammar documentation.
- Kept 12 deep reference resources versioned and reduced the resident cuttable
  surface to about 26.3k characters.
- Corrected the token-reduction gate to include experimental-surface growth.

### 0.1.1

- Hardened authenticated self-only identity/session rules and permission
  checks.
- Added permission-gated workspace paths, shared view, health, and memory.
- Added configurable aggregate metrics telemetry.

### 0.1.0

- Added ephemeral remote-monitor tokens and read-only monitor endpoints.
- Added attachable policies, communication presets, guardrail/group
  administration, enriched agent graph cards, and loopback trust hardening.
- Made memory a registration-time experimental MCP surface.

### 0.0.x

- Built the MCP reference-resource system, HTTP hub, live dashboard, inbox
  receipts, semantic search, monitoring guidance, and dashboard observability
  waves.

## License

Copyright 2026 Okto Labs.

Okto Nexus is distributed under the Elastic License 2.0 together with the
project's SaaS, competing-service, internal-use, and branding addendum. It
permits internal and qualifying single-tenant use and prohibits the specified
multi-tenant, white-label/OEM, competing, and large-scale internal-platform
uses; applicable notices and attribution remain required.

Read the complete
[LICENSE](https://github.com/OktoLabsAI/okto-nexus/blob/main/LICENSE) before use
or redistribution. It is also included in the source distribution and served
by the running hub at `GET /api/v1/license`.
