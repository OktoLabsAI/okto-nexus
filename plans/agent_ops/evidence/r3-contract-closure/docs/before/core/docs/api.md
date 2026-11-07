# Core API (`0.0.14`)

## External participant configuration

The separate `nexus_connector_core.participant_config` module exposes
`ParticipantClientConfig`, `PARTICIPANT_CONFIG_REVISION`,
`participant_client_config`, `export_participant_config`,
`plan_participant_config` and `plan_participant_removal`.
See [participant configuration](participant-config.md) for the pure contract,
ownership rules and the host's credential/persistence responsibilities.

## Runtime automation

`DEFAULT_RUNTIME_AUTOMATION` supplies the shared defaults for automatic message
delivery and runtime recovery. `RuntimeAutomationPolicy` describes those settings
and the bounded retry policy. `RuntimeAutomation` supervises host recovery and
Connector reconnections through callbacks, without replaying submitted native
operations or bypassing the host's ownership and authorization checks.

## Harness configuration and native input

`get_runtime_connection_contract` exposes the trusted adapter's host integration
contract without module paths or credentials. Additional managed connectors
confirm their registered contract at opening; registration alone does not prove
readiness. A connector declaring no tool transport receives no session tool
credential. Fallback requires transport binding contract version 1.

`CONFIGURATION_SCHEMA_VERSION` identifies the discovery schema.
`discover_harness_configuration` describes adapter settings;
`query_harness_configuration` queries native runtime observations, and
`probe_selected_configuration` probes a selected installation with an explicit
working directory and environment. Discovery does not grant execution authority.

`HarnessSettings` carries typed session settings. `validate_harness_settings`
validates adapter settings; `harness_settings_dict` serializes them.
`validate_harness_configuration` also checks the discovered supported values.
`parse_harness_configuration_file` validates the bounded, versioned JSON envelope,
rejecting unknown and duplicate fields; `export_harness_configuration_file`
produces that envelope. Files contain settings, not credentials or grants.

`native_input_response` converts a canonical decision to the originating
harness's native response contract.

This is the development API of the independent `okto-nexus-connector-core` wheel (correction revision C1).
The trusted host supplies authority, selected binaries, workspace roots,
credentials and canonical application state. Core does not import Nexus Server
or Connector code. The supported top-level exports are listed below; native
adapter modules and `CopiedAdapterFactory` are not a public host API.

| Export | Use |
| --- | --- |
| `RuntimeCore`, `LocalRuntimeCore`, `create_runtime` | Async port, local implementation and the supported composition factory. `create_runtime(journal=…, environment=…, candidates=…, workspace_roots=…, …)` builds the real runtime from typed host inputs (trusted callbacks for Codex client identity/resume/Pi native action, budgets, optional installation ledger, clock and event sink); hosts never import the private adapter bridge. A `native_factory` parameter exists for contract-level smokes with fakes. |
| `ExecutionContext` | Host-issued server/executor/binding/agent/workspace identity, revisions, generations, monotonic lease deadline and allowed actions. Never derive it from a peer payload. |
| `RuntimeCatalog`, `RuntimeDescriptor`, `get_runtime_catalog`, `CATALOG_FORMAT_VERSION` | Single-source runtime catalog (C9): enumerate what this Core knows - adapter IDs, family, connection mode, implementation platforms, support status (managed connections only) - cheap, sync, no native provider modules, no spawn/journal/credentials. `DiscoveryRequest(adapter_ids=None)` asks the catalog which adapters admit discovery; availability/eligibility are separate concepts (local inventory + Server-side binding policy). |
| `installation_ref`, `resolve_installation`, `INSTALLATION_REF_SCHEME`, `REF_NOT_FOUND`, `REF_AMBIGUOUS` | Installation identity (C11): `candidate_ref` in the projection is now the opaque ref of the SELECTABLE LOCAL INSTALLATION (`nexus-install-v1:<sha256>` over the canonical executable + launch script) - byte-identical copies in distinct locations are TWO installations (distinct refs, SAME build identity). `resolve_installation(inventory, adapter_id, candidate_ref)` resolves a selection to EXACTLY one `InstallationCandidate` on the producing host: zero matches raise typed `INSTALLATION_REF_NOT_FOUND` (missing/stale/foreign executor), more than one distinct match raises typed `INSTALLATION_REF_AMBIGUOUS` (reselection - never an order-based pick). Legacy v1 refs (content fingerprints) still resolve when the inventory proves exactly one target; identical copies are ambiguous by construction. Alias policy: PATH entries/symlinks resolving to the same canonical target are ONE installation (discovery dedups by ref). Move/rename changes the ref (old ref = stale, reselect); a content update keeps the ref but prepare/open keep refusing drift. Refs know nothing of authorization - the agent's policy stays in the Server. |
| `evaluate_runtime_availability`, `AvailabilityReport`, `CandidateAvailability`, `AVAILABILITY_FORMAT_VERSION` | Per-candidate TECHNICAL availability (C10): assess an `Inventory` (from `runtime.discover`) passively - the registry's platform support, `compatibility`'s exact-build qualification and the containment preflight of the EXECUTING host (never the rendering UI's). States: `NOT_INSTALLED`, `UNSUPPORTED_PLATFORM`, `NOT_PROBED`, `UNQUALIFIED_BUILD`, `CONTAINMENT_UNAVAILABLE`, `PREPARATION_REQUIRED`, `READY_FOR_RUNTIME` with stable `reasons` codes; an absent probe stays inconclusive (never READY by omission); two builds of one family never merge (`candidate_ref` = the producing host's inventory fingerprint; the executing host resolves it at prepare time, which revalidates). `AvailabilityReport.to_dict()` is the explicit versioned JSON-safe remote projection (no paths/modules/credentials; NXL frames unchanged - Connector/Server transmit it on their own versioned API). `READY_FOR_RUNTIME` is TECHNICAL ONLY - the agent's authorization stays in the Nexus Server. |
| `DiscoveryRequest`, `Inventory`, `InstallationCandidate` | Discover or pass explicitly selected local native candidates; discovery is not qualification. |
| `LaunchIntent`, `PreparedLaunch`, `OpenOperation` | Prepare a selected managed launch and open a session. `open` revalidates binary/profile/root before native effect. |
| `TurnOperation`, `ControlOperation`, `CloseOperation` | Submit text, interrupt/steer a targeted turn, or close an owned session. Steer targeting is adapter-specific (see below). Use a new operation ID for each new intent. |
| `CodexResumeGrant` | Public trusted-host resume contract for binding one stored Codex thread to one open (C2/R09). Construct from this package; the bridge validates the exact type and every binding field. |
| `NativeApprovalOperation` | Host-authorized response to one pending Codex/Claude native approval or input request. The host passes the redacted event's `native_approval` projection; the adapter checks it against its original in-memory request. |
| `Operation`, `OperationKey`, `OperationReceipt`, `intent_hash`, `submit_frame_intent_hash` | Semantic intent identity and namespace-scoped durable receipt. Reuse an operation ID only for the identical intent. |
| `SessionKey`, `RuntimeSnapshot`, `ReconcileRequest`, `ReconcileReport` | Namespace-scoped inspection and recovery queries. A missing process-local handle yields unknown ownership, not proof of stop. |
| `ClaimedSession`, `SessionClaimPage` | Paged durable session-ID history with the original open operation ID and, for new Core opens, opening connection/owner generations. These are claims, not active-process or lease observations. |
| `SessionLeaseState` | Durable last-known lease fence for one claimed session, written atomically with the claim and advanced by `renew_lease`/`revoke_lease` through journal CAS. Fence evidence for host reconciliation — not process liveness, not a lease deadline, not takeover authority. |
| `ProcessBirthEvidence`, `ProcessBirthRecord` | Historical OS birth identity for a Core-owned process container. PID/token are diagnostic evidence, never authority to signal or reattach after restart. |
| `ProcessBirthObservation` | One read-only, transient comparison of a stored birth to the current OS PID; it does not grant ownership. |
| `RuntimeEvent`, `EventCursor` | Durable technical event stream; cursor includes server, executor, session and stream epoch. |
| `StorageStatus` | SQLite database/WAL/SHM observation. Logical quotas are not a hard filesystem quota. |
| `OwnedSlotLedger`, `SQLiteOwnedSlotLedger` | Optional installation-wide owned-slot port and Core-owned SQLite implementation. Every runtime in that installation must receive handles to the same absolute ledger path. |
| `OwnedSlotReservation`, `OwnedSlotPage` | Bounded read-only inventory of unresolved reservations and their original open operation IDs; it is not process-liveness or release authority. |
| `ShutdownPolicy`, `ShutdownReport` | Bounded drain/interrupt observation and per-session outcome. `unknown` retains ownership. |
| `CoreError` | Typed failure with `code`, `stage`, `possible_effect`, `retry_safe` and optional `operation_id`. C3/S07: `code` is a stable machine-readable enum; human diagnostics (redacted by the raiser) travel in the separate `message` field (`str(exc)` shows the message). |
| `OperationNotAdmitted` | A `CoreError` raised when productive quota refuses a turn before any native effect. Its correlated `refusal` is **not durable in Core**. The host must persist that fact in its publication obligation before publishing it, retain its own replay identity, and reconcile normally if it crashes before persistence. No reserved interrupt/close rows are consumed. |
| `CONTRACT_REVISION` | Exact NXL revision required by development negotiation; see [compatibility](compatibility.md). |

`LocalRuntimeCore` implements `discover`, `prepare`, `open`, `submit`,
`control`, `decide_native_approval`, `events`, `acknowledge_events`, `compact_events`, `storage_status`,
`checkpoint_wal`, `inspect`, `claimed_sessions`, `process_birth`,
`observe_process_birth`, `persisted_lease`, `reconcile`, `close`, `shutdown`, `renew_lease` and
`revoke_lease` as defined in `RuntimeCore`. `events` is an async iterator; the
other public operations above are awaited. `acknowledge_events` is for a
trusted host **after** its Server durable-ingress ACK, not on network receipt.
The local constructor's `reconnect_fence_seconds` bounds the wait for pending
session native sends before `renew_lease`/`revoke_lease` can report a
successful generation or revocation update; a busy error leaves that update
unapplied.

`context_observation_supported(SessionKey)` reports optional, observed support
on a live owned session. `observe_context(SessionKey, envelope, guard=...)` is a
trusted-host context-storage port, not an execution command or a remote R4 action.
Only a registered connector that confirms context-observation contract 1 and
implements the guarded method qualifies. The host must first commit a durable
send intent, bound its physical workers, and never replay an uncertain call.
Its mandatory guard revalidates the source audience, credential, approved
observer endpoint and host owner at the native write frontier. Core additionally
checks the live lease, session scope and containment fence. The envelope must
request information without a response. Success proves only the method returned:
it creates no turn, inference, execution grant or runtime result. This port does
not add observation support to remote executors or to built-in harnesses.
`decide_native_approval` requires `approval.decide` or `input.provide` in the
host-issued `ExecutionContext` and in the active binding. The Core first
requires an exact matching native request event that its own journal has
committed for this live session. A fabricated, edited, already answered or
terminal-turn request fails before operation admission. Its intent is
durable before the native reply; a successful write returns `SUBMITTED`, not
proof that the provider acted. Only the response digest enters the journal,
not operator answer content. Stale requests fail before write; a write error
remains uncertain. Request and answer JSON have a 16 KiB encoded ceiling and
a 64-level structural ceiling. Grossly oversized, cyclic or non-JSON input is
refused before canonicalization; exact encoded-size excess is refused before
journal admission.
`CopiedAdapterFactory(native_approvals_enabled=True)` is
an explicit host opt-in, off by default, and does not by itself qualify a
provider build or grant an approval decision.
The opt-in also requires both `approval.decide` and `input.provide` in the
launch context; otherwise launch refuses before resolving credentials.
`compact_events(max_rows=...)` accepts only an integer from 1 to 4,096
(default 128); invalid batches fail before calling the journal port.
`turn.steer` targeting is adapter-specific. The Codex app-server adapter
requires `expected_turn_id` naming the active native turn and refuses a
steer without one before admission. The Pi RPC adapter has no native turn
ID on the wire: its steer is admitted only with `expected_turn_id=None`,
targets the agent run Core observed starting (`agent_start`) for the active
submit, and refuses before admission when a native turn ID is supplied.
The copied-adapter bridge refuses an ID-less Pi steer before the native
write with a retry-safe `STALE_TURN` when no submit is active or its agent
run has not been observed starting; delivery then follows Pi's native
next-turn-boundary steering queue (`queue_update`), not immediate
injection, and the steered content stays part of the same active turn. A
Pi follow-up after `agent_settled` is a new `turn.submit`. Every steer
still requires `turn.steer` in the host-issued `ExecutionContext` and in
the active binding. This contract is exercised against contained peers
and the public runtime; real-provider steer/queue behavior remains
unqualified.
`runtime.open` atomically claims its session ID in the journal namespace;
host journal adapters must implement the `claim_session` admission flag and
atomically retain the supplied opening generations with that claim. Legacy
claims without this evidence report `None`, never a guessed generation.
When the opening admission also supplies the authorization/configuration
revisions, the claim seeds a durable `session_lease_state` row.
`renew_lease` and `revoke_lease` advance that row through journal CAS before
the in-memory generation changes: a second Core instance sharing the journal,
or a host-side CAS, makes an older renewal fail `STALE_GENERATION` without
ever becoming active, and a revocation committed durably can never be
un-revoked. A legacy claim without lease evidence fails renewal with
`SESSION_UNKNOWN` rather than being seeded from memory. `persisted_lease`
reads the last durable fence for host reconciliation after restart; it is
evidence, not liveness or takeover authority. Host journal adapters must
implement `cas_session_lease`/`get_session_lease`.
For managed launches, the Journal port must also implement
`reserve_owned_slot`/`release_owned_slot`; a reservation is acquired after
possible-effect admission but before native launch and is retained on an
uncertain outcome. `JournalLimits.max_owned_slots` defaults to eight for one
shared SQLite file. For distinct technical journals, construct separate
`SQLiteOwnedSlotLedger` handles over one installation-owned absolute local
path and pass each as `LocalRuntimeCore(owned_slot_ledger=...)`; otherwise
there is no cross-journal cap. The host owns ledger lifetime and must not
delete, replace, or reinterpret unresolved reservations as free slots.
The host may call `owned_slot_page(after_rowid=..., high_water_rowid=...,
limit=...)` on its ledger to inspect unresolved reservations across all
namespaces. The first page fixes a high-water row ID; pass it and
`next_after_rowid` to subsequent pages. `limit` is 1–4096 (default 128).
Concurrent release can remove a row between pages, so this is a bounded
inventory, not an atomic point-in-time snapshot or proof of physical stop.
`SESSION_CONFLICT` on a new operation means the session ID has already been
used, even if the prior open was safely refused.
For Core-owned child containers, `open` also stores immutable
`ProcessBirthEvidence` under that claim before returning success. The
`process_birth(SessionKey)` query returns the historical `ProcessBirthRecord`
or `None`; its PID/token do not grant process-control authority. A host Journal
adapter must implement `record_process_birth` and `get_process_birth`.
`observe_process_birth` returns `UNRECORDED`, `MATCHING_LIVE`,
`DIFFERENT_BIRTH`, `NOT_RUNNING`, `NOT_OBSERVED`, or `UNKNOWN` from a
read-only OS check. Even `MATCHING_LIVE` is a transient observation, not a
lease or permission to signal the PID.
`reconcile` accepts at most 256 distinct operation IDs and 256 distinct
session IDs per call, each 1–160 characters, matching the bundled NXL
`reconcile.request` frame. Invalid requests fail before journal lookup; hosts
should batch larger recovery scans.

Host journal adapters should run both
`nexus_connector_core.testing.run_journal_conformance(adapter)` and
`run_journal_restart_conformance(open_journal)`. The latter accepts a callable
returning an async context manager: each call must open the same private
backing store and close its adapter on exit. It checks operation/effect-marker,
session-claim, event-sequence and ACK continuity across two reopen cuts. It
does not simulate an OS crash or establish native process ownership.
Alternative installation ledgers should also pass
`run_owned_slot_conformance(ledger, max_slots=...)` and
`run_owned_slot_restart_conformance(open_ledger)` on a private empty store.

Minimal use with an injected test/native factory is exercised by
`tools/consumer_smoke.py` for separate embedded and remote consumer shapes.
Real Server/Connector integration and native provider qualification remain
open. Consumers should verify the installed contract bundle using
`python -m nexus_connector_core.conformance` with an expected manifest hash;
the current bundle requires explicit `development-partial` opt-in. A local
wheel can be installed without application dependencies; see the
[offline packaging evidence](../plans/implementation/evidence/offline-package-2026-09-26.md).

The `RuntimeCore` protocol and the top-level exported dataclasses are the
intended stable surface. Implementation-specific journal/configuration/native
helpers currently used by synthetic consumers are provisional and must not be
treated as a qualified cross-application integration contract.

## Availability consumption (C10) - the two integration paths

Passive discovery is also available through `discover_installations`, without
constructing a runtime, journal or credentials. R4 hosts use
`build_executor_inventory_snapshot` and `calculate_inventory_revision` over
the complete Core inventory, and verify remote projections with
`verify_executor_inventory_snapshot`. `SNAPSHOT_FORMAT_VERSION` versions this
envelope independently from catalog and availability formats. Keep the full
local candidate for selection; the published snapshot contains opaque refs.
`get_executor_inventory_schema` returns the generated current HTTP inventory
schema verified by the same R4 manifest as the wire bundle. Consumers compose
these definitions into their HTTP response schemas without copying enums.

The catalog (`get_runtime_catalog()`),
`evaluate_runtime_availability()` and `resolve_installation()` complete
the selector contract (projection format **2**; see the installation
identity row above for the v1 -> v2 migration rules):

* **Local (Nexus Server, embedded Core):** the Server composes its
  `RuntimeCore`, runs `await runtime.discover(DiscoveryRequest())` and
  evaluates the returned inventory on ITS OWN host, then applies agent
  policy/permissions on top of the TECHNICAL states before publishing
  options to the UI. `READY_FOR_RUNTIME` is never the authorization.
* **Remote (Nexus Connector):** the Connector's Core produces the
  facts of ITS host - `evaluate_runtime_availability(inventory)` and
  `report.to_dict()` - and transmits the versioned projection to the
  Server through the Connector/Server API. The Server renders that
  executor's options from the received facts; it never re-derives
  build/platform/containment rules and never substitutes its own
  platform for the executing host's.

The UI renders received descriptors/states verbatim (state + `reasons`
per candidate); it keeps no authoritative runtime array. `OFFLINE`,
`STALE`, TTL, connection and authorization states belong to the
hosts' application layer, not to the catalog/availability projection.
`examples/availability_projection.py` runs the reference scenario -
REAL discovery of two byte-identical copies in distinct trusted roots
(the A11-01 case), removed attach rejected as unsupported, missing
installation - through catalog -> discovery -> availability ->
projection -> selection -> `resolve_installation` -> existing
composition, and emits the JSON fixture (`--json`) with the acceptance
criteria for Server UI tests: every row renders state+reasons,
same-family rows never collapse (distinct refs, distinct labels),
removed attach is absent from the catalog, `NOT_PROBED` never renders ready,
`display_name`/`label` are never identities, and a projection with an
unknown `format_version` renders INCOMPATIBLE
(`AvailabilityReport.from_dict` refuses it typed). `executor_id`,
`inventory_revision` and TTL are the hosts' envelope around a
selection: a ref from another executor does not resolve against this
inventory (typed not-found); the Server validates scope/revision, the
Core never issues network endpoints.

## Independent R4 development exports

`ControlTargeting`, `get_control_targeting` and `validate_control_target` expose the
registry's control contract. Catalog format 2 includes these facts in each
`RuntimeDescriptor.control_targeting`. Validation is shared with runtime
admission; active-run identity is checked again at the native write frontier.
Implemented targeting does not grant authority or qualify a provider build.

All R4 exports below require authenticated host authority. The runtime lease
methods install that authority; pure reducers alone grant no native effect.
See [the R4 guide](nxl-r4-development.md)
for native decision hash domains and the remaining executable-bundle gate.

| Public exports | Host responsibility and behavior |
|---|---|
| `R4_CONTRACT_REVISION`, `R4_BUNDLE_EXECUTABLE`, `verify_r4_bundle` | Inspect the verified executable R4 bundle independently of historical R3. Executability does not grant host or native authority. |
| `R4_PREVIEW_REVISION`, `verify_r4_development_bundle` | Compatibility aliases for the explicit R4 revision and verifier; preserved wire bytes and return shape. |
| `decode_r4_frame`, `encode_r4_frame`, `r4_submit_intent_hash` | Strict closed schemas, bounded UTF-8 and independent JCS intent hashing. Preserve R3 history. |
| `r4_close_operation` | Validate an R4 close frame and convert its reason and bounded drain/interrupt policy into `CloseOperation`. Apply it with the installed context; never discard policy fields. |
| `R4ReconcileAttempt`, `R4ControlProjection`, `reduce_r4_reconcile_accepted` | Correlate a Server ACK with its connection and reconciliation attempt. Control readiness does not imply a session lease. |
| `R4AttachAttempt`, `R4LaneProjection`, `reduce_r4_binding_attached`, `r4_lane_ready` | Correlate committed attach ACKs, revisions and local expiry; socket write alone does not admit a lane. |
| `R4LeaseAttempt`, `R4LeaseProjection`, `r4_lease_renew_frame`, `reduce_r4_lease_grant` | Capture monotonic time before the request, correlate scope/serial, and consume transport delay from the granted duration. |
| `R4Authority`, `R4LeaseApplication` | Immutable full R4 context scope and the actual runtime application result. Use `RuntimeCore.begin_r4_lease_request`, `install_r4_lease`, `r4_operation_context` and `revoke_r4_lease`; never manufacture a context or ACK from receipt of a grant. |
| `reduce_r4_lease_applied`, `r4_lease_productive` | Track reported Core installation and check local deadline/action. The host must actually install or renew the Core context before ACKing it. |
| `R4ReceiptProjection`, `reduce_r4_receipt` | Validate scoped revisions, stages, possible effects and idempotent replay. Hosts persist the result atomically. |
| `project_r4_open_receipt`, `project_r4_turn_receipt`, `project_r4_steer_receipt`, `project_r4_interrupt_receipt`, `project_r4_close_receipt` | Verify the corresponding Core journal semantic before projecting a distinct R4 receipt; open also requires prepared launch/stream evidence. |
| `project_r4_decision_receipt`, `r4_native_decision_operation`, `r4_operational_request_hash` | Preserve native request evidence, validate response digests and project approval/input receipts from the exact applied operation. |
| `R4EventCommitProjection`, `reduce_r4_durable_event_batch`, `r4_event_ack_frame` | Compute contiguous event ACKs. The host commits durable ingress before emitting an ACK and retains connection scope. |
| `R4ApprovalProjection`, `reduce_r4_approval_request`, `reduce_r4_approval_decision` | Retain the complete operational request hash and correlated decision notification. These reducers never apply a native decision. |


### Waiting for an owned close result

For policy close, `close(operation, context, wait_for_completion=True)` joins the
retained producer through the final receipt commit. The physical drain/interrupt
deadline is unchanged. The default remains a bounded observation that can return
OUTCOME_UNKNOWN while the producer continues. Canceling either waiter does not
cancel the producer. Trusted daemon/embedded operation owners use the complete
wait; failures of the producer, including storage failures, propagate to them.
This option requires an explicit close policy and is not a wire payload field.

## Durable R4 receipt bindings

The public functions are `prepare_r4_receipt_binding`,
`validate_r4_receipt_binding` and `project_r4_bound_receipt`.

`prepare_r4_receipt_binding(frame, context, prepared=..., stream_epoch=..., applied_operation=...)` verifies the dispatched semantic and returns a schema-1, non-secret record associating its R4 hash with the exact Core hash. Supply prepared launch/stream for open and the typed native decision for approval/input. The trusted host must commit this record before calling the runtime. It contains no prompt, response, native request, executable path, environment or credential.

After restart, read `Journal.get_receipt(OperationKey(...))` and call `project_r4_bound_receipt(binding, receipt, key=key, receipt_revision=...)`. This validates the stored digest, namespace, operation/session IDs and Core hash, and preserves the original source connection. `validate_r4_receipt_binding` returns a detached checked record for storage readers. The digest detects corruption, not hostile forgery: these are trusted local records, not network authority. No API creates a receipt from absence, renews a lease, restores a native handle or authorizes replay. Missing or legacy associations remain unresolved.

## Resource release and passive discovery cancellation

`OwnedSlotState` records the historical session reservation and release fact;
it never grants authority over a live process. `project_r4_resource_release`
requires matching receipt binding, claimed session, released owned slot and
opening receipt before projecting an EXITED resource proof. An effect-capable
intermediate or unknown opening outcome is retained unchanged: the independently
released owned slot proves containment, not operation success. Mismatched scope,
unreleased slots and unstarted admission receipts are refused. `r4_resource_release_digest` computes the
scoped proof digest; a digest alone is not evidence that a process stopped.

`DiscoveryCancelled` reports that the host stopped passive observation before
receiving an inventory. Hosts should retain shutdown ownership and distinguish
cancellation from an empty successful inventory; it does not authorize a launch.

## Native extension domain requests

`native_action_bridge` provides typed `MessageCreate`, `RuntimeInputList` and
`RuntimeInputRespond` requests alongside the handoff requests. Their canonical
backend methods are `create_message`, `list_runtime_inputs` and
`respond_runtime_input`. The bridge enforces the host-issued session grant;
domain state, replay and recipient policy remain in the Nexus backend.

Pi's local extension exposes `nexus_message_create`, `nexus_runtime_input_list`
and `nexus_runtime_input_respond`. Message payloads contain content and target;
the authenticated session supplies sender and workspace. Question answers retain
the source harness contract. Tool call IDs provide operation identity. A lost
message or answer acknowledgement is `OUTCOME_UNKNOWN`, never an instruction to
retry with a new ID. Requests and responses remain bounded to 16 KiB.
## Technical execution capacity

`CAPACITY_CONTRACT_REVISION` identifies the independently negotiated capacity
protocol. `CAPACITY_REASONS` and `RESERVATION_STATES` define its bounded outcomes.
`CapacityScope` binds an attempt to the authenticated connection, session and
authorization revisions. `CapacityAssessment` is an advisory observation;
`CapacityConsumption` correlates admission with an operation; `CapacityReservation`
and `CapacityReservationPage` expose durable reservations and paginated recovery.
`require_same_capacity_request` rejects reuse of an attempt with changed scope,
and `capacity_contract_supported` checks protocol compatibility.

`CapacitySlotLedger` is the storage port and `RuntimeCapacityAuthority` revalidates
host authority. `CapacityChangePublisher` publishes bounded change hints; it does
not authorize admission. `OperationCapacityDeferred` signals pre-effect capacity
deferral and `CapacityRetryWaiter` waits for relevant changes without retaining an
execution worker.

`CAPACITY_FRAME_TYPES` and `CAPACITY_REQUEST_TYPES` enumerate control frames.
`encode_capacity_frame` and `decode_capacity_frame` validate the byte-pinned schema,
while `verify_capacity_bundle` checks packaged resources and fixtures.
`decode_control_frame` routes negotiated extensions; `execute_capacity_control`
dispatches an authenticated capacity request and `capacity_result_frame` or
`capacity_denial_frame` correlates its result with the original request.

`ExecutionCapacity` implements the public `RuntimeCapacity` port over the host's
physical slot ledger. Assessment is advisory. Reservation, lookup, consumption
and release use the exact immutable `CapacityRequest`; the host still checks its
authenticated owner and native execution authority. These operations do not
decide ownership of application work.

If a reserve response is lost, look up the original request before retrying.
To abandon an attempt that has no host record, call `release_capacity` with
the ID returned by `capacity_reservation_id` for that request and reason `CANCELLED`. The host atomically
persists a `RELEASED` record with no consumption in the same journal used by
reserve. A delayed reserve replays that record without taking a slot. An empty
lookup alone is not proof that a delayed request cannot still arrive.

The proposed ID is derived from the complete immutable request. A persisted
reservation's ID remains authoritative, including opaque IDs from older Core
versions; never replace one with the proposed ID. If known history disappears,
retain uncertainty rather than manufacture a replacement no-effect record.
Older hosts may refuse cancellation before reservation. Treat that refusal as
unresolved; it must not grant permission to create a competing attempt.

`prepare_r4_lease_refusal`, `validate_r4_lease_refusal` and
`persist_r4_lease_refusal` preserve a correlated refusal before productive work.
`prepare_r4_preopen_refusal`, `validate_r4_preopen_refusal` and
`persist_r4_preopen_refusal` provide the corresponding preopening evidence.
`PREOPEN_REFUSAL_REVISION` versions that negotiated extension, and
`validate_r4_preopen_report` validates its recovery report. These records prove
only their original attempt's outcome; they do not authorize replay of uncertain
native effects.

Cancellation does not release another attempt's session or an active turn.
Consumed reservations enter `RELEASE_PENDING` until the existing journal and
correlated termination evidence allow release. TTL and cancellation acknowledgements
must never be used to infer that native effects have stopped.

## Journal, inventory, and startup refusal extensions

`JournalLocation`, `JournalRegistration`, `JournalLocationPage`, and
`JournalLocationRegistry` identify and page registered durable journals.
`IndependentInventoryObserver` separates passive discovery from productive
startup. `HarnessObservationResult`, `HarnessObservation`,
`InventoryObservationBatch`, and `InventoryRefreshFrontier` carry partial
per-harness observations. `inventory_observation_fresh` requires a completed
observation within its TTL; pending or failed observation is never absence.

`STARTUP_REFUSAL_REVISION` identifies the bounded startup-refusal extension.
`prepare_r4_startup_refusal`, `validate_r4_startup_refusal`,
`persist_r4_startup_refusal`, `encode_startup_refusal`, and
`decode_startup_refusal` preserve a correlated pre-effect refusal.
`startup_refusal_accepted` and `startup_refusal_deferred` distinguish its
admission outcome. `prepare_r4_stopped_refusal`,
`validate_r4_stopped_refusal`, `validate_r4_operation_refusal`, and
`persist_r4_operation_refusal` require exact operation and containment evidence
before a stopped opening is reported as safe to release.

# Portable connection configuration

`nexus_connector_core.connection_configuration` provides
`parse_portable_connection_configuration(value)` and `export_connection_configuration(value)`
for `okto-nexus-connection` version 2 templates. These contain native preferences,
connection name, runtime/session policy, message/tool policies and requested limits.
`session_policy` accepts `shared`, `per_sender`, `per_sender_session`, or `null`
(inherit). Since Core 0.2.63.dev0, `per_sender_session` preserves a separate target
conversation for each sending agent and verified source session. Routing and
durable affinity are owned by the Nexus Server; Core preserves this policy in
configuration imports and exports. Sessionless senders use their own per-agent
fallback conversation, separate from verified source sessions.
They never contain identity, credentials, installation IDs, execution-host selection,
workspace/login paths, workspace names or local secret references. Version 1 imports
are accepted after discarding all destination fields. Duplicate/unknown fields fail.
`materialize_connection_configuration` combines a template with explicit destination
arguments. `parse_connection_configuration` validates that complete version 1 shape
for the internal Server API; it is not the portable export format.
This document is a configuration draft, not execution authority. Hosts must
authenticate the operator, resolve their own installation, validate directories,
test the selected configuration and explicitly commit it before normal runtime
use. Importing JSON must never renew or recreate an execution grant implicitly.
