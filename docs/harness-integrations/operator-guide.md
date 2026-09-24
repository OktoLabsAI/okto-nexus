# Harness integrations — operator guide for 0.2.0

This guide describes the implemented remediation on `feature/v0.2.0`, surface57.
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

Approved backend credentials resolved from secret references are scrubbed from
native diagnostics, approval projections and durable output. For connections
with known credentials, raw text payload fields are withheld and normalized
streaming text is redacted before journal capture, including values split across
frames. The compatibility report labels this redaction policy. Native approval
still requires its original authorized decision. See the
[redaction evidence and limits](../../plans/pr34-remediation/P03_BACKEND_SECRET_REDACTION.md);
this does not discover unknown secrets inside external credential files. The protection applies to new captures; existing append-only journals and results are not rewritten or replayed. If historical exposure is confirmed, rotate the affected credential and use the approved retention/incident procedure.

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

Conversational command contract v3 accepts canonical data, for example:

```json
{"schema_version":1,"content":[{"type":"text","text":"Review this proposal"}],"subject":"Proposal","response_requested":true}
```

Only conversational text blocks, optional subject, `intent="conversation"` and
boolean `response_requested` are input fields. The server fills sender, recipient,
workspace, operation/root IDs and untrusted-content provenance from the authenticated
command and approved session. The adapter translates this complete canonical
envelope; a steering command uses server intent `runtime_control`. Payload identity,
trust, handoff/claim IDs, arbitrary native options and artifact references are
rejected. Use canonical artifact/message/handoff APIs for those workflows.

Legacy nonempty text/content strings normalize to text; both keys are accepted only
when equal. Legacy native prompt rendering and persisted v2 idempotent retries stay
compatible. JSON-string objects are parsed consistently with the MCP convention;
invalid JSON and non-object values are rejected explicitly. The complete payload
remains bounded to64 KiB. None of these formats grants task execution authority.

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

Protocol readiness rejects Pi get_state responses unless success is true and data
is an object. Codex thread/start must return a bounded nonempty string thread ID.
Failure reports protocol_incompatible and quarantines that failed open; it does
not prove compatibility of other capabilities or prohibit healthy adapters.

Codex session compatibility_report records only a recognized native version from
initialize. Migration056 stores this independently from caller metadata. Unknown
or prerelease version formats remain unobserved; private home paths, full user-agent
and other handshake fields are discarded. capabilities_verified remains false:
this observation is not effective-capability negotiation or permission. REST, MCP
session reads and authorized bindings expose the same stored report.

Profiles with required_native_requests now require both adapter declaration and
a matching server-owned runtime contract before readiness. The current exact
Codex0.156.1 request contract covers the four documented approval/input methods.
Unknown versions or adapters without equivalent evidence cannot satisfy explicit
requirements; they return native_requirements_unverified and quarantine that open.
An observed version alone does not grant permissions or verify all capabilities.
For native command approvals, a human rejection maps to decline when available,
or cancel when the native request offers only cancel. Approve maps only to accept;
policy-amendment and session-wide alternatives are never inferred.

Claude stream also records `executable_version` from a read-only `--version`
probe of the approved executable, with the same isolated environment and working
directory. The owned probe has a three-second deadline and bounded output; a
timeout stops startup and reaps its process tree. No model turn is used to discover
the version. Malformed output grants no compatible native requests.
The exact 2.1.280 contract includes Write/Edit/Bash and AskUserQuestion. In 2.1.281,
only Write and AskUserQuestion have been qualified; Edit/Bash remain unverified
for explicit profile requirements. Native denial and explicit question input were
executed locally on 2.1.281. This is not a sandbox or general capability grant.

Attach requires `peerProtocol` to be the integer `1`, both at open and immediately
before sending. Missing/null, boolean, float and other versions fail with
`protocol_mismatch`; a live socket alone cannot establish wire compatibility.
The server-owned report records `attach_registry_protocol`, `cc_socks_peer_1`, a
bounded version when present, and `ack_level=NONE`. These are local preconditions,
not native acceptance: no token is sent by the probe, writes stay unconfirmed,
close detaches, and managed work/interrupt/steer remain unsupported. No native
Claude attach session has been qualified in this remediation campaign.

Steering and interruption require `compatible_controls` from the server-owned
session report and a tested `control_contract_basis`. Declaration alone is not
enough. The shared admission service, dispatcher revalidation and supervisor send
all enforce this; missing/unknown reports return `native_control_unverified`.
This check is additional to grants, current profile, active operation and turn
fencing, and never authorizes an otherwise denied control. Conversation and
cleanup retain their separate contracts.

Current control version contracts are Codex0.156.1, Claude2.1.281 and Pi0.85.1.
Pi uses the same bounded owned executable-version probe as Claude, with its own
strict version format. Pi protocol fixtures/reference qualify the contract;
native Pi remains NOT_RUN. Codex and Claude controls have isolated local native
observations; consult the milestone evidence for failures and precise scope.
No version match establishes native deduplication, replay or general capability
verification. Trusted processless extensions can report a tested protocol contract
without inventing a native executable version.

From surface49, opening a compatible Codex endpoint can reuse an already live
connection. Sharing requires the same canonical agent, workspace, adapter,
profile ID/revision, resolved backend environment and HITL mode. Secret rotation
or a profile change creates a separate connection. No native or caller metadata
can select another connection. The comparison key is private process memory and
is never persisted or returned. Pi, Claude stream and attach do not gain sharing.

Each open still creates its own logical session and native thread, with its own
delivery lane and event attribution. Closing one session detaches that thread;
the process stays alive for its siblings. Closing the last session observes owned
process termination. This does not fan out an inbox delivery to multiple endpoints
or authorize additional work. Simultaneous first opens may create separate owned
connections; reuse selects a ready live connection, never a speculative startup.

## Store writer compatibility (schema 057)

Upgrade every writer sharing the Nexus home before enabling runtime integrations. The first runtime owner claim activates a persistent version-1 writer contract. Older connections cannot mutate protected identity, delivery, handoff or runtime records, even if they connected before activation. Do not remove its triggers or lower the required version to roll back an application package.

Keep each producer's `feature_harness_integrations` setting aligned with the serve owner. A mismatch rejects message admission with `CONFIG_ERROR` and reason `runtime_writer_mode_mismatch`, before creating a delivery. `runtime_writer_incompatible` requires a compatible client upgrade. Correct the configuration/version and review the rejected request before resubmitting; these errors do not authorize replay of an uncertain native operation.

An authorized owner settings change switches admission mode atomically; disabling retains the compatibility fence and durable history. Inspect `writer_contract.required_contract` and `writer_contract.admission_enabled` through operator-only `GET /api/v1/harness/diagnostics` or MCP `harness_list(view="diagnostics")`. These compatibility declarations do not replace Nexus authentication.

## Combined offline backup and restore

A database-only copy does not preserve the runtime journal or external artifacts. Use the repository's [tested offline procedure](../../plans/pr34-remediation/P12_COMBINED_BACKUP_RESTORE.md) after stopping all writers, artifact maintenance and managed native owners. The procedure requires explicit acknowledgement of quiescence, checks owner exclusion, uses SQLite's backup API, validates file hashes/references and journal checkpoints, and refuses overwrite. It never starts a native process or replays a prompt.

Restore into a new home and start with an explicit `--feature-harness-integrations false` while reviewing uncertain operations and preserved executor reservations. Retain the original store and dedupe history. The snapshot contains private store data and must receive the same access restrictions. The procedure lives at `plans/pr34-remediation/offline_runtime_backup.py`; it is not a remotely callable admin endpoint.


## Capture capacity admission fence (schema 062)

A known journal quota or write/fsync failure pauses new executable delivery,
send/steer and open admission in the shared store. Updated REST/MCP callers
receive `CONFLICT` with reason `runtime_capture_unavailable`; independent stdio
writers see the same fence. Database triggers also reject inserts by already-open
older writers. A rejected transaction preserves no new message, reservation,
grant charge or executable intent. Existing authorized idempotent replies remain
readable; stop controls retain their separate authorization.

The active owner records capture availability through its owner/epoch fence. A
stale owner cannot reopen admission. The health update performs SQLite work only
after journal IO has ended. If SQLite cannot persist the update, an error is logged
and the owner retains a bounded recovery retry; native dispatch still checks
capture availability immediately before calling the adapter. No availability
report promises that a concurrent future disk write will succeed.

For quota exhaustion, use operator journal diagnostics and compact only records
already projected into SQLite. Successful compaction revalidates capture and
restores admission without deleting projected results. An uncertain write/fsync
failure cannot be cleared by compaction: quiesce the owner, repair storage and
restart with the matching journal/database so integrity and checkpoint recovery
run. Do not lower writer requirements, remove triggers or replay uncertain
operations to clear the condition. A new healthy owner revalidates the journal
before restoring admission. SQLite capacity failures reject writes and never
acknowledge a new durable intent; restore storage before reviewing/resubmitting a
definitively rejected request.
