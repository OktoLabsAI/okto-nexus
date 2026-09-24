# Final finding and release audit at39c5e6c

IN PROGRESS. This is a source/evidence index, not a passed final gate. Current immutable-source Windows regression is running; Linux full regression and local installation remain pending. Historical scoped results are preserved with their original SHA/generation.

| Finding | Current implementation | Scoped evidence |
|---|---|---|
| F01 — Canonical identity is preserved by runtime lifecycle | [RuntimeOpenService.open](../../src/okto_nexus/application/runtime_open.py) | [P12_IDENTITY_ACCEPTANCE](P12_IDENTITY_ACCEPTANCE.md), [P12_IDENTITY_FAILURE_ACCEPTANCE](P12_IDENTITY_FAILURE_ACCEPTANCE.md) |
| F02 — Authenticated actor and current grant authorize shared runtime surfaces | [RuntimeAccessService.authorize](../../src/okto_nexus/application/runtime_access.py) | [P12_MONITOR_AUTHORIZATION](P12_MONITOR_AUTHORIZATION.md), [P12_OPERATION_AUTHORIZATION](P12_OPERATION_AUTHORIZATION.md), [P12_AUDIENCE_NATIVE_AUTHORITY](P12_AUDIENCE_NATIVE_AUTHORITY.md), [P12_ATTACH_WORK_INTEGRATION](P12_ATTACH_WORK_INTEGRATION.md) |
| F03 — One inbox executor; context-only observation is a separate nonexecuting capability | [RuntimeDeliveryPlanner.enqueue](../../src/okto_nexus/application/runtime_delivery.py) | [P12_PULL_PUSH_RACE](P12_PULL_PUSH_RACE.md), [P12_CONSUMPTION_ACCEPTANCE](P12_CONSUMPTION_ACCEPTANCE.md), [P12_MIRROR_OBSERVATION](P12_MIRROR_OBSERVATION.md) |
| F04 — Transactional outbox plus indexed owner drain survives lost wakeups | [RuntimeDispatcher](../../src/okto_nexus/application/runtime_dispatcher.py) | [P12_COMMIT_CRASH](P12_COMMIT_CRASH.md), [P12_DELIVERY_ACCEPTANCE](P12_DELIVERY_ACCEPTANCE.md), [P12_OWNER_FENCING](P12_OWNER_FENCING.md), [P12_PRODUCER_ACCEPTANCE](P12_PRODUCER_ACCEPTANCE.md) |
| F05 — Durable event ingress and fenced admission preserve observed versus projected facts | [RuntimeEventIngress](../../src/okto_nexus/application/runtime_event_ingress.py) | [P12_CAPTURE_ADMISSION](P12_CAPTURE_ADMISSION.md), [P12_PROJECTION_COMMIT_CRASH](P12_PROJECTION_COMMIT_CRASH.md), [P12_CAPTURE_AND_RECEIPTS](P12_CAPTURE_AND_RECEIPTS.md) |
| F06 — Canonical versioned envelope retains message and sender correlation | [module](../../src/okto_nexus/domain/delivery.py) | [P12_CANONICAL_PAYLOAD](P12_CANONICAL_PAYLOAD.md), [P12_FRAGMENTED_PIPES](P12_FRAGMENTED_PIPES.md), [P12_OPERATION_EVENTS](P12_OPERATION_EVENTS.md) |
| F07 — Canonical claim/grant/epoch owns executable work; conversation is not a claim | [RuntimeWorkService](../../src/okto_nexus/application/runtime_work.py) | [P12_WORK_ACCEPTANCE](P12_WORK_ACCEPTANCE.md), [P12_APPROVAL_ACCEPTANCE](P12_APPROVAL_ACCEPTANCE.md), [P12_ATTACH_WORK_INTEGRATION](P12_ATTACH_WORK_INTEGRATION.md) |
| F08 — Persistent causal roots, deadlines and atomic budgets survive restart | [RuntimeCausalityService](../../src/okto_nexus/application/runtime_causality.py) | [P10_CAUSAL_ADMISSION](P10_CAUSAL_ADMISSION.md), [P10_PROCESS_RESTART](P10_PROCESS_RESTART.md), [P10_MATRIX_COMPLETION](P10_MATRIX_COMPLETION.md) |
| F09 — Trusted adapter registry and verified capabilities permit a fifth adapter | [AdapterRegistry](../../src/okto_nexus/application/adapter_registry.py) | [P02_ADDITIONAL_ADAPTER_COMPOSITION](P02_ADDITIONAL_ADAPTER_COMPOSITION.md), [P02_EFFECTIVE_CAPABILITIES](P02_EFFECTIVE_CAPABILITIES.md), [P12_MIRROR_OBSERVATION](P12_MIRROR_OBSERVATION.md) |
| F10 — Explicit feature gating and shared declared boot/owner composition | [register](../../src/okto_nexus/adapters/inbound/mcp/tools/harness.py) | [P12_BINDING_AND_DISABLED](P12_BINDING_AND_DISABLED.md), [P12_COMPOSITION_A6A18B4](P12_COMPOSITION_A6A18B4.md), [P12_MIGRATION_ROLLOUT_INTEGRATION](P12_MIGRATION_ROLLOUT_INTEGRATION.md) |
| F11 — Bounded lifecycle, exact process birth identity, observed stop and no ambiguous replay | [RuntimeLifecycle](../../src/okto_nexus/application/runtime_lifecycle.py) | [P12_BIRTH_AND_PROCESS_IDENTITY](P12_BIRTH_AND_PROCESS_IDENTITY.md), [P12_SIGNAL_DRAIN](P12_SIGNAL_DRAIN.md), [P12_SETTLE_AND_DETACH](P12_SETTLE_AND_DETACH.md), [P12_RECOVERY_PRESSURE](P12_RECOVERY_PRESSURE.md) |
| F12 — Canonical workspace/session presence is per binding | [RuntimeOpenService.open](../../src/okto_nexus/application/runtime_open.py) | [P12_BINDING_ACCEPTANCE](P12_BINDING_ACCEPTANCE.md), [P12_BINDING_AND_DISABLED](P12_BINDING_AND_DISABLED.md), [P12_AUDIENCE_PRIVACY](P12_AUDIENCE_PRIVACY.md) |
| F13 — Approved profiles, explicit environment and streaming secret redaction | [EndpointService.validate_profile](../../src/okto_nexus/application/endpoints.py) | [P03_BACKEND_SECRET_REDACTION](P03_BACKEND_SECRET_REDACTION.md), [P12_PAYLOAD_BOUNDARIES](P12_PAYLOAD_BOUNDARIES.md), [P12_WORK_ACCEPTANCE](P12_WORK_ACCEPTANCE.md), [P12_IO_BOUNDARIES](P12_IO_BOUNDARIES.md) |
| F14 — Replay retains durable identity and cursor; operation facts are separate | [RuntimeControlService.replay](../../src/okto_nexus/application/runtime_control.py) | [P12_REPLAY_ACCEPTANCE](P12_REPLAY_ACCEPTANCE.md), [P12_OPERATION_EVENTS](P12_OPERATION_EVENTS.md), [P12_ATTACH_WORK_INTEGRATION](P12_ATTACH_WORK_INTEGRATION.md) |
| F15 — Target discriminator normalization precedes authorization | [message_action_for](../../src/okto_nexus/application/governance.py) | [P10_NOTIFICATION_TARGETS](P10_NOTIFICATION_TARGETS.md), [P10_MATRIX_COMPLETION](P10_MATRIX_COMPLETION.md) |

The machine-readable [audit index](evidence/p12-final-audit-39c5e6c.json) retains all129 original IDs and their direct evidence references; every referenced repository path was checked. Finding-to-group mappings express coverage scope and do not turn every group member into a new current-source PASS. The final per-node full-suite manifests must be joined separately.

Native Codex/Claude results remain scoped to752cd72 and installed versions documented in P12_NATIVE_FRAMES.md. Pi native is NOT_RUN by user decision; dedicated native attach is NOT_RUN without an approved session. T-E2E-01 cannot be claimed from separate two-provider campaigns. T-E2E-07 remains pending until this report is finalized.

Read-only GitHub recheck on2026-09-24: PR34 OPEN, head d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397, base27b06fe48b9f95b35c94f50827fea83d178f4e12. No post-review source changes, PR comment or merge.

Release preparation uses a git archive of39c5e6c under a fresh D directory. npm ci, TypeScript/Vite build to a private output directory and uv lock --check passed. The three pre-existing modified generated assets and private guardrail directory are excluded from packaging. Vite reports a chunk over500kB; that warning is retained, not treated as a failed compilation. Packaging and installation results will be recorded separately.

Full-repository Ruff found7 errors in the historical diagnostic p11_writer_mode_probe.py (a leading plus and import placement). Changed production/test files passed Ruff. Preserve the historical reproduction before repairing its runnable copy; do not silently claim the full lint gate passed.

The obsolete diagnostic has now been archived as .py.txt with byte-identical SHA256 2844bffcddc261f5054acaea8f5d794c288a557844f9aeed079db4af8e033f9f. Its old command remains explicitly historical. No production/test file was changed during the running suite.

## Complete requirement catalogue, awaiting final execution join

At8072207, all129 original IDs now have an explicit verification route in
[evidence/p12-final-node-catalogue.json](evidence/p12-final-node-catalogue.json).
122 rows have explicit test-node mappings; seven require separately recorded
native/stress/performance/report evidence. This classification is not a count of
passed requirements. Native/UI opt-in nodes inside the122 also need their own
campaign results; default-suite skips do not qualify them.

105 node mappings come from existing explicit scoped review catalogues. The
[17-row supplement](evidence/p12-final-coverage-supplement.json) joins previously
scattered mappings after source-assertion review, retaining exact platform scope
for external-work sockets and browser tests. All listed functions exist in the
current source;93 source-file hashes are recorded. Existence/hash checking is an
integrity check, not behavioral proof. Historical partial coverage classifications
are retained and must not become complete merely because a node passed.

T-API-01 explicitly includes the failed ordinary grouped-receipt node from the
current Windows regression. The five-file correction will change some recorded
hashes at integration and must be reflected in the final join. No requirement,
phase or task is promoted by this catalogue. Current Windows full result and
Linux running status are recorded in P12_FULL_REGRESSION_39C5E6C.md.

## Current-source join preparation at336357a

The current implementation isff905c4. Final Codex7/Claude stream6 native cases
passed at that source; the corrected package is built and validated. Full Windows
and Linux runs remain active. Earlier pending descriptions above are historical.

The final assertion-route audit found three omissions in the older catalogue:
T-LIFE-03 still referenced only pre-joint-stimulus signal tests, T-LIFE-11 lacked
the real fragmented/full-pipe case, and T-MIG-04 lacked the nonempty interrupted
backfill case. These tests already exist and passed their recorded scoped gates;
no production/test change was needed. Their actual assertions were read again.
The current [release catalogue](evidence/p12-release-node-catalogue.json) retains
the old partial mappings and adds the missing joint stimuli, with94 exact Git
blob hashes atff905c4. It also explicitly links the integrated receipt correction.

`join_release_evidence.py` keeps original source identities, requires an explicit
reviewed equivalence basis and manifest hashes, rejects nonterminal/failed
campaigns, and retains platform skips while matching every observed parameter.
A failing platform cannot be hidden by another passing platform. Native calls
require passing setup/call/teardown. The generated join is explicitly execution
evidence only; it cannot itself promote behavioral acceptance or backlog status.
Ten integrity cases passed on Windows and Linux. The complete final release join
will be generated only after both full regression processes terminate.

The previous accumulated status was archived verbatim in
IMPLEMENTATION_HISTORY_TO_336357A.md; IMPLEMENTATION_STATUS.md now contains only
the current resume instructions and links to history. No run was restarted.
