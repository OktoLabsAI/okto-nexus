# R4 execution operations

This is the current execution guide for the development branch. The
[acceptance ledger](../../plans/r4_execution/acceptance_inventory.json) records
the scope actually verified. G0–G3 and final release acceptance remain open.
Historical native captures and synthetic peers do not qualify the current Core,
provider, operating system or remote topology.

The development dashboard now reads scoped executor choices and current runtime
options, with explicit host, installation and workspace selection. It invalidates
the selected installation when inventory revisions/freshness or host access change.
Consent, binding apply and runtime operations are not yet implemented in that panel.
Legacy endpoint/profile controls remain in a collapsed maintenance section. Use
the authenticated R4 HTTP and Connector CLI flows to complete development setup;
do not treat a legacy connection command as remote Connector setup. Full browser
acceptance remains pending.

Request runtime options with `executor_id` and, for binding/start eligibility,
the explicitly selected `workspace_id`. The subject and an authenticated operator
can inspect executor-owned technical facts. Eligibility combines current inventory
freshness, connectivity, configuration and authorization in one transaction.
Preparation can remain available for an unqualified installation, but start
requires `READY_FOR_RUNTIME`, an approved current binding and execution authority.
Reads neither consume grants nor create operations. Missing or ambiguous choices
remain blocked with separate policy reasons; Core's technical assessment is
preserved. Eligibility is a preview, and admission revalidates current authority.

An operator inspecting another agent currently receives
`SUBJECT_IDENTITY_REQUIRED` for start: the public intent route still requires
that subject's authenticated identity. Operator inspection does not create an
agent credential or delegate execution. The contract's inventory-refresh HTTP
route and complete browser onboarding remain pending.

On a remote Connector host, explicitly observe a selected `NOT_PROBED`
installation with `okto-nexus-connector executor probe --help`. Select the exact
candidate and inventory revision from `discover --server-id SERVER_ID`.
The probe runs Core's contained version observation, persists byte-bound local
evidence and leaves publication to the daemon. Wait for the updated Server
inventory before preparing a realization/binding. A recorded version does not
override Core qualification or grant execution. The embedded Server's equivalent
explicit qualification surface remains pending.

Read the current binding with `GET /v1/connections/bindings/{binding_id}` as its
subject or an operator. It returns the current references, revisions and canonical
state, including replacement, disabled, stale and revoked bindings. An APPROVED
binding records consent; it does not promise a fresh inventory, an online executor
or authority to start. Inspection remains available to an operator when execution
is disabled or the provider has been removed. Responses never include executor
paths, local configuration or credentials.

## Start and connect

Install the approved Nexus artifact with its `serve-lite` or `serve` extra and
the exact Core artifact selected for the campaign. Local execution embeds Core;
it does not require the Connector application or a sibling source checkout.
The Connector application runs on a remote execution host and uses the same
qualified Core version, artifact hash and R4 contract revision as the Server.

```sh
okto-nexus serve --help
okto-nexus serve
okto-nexus admin --help
```

The default dashboard is `http://127.0.0.1:8202/`; agents connect directly to
`http://127.0.0.1:8202/mcp` over streamable HTTP. Authenticate with their existing
Agent key in the Authorization Bearer header. Nexus MCP stdio was removed.
Core's native stdio protocols are a different transport, owned by Core.
An Agent ID in a request is not authentication. Executor tickets and session MCP
capabilities have distinct audiences and cannot replace operator credentials.

For an existing client configuration, use the implemented migration command:

```sh
okto-nexus admin migrate-mcp-entry --help
```

Select only the intended Nexus entry and inspect the migration backup. Do not
replace other MCP servers or copy credentials from historical captures.

## Discover, approve and submit

Use these existing HTTP routes with authenticated requests. `/v1` returns direct
JSON objects and `X-Nexus-Connections-Revision`; `/api/v1` retains its legacy
envelope. Consult the returned schema/revision rather than mixing body formats.

| Action | Route |
|---|---|
| Inspect protocols and readiness | `GET /v1/connections/protocol` |
| Inspect the authenticated identity | `GET /v1/connections/me` |
| List scoped execution hosts | `GET /v1/agents/{agent_id}/executors` |
| Read scoped choices for an Agent | `GET /v1/agents/{agent_id}/runtime-options` |
| Read executor inventory | `GET /v1/runtime/executors/{executor_id}/inventory` |
| Prepare an approved local realization | `POST /v1/runtime/executors/{executor_id}/realizations` |
| Prepare a binding | `POST /v1/connections/bindings:prepare` |
| Apply the reviewed binding proposal | `POST /v1/connections/bindings:apply` |
| Read the current scoped binding | `GET /v1/connections/bindings/{binding_id}` |
| Resolve an intent | `POST /v1/runtime/intents:resolve` |
| Submit the resolved operation | `POST /v1/runtime/operations` |
| Inspect a durable operation | `GET /v1/runtime/operations/{operation_id}` |
| Inspect a session | `GET /v1/runtime/sessions/{session_id}` |
| Read sequenced session events | `GET /v1/runtime/sessions/{session_id}/events` |

For local execution, an operator selects a current inventory candidate, approves
the workspace and dedicated provider configuration, then prepares and applies
the binding. Binding creation does not start a process. Preserve the returned
executor, realization, workspace binding and binding references; do not invent
IDs or substitute a Server path for a remote workspace.

For remote execution, register the executor through
`POST /v1/connections/executors:register`. The remote host publishes its own
inventory and keeps its executable paths, provider home and credentials locally.
The Server dispatches admitted operations over the authenticated executor link.
An open socket or an issued ticket alone does not establish execution readiness.

Resolve `runtime.start` against the selected binding and workspace binding. If
`can_submit` is false, inspect `blockers` and correct their cause. Submit the
returned `client_intent_id`, `operation_id`, `resolution_revision` and
`intent_hash`. Reuse the original intent and operation identity when inspecting
or retrying the same request. Do not generate a replacement operation to evade
an uncertain outcome. The Server, not the operator or Connector, owns dispatch.

## Capabilities, authority and outcomes

The four catalog adapters are `codex_app_server`, `pi_rpc`,
`claude_stream` and `claude_attach`. A catalog entry is not proof
that its native version is installed, usable or qualified. Read current protocol
readiness, inventory evidence, binding status, effective session capabilities
and authorization. Missing qualification must remain unavailable; do not bypass
`remote_execution_ready` or promote synthetic test results into provider support.

Remote NXL uses the exact negotiated R4 revision from Core. R3 persisted bytes
remain historical data, not permission to submit a new R4 effect. An unsupported
method, version, platform or missing capability must produce a refusal rather
than a simulated success. Claude attach is an external session: a socket write
does not prove native acceptance or completion, and detaching does not authorize
termination of the external process.

Admission, transport delivery, native receipt and task completion are separate
facts. `RECONCILING`, `possible_effect=true` or `retry_safe=false` require
inspection/reconciliation; they do not authorize automatic replay or transfer.
Native terminal events do not complete a canonical handoff. Managed work still
requires its claim, grant and explicit authorized completion. MCP pull and managed
delivery share one logical claim; observer endpoints do not execute it.

Approval and input decisions require current scoped authority and correlation
to the pending request. Inspect the decision using the operation/session views;
neither a notification nor a submitted decision proves that Core applied it.
Revocation, expired grants and changed ownership continue to deny new effects.

## Shutdown, migration and recovery

```sh
okto-nexus admin shutdown --help
okto-nexus admin shutdown-status --help
okto-nexus admin backup --help
okto-nexus admin migrate-execution --help
```

Drain owners before migration or restore. A timeout is not proof of termination.
The database-only admin backup is not a complete native runtime recovery snapshot.
Follow [migration and recovery](migration-and-recovery.md) for the repository's
offline combined backup procedure, which preserves Nexus data, Core journals,
artifacts and owned session MCP configuration. Restore only into a new home after
stopping all writers. Preserve uncertain outcomes and original ownership/path
constraints; restoring data cannot undo a provider effect.

## Evidence and remaining acceptance

See [current evidence](evidence-index.md) for installed artifact campaigns and
their limits. Final local provider execution, independent remote hosts, the
required platform/Python/provider matrix, packaged dashboard and complete
regressions must be proved against the final artifact tuple before release.
The older [operator notes](operator-guide.md) and
[administration reference](runtime-administration.md) describe retained legacy
records and contracts; their legacy profile/open examples are not R4 onboarding.
