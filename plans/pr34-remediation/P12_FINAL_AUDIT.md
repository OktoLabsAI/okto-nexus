# Final scoped delivery — Nexus0.2.0 / PR34 remediation

The implementation and the user-authorized campaign are complete on
`feature/v0.2.0`. Local Nexus0.2.0 is installed and verified. The generated
[release report](evidence/p12-release-report.json) records **127 scoped PASS and
2 NOT_RUN** across all129 original requirements. All15 findings have code and
evidence links below. No merge, tag, publication or personal database migration
was performed.

**The unrestricted four-native-connector gate is NOT PASSED.** Pi native was
explicitly excluded by the user, and no dedicated Claude attach session was
approved. T-E2E-01 (three native providers concurrently) and T-E2E-02 (dedicated
native attach) remain NOT_RUN. Separate Codex/Claude campaigns do not satisfy the
three-provider stimulus. Fixture support is never labeled native qualification.

## Implementation and source identity

Runtime/test source is `ff905c433e1a92ae35993b2189919f75ad07dd51`. Later milestones
change only plan instruments, evidence and documentation. The final benchmark
uses7560970 with an explicitly empty src/tests/scripts/frontend/config/lock diff
fromff905c4. PR34 remains OPEN atd7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397,
base27b06fe48b9f95b35c94f50827fea83d178f4e12; no later PR source was overwritten.

The integrated model retains one canonical agent identity with authorized
endpoints and runtime bindings. Shared REST/MCP/internal use cases enforce actor,
workspace, grants and epochs. Inbox remains the logical delivery; transactional
transport attempts, durable journal/projection and canonical claims preserve
single execution, explicit uncertainty and handoff verification. All four native
adapters remain. An additional processless/context fixture proves registry
extension without adding a full A2A server or external orchestrator.

Schema064 is shipped:35 additive remediation migrations030–064 after the
preserved029 baseline. Upgrade, interrupted populated backfill, writer fencing,
retention, offline combined backup/restore and safe disable/cutover are qualified
in the linked migration evidence. Recovery never blindly replays an uncertain
operation. Operational rollback retains schema/deduplication and reconciles;
older writers are not assumed compatible.

## Final validation

| Campaign | Actual result and scope |
|---|---|
| Full Windows |2637 PASS,121 SKIP, exit0; Python3.13.1;2897.91s |
| Full Linux |2714 PASS,44 SKIP, exit0; Python3.13.12;2725.21s;2 passing subtests |
| Installed Codex0.156.1 |7 PASS, real approved local profile;1631 classified frames; observed gpt-6-astra/openai |
| Installed Claude stream2.1.281 |6 PASS, real approved local profile;256 classified frames; model not observed |
| Dashboard |15 PASS, isolated sandboxed Edge153.0.4234.48; Linux browser NOT_RUN |
| Package/local installation |Lock, temporary frontend build, wheel/sdist and Twine PASS;267 installed package files byte-match corrected wheel;69 other dependencies preserved |
| Installed integration |Actual installed MCP smoke and feature-ON authenticated HTTP/durable-result synthetic-peer smoke PASS |
| Final performance |Sequential Windows/Linux original/current comparison;120 measured turns/revision/platform, no dropped samples; measured higher latency published |

These rows overlap and are not added into a new total. Native/UI opt-ins were
OFF in default full suites; their skips remain skips and have separate evidence.
Both full suites retain a Starlette/httpx deprecation and a deliberate Pi
fault-injection thread warning. Earlier failing full suites, reproduction REDs,
preparation failures and storage failures remain historical evidence.

Windows ran a frozen five-file candidate based on39c5e6c. Its original base/diff
is retained:543 tracked files matchff905c4 with12 exact byte matches and531
explicit CRLF-only UTF-8 differences. No other difference; post-terminal rehash
found zero mutations. This is not a fabricated committed source identity or an
all-file raw-byte claim. Linux ran a clean exactff905c4 checkout and remained
clean after exit. See [source qualification](P12_CORRECTED_RELEASE.md),
[Windows manifest](evidence/p12-full-corrected-windows.json),
[Linux manifest](evidence/p12-full-corrected-linux.json).

[Native evidence](P12_NATIVE_FRAMES.md) records zero outbound native status queries,
no unclassified outbound frames/overflow and observed owned cleanup. Compatible
protocol request types are broader than the actual tested cases. Codex uses the
approved read-only/on-request profile; Claude retains default permission controls,
which is not an OS-sandbox claim. Fresh copied credentials were removed.

[Installed release](P12_LOCAL_INSTALLATION.md) used the explicit corrected wheel,
existing Python/serve extra and offline pinned dependency resolution. Fresh test
homes and allowlisted environments excluded personal stores and provider defaults.
[Final performance](P12_FINAL_PERFORMANCE.md) publishes higher synthetic latency
without weakening policy/fsync or claiming a universal SLO. The separate
[operational probe](P12_OPERATIONAL_METRICS.md) records durability/dispatch/event
boundaries and bounded aggregate resource/state observations.

The prior measured kill/recovery-under-load campaigns retain their original
bf5636c/af53f82 source identities and limits in P12_CRASH_PRESSURE.md and
P12_RECOVERY_PRESSURE.md. They were not rerun or relabeled asff905c4 load cycles;
the final full suites reexecute the shared crash/recovery scenarios. Historical
cycle counts are not added to current full-suite or benchmark totals.

## Findings to implementation and evidence

| Finding | Code | Behavioral evidence |
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

The finding-group associations are coverage scope, not independent native claims.
Every original requirement has a route in the
[release catalogue](evidence/p12-release-node-catalogue.json),94 exact Git-blob
test hashes and retained historical partial classifications. The
[execution join](evidence/p12-release-execution-join.json) records every matching
parameter/platform observation for122 node-based routes; all pass within their
recorded scope. Seven campaign/report routes are separately assessed. The final
report joins these with the prior behavioral acceptance review, rather than
promoting requirements just because a function exists or a component test passes.

Three stale catalogue omissions were corrected without changing product code:
the actual active-turn/pending-journal shutdown case, real fragmented/full pipes,
and populated interrupted migration backfill. The inherited Windows route for a
POSIX-only attach socket was moved to its actual Linux scope; the Windows SKIP
remains in the full manifest. Ten join-integrity tests pass on both platforms. The final combined evidence-tool,
join and metric-probe selection also passed29 tests on each platform; exact
commands/hashes are in evidence/p12-final-evidence-integrity.json.

## Report reproduction and preparation outcomes

```text
rtk proxy python -X utf8 plans/pr34-remediation/join_release_evidence.py plans/pr34-remediation/evidence/p12-release-join-recipe.json plans/pr34-remediation/evidence/p12-release-execution-join.json
rtk proxy python -X utf8 plans/pr34-remediation/build_release_report.py plans/pr34-remediation/evidence/p12-release-execution-join.json plans/pr34-remediation/evidence/p12-release-separate-assessments.json plans/pr34-remediation/evidence/p12-release-report.json
```

Both final commands exit0. Report generation first rejected an optional missing
historical notes field and then a test-node reference treated as a file path.
The reader was corrected to preserve optional notes and validate the file portion
of an already joined test node. These were plan-only report preparation failures,
not hidden product-test failures. Final generation verifies129 unique IDs, source
and evidence hashes, terminal suites, original candidate provenance, native and
installed source identity, reference paths and all15 finding code blobs. The
report is read back and its derived counts checked.

## Readiness and remaining external qualification

[Backlog](../../05_BACKLOG.json) now distinguishes implementation from missing
external qualification.60 tasks are VERIFIED in the recorded scope; P07-T02,
P07-T06 and P12-T02 remain IMPLEMENTED only because Pi/dedicated attach native
qualification is unavailable. P07/P12 retain IMPLEMENTED phase status; other
phases are VERIFIED. No remaining code work is inferred from those native limits.
Individual tasks retain their implementation references, hashes, historical
commands/results and final review in
[evidence/p12-release-task-review.json](evidence/p12-release-task-review.json).

Ready for local testing and review in the authorized scope. The unrestricted
four-native gate remains open; a future approved campaign must create fresh
isolated Pi/backend and dedicated attach sessions, then run the missing cases.
Do not reuse old LAN endpoints, interactive sessions, credentials, stores or real
sends automatically. No automatic merge is authorized or performed.

The three pre-existing modified generated static assets and private
`.nexus-policy-guardrail-test/` remain untouched and uncommitted. Raw logs/XML and
release artifacts stay in task-private directories; committed manifests exclude
captured credentials/payloads. The
[earlier audit](P12_FINAL_AUDIT_HISTORY_TO_7560970.md) preserves superseded pending
states; [current status](IMPLEMENTATION_STATUS.md) is the resume entry point.
