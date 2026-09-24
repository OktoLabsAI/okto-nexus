# Runtime administration — surface 45

This reference describes the implemented 0.2.0 administrative subset. The release
and complete P11/P12 gates are still pending; consult the
[execution status](../../plans/pr34-remediation/IMPLEMENTATION_STATUS.md).

Enable `OKTO_NEXUS_FEATURE_HARNESS_INTEGRATIONS=true` explicitly. Authenticate as
the operator using the existing Nexus authentication mechanism. An agent ID in
the body cannot supply operator authority. These operations configure existing
agents' connections; they never register or replace the Agent profile. Configuring
an endpoint does not itself spawn a process.

`harness_list` keeps the same tool name. Its `view` selects `adapters`, `endpoints`,
`profiles`, `bindings`, `outbox`, `journal` or `artifacts`. `maintenance` is an object (or JSON object
string); its `action` defaults to `list` for endpoint/profile views. Do not pass
`compact` outside the journal view.

| MCP view/action | REST equivalent | Required parameters in maintenance |
|---|---|---|
| bindings | GET /api/v1/harness/bindings | Optional agent_id, limit (1..100, default50), after_endpoint_id |
| outbox/inspect | GET or POST /api/v1/harness/outbox | Optional operation_id, limit (1..100, default50), after_operation_id |
| outbox/cancel_pending, release_to_inbox, abandon_command | POST /api/v1/harness/outbox | operation_id, expected_state, expected_attempt_id, expected_owner_epoch, idempotency_key, reason; uncertain actions also require acknowledge_duplicate_risk=true |
| profiles/list | GET /api/v1/harness/profiles | None |
| profiles/create | POST /api/v1/harness/profiles | profile_id, adapter_id |
| profiles/update | PATCH /api/v1/harness/profiles/{id} | profile_id, expected_revision and one or more mutable fields |
| endpoints/list | GET /api/v1/harness/endpoints | None; agent_id is an optional filter |
| endpoints/create | POST /api/v1/harness/endpoints | endpoint_id, agent_id, adapter_id, project_root; profile_id for managed processes |
| endpoints/update | PATCH /api/v1/harness/endpoints/{id} | endpoint_id, expected_revision and one or more mutable fields |
| endpoints/boot | PUT /api/v1/harness/endpoints/{id}/boot | endpoint_id, expected_revision, enabled |
| endpoints/reconcile | POST /api/v1/harness/endpoints/{id}/reconcile | endpoint_id, expected_revision, idempotency_key, reason, acknowledge_uncertain_effects=true |

REST bodies omit `action` and path-bound `endpoint_id`. Both surfaces use the same
input models and application services. Unknown fields and implicit type coercion
are rejected: send JSON `true`, not the string `"true"`. Revisions must be positive
integers. Surface 39 introduced strict validation; surface 40 extends edits.
Clients caching older schemas should refresh `nexus_info`. Reference resource
`tool-docs/identity` is version 9. Surface 41 adds scoped binding discovery;
surface 42 adds explicit operation recovery.

The `bindings` view is also available to authenticated agents with current
endpoint-scoped `discover` grants. The operator issues those through
`POST /api/v1/harness/grants` with actor_agent_id, endpoint_id,
actions=["discover"] and expires_at (within 24 hours). A grant only restricts
existing policy: the caller must retain events.read and communication reachability
to the represented Agent. Revocation, expiry, key rotation, inactive agents and
changed profile revisions remove visibility. A discovery grant does not allow
open/send/read-content/control; no grants returns an empty agents array.

For example, call `harness_list` with
`{"view":"bindings","maintenance":{"agent_id":"worker","limit":20}}`.
The response groups endpoints under each canonical agent_id and lists its
canonical skill_names without rewriting the Agent. It omits private metadata,
paths, environment, secret references, configuration and notification audiences.
`declared_capabilities` describe the adapter contract; `capability_verification`
is `not_probed`: an endpoint declaration alone does not qualify its binary.
Surface52 separately exposes per-session `effective_capabilities`. A session's
`current_owner_ready_record` means its persisted lifecycle/profile and owner lease
are current. `process_liveness=not_probed` explicitly avoids inferring a live
native process from a stored row.

While has_more=true, pass next_endpoint_id as after_endpoint_id. Cursors only
contain visible endpoint IDs. Each endpoint shows at most ten latest sessions
and sessions_has_more. A scan exceeding 1000 candidate endpoints without finding
the requested page fails with QUOTA_EXCEEDED; narrow agent_id. Reads neither
contact the harness nor resolve credentials or modify presence. REST, MCP HTTP
and authenticated MCP stdio use the same persisted projection.

List responses use `{ok:true,data:{items:[...]}}`. Profile discovery omits command
paths, environment values and secret reference names. It exposes the profile ID,
adapter, enabled/inherit-ambient switches, revision and supported non-sensitive
configuration fields. The listing does not resolve secrets.

Profile creation defaults to disabled and `inherit_ambient=false`. Only an
approved profile may back a managed endpoint. Backend configuration belongs to
the profile; opening a session cannot override it arbitrarily. Configure dedicated
tool homes through supported profile environment fields when needed. Do not put
raw credentials in the payload; never forward the Nexus operator key to a child.

Profile updates accept config, secret_refs, inherit_ambient and enabled. Omission
preserves the existing value; an explicit object replaces the whole object, so
send `{}` to clear secret references. Null is not a clearing operation for these
fields. Profile ID and adapter are immutable. Use enabled=false to retire a
profile without deleting its history or referenced operations.

For an existing `worker` Agent and enabled `approved-codex` profile:

```json
{
  "view": "endpoints",
  "maintenance": {
    "action": "create",
    "endpoint_id": "worker-code",
    "agent_id": "worker",
    "adapter_id": "codex",
    "project_root": "/approved/project",
    "profile_id": "approved-codex",
    "enabled": true,
    "response_policy": "conversation"
  }
}
```

Use an actual absolute local project path. Endpoint creation also accepts priority,
selection_group, consumption and public_config. Public configuration supports
explicit notification targets and opt-in bounded result relay where correlated
results are supported. Endpoint updates accept public_config, enabled, priority,
selection_group, response_policy, consumption and profile_id. Omitted fields are
preserved. An explicit public_config replaces that entire object; removing
notify_target restores the private correlated reply destination. Null can clear
selection_group; a managed endpoint cannot clear its required profile. Agent,
adapter and workspace are immutable. A stale revision fails with `CONFLICT`.

Every configuration edit atomically revokes affected execution grants and disables
their previously approved boot bindings. Re-enabling a profile/endpoint does not
restore those grants or boot approvals. Issue fresh scoped grants and explicitly
reapprove boot after reviewing the new revision. The configuration audit shares
the existing access log and records actor, resource, old/new revision and changed
field names, never configuration or secret values. Operator diagnostics expose
the latest 100 records as `configuration_changes`.

Editing a profile does not change a running process's environment. Its old session
revision cannot admit new sends, even if the edited profile is later re-enabled.
Close it and open a session with the new profile. Operator interrupt/close remain
available; already accepted work is not silently declared cancelled. Late terminal
events remain durable while publication under the revoked configuration is blocked.
Changing an endpoint to a different profile requires previous sessions to be
stopped/detached and no pending open request; equal numeric revisions of different
profiles do not preserve a grant. Unknown sessions require recovery or a separate
explicitly approved endpoint, never reuse based only on a stored PID.

Boot requires a current enabled profile and endpoint. Attach cannot use a saved
PID as boot authorization. Reconciliation requires a quarantined endpoint without
an active ready/closing runtime, an explicit reason and acknowledgement of uncertain
prior effects. Retrying the same reconciliation through either surface returns
the same reconciliation ID. It does not resend an ambiguous delivery or invent
native completion.

## Recovering an uncertain transport attempt

Inspect outbox through either surface. The returned state/attempt_id/owner_epoch
are the snapshot required for recovery. Inspection includes administrative
commands and conversation deliveries, not their payloads or credentials. Review
the operation, native lifecycle and evidence before deciding; process timeout or
lease expiry is not proof that a write never happened.

Use cancel_pending before send-intent (PENDING/CLAIMED), or during a proven-safe
RETRY_WAIT. It cancels that
intent and releases its conversation inbox reservation without marking the
message read. For an uncertain conversation delivery, release_to_inbox explicitly
returns the same logical delivery to the recipient's canonical pull inbox. It
does not create a replacement message, retry the native transport or invent ACK.
For an uncertain administrative command, abandon_command retires its tracking
without creating an inbox delivery. Both uncertain actions require the explicit
duplicate-risk acknowledgement. Managed handoffs cannot be treated as conversation;
their canonical claim recovery remains a separate operation.

For a conversation rejected before any native turn write, use the same
`release_to_inbox` action with `acknowledge_duplicate_risk: false`. The owner
must have persisted `REJECTED`, reason `native_write_not_started`, ACK `NONE`,
an attempt ID and no observed native thread/turn. The service checks this proof;
a caller cannot assert it by supplying a reason or a status. The exact snapshot,
operator authorization and idempotency key are still required. The original
rejection/attempt remain in history, the same delivery becomes pullable, and no
new native call, receipt or endpoint quarantine is produced. An in-flight call
still blocks release. Any generic rejection or uncertain send uses the stricter
recovery rules above; a handoff must use canonical claim recovery.

Surface54/schema059: inspect a specific delivery `operation_id` through either
operator surface to receive `attempt_history` (latest64 observations, ordered by
sequence) and `attempt_history_truncated`. This includes owner, endpoint/session,
state, ACK, native references, reason and provenance, never message payload or
credentials. List pages remain compact. These are transport observations, not
additional work items. Administrative command history is not synthesized here.

The additive migration snapshots the current known attempt with provenance
`migration_snapshot`; it cannot reconstruct attempts overwritten by older versions.
Subsequent committed transitions are recorded atomically as `observed_transition`,
including a claim returned to PENDING on owner change. Full history remains in
the database; detail truncation does not delete it. Existing backup/restore includes
the table. Do not delete or rewrite its records to force a retry; operational
rollback remains admission-off/drain/recovery, not reverse SQL.

Surface55/schema060: a transient local adapter lane refusal before native write
can enter `RETRY_WAIT`. Only that typed server-side proof enables automatic retry;
an error string, generic rejection, timeout, write acknowledgement or missing
reply cannot. Delivery inspection/history exposes `next_attempt_at` and
`retry_basis=LANE_BUSY_BEFORE_WRITE`. There are at most3 attempts total, with1s
then2s exponential delays plus0..25% jitter. Deadlines survive owner replacement.
The coordinator waits for deadlines or wakes, with the existing bounded recovery
scan for a due but occupied lane. No harness status polling or extra threads are
introduced. Other agents can proceed; later normal operations on the same lane
remain ordered. Controls retain their own priority and are not automatically retried.

Each retry uses the same operation, message, inbox reservation, causal admission,
handoff binding (if present) and envelope hash, with a new attempt ID. Current
authorization and profile/binding revisions are revalidated. Permanent capability
rejection remains REJECTED; uncertain transport remains fenced. After3 pre-write
refusals, the delivery is REJECTED with its non-delivery proof preserved for
explicit authorized inbox recovery. Managed work still requires canonical claim recovery, never an inbox
release or borrowed endpoint grant. No personal database is migrated by tests.

Surface56/schema061 adds safe fallback for new conversations. To permit it, the
operator explicitly assigns a nonempty `selection_group` to interchangeable,
enabled and approved endpoints of the same agent/workspace. Approve each target's
runtime profile separately, including its native security controls. This declares
those approved configurations valid alternatives; do not group unrelated contexts.
Ready alternatives are preferred, then priority, then stable endpoint ID. Disabled,
quarantined, incompatible or feature-disabled candidates are excluded. An eligible
target may be opened on demand under the normal owned-start lifecycle.
Targets also need the trusted adapter descriptor's `input_schema.transport_binding_contract=1`.
All four built-in envelope adapters implement it. An extension must explicitly
support the versioned binding; endpoint metadata cannot opt an adapter into this
contract. A legacy extension still supports its ordinary advertised deliveries.

Only typed pre-write rejection can select an alternative. The next binding and its
revisions are committed with RETRY_WAIT, and become the current binding only at
the next fenced claim. Original endpoint/profile approval, target approval and
current actor authority are all checked before effects. The original message,
envelope hash, causal admission and inbox reservation remain unchanged. Native
framing labels current transport endpoint/profile separately from the original
admission snapshot; neither creates authority. Inspection exposes `admission_binding`
and `next_binding`, and immutable history records the selection and revisions.

Continuation/relay contexts, controls and managed handoff grants keep their original
binding. They cannot borrow another endpoint's authority. Unknown writes, acceptance
and lost replies never enable fallback. Generic startup exceptions remain ambiguous
unless the adapter supplies explicit non-delivery proof; an error string is not proof.
The existing bounded retry budget applies. Endpoints already attempted are excluded
from alternative selection; a transient refusal may still retry its same endpoint
when no approved alternative is eligible. No endpoint fan-out or duplicate inbox is
created. Rollout is additive and uses the existing owner stop/upgrade/start procedure.

```json
{
  "view": "outbox",
  "maintenance": {
    "action": "release_to_inbox",
    "operation_id": "op_from_inspection",
    "expected_state": "OUTCOME_UNKNOWN",
    "expected_attempt_id": "attempt_from_inspection",
    "expected_owner_epoch": 1,
    "idempotency_key": "operator-reviewed-recovery-1",
    "reason": "Reviewed the uncertain attempt and prior runtime",
    "acknowledge_duplicate_risk": true
  }
}
```

Copy actual snapshot values; do not use the example identifiers or epoch. A
changed state/attempt/epoch conflicts. The same key and exact request return the
committed response after a lost reply; changing the request under that key
conflicts. Audit, reservation release and source update commit together.

Recovery refuses an in-flight call, ready/closing runtime or reserved start on
the affected endpoint. Stopped/detached/unknown records still do not prove absence
of prior external effects: the operator explicitly accepts possible duplication.
The original uncertain transport state and ACK remain in history beside the
reconciliation record. Late exact correlated results stay durable but cannot
consume the released delivery, publish or relay under the surrendered authority.

Uncertain recovery quarantines the endpoint and revokes its grants/boot approvals.
Review and explicitly reconcile that endpoint before reuse, then issue fresh
grants/boot approval as needed. This separates the decision about the old delivery
from authorization to run new work. There is no retry-all operation. Operator
outbox maintenance remains available when new harness admission is OFF, including
through an already registered MCP surface; sending remains disabled. A newly
started MCP server with the flag OFF does not publish harness tools, so use REST
for that recovery path.

Migration054 only adds audit storage, nullable reconciliation references and
indexes. Rollback deactivates admission and uses these records; never delete
outbox rows, reset attempt IDs or reverse the migration to force another send.

## Native questions and permissions in the dashboard

Open Approvals as the operator and choose Review request. Supported Codex
blocking questions, flat form elicitation and Claude AskUserQuestion requests
show explicit answer controls. Nothing is selected from a native default and
opening the detail does not answer it. Choose/fill the requested values and press
Send answer. Multiple choices remain distinct values; numeric/boolean fields
retain their types. For a permitted empty string, explicitly select Send empty
text. Optional omitted fields are not filled automatically.

Permission requests instead show Approve request after review. Reject declines
the request without fabricating answer data. These operations use the existing
operator-only REST approval service, which validates the stored native request,
correlation, answer, current authority and deadline. Agent credentials cannot
approve their own requests. No additional MCP decision tool is introduced.

The detail distinguishes the canonical decision from runtime delivery. It shows
native state/reason/expiry and the recorded response. Expired or no-longer-pending
requests have no answer control. A recorded approval does not prove the runtime
received it or that work completed. Secret questions and unsupported remote/URL
schemas remain outside the supported native contract; the UI does not resolve
them or relax sandbox/approval policy. The original request remains available
for operator inspection.

The existing journal/artifact maintenance actions remain available. Managed-work
qualification follows the per-session contract below. Deleting persistence rows is not an operational substitute for
those actions. Migration 053 is additive; operational rollback uses deactivation,
drain and recovery, not reverse SQL or deletion of the audit/history.

## Runtime diagnostics in the dashboard

Open Runtimes to inspect authorized records across all workspaces. Connections are
grouped under canonical agents with their skills, endpoint health, declared
capability verification and stored runtime lifecycle. Multiple visible ready
bindings prompt a selection review; this is not a replacement for server-side
workspace/priority/selection-group resolution. Detached does not mean the external
process ended, and persisted readiness is not a liveness probe.

Transport cards distinguish conversation deliveries from runtime commands and show
state, ACK evidence, reason and expandable attempt/owner/session/reconciliation
metadata. Unknown outcomes never display automatic retry as recovery. Use the
operator API procedure above for mutations; Review native approvals opens the
existing Approvals view. Cards do not expose message bodies or private config.

Refresh fetches current authorization and clears the previous snapshot on failure.
Pages are bounded to50 endpoints/operations with explicit next/first controls;
only10 sessions per endpoint are shown, with an indicator for older records.
When admission is disabled, operator operation inspection remains available even
if connection discovery is denied. No native status polling is introduced.

## Recovering managed handoffs

Surface43 adds `recover_handoff` to the same outbox maintenance endpoint and
`harness_list` maintenance facade. Supply the existing exact transport snapshot,
idempotency key, reason, `acknowledge_duplicate_risk=true`, plus
`expected_handoff_id` and `expected_claim_epoch` from operation inspection.
Only the current operator may act, including with admission disabled. Close or
reconcile the endpoint first; active calls, starts and ready sessions block recovery.

Recovery atomically changes the matching CLAIMED handoff to OPEN and emits
`handoff.recovered`. It preserves transport state/ACK, quarantines the endpoint,
revokes grants/boot, and fences late old results. It does not release the old work
envelope as a conversational inbox item, create a new delivery or start a process.
VERIFYING, COMPLETED, REJECTED and CANCELLED handoffs are refused. An explicit
new claim increments the epoch; reusing old completion authority is rejected.
Recovery acknowledges possible prior external effects; it does not undo them.

Migration055 extends the existing audit additively: transport `action=abandon_command`
plus `canonical_action=reopen_handoff`, handoff ID and claim epoch. The API action
remains `recover_handoff`. This mapping preserves migration054 enum and existing
idempotency hashes; no replacement audit table or independent work queue exists.

Session compatibility_report (migration056) is a server-owned, redacted observation
independent of caller metadata. Codex initialize may supply native_version; unknown
formats remain null and capabilities_verified=false. This does not elevate grants
or claim compatibility of untested protocol features.

Surface45 checks required_native_requests again after native startup, inside the
bounded startup worker and before presence/session publication. A rejected open
ends only its logical session and cancels its owned startup scope. Version contract
matching covers Codex0.156.1. Surface46 adds Claude stream's bounded, owned read-only
version probe: 2.1.280 Write/Edit/Bash/AskUserQuestion, and 2.1.281 Write/AskUserQuestion
only. Unknown versions and unqualified methods cannot satisfy explicit requirements.
Pi and attach still require equivalent evidence. Canonical approval decision decline
may translate to native cancel when decline is absent from availableDecisions. The
audit retains the canonical decision and original native choices; it is not an ACK.

Surface47 adds the attach registry observation to the stored compatibility report.
Exact integer peerProtocol=1 is mandatory at open and rechecked before each send;
absence is no longer treated as compatible. Existing protocol1 injection remains
available on supported POSIX systems. This check adds no acknowledgment, result,
approval, managed-work or process-ownership capability to the external session.

Surface48 adds server-owned compatible_controls/control_contract_basis to native
observations and enforces them for steer/interrupt before enqueue and dispatch,
including the supervisor's internal send path. An unknown version cannot borrow
the adapter's declared steering behavior. Pi observes its executable version with
the same bounded owned probe used by Claude. This is a narrow control contract;
Surface52 extends this to the effective capability contract below.

## Qualified session capabilities (surface52)

The installed trusted adapter probe reads server-owned observations outside SQLite
write transactions. Effective capabilities intersect that probe with the registered
descriptor and the approved profile. A profile may only remove capabilities using
`config.disabled_capabilities`, a unique list of capability field names. For example,
`["managed_work", "multiplexing"]` retains conversation but disallows managed work
and shared connections. `interrupt_requires_settle` is a safety constraint and cannot
be disabled. Required native requests conflict with disabled approvals.

Current conversation contracts are Codex0.156.1, Claude stream2.1.280/2.1.281 and
Pi0.85.1. Pi is fixture-qualified only; its native campaign remains NOT_RUN.
Attach requires exact integer peerProtocol1 and retains unconfirmed injection only.
Neither attach nor any spawned connector gains native deduplication, native replay
or an agent ACK from this contract. Unknown versions remain inspectable and closable,
but cannot execute turns or borrow advertised controls or multiplexing. Qualify an
updated binary with protocol tests and an isolated campaign before adding its exact
version; editing caller metadata cannot grant compatibility.

Managed work additionally requires events and correlated results; approvals require
HITL enabled. Every action still checks current identity, grant, policy, scope and
profile revisions. These capability checks do not replace native sandbox/approvals.
Direct admission, dispatch and native send enforce the intersection. A newly opened
on-demand runtime can prove incompatible after an intent was committed: the attempt
becomes REJECTED with native_write_not_started and ACK NONE before turn bytes are
written. The logical delivery remains reserved until explicit operator recovery;
there is no silent fallback to another executor.

Runtimes shows session capabilities separately from adapter declarations. Closed,
stale or non-current-owner records expose no effective execution capability. Their
stored compatibility_report remains historical evidence, not live authorization.
No native status polling is used to render this view. An installed extension with
no trusted compatibility probe fails closed for execution; no remote loader exists.

## Transport capacity and scheduling (surface53/schema058)

Unread logical push reservations are limited to256 total,32 per authenticated
actor,32 per recipient agent,128 per workspace and4MiB of stored canonical envelope
bytes. The limit includes accepted/unconfirmed and unknown attempts until their
result is captured or their reservation is explicitly reconciled. Endpoints do
not each receive a separate agent quota. These are transport limits; handoff claims
and causal-root budgets retain their own meaning.

If admission exceeds capacity, the current API returns QUOTA_EXCEEDED with reason
runtime_delivery_backpressure. The new message/delivery or managed claim/grant
transaction rolls back together. Do not treat it as accepted work or retry a
different native operation. Existing messages, attempts and results are retained;
ordinary logical delivery that does not request a transport executor still works.
Inspect backlog, finish work, or use authorized cancellation/reconciliation to
release capacity. Time passing does not make an unknown write safe to repeat.

Migration058 adds a partial reservation index and an INSERT guard on the existing
outbox. The guard also bounds an already-open writer using the prior enqueue SQL;
it does not depend on every producer immediately loading new Python code. An older
producer may report a generic database/internal error for this refusal; upgrade
writers for the prescribed QUOTA_EXCEEDED diagnostic. No rows are pruned on upgrade.
If an existing store exceeds a new limit, inspect/reconcile it until admission is
available; never delete reservations or reverse the migration to regain capacity.

Each represented agent may occupy one normal transport-write worker across both
inbox and direct-command dispatchers. Native acceptance or even a durable result
does not release that capacity while the original call is still running. Accepted
inference can remain concurrent across approved sessions after each transport call
returns. Controls/close have separate priority workers, preserving expected-turn
and authorization fences. Unreconciled unknown writes retain their normal-agent
fence; explicit recovery must first prove the original call is no longer in flight.
Selection takes the oldest eligible item per lane and agent before truncating a
batch, so repeated rows from one endpoint cannot consume other eligible slots.

## Reviewing historical profiles

Operator `GET /api/v1/harness/diagnostics` and MCP `harness_list` with
`view=diagnostics` include `legacy_profile_review` schema version1. For up to100
agents with legacy-unlinked sessions it classifies capabilities/metadata as
present, missing, empty or invalid, without exposing their contents. A truncated
response requires a remaining-agent inventory from an offline store copy.
Absence is not proof of past corruption: intentional empty fields also require
human review. Diagnostics does not restore data or read a backup automatically.

Keep a consistent backup and compare the exact Agent ID and fields against a
trusted pre-damage backup/export. If no trusted source exists, preserve the
missing fields and diagnostic. Restore only reviewed fields through existing
operator Agent administration; register reviewed capabilities in the canonical
catalogue first. Never infer skills from runtime names or copy session metadata
as a replacement profile. Verify the canonical profile afterward. Historical
sessions remain legacy-unlinked, with no invented endpoint or end timestamp;
restoration neither opens a runtime nor replays unread work.

## Disabling admission with captured results pending

Deactivating a canonical Agent (`is_active=false`) also blocks new open, send,
steer and managed-work actions through its existing endpoints, including
operator requests and repeated command keys. Operator read, interrupt and close
remain available for recovery. Reactivation does not erase command deduplication
or turn an uncertain attempt into a safe new send. Administrative retention
keeps referenced messages, delivery reservations, attempts and causal records;
it can still prune unrelated expired history.

Disabling `feature_harness_integrations` blocks new native sends and publication,
while owner maintenance continues projecting captured journal facts. A result
may remain `PENDING_AUTHORIZATION` until a later explicitly authorized rollout;
this does not indicate publication or handoff completion. Inspect its durable
result and publication fields independently.

If a transport call times out or raises after writing, its operation can be
`OUTCOME_UNKNOWN` before captured native acceptance is projected. Exact matching
session/connection/attempt/current-owner observations can subsequently establish
acceptance and a durable result. This is reconciliation of observed facts, not
a second send. Previous-owner events retain the frozen recovery boundary;
explicit operator reconciliation continues to fence surrendered authority.
Neither disabling the feature nor lease expiry frees an uncertain delivery for
another executor. Use the existing authorized reconciliation procedure when
there is no conclusive native evidence.
