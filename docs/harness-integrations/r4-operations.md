# R4 execution operations

This is the current execution guide for the development branch. The
[acceptance ledger](../../plans/r4_execution/acceptance_inventory.json) records
the scope actually verified. G0–G3 and final release acceptance remain open.
Historical native captures and synthetic peers do not qualify the current Core,
provider, operating system or remote topology.

The development dashboard now reads scoped executor choices and current runtime
options, with explicit host, installation and workspace selection. It invalidates
the selected installation when inventory revisions/freshness or host access change.
For a unique preparation already published by the host, the panel now reviews
the Server proposal and applies explicit operator consent. It reuses an existing
binding on subsequent visits. Preparation references and scoped binding state
come from runtime-options; the browser never reconstructs them from display order.
Requests are recorded in tab storage before submission. After a lost approval
response, retry the same request or inspect its binding; do not generate another
approval to guess the outcome. For an embedded host, an operator can now prepare
an existing workspace or create one using an existing absolute directory on the
Server's computer. Select the installation, enter its workspace directory and
optional provider home/protected credential references, then explicitly approve
that configuration. Only reference names (`NAME=vault:reference` or
`NAME=provider:reference`) belong in the form; never enter credential values.
A blank provider home does not configure a login directory. Preparation neither
probes an unobserved build nor approves its binding or starts a runtime.

After a lost preparation response, retry the same recorded request, including
after reloading the tab. The browser preserves its original directories and
consent. A first request explicitly rejected by the Server can be edited and
approved again; an uncertain request is retained. Storage failure prevents
submission. The panel then selects the returned workspace and offers the separate
binding review. For a local installation marked `NOT_PROBED`, the separate
**Check installation version** control requests explicit operator consent to
select those exact bytes and run the Core's contained version command. No
workspace, provider login directory or provider credentials reach that process.
The observation survives restart and is reused only for the same discovery
evidence, Core version and platform; a file change requires a new check.
After a lost check response, refresh inventory first. A passive refresh can
recover a committed observation without executing the command again. Another
version check requires another explicit approval. This does not grant runtime
authority or qualify an unsupported build/platform. The runtime operations panel
provides separate review and submission for start/reuse, send, steer, interrupt
and close after selecting a binding.
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

Core 0.2.54 observes PATH installations even before local trust selection. These
appear with `untrusted` and `selection_required`, not as absent installations.
Windows discovery reads fixed Codex npm and Pi npm/managed release payloads
without executing shell or JavaScript launchers. Unknown custom wrappers are not
interpreted. Approve physical discovery roots on the execution host, or explicitly
select a local installation using the operator version-check control. Finding
an installation grants no authority.
The embedded Server accepts `--harness-root`; registered remote hosts use
`executor configure-discovery`. Neither option adds directories to PATH. Pi's
content identity includes its package dependencies, so discovery can take seconds.

The local version-check API is
`POST /v1/runtime/executors/{executor_id}/installations:check`, with
`agent_id`, `adapter_id`, `candidate_ref`, `inventory_revision` and `approved: true`.
It accepts only this Server's embedded executor and an authenticated operator.
It never accepts caller-supplied executable paths, command arguments or
environment variables. Concurrent checks are refused; disconnecting the HTTP
observer does not abandon the owned bounded Core probe. Shutdown waits for that
probe, and authority/identity drift prevents committing its result. Up to 64
local observations are retained per executor. A successful response reports
the observed version and `runtime_authorized: false`.

An authenticated operator can include `agent_id` in
`POST /v1/runtime/intents:resolve` to request an action for that agent. Omitting
it retains the authenticated agent's own scope. An ordinary agent cannot use
this field to represent another identity. The operator remains the recorded
actor; session, workspace, lease and runtime grant belong to the subject.
Resolution creates no native effect. Review the returned resolution, then submit
its exact `client_intent_id`, `operation_id`, `resolution_revision` and `intent_hash`
to `POST /v1/runtime/operations`. Recover a lost response by reading the same
`GET /v1/runtime/intents/{client_intent_id}`; do not mint a replacement operation.

Operator initiation does not issue a grant or consume the operator's unrestricted
administrative privilege as runtime authority. The subject still needs a separately
issued, current canonical execution grant. Operator identity/policy changes after
resolution invalidate admission and pending dispatch; changes after opening also
invalidate lease renewal and capability authority. Subject revocation, grants,
budgets, inventory and binding checks remain in force.

In **Agents → Connections → Runtime operations**, select an action and review
its session, message and target before **Submit reviewed action**. Start can
reuse an unambiguous session, create a new one explicitly, or reuse an entered
session ID. An initial message becomes a separate tracked turn. Steer and
interrupt distinguish a specific native turn ID from the current run at execution
time; those choices are not interchangeable.

The tab stores the immutable request, including its message, under the current
Server, actor and binding before sending it. If browser storage fails, nothing
is submitted. Reloading only reads the original intent and operation. After a
lost response, use **Check action result** or retry the same recorded review or
submission; do not create a replacement action. Admission, executor stage,
initial-turn status and available captured output are shown separately. An
unknown result is retained for reconciliation. This panel does not qualify a
provider or replace full history and independent-host browser acceptance.

Request a passive inventory refresh with
`POST /v1/runtime/executors/{executor_id}/inventory:refresh` and a stable
`{"client_intent_id":"your-request-id"}` under the authorized agent's bearer key.
Repeat the same request to read its current state: `PENDING`, `REQUESTED`,
`UPDATED` or `OFFLINE`. A `202` response records the request, not its completion.
An offline request stays queued. The embedded host consumes requests through its
existing 30-second refresh loop; a compatible connected Connector polls every
five seconds and then performs passive discovery. Discovery duration adds to
these intervals. At most 32 unresolved requests can be queued per executor.

`UPDATED` requires a new observation correlated with that delivery. A routine
inventory publication alone does not acknowledge a request. Refresh neither
probes CLI versions nor grants runtime authority. Older Connectors can continue
periodic publication but cannot consume these requests. The new Connector checks
`inventory_refresh_supported` before using the HTTP extension. Independent-host
acceptance of this flow remains pending.

In **Agents → Connections**, select an execution host and use **Request host
inventory refresh**. The panel reports queued, received, offline and updated
states. **Reload published inventory** only rereads existing Server data. An
uncertain reply offers **Retry inventory refresh**, which keeps the same request.
Pending requests survive navigation and page reload within the same browser tab,
scoped to the Server, authenticated identity and executor; credentials are not
stored in the refresh record. Switching hosts restores each host's pending
request. After completion, the panel reloads choices and clears the previous
installation selection so the user reviews the new observation.

On a remote Connector host, explicitly observe a selected `NOT_PROBED`
installation with `okto-nexus-connector executor probe --help`. Select the exact
candidate and inventory revision from `discover --server-id SERVER_ID`.
The probe runs Core's contained version observation, persists byte-bound local
evidence and leaves publication to the daemon. Wait for the updated Server
inventory before preparing a realization/binding. A recorded version does not
override Core qualification or grant execution. The embedded Server's equivalent
explicit version-check surface is described above; it does not qualify an
unsupported provider build.

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

In **Approvals**, R4 runtime requests use **Review request**. The detail panel
shows the agent, host and session, then asks for an explicit permission decision
or answer. **Approve request**, **Send answer** and **Deny runtime request** send
the original canonical request reference, revision, hash and CAS token to the
R4 decision endpoint. They do not use the legacy generic approval action.
Only a currently authenticated operator may confirm the decision.

After a lost response, **Check native decision** or reopen the recorded item in
Recent decisions. Reloading only reads; it does not submit another decision.
The tab stores immutable decision metadata but never the input response. An
uncertain input retry requires the same answer to be explicitly supplied again;
the Server verifies its digest and retained authority. No form value or provider
default is automatically chosen. Expiry disables new answers while leaving
recorded decision and delivery status readable. Confirmation, denial, pending
dispatch and uncertain native delivery remain separate facts.

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
