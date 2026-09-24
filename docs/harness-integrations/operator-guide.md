# Harness integrations — operator guide for 0.2.0

This guide describes the implemented remediation on `feature/v0.2.0`, surface43.
The release gate is still open. See [implementation status](../../plans/pr34-remediation/IMPLEMENTATION_STATUS.md)
for executed tests and remaining work. Captures under `evidence/` describe older
builds, not current configuration instructions or permission to reuse their
accounts, endpoints or sessions.

## Identity and setup

An Agent is the existing canonical identity, with its skills, role and policies.
An endpoint configures a connection for that identity in a workspace. A runtime
session is an instance of the connection. Opening a session neither registers an
Agent nor replaces its profile. Several endpoints may belong to one Agent; a
logical delivery has one selected executor, not one execution per endpoint.

Enable `OKTO_NEXUS_FEATURE_HARNESS_INTEGRATIONS=true` explicitly on the intended
store. `serve` owns native runtimes and the durable dispatcher. MCP stdio uses the
authenticated owner proxy instead of spawning independent copies. Use existing
Nexus operator authentication for administration. A payload `agent_id` is an
identifier, never a credential. Ordinary agents require current scoped grants and
canonical permissions; REST and MCP share application authorization.

For an existing Agent such as `worker`:

1. Create an approved runtime profile for the adapter. Profiles default to disabled
   and `inherit_ambient=false`. Configure executable, provider/model and dedicated
   tool home for the authorized environment. Use supported secret references;
   never forward the Nexus operator credential to the subprocess.
2. Create an enabled endpoint linking Agent, profile, adapter and absolute project
   path. This configures a connection without spawning it.
3. Open the endpoint on demand, or explicitly approve its revision for boot.
   Configuration edits revoke grants and boot approvals; re-enabling a record
   does not restore them.
4. Grant only the actions needed by each caller. Preserve sandbox and native
   approvals; an approved profile is not permission to bypass them.

Exact shared MCP/REST configuration requests, revisions and grant restrictions
are documented in [runtime administration](runtime-administration.md).

For Codex, configure a dedicated `CODEX_HOME` in the approved profile and use
`adapter_id="codex"`. After approving that profile and endpoint, a typical
operator request to `harness_open` or `POST /api/v1/harness/sessions` is:

```json
{
  "agent_id": "worker",
  "kind": "codex",
  "endpoint_id": "worker-code",
  "project_root": "/approved/project"
}
```

Replace identifiers/path with actual approved configuration. Opening cannot
arbitrarily override its stored backend or inherit personal provider settings.
Keep the returned session identifier for explicit controls. Readiness is not
proof that later work completed.

## Four preserved connectors

| Kind / substrate | Transport | Distinction |
|---|---|---|
| `pi` | RPC JSONL | Managed process; steer at a turn boundary; interrupt requires settle |
| `codex` | app-server JSON-RPC | Managed process; native threads may share a connection; correlated controls |
| `claude_code` / `stream` | stream-json | Managed process; events and supported native approval/input requests |
| `claude_code` / `attach` | private cc-socks | External interactive session; send-only, no native acceptance/result channel |

Use `harness_list(view="adapters")` or `GET /api/v1/harness/kinds` for the catalog.
Declared capabilities are not a probe of the installed binary. Binding discovery
reports `capability_verification=not_probed`; effective binary/version negotiation
remains pending. Do not infer native deduplication, resume, ACK or sandbox support.

Attach additionally requires `OKTO_NEXUS_FEATURE_HARNESS_ATTACH=true`, a supported
POSIX environment and the operator-selected PID of a dedicated interactive session.
It does not discover or authorize personal sessions. The private protocol may
change with Claude releases. A socket write does not prove acceptance, rendering
or completion. No steer, interrupt or correlated result is invented. Detaching
Nexus does not terminate the external session.

Managed process ownership is implemented for Windows and Linux. Closing one Codex
thread preserves a sibling sharing its process. Shutdown drains owned activity and
journal capture before releasing ownership. Failure to drain remains pending or
unknown; a timeout or saved PID does not prove termination.

## Conversation, work and controls

Canonical `message_create` routing addresses the Agent. The inbox records logical
delivery and outbox records transport attempts. Eligible push reserves that same
inbox item so pull and push do not execute it twice. Ambiguous bindings fail
explicitly. A message commit means durable Nexus acceptance, not native acceptance.

Conversational input may produce a reply without gaining task execution authority.
Executable work uses a canonical handoff claim and scoped execution grant, bound
to endpoint and claim epoch. Native terminal does not automatically complete work:
completion/rejection requires an authorized canonical call or the configured
structured-result contract. Verification stays separate. Lease expiry does not
automatically release an uncertain managed claim.

The eight optional names remain `harness_list`, `harness_open`, `harness_send`,
`harness_steer`, `harness_interrupt`, `harness_close`, `harness_get` and
`harness_event_list`. Administrative sends and controls require current authority.
Persisted commands return an operation ID. Supply the idempotency key and expected
operation/turn/owner fields required by the control; stale controls conflict.
Exact retries retrieve the original decision rather than create another attempt.

Legacy text/content inputs are normalized at the facade; conflicts are rejected.
Payloads cannot supply identity or unrestricted authority. The adapter translates
the canonical envelope.

Read one operation with `harness_get(operation_id=...)`, or a session with
`harness_get(session_id=...)`. Use `harness_event_list` for durable sequenced replay.
Native delivery/capture are event driven; bounded database recovery and IPC wake
are separate from native status polling. Await the correlated settle event after
interrupt where required.

## Results, approvals and diagnostics

Native events enter the durable journal before projection. Operation, attempt,
owner and native turn correlation govern attribution. Queued, transport-written,
native-accepted, terminal-observed and handoff-completed are different facts.

Results are private correlated replies by default. Additional audiences require
approved configuration and current authority. Harness relay is an explicit endpoint
option for supported correlated conversation results, with persistent causal
depth/count/deadline limits and audience checks. There is no unrestricted broadcast
or blanket ban on harness communication.

With HITL enabled, supported requests appear in the operator Approvals view. Review
and submit explicit answers; no native default is silently chosen. Human decisions
are shown separately from native delivery and work completion. Unsupported secret
or remote schemas do not bypass controls. See the
[native input procedure](runtime-administration.md#native-questions-and-permissions-in-the-dashboard).

`harness_list(view="bindings")` groups visible endpoints/sessions under the Agent,
omitting private configuration, paths and secrets. A current owner-ready record is
persisted evidence, not a liveness probe. Operator outbox inspection exposes attempt
and recovery metadata without message bodies. The Runtimes dashboard shows uncertain operations, multiple visible ready bindings
and detached sessions, with explicit limits on what those records establish.
Recovery mutations remain in the operator API; Review native approvals opens the
existing canonical approval controls.

## Recovery and rollout

Do not retry uncertain writes merely because a timeout or lease expired. Inspect
the operation and runtime, then follow the
[recovery procedure](runtime-administration.md#recovering-an-uncertain-transport-attempt).
Pre-send cancellation differs from acknowledged-risk takeover. Conversation takeover
releases the original inbox item without replaying native transport. Command
abandonment retains history. Uncertain recovery quarantines the endpoint and revokes
grants/boot. Late results remain durable but cannot publish or consume the released
delivery using abandoned authority.

Generic conversation recovery refuses managed handoffs. Use explicit operator
`recover_handoff` with the exact handoff ID and claim epoch after closing or
reconciling the runtime. It reopens the same handoff without sending work; a new
claim is required. The old work envelope stays reserved, and late old-epoch
results cannot complete a new claim. See the administration reference.

Disabling admission stops new harness work while existing capture/recovery remains
available. A restarted disabled store with runtime history starts a maintenance
owner without native boot. Fresh disabled MCP surfaces omit harness tools; use
operator REST for recovery. Migrations are additive. Rollback uses deactivation
and drain/reconciliation, never destructive reverse SQL. Full backup/restore and
cutover acceptance remains part of the pending gate.

Current real-binary evidence is indexed in
[the remediation native campaign](../../plans/pr34-remediation/NATIVE_CAMPAIGN.md)
and subsequent milestones. Selected isolated Codex and Claude stream scenarios have
run; this does not qualify every advanced scenario/version. Pi native and dedicated
Claude attach native remain `NOT_RUN`. Fixtures and historical PR counts are not
current real-provider results. Follow status/backlog for release requirements.
