# Contract and composition map

Specification versions: supplied 01/02 v1.0; current implementation below is
the P00 legacy baseline, not the target design.

| Boundary | Existing symbols | Evolution rule |
|---|---|---|
| Auth | http.app.ApiKeyAuthMiddleware, identity_ctx.current_agent; application.auth.AgentKeyAuthService | Construct trusted request context from authentication, never payload. Preserve keyless local REST only when no credential is supplied. |
| MCP | server.register_tools → tools.harness.register; envelope decorators only normalize errors | Optional façade; shared application authorization, including cached tools. |
| REST | routes.harness_* → same factory/supervisor helpers, separate _require_operator | Replace duplicated authorization decisions with shared use cases. |
| Canonical identity | IdentityService, SqliteAgentRepo, SqliteSessionRepo | Connection lifecycle reads profile, never upserts it. Presence belongs to a specific binding. |
| Message | MessageService.create_message → _send_uow → delivery/event → commit → _maybe_notify_inbox_subscribers | Reuse transaction for intent; callback becomes wakeup only. |
| Inbox | SqliteMessageDeliveryRepo + inbox services | Add consumption arbitration; retain logical delivery/receipt authority. |
| Work | HandoffService claim/complete/verification/dependencies, governance/approvals | Dispatch must derive from existing authorized claim; native terminal alone is not completion. |
| Runtime | HarnessSupervisor.open/send/close/open_declared, HarnessBootSpec | Preserve existing session table; add endpoint/operation ownership instead of second session entity. |
| Transport | PiRpcConnector, CodexAppServerConnector, ClaudeCodeStreamConnector, ClaudeCodeAttachConnector | Preserve real protocol capability distinctions; registry and versioned façade. |
| Persistence | SqliteHarnessSessionRepo, SqliteHarnessEventRepo; migrations 029 | Additive migration only. MigrationRunner rejects newer schemas; record writer compatibility in target. |
| Outputs | supervisor._handle_event/_persist_event/_deliver_notable_message | Journal first for durable terminal; atomic idempotent projection; ACL-controlled publication. |
| Serve | http.app.build_app; cli.serve.run_serve + watchdog | One owner for runtime/dispatcher. Stdio remains writer/client, not implicit process owner. |
| Artifacts | existing external artifact storage introduced in 028 | Reuse managed storage; no confirmed refs before durable write. |

Historical ADR 0004 freezes ports and prescribes publish-before-best-effort DB.
The current user specification explicitly supersedes those restrictions.
Layering rules remain: no sqlite3/mcp imports in domain/application.

Full legacy schemas, flags, SQLite definitions and measured surface are in
`evidence/p00-contracts.json`. OFF surface must match merge-base's 43-tool
legacy set, allowing explicitly recorded version/flag/schema metadata changes.


## Additive runtime event/lifecycle mapping (0.2.0)

- Event ingress port: `application/runtime_event_ingress.RuntimeEventJournal`;
  file adapter: `adapters/outbound/harness/event_journal.FileRuntimeEventJournal`.
- Captured result and checkpoint: migration 033 `runtime_results` /
  `runtime_journal_checkpoint`, projected atomically with existing `harness_events`.
- `HarnessEvent.event_id` / `sequence` expose existing persistence identities;
  optional `origin` defaults to native for old records. Migration 034 stores
  origin explicitly; peer payload strings cannot set the Nexus event origin.
- Shared process ownership: `RuntimeConnectionLifecycle` leases. Persisted
  connection IDs reuse migration 030's `harness_sessions.connection_id`.
- Runtime lifecycle vocabulary uses `protocol_ready`, `stop_requested`, `stopped`,
  `detached`, `outcome_unknown`. Legacy session `status` is not used to infer
  observed process exit; in particular a detached runtime can retain its last
  RUNNING value while its lifecycle truth is detached.
- Native per-connection/thread IDs remain distinct from canonical agent and
  runtime-session IDs. No new identity registry was introduced.

## Native transient event stream v2

The four built-in connectors declare `event_stream_contract_version = 2`;
EnvelopeConnector forwards it, defaulting to 1 for legacy trusted extensions.
This versions native `events()` replay semantics separately from the unchanged
canonical delivery envelope/adapter registration v1 and durable journal v1.
Native in-memory history is a bounded window. Expired replay raises explicitly;
live subscribers have bounded independent queues and overflow raises after
draining the retained prefix. The supervisor records uncertainty and quarantines
the affected binding. Historical replay goes through the authenticated canonical
event repository, never an assumption that a native list contains all events.
See P07_EVENT_BUFFERS.md for exact limits, validation and remaining boundaries.

## Event correlation v2 (migration 035)

Optional HarnessEvent operation_id/attempt_id/owner_epoch/delivery_phase originate
in EnvelopeConnector's trusted command registration, not native payload fields.
HarnessCommand carries the internal attempt context separately from prompt data.
Adapters implement delivery_event_phase; application code does not branch on
protocol event names. Legacy events default to uncorrelated. Envelope/registry
v1, native transient stream v2, and durable framed journal v1 are separate versions.
See P08_RESULT_CORRELATION.md for compatibility, guards and unfinished gates.

Migration 036 adds optional normalized output_text/output_snapshot to event data
and bounded derived output text/truncation/count to runtime_results. The adapter
delivery_output hook owns native vocabulary. InboxService's internal terminal
consumption reuses logical inbox state/receipts with explicit native_terminal
provenance; no public ack bypass or new work queue is introduced. See
P08_CONSUMPTION_MATERIALIZATION.md. Existing inbox `read` vocabulary does not imply
human reading or handoff completion for this path.

Linux managed process ownership: OwnedLinuxPopen/isolated subreaper guardian,
owner pidfd plus private cancel/proof descriptors. Popen.pid identifies the guardian;
native protocol IDs remain separate. Observed stop requires guardian cleanup proof.
Managed adapters advertise Windows/Linux; attach retains POSIX. See
P07_LINUX_OWNERSHIP.md for exact platform evidence and limitations.


## Capture admission mapping (schema062)

The logical capture-health admission fence reuses runtime_writer_contract via
capture_available, rather than a new work queue/health authority. Only the current
runtime owner/epoch updates the bit. RuntimeEventIngress serializes capture faults
with validated compaction/startup recovery and records health outside journal IO;
RuntimeDispatcher retries failed health persistence with its bounded coordinator.
SQLite repositories and insert triggers arbitrate new delivery, send/steer and
open intents in the same canonical transaction across all writers. Existing
idempotent replies and stop controls remain separately authorized. Native dispatch
retains a final journal check. No adapter capability, native ACK or result
semantics change; tool surface57/identity25 remain, with additive schema062.


## Optional context observation contract v1 (schema063)

ContextObservationConnector.observe_context is a separate optional port; the existing HarnessConnector
and four native send/control contracts remain unchanged. Descriptor input_schema.context_observation_contract=1,
trusted capability probing, method existence and approved profile restrictions must all agree.
RuntimeDeliveryPlanner selects only ready same-agent/workspace mirror_only/response_policy=none bindings.
It derives information envelopes without execution bootstrap and persists them with the original intent.

runtime_context_observations is subordinate outbox transport state with a foreign key to delivery_outbox;
it creates no new logical delivery, consumer reservation, task, claim or executable budget. An additive
table preserves the existing unique executor-per-delivery constraint and closed administrative command
vocabulary. RuntimeCommandDispatcher is reused with one bounded observation slot under RuntimeDispatcher's
existing owner/wake/shutdown. Timeout cannot free that slot before the call returns. No new orchestrator,
external broker, SDK or native acknowledgement was introduced.

The public additive context_observations projection on harness_get is filtered through each observer
endpoint's read authorization. Read-only authorization suppresses audit writes in that read snapshot;
the enclosing operation access remains audited. Stored attempt durability is distinct from acceptance
and result durability. The fifth processless adapter proves this extension; native built-in descriptors
continue to advertise no context_without_execution capability.

## External attach work contract v1 (surface58/schema064)

public_config.nexus_work_session_id pins an active, same-agent/workspace canonical session; configuration
is never proof. ExternalWorkChannel reuses agent authentication and verify_session_credentials(strict)
with a persisted nonsecret fingerprint, existing execute_work grant and canonical claim_epoch. Managed
external attach requires authenticated self-claim and prior explicit Nexus ACK before complete/reject.

RuntimeWorkService and the existing InboxService/HandoffService perform all mutations in their original
writer transactions. runtime_handoff_bindings stores external session/ACK/completion facts; delivery_outbox
stores external_completed_at. No new inbox, task queue, native event or result table is introduced. The
trusted HarnessCommand.external_work_channel flag is set only after server-side revalidation, never from
a native/public payload. QualifiedConnector retains false native managed_work/events for attach.

Public operation inspection exposes external_work separately from native result durability. Discovery
exposes configured/authentication-required only, with no external session ID/secret. A narrow ConnectionFactory
capability marker and migration triggers fence old writers that would otherwise bypass the new proof through
legacy completion. Legacy unbound writers remain subject to the existing global contract. Scope/evidence:
P12_ATTACH_WORK_INTEGRATION.md; configuration history: P12_ATTACH_WORK_CHANNEL.md.
