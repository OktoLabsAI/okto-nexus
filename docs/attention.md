# Operator attention API

The attention API projects canonical Nexus facts into `action_required` and
`watch` groups. It uses no model inference. Version 1 contains the twelve
initial classifiers plus generic pending approvals. The dashboard page and global badge are a separate PR-07
delivery; this document describes the backend contract.

Generic approval controls use the canonical decision registry and current
recipient. A control means that an existing decision form can be opened;
approved re-execution still validates its business rules. A valid rejection
can remain available when approval would fail those rules. Known expired or
archived requests retain inspection only. Legacy native approvals without a
correlated current native request never gain a generic execution action.

PR-06 remains in progress. One known episode gap is a global execution-feature
toggle off/on/off without a persisted source change: the blocking occurrence
reuses its ID and viewing preference. This behavior is tested as a limitation,
not as acceptance of episode recurrence. Client reconciliation and browser
acceptance also remain open in PR-07.

`feature_attention` defaults to `true` and can be changed through existing
settings or `OKTO_NEXUS_FEATURE_ATTENTION` / `--feature-attention`. It is
independent of harness integration and external observation. Disabling it
returns `409 FEATURE_DISABLED`; existing work and decision endpoints continue
to operate. The two time thresholds are `attention_unclaimed_seconds` and
`attention_disconnected_seconds`, both defaulting to 300 seconds. They accept
integers from 0 to 86400; zero disables that temporal escalation. Their CLI and
environment names follow the existing settings convention.

## Reads and viewing preferences

All routes require the existing operator authentication and origin controls.
An ordinary agent key cannot read attention, including when a human session
cookie accompanies that key. Authorization is checked again in the transaction.
Responses use the existing `{ok,data}` / `{ok,error}` envelope and `no-store`.

| Request | Contract |
| --- | --- |
| `GET /api/v1/attention` | A page, exact filtered total and counts, snapshot revision, event cursor, observation time and next refresh deadline. |
| `GET /api/v1/attention/summary` | The same filtered relation and authorization, without page items. |
| `POST /api/v1/attention/{attention_id}/seen` | Body: `source_revision`, `preference_revision`, and boolean `seen` (default true). |
| `POST /api/v1/attention/{attention_id}/snooze` | Body: both revisions and `until`, an explicit timezone timestamp in the next 30 days, or null to clear. |

Filters are `workspace_id`, `agent_id`, `category`, `kind`, `state`, `priority`
and `seen`. `category` is `action_required|watch`; priority is 10, 20 or 30,
with 30 first. `state` accepts `active` (default), `all`, `open`, `resolved` or
`expired`. `seen` accepts `all` (default), `seen`, `unseen` or `snoozed`.
Unknown and repeated query keys are rejected. The legacy middleware's
`api_key` query parameter retains its existing authentication behavior.

`active` excludes snoozed occurrences and results already seen. Seeing an open
approval leaves it active. `state=all&seen=snoozed` includes currently snoozed
records; `state=active&seen=snoozed` is deliberately empty. Resolution belongs
to the source, independently of these viewing filters. A canonical result has
`resolution=resolved` and remains active until seen or snoozed.

The installation has one shared operator viewing principal. Seen/snooze state
is shared across that operator's devices and survives restart. It creates no
new user or agent. Preferences use compare-and-swap: a changed source or
preference revision returns `409`, and a removed occurrence returns `404`.
The caller must refresh. Neither action approves work, consumes an inbox
delivery, verifies a handoff, pauses execution, or changes a productive result.

Page size is 1–200, default 50. Ordering is priority descending, first detection
ascending, then attention ID ascending. Pass the opaque `next_cursor` with the
same filters. A material snapshot change returns `409` rather than silently
skipping records. The cursor is a page fence, not an authorization token;
authentication and filters are always reapplied. Unrelated stream events do
not invalidate an otherwise identical page. List and summary are separate
requests and can naturally observe different commits.

Each occurrence contains metadata references, a stable episode ID, a source
revision, resolution, freshness and action descriptors. It contains no native
prompt, message/result body, secret, credential, CAS token or raw error text.
`allowed_actions` describes the current view. Commands remain on the existing
endpoints and revalidate authority, revisions and native decision fencing.
Execution references include `executor_id`, so autonomous worker operations can
open the existing administrative inspector without guessing the host from a
session. Delivery references include `message_id`; cleanup references include `result_id`
and the canonical maintenance ID as `source_id`. These identifiers let the
client open the original record without copying its content into attention.

Approval summaries and details expose `decision_revision`. The existing
approval decision endpoint accepts optional `expected_decision_revision`, a
nonnegative integer checked inside the decision transaction before handlers.
Clients opening a fresh form should submit this revision: an earlier form
cannot decide again after failed re-execution returns the approval to pending.
Older callers that omit the field retain the existing command contract.

The existing artifacts inspection command accepts `maintenance_id` with
`action=inspect`, including completed maintenance and records beyond the
100-row overview. It returns the original receipt's metadata and associated
result reference. The selector cannot be combined with a mutation or used to
retry cleanup; explicit cleanup retains its canonical idempotency contract.
Inspection uses the existing operator recovery authorization and audit, and
remains available with harness execution disabled or no active dispatcher.
Mutations still require the active serve owner. The existing handoff listing
accepts `handoff_id` to read an exact scoped record beyond its overview limit.

## Classifier contract

All actions below belong to the authenticated operator. Question replies are
additionally restricted to the canonical interlocutor; verification requires
the canonical verifier policy, visibility, permission and anti-self check.
Inspection descriptors do not grant command authority.

| Kind | Source and predicate | Action, priority and end of condition |
| --- | --- | --- |
| `approval_pending` | A canonical approval without a correlated native request, current registry wiring and recipient; coordination receipts and binding proposals must match their original scope, revision and known deadline. | Inspect; open the existing decision control only while a valid pending operator decision remains (20/action), otherwise 10/watch. No invented expiry for governance approvals. Archive, decision, known expiry or stale proof removes the decision action. |
| `native_permission_pending` | Canonical native request plus approval, including native MCP tool permission. Current request, grant, scope, lease, lane and initiating authority are revalidated with shared pure command predicates. | Inspect approval; decide only while live and addressed to the operator (20/action), otherwise 10/watch. Decision, archival or staleness resolves it; expiry removes the decision action and retains a historical reference while the native record exists. |
| `native_question_pending` | Native question whose canonical interlocutor is the operator. | Inspect; respond only with current native authority (20/action), otherwise 10/watch. Resolution/expiry follows the native request. |
| `question_waiting_for_agent` | Native question addressed to another agent, or missing recipient proof. A broken domain link never falls back to borrowing the operator identity. | Inspect only, 10/watch. No human reply on behalf of the agent. Missing proof is unavailable; native resolution/expiry ends the active condition. |
| `verification_pending` | Handoff in `VERIFYING`, keyed by handoff and claim epoch. | Verify only for an eligible operator (30/action); otherwise inspect (20/watch). Leaving `VERIFYING` removes the occurrence. Automatic verification does not invent a human verifier. |
| `execution_outcome_unknown` | Pending canonical operation with latest receipt `OUTCOME_UNKNOWN` or dispatch `RECONCILING`. | Inspect operation/recovery, 30/action. No generic retry action. Terminal or confirmed-not-sent reconciliation removes it. |
| `delivery_parked` | Canonical inbox delivery in `parked`. | Inspect delivery, 20/action. Leaving parked removes it; a later entry gets a new episode. Attempt counts alone do not create incidents. |
| `runtime_recovery_attention` | Recorded runtime pending-delivery attention with a still unread, unconsumed delivery and no outbox admission. | Inspect recovery, 30/action. Canonical recovery progress, consumption or admission removes it. Historical recovery failures and normal recovery are insufficient. |
| `execution_authority_blocking` | Actually pending managed message/handoff delivery, queued canonical execution or live native request, with a current explicit authority denial. Identity, audience, source/initiator/responder, grants, revisions, runtime configuration and correlated relay/notification provenance are revalidated from batched facts. | Inspect/review authority, 30/action. Restored authority or leaving the pending condition removes it. No automatic grant renewal. Ordinary claims, silence, absent inventory, recovery and unapplied lease renewal do not prove revocation. |
| `executor_disconnected_with_work` | Disconnected executor and relevant pending operation; excludes idle warm one-shot preparation. | Inspect executor/recovery, 20/watch; 30/action after the configured disconnection threshold. Reconnection or terminal work removes it. Offline without work is insufficient. |
| `handoff_unclaimed_aged` | Open, unclaimed handoff with an eligible registered candidate and satisfied dependencies, older than the configured threshold. | Inspect handoff, 20/watch. Claim, lost eligibility or unsatisfied dependency removes it. Waiting starts from the current open generation or last dependency completion, not the GET time. |
| `result_unseen` | Canonical execution result with a terminal sequence and success, failed or interrupted outcome, or a completed/rejected handoff. A proven native result and its handoff share one occurrence per claim epoch, including MCP completion and either arrival order. | Inspect handoff and/or result, 10/watch, resolution resolved. Seen hides the result from active views without changing its outcome. Partial native-result retention does not resurrect the retained handoff notification. |
| `cleanup_attention` | Successful productive result plus an explicit operator cleanup receipt still pending after an unconfirmed cleanup failure. | Inspect maintenance, 20/action. Confirmed maintenance completion removes it. Normal automatic cleanup does not imply failure, and the productive result remains successful. |

Native authority uses current facts rather than invoking mutating admission or
lease maintenance during GET. Source SQL materializes shared agent/endpoint
facts in batches. Exact counts and keyset pages use one filtered relation with
no per-occurrence service calls. Processing has a five-second budget, including
policy reads and cooperative Python fact preparation; exhaustion returns `503 ATTENTION_QUERY_BUDGET`, not an empty
success. SQLite projection failures return a sanitized error. Narrow filters
and refresh if the budget is exceeded; this is not a claim of unlimited scale.
An explicit kind filter prepares only that classifier family. Whole-engine
batch tests include distinct agents, endpoints and profiles across workspaces;
query count does not grow with the number of occurrences.

Authority classification concerns revoked/expired authorization and configuration,
not communication-content guardrails. The latter remain on the canonical send
path, including their configured tokenizer; attention does not scan message
content or predict their verdict. External/attach execution is not promoted into
the managed canonical authority classifier. Existing managed-handoff authority
identities retain their migration-161 episode references when the same original
condition applies, while source revisions still reflect current facts.

## SSE and reconciliation

Use the existing `/api/v1/stream?view=attention` with its cursor/workspace/stream
parameters. Legacy stream consumers retain their existing behavior. The
attention view sends metadata-only controls:

- `attention-reset`: obtain a fresh canonical snapshot. Every initial connection
  or reconnect requests one. A cursor outside retained bounds uses reason
  `retention_gap`, including insertion and pruning since cursor zero.
- `attention-invalidated`: one notification per fetched batch of up to 500
  events. Coalesce these notifications before reading a new snapshot; native
  token bodies and historical notification toasts are never replayed here.
- Authorization loss or feature disablement sends a reset with `clear=true`;
  remove protected content and counters. Source failure uses `clear=false`;
  retain the last authorized view as stale. Initial authorization failures
  retain the normal HTTP error contract.

`event_cursor` and `event_low_watermark` come from the same read transaction as
the snapshot. The cursor high-water mark survives event retention. Reconcile
after gaps; do not infer that an absent invalidation means absent work. Honor
`next_refresh_at` / `refresh_after_seconds` even without SSE activity: refresh
is capped at 15 seconds and shortened for known native authority deadlines,
disconnection escalation and snooze expiry. This also reconciles preferences
changed on another device. Network/read failures must never replace the view
with a successful zero count. The PR-07 client must implement these behaviors.

## Persistence and rollback

Migrations 161 and 162 are additive. `attention_preferences` stores only viewing state
under the existing operator principal. `attention_operation_epochs` stores a
current source reference, state, counter and stable transition timestamps for
deliveries, runtime recovery, dispatch and executor connection state. Triggers
also anchor grant, endpoint and profile revision transitions, so retry and health
timestamps cannot move the beginning of an authority episode. They also observe
endpoint enablement/activation and profile enablement even when a canonical
retirement does not increment the revision. History reset preserves anchors for
the resources it retains; source deletion triggers remove the others. Anchor
updates are atomic with the original transaction; rollback rolls
both back. The counter distinguishes reentry even at the same timestamp.
Backfill means first stored observation at upgrade, not invented past history.
Migration 162 extends authority transition counters without storing the
configuration values or credentials being compared. A deleted configuration
can retain a metadata tombstone while pending canonical work still references
it. Explicit history reset removes those obsolete tombstones and preserves
counters for configuration that survives the reset.

Handoff result timestamps are anchored to the first and latest known canonical
result in that claim epoch. They survive partial execution-result retention.
The 161-to-162 upgrade transfers preferences from exactly correlated native
result identities to their shared handoff identity in the same transaction.
It preserves any existing seen mark, the furthest snooze deadline, and the
original preference records. The merged revision advances so old forms cannot
overwrite it. Timestamp comparison preserves timezone offsets and microseconds.
Unrelated native results keep their previous identity and preferences.

Work-source deletion removes its auxiliary transition anchor. Preferences are kept:
age-based deletion could make a still-retained result appear unseen again.
The view is reconstructed from canonical facts plus these durable metadata
anchors on each read; there is no second work queue or event-history replay.
Do not discard episode anchors while retaining preferences and assume identity
continuity. Resolved non-native conditions disappear when their source condition
ends; attention does not create a separate historical incident archive.

Two additional nullable maintenance columns record an explicit cleanup's first
unconfirmed failure time and a fixed diagnostic code. No exception payload is
copied. A failure to record that marker preserves the original maintenance
receipt and reports the uncertainty without automatically repeating cleanup.

GET performs no lifecycle or preference writes. Existing authentication/audit
side effects remain governed by their own contract. Disable `feature_attention`
for operational rollback while retaining migration 162 and its metadata. An
older binary that does not recognize schema 162 refuses startup; do not delete
migration records or downgrade a live database to bypass that protection.
