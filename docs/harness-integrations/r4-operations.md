# R4 execution operations

This is the current execution guide for the development branch. The
[acceptance ledger](../../plans/r4_execution/acceptance_inventory.json) records
the scope actually verified. G0–G3 and final release acceptance remain open.
Historical native captures and synthetic peers do not qualify the current Core,
provider, operating system or remote topology.

**Agents → Connections** (the cable icon) owns the complete local configuration:
select Local, Remote or All access, choose and save the local runtime integration,
discover/check an installation, configure its environment and workspace mappings,
approve its binding and explicitly authorize execution with a duration and action
budget. The MCP HTTP address uses the agent's original API key. There is no
additional connection key or legacy connection setup.

The trusted loopback dashboard can initiate runtime actions as the reserved
operator without minting an operator API key. Recorded operations and message
deliveries retain that operator's policy snapshot and revalidate it before
execution and result publication. The represented agent still needs its own
current execution grant; remote callers still authenticate normally.

For Meta-harness to run an agent automatically, enable **Reply automatically to
messages in this workspace** in its local connection and save the message policy.
This opt-in is scoped to that agent, connection and workspace. Changing the policy
revokes existing execution permissions, so authorize a new duration/action budget
after saving. The underlying Core output is published back into the conversation.
A provider authentication error can also appear as a runtime result: configuring
a connection does not itself log into the provider.

**Settings → Global runtime defaults** controls runtime availability and
conversation isolation. **Agents → Connections → Runtime policy for this agent**
can inherit or override each setting independently. Explicit agent overrides
take precedence over global defaults, including an enabled override when the
global runtime default is disabled. The global setting is a default, not an
unconditional kill switch. Existing per-sender connections migrate to an explicit
per-sender agent override; other agents inherit the shared-session global default.

Select **MCP only — runtime disabled** to block new runtime work for the affected
agents while retaining authenticated MCP access and inbox delivery under their
existing permissions. Pending resolutions and execution grants are invalidated.
Active local sessions close when lease renewal detects revoked authority; the
setting does not synchronously kill an already-running turn. Enabling runtime
again requires fresh execution permission. Close/interrupt containment remains
separate from admitting new work.

**Conversation sessions** defaults to **Shared session**. Select **Separate
session per sender** globally or in the agent override to keep one conversation per sender within the approved
connection/workspace. Follow-up messages reuse that sender's live session;
different senders can execute concurrently within existing Core capacity and
execution budgets. Dispatch remains ordered within each sender's conversation,
and result publication retains the original message and recipient correlation.
This selection also applies to explicitly dispatched managed handoffs, using
their creator as sender; creating a handoff alone still does not dispatch it.

Select **Separate session per sender + source session** (`per_sender_session`)
to isolate multiple conversations belonging to the same sending agent. For
example, A/session-1 and A/session-2 receive different sessions at C; another
message from A/session-1 reuses its existing session at C. Different source
sessions can dispatch concurrently; ordering is retained within each session.
The setting is available globally, as an agent override, in connection setup,
and in portable JSON/Connector `configure` (Core 0.2.63.dev0 or later).

Managed MCP and native tools use the authenticated runtime scope, including
server, executor, and canonical session ID. Automatic runtime results retain
their originating runtime session. Traditional MCP sends use `from_session_id`
with its verified `session_secret`; a bare attribution ID does not establish
session affinity. Approval replay preserves verified origin without storing
credentials. Messages without verified session provenance (including operator
UI messages, historical messages, and managed handoff dispatches without a
creator session proof) share a separate session per sender. Browser tabs and
message subjects are not session identifiers. Existing `shared` and `per_sender`
settings are unchanged; this mode does not change reply recipient selection.

Close affected agents' existing sessions before changing isolation, then renew
execution permission. Explicitly overridden agents are unaffected by changes to
defaults they do not inherit. Sender affinity persists in SQLite and is committed with admission;
unresolved sessions require reconciliation rather than silently opening a
duplicate. A closed session is replaced on the next message. Manually opened
sessions are not adopted by an isolated conversation. Context isolation does not
isolate workspace files or tool permissions, and each live sender session uses
additional runtime resources.

Use **Reconfigure local environment** to change an existing local connection's
workspace/provider home. Close its active sessions, prepare the new environment,
then review and approve the replacement using the existing connection name.
Stale connections expose the same preparation/review path. A replacement gets a
new review and preparation identity while uncertain requests remain recoverable.
For Claude Code, the provider home is the directory containing `.claude`, whose
login must already be configured; a blank provider home supplies no login.

Remote identity, installation and integration are configured in the Connector.
The agent ID selects the identity; its existing API key authenticates it. Local,
Remote and All restrict execution and do not grant a Connector authority by
themselves. The backend checks these restrictions during preparation, resolution
and before dispatch. Changing them invalidates earlier reviewed work. Existing
sessions retain their authenticated containment path.

Workspaces belong to messages/tasks, not agent identity. A local workspace mapping
authorizes a directory for that work; it does not set the agent's default
workspace. Runtime actions and history are in **Messages → message → Execution
recipient** and use that message's workspace. The remote view selects connections
already configured by the Connector, without choosing its runtime integration.

The dashboard reads scoped executor choices and current runtime options. It invalidates
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
Legacy endpoint/profile setup and scoped-key opening routes have been removed.
Historical records remain readable for audit and recovery. Full product acceptance
remains pending; see the current ledger for verified browser coverage.

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

In **Messages → message → Execution recipient → Runtime operations**, select an action and review
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

The selected operation's **Session history** panel reads recorded events in pages
of up to 100. Use **Previous events**, **Next events** and **Refresh history page**
to browse without sending runtime commands. Expand an event for its timestamp
and recorded payload. A missing-event warning means the displayed history is
incomplete. Refresh stays on the current stream and page; errors retain the last
successful page with an explicit warning. Reload recovers the selected operation
and reads history from the first page. This panel does not list all past sessions
or repair uncertain runtime state.

Use **Previous sessions → Refresh session list** on the selected connection to
browse earlier sessions, including closed ones. **View history** opens their
recorded events without resuming execution. The list is ordered by session ID
and paginated; refresh starts at the first page. Sessions opened under older
workspace realizations of the same binding remain historical records, not
authority to execute under the current realization. The API equivalent is
`GET /v1/runtime/sessions` with required `executor_id`, `binding_id`, `agent_id`
and optional `after_session_id`/`limit` (1–100). Subject, recorded opening actor
and current verified operator visibility matches individual session reads.

If the executor goes offline or its published inventory becomes stale, select
the recorded installation and workspace to recover the existing request or read
previous sessions. Historical connection visibility does not enable preparation,
new binding approval or runtime start. An admitted operation with an uncertain
effect remains in reconciliation; reload and **Check action result** only read
its original identity. Keep that request and the executor's durable journals for
reconciliation. Missing confirmation does not establish that the action failed
or that repeating it is safe.

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

The three catalog adapters are `codex_app_server`, `pi_rpc` and
`claude_stream`. A catalog entry is not proof
that its native version is installed, usable or qualified. Read current protocol
readiness, inventory evidence, binding status, effective session capabilities
and authorization. Missing qualification must remain unavailable; do not bypass
`remote_execution_ready` or promote synthetic test results into provider support.

Remote NXL uses the exact negotiated R4 revision from Core. R3 persisted bytes
remain historical data, not permission to submit a new R4 effect. An unsupported
method, version, platform or missing capability must produce a refusal rather
than a simulated success. Claude attach is no longer supported. Historical
attach records remain readable, but cannot authorize new execution.

For runtime message delivery, `Received` (`delivered_at`) is recorded when a
correlated `turn.submit` receipt first proves native acceptance (`SUBMITTED`,
`RUNNING`, or `SUCCEEDED`). Session opening and transport writes alone do not
mark a message received. Repeated receipts preserve the first timestamp;
the final processing acknowledgement remains separate. MCP inbox pull/ack
semantics are unchanged, and runtime receipts only update their own push delivery.

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

## Local execution permission limits

Local preparation pre-fills the provider directory from Core discovery:
`CODEX_HOME` or `~/.codex`, `CLAUDE_CONFIG_DIR` or `~/.claude`, and
`PI_CODING_AGENT_DIR` or `~/.pi/agent`. Only existing directories are suggested;
an invalid override does not silently fall back to another account. The local
operator can edit or clear the field. Suggestions neither read credentials nor
authorize access and are not included in the portable executor inventory.

The **Authorize local execution** form offers independent **No expiration** and
**Unlimited actions** options. Existing grants retain their original limits;
new forms still default to 60 minutes and 20 actions. Select both options for
consent that remains valid until revoked, without an action quota.

The grants API accepts explicit `expires_at: null` and `max_executions: null`
for local (embedded) bindings only. Bounded values retain the 24-hour and
1..1000-action validation. Only an operator may issue these permissions.
Unbounded consent does not bypass agent, workspace, connection, runtime policy,
credential or profile checks, nor the independent causality limits.
Core leases and session MCP credentials remain short-lived and renewable;
revocation, deactivation and disabling runtime still stop execution.

## Runtime prompt context

Nexus supplies its agent identity, delivery correlation and instructions for
using Nexus tools. It does not instruct the harness to avoid tools or limit
its available capabilities. Internal transport trust metadata stays in the
stored envelope and is omitted from the model prompt. Nexus authorization
continues to apply at the authenticated tool boundary.

## Nexus tool approval policy

In **Agents > Connections**, select the runtime workspace and installation.
**Permissão para tools / MCP do Nexus** offers **Sempre permitir** for the Nexus
server generated for that integration. Codex receives a per-server tool approval
policy; Claude Code receives a scoped MCP tool allowlist. Pi native bridge tools
already run without harness approval prompts. Agent capabilities and Nexus domain
policies remain enforced, and other MCP servers and shell commands are unaffected.

The default is **Solicitar aprovação do harness**. Only an operator can change
this setting. Close the integration's runtime sessions before saving, then
reauthorize execution and start a new session. Saving changes the endpoint
revision and invalidates its execution grants; existing sessions are never
silently granted broader tool permissions.

Codex MCP permission requests with an empty form expose **Approve request**.
The canonical response contains an empty content object. Expired requests remain
readable but cannot be approved; trigger a new request to continue.

## Execution log

The **Execution log** menu is an operator-only, read-only troubleshooting view.
It combines canonical receipts (including provider authentication failures),
dispatch failures before opening, committed runtime error/lifecycle/turn/input
events, and runtime authorization decisions. Filter by workspace, severity,
agent ID, adapter ID and local date/time; results are paginated newest first.
Use **Refresh log** to retrieve new records.

Expand **Diagnostic details** for endpoint, executor, session, operation and
structured error facts. Native prompts, tool arguments, full frames and stderr
are excluded; known credential patterns in diagnostic messages are redacted.
This view reads existing durable records, not the server console log. Dispatch
failure rows are current snapshots and explicitly use operation creation time,
because the dispatch table does not retain an error observation timestamp.
Historical faults remain visible after recovery and do not establish current
runtime health. MCP acknowledgement and execution behavior are unchanged.

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
# Native questions and interlocutors

Native input requests resolve their recipient from the admitted source turn.
For message delivery, Nexus follows the canonical delivery mapping to the
original message sender; the runtime subject is not assumed to be the sender.
This preserves A/C and B/C routing even when both turns share C's session.
A missing domain message is not replaced with the operation actor. Direct
runtime turns use their authenticated initiating actor.

Only that authenticated recipient may submit an answer, and dispatch rechecks
the same authority. Tool permission decisions, including Codex MCP permission
elicitations, remain operator decisions. Core validates input answer shape
before Nexus commits its decision; rejected input leaves the question pending.

`GET /v1/runtime/input-requests` returns live questions for the current identity,
optionally filtered by `workspace_id`. The local dashboard adapter exposes the
same use case. Meta-Harness renders operator questions with the existing native
choice/custom-text controls and canonical response submission.

Managed MCP sessions expose `runtime_input_list` and `runtime_input_respond`.
Both require explicit session capability actions; the listing is limited to the
bound agent/workspace and responding preserves the native answer contract.
Native permission requests cannot be decided through these session tools.
A committed response records a non-secret capability reference and the actor
revision guard. Before native dispatch, Nexus checks the same capability,
actions, owner, grant, revisions and applied lease again. The reference is
internal provenance, never an inbound credential or a reconstructed agent key.
Canonical-key callers and the operator UI keep their existing authentication.

Managed MCP sessions can use `agent_list`, `agent_get` and `capability_list`
for discovery. Both local and remote session credentials include these actions;
each call still requires its explicit action and a valid session, grant and
applied lease. Agent discovery preserves the authenticated agent's outbound
and each peer's inbound communication scope. `agent_get.agent_id` identifies
the peer being queried, not a replacement caller. Profiles include public
presence and connection status without runtime host paths or credentials.

`coordination_health` additionally requires `health.read`, the enabled health
feature and the session's canonical workspace ID as `project_root`. It cannot
read another workspace. Communication permissions continue to apply to managed
message, handoff and event tools; session actions do not override those permissions.
`harness_list` connection administration remains unavailable to session
credentials. Use agent discovery for peer status; full communication access
does not confer operator privileges. Existing credentials are not broadened
in place: these added actions are issued with newly opened sessions.

Application and public HTTP MCP tests cover these tools, malformed answers,
recipient isolation and revocation before dispatch. Pi exposes the equivalent
`nexus_runtime_input_list` and `nexus_runtime_input_respond` tools through its
Core-owned extension and scoped native socket. Native HTTP actions `input_list`
and `input_respond` use the same decision service. Responses omit
`client_intent_id`: Nexus derives it from the caller session scope and action ID,
so replay cannot duplicate the decision or change an existing answer.
The installed Pi 0.87.1 successfully called the list tool in an isolated campaign;
the response path has native HTTP fixture coverage, not yet a provider-to-provider
qualification. Automatic question delivery to another harness and the complete
provider-to-provider question matrix remain to be integrated and qualified.

Managed MCP sessions also expose `message_create` with explicit capability
permission. Supply the bound `workspace_id` and `from_agent_id`; omit legacy
`from_session_id` and `session_secret`. The existing domain sender permissions,
audience, governance approvals and causal budgets still apply. A queued runtime
delivery records a non-secret capability reference and revalidates that sender
before dispatch and result publication. Approval re-execution retains the same
sender reference and fails if it has been revoked; it cannot borrow the
operator's identity. Canonical-key MCP authentication is unchanged.

This enables a managed harness to activate another runtime through a private
message. Its captured reply targets the original sender's inbox. Sending that
reply into another runtime turn additionally requires the endpoint's existing
`relay_results` policy; inbox publication alone does not imply that policy.
Pi exposes the same domain operation as `nexus_message_create`. Pass
`message={subject,body,target:{strategy:"direct",agent_id:"recipient"}}`, with
optional channel, parent-message and artifact references. The Server supplies
sender and workspace from the native session capability. The Core socket and
Connector HTTP backend carry a typed `MessageCreate` request; they do not
implement message delivery themselves. Native action receipts commit with the
message or pending approval. Repeating a tool call ID returns its recorded
result; changing its content conflicts. A failed receipt write rolls back the
message. Deferred approval uses the normal durable executor, not the native
request's transaction-bound connection.

An isolated real campaign on 2026-10-03 qualified managed MCP message creation
with Codex 0.159.0-alpha.12.1 and Claude 2.1.288. Both directions also completed
native questions: Claude AskUserQuestion answered by Codex and Codex
requestUserInput answered by Claude, with the canonical decision actor equal to
the originating agent and native `input.provide` receipts. The initiating
harness explicitly polled `runtime_input_list`; this is not evidence of an
automatic question-triggered wake. Messages and returned Green answers were
checked in the dashboard. Pi and deployment to the user's main server remain
separate validation work.
