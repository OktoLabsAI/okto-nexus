# Nexus 0.2.2 — migration of runtime regressions

The release remains gated on the complete installed suite. This document does
not declare the historical suite equivalent to the current suite or authorize
skipping failing cases.

The previous HTTP fixture created native profiles and endpoints through removed
setup APIs before every test. The fixture now starts an authenticated, isolated
server without those resources. Tests of retained services can run directly;
execution tests must prepare an approved R4 realization and binding.

## Completed contract changes

- Scoped `nxsconn_` issuance/redemption tests are retired because those endpoints
  were removed. Original agent credentials, refusal of retained scoped keys,
  concurrent session admission and authority changes remain tested in R4.
- PR34 profile preservation, REST/MCP foreign-session authorization, event replay,
  single delivery ownership and lost commit notifications use current R4 tests.
- Configured identity is preserved across open/close. Authenticated requests may
  update `last_seen_at`; this is presence, not a profile mutation.
- Retained MCP method denials still fence an already authenticated HTTP client.
  Execution policy revision conflicts use the current execution-policy API.
- Artifact filesystem transactions, permission revalidation and fsync tests no
  longer require a legacy connection. Large-output approval/rejection and
  publication rollback now run through Core and the canonical result pipeline.
  The retry fixture shortens the configured recovery period before the fault;
  recovery after the fault receives no explicit wake or user action.
- Additive identity migration assertions preserve all old columns and verify the
  new deletion marker. The trace migration fixture includes migrations >=100.
- The bounded pressure worker is retained under `tests/`, independent of the
  deleted historical campaign script.
- Two ordinary authenticated R4 agents exchange results with persistent depth
  and execution budgets. Failed/interrupted turns publish their captured output
  without admitting a relay. The initiating actor remains unchanged.
- Concurrent intents exhaust a one-action grant at dispatch: exactly one native
  turn, a durable permission denial for the other, and close remains available.
  REST and MCP refuse revoked, expired, credential-changed, permission-changed
  profile-changed and configuration-changed authority before native dispatch.
- Enabling canonical execution preserves historical unread inbox records.
  Only a newly received message creates execution; repeated and historical
  post-commit notifications cannot create additional native work.

`tests/runtime_contract_retirements.json` records the exact removed functions,
source revision, source digests, reasons and executable replacement references.
`test_runtime_contract_inventory.py` checks those references. This is a structural
guard; behavioral adequacy still requires review and successful execution.

## Remaining release gate

Local focused verification: 25 passed for migrated authorization, identity,
durable delivery, artifacts, migration and pressure cases; four additional relay
cases passed. A separate diagnostic of the old fixture consumers found 60 passes,
679 failures, 20 platform/UI skips and two setup errors after removing obsolete
fixture provisioning. These scopes overlap and must not be added. The diagnostic
is an inventory, not a successful release campaign. No blanket skip/xfail or
collection exclusion was added.

Additional combined verification: 23 cases passed for seven grant regressions
(including a deterministic simultaneous admission barrier), 15 contract
migration cases (including retained inbox activation), and the retirement
inventory check. A separate artifact recheck passed four behavioral cases and
the inventory check. These scopes overlap; they are incremental checks, not
completion of the release gate.

Further migration found and corrected exhausted-grant idempotency: the public
REST/MCP command bridge no longer requires unused budget to recover a recorded
intent. Current credentials, grant revocation, policy and configuration are
still checked; atomic dispatch remains the sole budget consumption boundary.
The before-fix REST and MCP regressions both failed with PERMISSION_DENIED;
after the correction all 13 grant/concurrency checks passed, including a revoked
grant that cannot recover its old reply. The relay campaign now has ten passing
cases (self-output refusal, concurrent republication, source revocation,
interleaved roots, approval/rejection and original budgets/outcomes). Seven
retained admin validation/redaction cases also passed. Canonical boot, settings,
binding replacement and command coverage passed 55 cases. Counts overlap the
previous campaigns and do not constitute the complete installed suite.

Review the remaining historical execution scenarios by contract, migrate missing
R4 behaviors, retain service/history tests, then run the complete installed matrix.
Do not merge PR #49 or create v0.2.2 until that gate passes. Harness support is not
being retired: Core still provides Pi, Codex, Claude stream and Claude attach.

The exhausted-grant campaign also passed all 13 cases against the installed
wheel outside the checkout with unchanged campaign inputs. Qualification,
inventory, realization and dispatch contract checks passed 69 cases. Historical
journal tests now seed retained sessions directly, preserving their original
filesystem, transaction, replay and authorization assertions without opening a
removed native owner: journal 12 passed, public replay 6 passed, retention 7 passed.

Canonical publication migration retains all nine governed-publication cases,
including guardrails, approval rejection, source/audience tampering and strict
mode. Four artifact-maintenance cases preserve generation-safe cleanup,
lost-response reconciliation and quota recovery while asserting one native
effect. Eight causal cases cover simultaneous children, immutable root limits,
deadlines, retention and authenticated parent lineage. Eight snapshot cases
combine canonical Core output/private artifacts with a retained legacy journal;
corruption and semantic watermark checks remain. Each focused source campaign
passed; these results still do not replace the complete installed release gate.

The publication/artifact/causal/snapshot campaign passed 29 cases against the
installed wheel outside the checkout, with no changed inputs. Further source
campaigns passed self-connection discovery (10), handoff admission (12),
immutable commands (6), canonical target grammar (5) and payload validation (2).
A nonempty private-history regression exposed an existence leak across the mixed
legacy/canonical compatibility views. The bridge now returns uniform denials for
foreign/missing resources while native R4 keeps its scoped NOT_FOUND contract;
five private-history/event-view cases passed. Fifteen shutdown cases passed,
including a Core native open that returns after the shutdown deadline and is
contained before releasing ownership. These are incremental, overlapping checks;
the complete installed matrix remains a required release gate.

The installed handoff/shutdown campaign passed 68 cases and exposed one test
ordering race: terminal receipt persistence can precede result projection. The
private-history test now waits for its actual positive result via the public API.
A follow-up installed campaign passed all four private-history/monitor cases
with unchanged inputs. Additional source checks passed six payload-boundary
cases, seven cached-control/private-history cases, ten binding discovery cases
and the real TCP/MCP connection/history scenario. Fourteen fanout cases now use
three approved Core bindings, including bounded children, retained decisions,
transaction rollback with automatic recovery, origin governance and explicit
artifact readers. Eight retained-factory refusal cases and two result-schema
migration cases keep their original assertions using retained records instead
of removed setup APIs. No full matrix success is claimed by these focused runs.

The combined payload/privacy/control/discovery/monitor/fanout and retained-history
campaign passed 52 installed-wheel cases, with unchanged inputs. Boot migration
adds independent failed/hung native starts, pre-admission consent revalidation,
open-only endpoint authority, bounded admission and refusal of attach-PID boot.
An uncertain boot remains the same single operation after server restart. All
12 source boot cases passed. Six current-settings cases preserve concurrent CAS,
omitted config, grant/boot invalidation, transactional rollback and refusal to
edit a live launch. Retained endpoint reconciliation remains tested through REST
and MCP and cannot restore the removed Server native factories.

The boot/configuration/retained-reconciliation campaign passed all 34 installed
cases with unchanged inputs. Three real Core adapter pipe cases passed (Pi,
Codex, Claude stream): fragmented UTF-8, stdout pressure, 2 MiB of stderr, two
durable results and confirmed process close. Core protocol faults retain bounded
evidence and reap the child. A real Codex stale-control case exposed unnecessary
agent containment after a durable pre-write refusal. Embedded dispatch now
publishes a matching FAILED/no-effect Core receipt without closing the healthy
session; missing or inconsistent proof still triggers recovery. The corrected
real-native control case and five positive/negative proof cases passed. Four
command admission/interrupt/atomic enqueue cases and four existing open-drift
cases passed separately. These overlapping focused checks do not satisfy the
complete installed release matrix.

The native-command/protocol/pipe campaign passed all 39 installed cases with
unchanged inputs. Canonical correlation adds real Codex bounded large output,
atomic rollback recovery and consumption of two logical deliveries (four source
cases passed). Historical session recovery retains two tests with seeded records;
canonical open reservation passed its durable-before-effect and replay assertions.
Audience migration exposed a missing post-commit publication notification: local
events/receipts and remote event/receipt ingress now wake the dispatcher after
commit. With the recovery interval left long, all three audience cases passed.
The local dispatch/publication campaign passed 35 cases, and event/receipt/public
remote bootstrap passed 20. A paused publication scan also preserves the native
commit wake; the receipt route observes committed state from a separate connection.
These incremental checks do not replace the required complete installed matrix.

The real Codex foreign-terminal case also exposed a host recovery gap. Core
correctly fences an ambiguous event stream, but Nexus did not start scoped
containment from its durable stream-loss fact. The host now checks that fact
across acknowledged pages. Reconciliation also settles only ACCEPTED/PENDING
operations with zero transport attempts and no receipt/local publication on a
proved closed session, avoiding an impossible wait for an executor receipt.
The real-peer regression passed: owned process stopped, subject READY again,
no result invented or old message replayed, and new authorized work succeeds.
The existing agent-isolation and native-protocol campaign passed 17 cases.

The stream-recovery/correlation/audience/queue/reconciliation campaign passed all
57 installed-wheel cases with unchanged inputs. Eight further source cases
preserve message-event rollback, push/pull exclusivity, unverified internal
senders, changed permissions, SQLite writer independence, cross-transport open
replay/concurrency and real SQLite capacity refusal/recovery.

The delivery-boundaries campaign passed nine installed cases with unchanged
inputs. A three-agent Core competition passed private winner/loser assertions.
Managed work tests now retain explicit completion after native output and lease
expiry, strict REST/MCP credentials, and revoked/reworked late output. They
exposed a compatibility inspection defect: canonical deliveries incorrectly
reported no session, no native acceptance and no durable result. Inspection now
uses the canonical session/acceptance and waits for materialized terminal output.
Three lifecycle cases, the strict-before-registration case and eight scoped
history/control/competition cases passed.

The work-inspection installed campaign passed 25 cases with unchanged inputs.
The broader local R4 installed campaign was interrupted to correct a newly
reproduced publication race; its nonzero exit is not an acceptance result.
Structured work can arrive between the handoff scan and the conversation scan.
The conversation publisher previously marked that pending result BLOCKED before
the handoff projector processed or retried its admitted completion contract.
Conversation scanning now leaves structured results pending until their work
outcome exists. The deterministic before-fix regression failed; all 16 native
structured-result cases passed after correction, with three additional grant,
read-snapshot and cross-transport claim cases passing separately.

Eight authority cases preserve endpoint policy revalidation while honoring the
documented operator-only represented R4 identity. Two real Codex capture cases
passed with Server projection paused, including delayed durable Core storage,
256 backpressured deltas, exact reconstructed output and confirmed process close.
These are focused checks; the complete installed release matrix is still required.

The structured-work/capture/grants/operator installed-wheel campaign passed all
66 cases with unchanged inputs (`build/release-structured-grants-installed`).
The isolated source artifact-boundary follow-up passed three cases: private
readers, quota refusal before filesystem effects, and publication-worker shutdown
ownership with an independently advancing heartbeat. These additional cases are
not part of the 66-case installed acceptance scope.

Actual Core Codex permission tests cover command/file approval, cancel-only
decisions without policy amendments, exact replay, lost native acknowledgement,
expired/revoked authority, stale turns and retained requests after server restart.
Fault injection found two gaps. Native decision dispatch did not recheck a HITL
flag disabled after lease issuance; it now refuses before effect. A failed Server
event transaction was treated as a failed Core stream and contained healthy work;
only persistence errors at that commit boundary now defer publication, retaining
the native lease and retrying the unacknowledged batch. Core journal/stream faults
still enter scoped recovery. The deterministic projection test observes repeated
rollbacks, an ACTIVE/READY session and no partial request, then removes the storage
fault and observes one native response without restart or manual retry.

The native permission/artifact/isolation/correlation campaign passed all 47
installed-wheel cases with unchanged inputs (`build/release-native-recovery-installed`).
The independent decision/ingress/recipient/managed-authority campaign passed 58
installed-wheel cases with unchanged inputs (`build/release-native-authority-installed`).
Containment regressions now inject unreadable Core history after an event is
durable; transient Server commit failures separately verify automatic publication
retry while keeping the healthy native session alive. Four focused containment
cases also passed against source. The complete installed release matrix remains
required: a current diagnostic of historical configuration and operation-recovery
tests still fails 21 cases at obsolete setup, while two retained migrations pass.

The first completed full Linux/Python 3.11 run at f0ffd67 reported 3347 passed,
439 failed and 108 skipped in 5467 seconds (run 37625316285). This is a failed
release gate, not an acceptance result. One failure was in the current R4
Connector roundtrip: post-commit receipt wake assumed the optional dispatcher
attribute had been initialized. Receipt/event wake now tolerates its absence.
The roundtrip and three canonical recovery checks passed against source.

Real Core question/form input checks passed 15 source cases, including invalid
values, exact replies, transaction rollback and stale authority. Eight manual
conversation-recovery cases passed, followed by 15 handoff-recovery cases and
two retained-home/retired-stdio cases in focused source runs. The first combined
input/recovery installed campaign had 41 passes and one test race: it fetched a
recovery snapshot after the close receipt but before asynchronous domain release.
The test now waits for that real release before submitting its exact snapshot.
The corrected installed campaigns must finish before these changes are accepted.

The corrected input/conversation-recovery campaign passed all 42 installed-wheel
cases, and the handoff/restart/remote-receipt/event campaign passed all 37 cases.
Both reports contain unchanged inputs (`build/release-input-recovery-fixed-installed`
and `build/release-handoff-remote-recovery-installed`). These overlapping focused
checks do not replace the complete installed release gate. Linux/Python 3.13 on
the earlier f0ffd67 revision also exposed a live receipt observation race during
a proved pre-write opening refusal; a deterministic reproduction currently fails
and remains to be corrected before acceptance.

The live provisional-receipt race now has a deterministic before/after test.
Active producers own their unsettled Core journal facts until they finish;
background recovery no longer publishes an intermediate crash fence over a
proved no-effect refusal. Transient Server receipt-commit errors now defer
publication without containing the native session or replaying its operation.
All 51 installed receipt/isolation/command/correlation/native-approval cases
passed with unchanged inputs (build/release-receipt-recovery-installed).

The complete f0ffd67 baseline matrix (run 37625316285) finished unsuccessfully:
Linux 3.11: 3347 passed, 439 failed, 108 skipped; Linux 3.12/3.13: 3345 passed,
441 failed, 108 skipped each. Windows jobs reached the 120-minute limit before
completion. These are baseline diagnostics, not current-head acceptance.
Windows additionally exposed remote fixture event-loop blocking and a handoff
fixture admitting a conversational creation notification before managed work.
Their validation is pending. No full-suite approval, merge or release tag follows
from the focused passing campaigns.

The remote and handoff fixture follow-up passed all 25 installed-wheel cases
with unchanged inputs (build/release-windows-fixture-installed). Remote REST
requests now run outside the asynchronous WebSocket/lease-renewal loop. The
handoff fixture enables conversation only after its creation notification and
asserts that emitted output belongs to the managed operation being tested.
The more recent Linux 3.11 diagnostic at 929bb87 (run 37632532345) still reports
3376 passed, 407 failed and 108 skipped. It predates the latest local fixes and
is not current-head acceptance; the complete release gate remains open.

The pending-capacity/MCP/writer follow-up passed 44 installed-wheel cases with
unchanged inputs (build/release-capacity-mcp-installed). A regression exposed
that pending cancellation released the logical inbox while retaining canonical
admission capacity until the next dispatch scan. Cancellation now resolves only
proved unsent mapped operations in the same transaction as the audit and inbox
release, without inventing an executor receipt. In-flight cancellation remains
refused. Coverage includes competing admissions, legacy SQL writer fences,
byte capacity, managed-claim rollback, REST/MCP lifecycle and recovery.

CI now runs four exhaustive file partitions for each OS/Python combination.
Partition checks prove every test file occurs exactly once; no test selection,
skip or xfail removes failures. Feature branches use the PR campaign instead of
also starting an identical push campaign. This addresses Windows job timeouts;
it does not make the outstanding full regression gate pass.

The follow-up passed 42 installed-wheel cases with unchanged inputs
(build/release-replay-cancel-installed). A deterministic reserved-before-cancel
test now proves cancellation cannot close the healthy dispatch connection and
that a subsequent opening succeeds. The exact cancelled reservation is an
idempotent pre-send refusal; other stale reservations still conflict. Canonical
event replay checks session authority before validating its cursor, preserving
the REST/MCP foreign-session denial contract. New regressions cover concurrent
event append, acknowledged Core compaction, all four logical write rollback
boundaries, dropped commit wakes, and isolated MCP client processes.

Retained legacy public replay tests remain in place, separately from the new
canonical replay checks. All seven retained replay/inventory cases passed in
the installed wheel (build/release-retained-replay-installed); twenty retained
journal/admin cases also passed against source. No historical native owner is
opened by those fixtures. The complete matrix is still pending.

The dispatch/workspace follow-up passed 68 installed-wheel cases with unchanged
inputs (build/release-fairness-workspace-installed-v2). A blocked opening now
reserves at most one productive worker per agent, leaving capacity for healthy
peers. First-use project handoffs register the workspace in the same transaction
as the handoff and notifications; an injected post-insert failure rolls back
all records. The broader source handoff/governance suite passed 175 cases.
Restart replay tests now observe the actual failed publication without requiring
a transient Server write failure to contain the native agent. Five installed
first-cause isolation tests also passed after initializing the current owner
fixture (build/release-failure-fixture-installed).

Claude stream permission tests exposed a real Core 0.0.3 output normalization
gap: a result-only response reaches the terminal event but loses its text.
An isolated Core correction is under test; the published Core is unchanged.
The late-cancellation close test passed with the documented 30-second drain
and 15-second interrupt budget. Full-suite acceptance remains outstanding.

The 2026-10-07 merge review validated 175 installed-wheel cases with one
pre-existing skip and unchanged inputs (build/review-merge-installed). This
includes local/remote MCP availability, discovery permissions, Graph presence,
tool-description size, canonical delivery/retry and the embedded lifecycle.
Core 0.0.4 and Connector 0.0.3 are now published; this campaign uses those
installed dependencies rather than the earlier Core 0.0.3 checkpoint above.

The review found and corrected two runtime defects: a direct turn could bypass
a conversation waiting for a safe retry on the same session, and lease renewal
could replace the Core context while close/interrupt persisted its pre-effect
binding, causing STALE_GENERATION and unnecessary agent recovery. Retry ordering
now includes direct turns. Local lease-context replacement waits for active
controls, while controls remain concurrent and bypass blocked productive calls.
Deterministic tests reproduce both renewal races with the former control gate;
the corrected installed package passes both and concurrent close admission.
The remote Connector already handles compatible pre-effect context changes and
required no modification in this review.

Nine legacy safe-retry test functions (eleven parameterized cases) were retired
only after validating their canonical replacements. The manifest records each
source hash and replacement. Coverage includes bounded exhaustion and pull
release, cancellation, authority changes, preserved deadlines after ownership
change, missing proof commits, same-session ordering and independent sessions.

The full release gate remains open. Current-head CI at f042dd1 failed; four
completed shard artifacts contain 207 distinct failing cases before these
review corrections, and the complete matrix was still running when inspected.
Other legacy connection, historical work, protocol, fallback and recovery tests
still require individual review. The focused campaign is not full-suite
acceptance and does not authorize declaring the release ready for merge.

The live Meta-harness incident exposed a reset omission: connection preservation
did not include execution_local_observations. With those rows absent, unchanged
approved executables lost their selected/version evidence, while automatic
observation recovery only considered changed fingerprints. Reset now preserves
the observations, and passive refresh rechecks approved locations when their
observation is missing even if the executable is unchanged. Probe failures still
block that installation and are retried on later refreshes; disabled bindings and
different paths are not automatically selected. The installed-wheel campaign
build/review-inventory-installed passed all 22 cases with unchanged inputs,
including reset/delivery, repeated observation recovery, transient probe failure,
and control/renewal concurrency. Read-only version checks on the affected host
confirmed Pi 0.87.1, Claude 2.1.292 and Codex 0.160.1 responded successfully.

The policy/protocol review passed 38 installed-wheel cases with unchanged inputs
(build/review-policy-protocol-installed-v2). Four legacy functions were replaced
by reviewed canonical cases for global/agent disable, unread inbox preservation,
pre-spawn authority changes, malformed Pi readiness and invalid Codex thread IDs.
The actual Core native factory and subprocess handshakes exposed missing Pi
close outcomes: a rejected startup discarded transport ownership and could be
classified OUTCOME_UNKNOWN despite successful cleanup. Core 0.0.5 retains the
transport and reports observed tree containment without inventing stop proof.
Nexus and Connector pin that patch; Connector 0.0.4 has no additional behavior
changes. The integrated cases prove the other binding of the same agent still
opens after protocol rejection. Complete matrix validation remains outstanding.

Relay review passed 29 installed-wheel cases with unchanged inputs in
build/review-relay-installed-v2, including real fragmented native pipes for all
three adapters. Four legacy functions now map to canonical tests for persistent
budgets, processing receipts without execution, failed/interrupted/unknown
outcomes, three-agent routing and distinct bindings of the same agent. Unknown
outcomes remain durable ingress evidence rather than invented terminal results.
Core 0.0.5 was promoted through PRs 27/28 to main and tagged v0.0.5; Nexus 0.2.2
still requires the full regression gate before promotion.

The next consumption review passed 38 installed-wheel cases with unchanged
inputs (build/release-consumption-installed). The four retired legacy functions
have explicit replacements for native terminal consumption, lost confirmation
without replay, refused-socket fallback across three bindings, and rejection of
executable mirror consumers on REST and MCP. The automatic receipt check waits
for the independent background reducer instead of acknowledging work in the test.

Public replay review reproduced a credential leak in native approval events:
the authenticated ingress retained the exact operational request as required,
but public history returned it alongside its scrubbed presentation. Replay now
verifies original event integrity and returns only the scrubbed request. Original
wire correlation and protected storage are unchanged. Real Codex and Claude
approve/deny cases cover both REST routes, MCP replay, approval list/detail,
subject/operator reads, rejected subject decisions, exact replies and process
closure. Fragmented native text remains scrubbed across repeated turns.
The installed campaign build/release-event-replay-installed passed all 38 cases
with unchanged inputs, combining this protection with consumption and identity
coverage; the source campaign passed 12 replay/redaction cases. Two legacy
redaction functions now reference these reviewed replacements. No runtime was
restarted or updated for this review.

The release gate remains open. CI run 37723682286 at 5f5d0e2 completed its first
Linux shard with 48 failures, 1075 passes and 17 skips, mostly using removed
legacy connection setup. The remaining matrix was cancelled after this failure
and the replay correction, so it is not a passing full-suite result. The other
historical contracts still need individual review before Nexus main/tag promotion.

Endpoint configuration review reproduced a canonical-ID lookup failure when
updating notification settings. The validator now resolves managed Core IDs to
their native descriptors, preserves binding aliases and separately controlled
settings, and rejects alias edits through this operation. The installed campaign
build/release-endpoint-installed passed 25 cases with unchanged inputs: all three
adapters, notification authorization and stale revisions, approved provider-home
isolation, configuration authority, and rejection of removed attach creation.
Two legacy notification functions map to current equivalents; two positive
attach-creation functions are retired according to the explicit removal decision.
This does not claim default Pi profile isolation or a passing full release gate.

Admission-race review passed 16 installed-wheel cases with unchanged inputs
(build/release-admission-installed). The current writer gate serializes a pull
before SQLite BEGIN IMMEDIATE at both sides of push reservation; three concurrent
approval decisions create one native turn; and two agents competing through three
bindings consume one work grant and create one executor. The winner's separate
runtime-open grant remains independently accounted. Three legacy functions now
reference these current behavioral replacements.

Core 0.0.6 and Connector 0.0.4 promotion matrices passed. Core PR 30 merged to main
at c2f66bbe042216749b6df231ba5b984727513ccc with remote tag v0.0.6; Connector PR 44
merged at 8a7b6a08b5849e69dfcd67fb85b6ea4620c3801f with remote tag v0.0.4. Nexus
already pins both corresponding artifacts. Nexus main/tag promotion remains
pending its own complete regression gate.

Identity and public-route review passed 59 installed-wheel cases with unchanged
inputs (build/release-context-installed). Native conversation/work envelopes for
all three managed adapters preserve the exact sender, subject, logical message,
public agent identity and approved profile without copying private metadata.
REST and MCP both open/send/close each managed adapter. Ambiguous implicit opens
have no effects, while an explicit choice succeeds. Five historical functions
now map to these cases and the existing per-call environment override denials.

The serve shutdown fixture now creates an approved canonical local binding and
uses Core's Pi adapter against a disposable real subprocess. Windows validation
passed seven installed-wheel tests with unchanged inputs
(build/release-shutdown-installed); the two existing POSIX signal cases remain
platform-skipped on Windows. Graceful exit, explicit session close and owner kill
all stop the exact witnessed child and grandchild. The tests retain their names
and process-identity assertions rather than replacing them with mocked shutdown.

Terminal projection review passed 51 installed-wheel cases with unchanged inputs
(build/release-terminal-installed). Atomic result projection rolls back on storage
failure, recovers captured bytes without reexecution, and releases the next delivery.
One historical storage-failure function maps to this current behavior. Two positive
external-attach relay functions are retired under the explicit attach removal;
their replacements cover creation denial and no invented results for unknown outcomes.
This does not retire or claim coverage for custom context-only observers.

Attempt and fallback review passed 67 installed-wheel cases with unchanged inputs
(build/release-attempt-installed, wheel SHA256
46156560cd1cbd45791acb4eb2bda66b3d0d8d50cb4b0c6cc626c2c0d00b345c).
Canonical admission now records the turn identity as the delivery attempt, and
retry admission preserves it so accepted receipt transitions remain in immutable
history. Approved fallback preserves the logical delivery and envelope across
both existing and on-demand target sessions. Scope exclusions, authority changes,
uncertain writes, work grants, receipt storage recovery, and offline restore
were exercised through current execution paths. Nine historical functions map
to these behavioral replacements; continuation and startup fallback remain open.

Retained-worker review reproduced premature capacity release after a native
receipt. The embedded owner now supplies its still-running operation identities
to reservation: live calls count toward item/byte and per-agent limits even
after receipt persistence, without counting a durable reservation twice.
Control lanes retain independent capacity. Source validation passed 26 worker,
dispatch-pump, and agent recovery cases (including Windows owner termination),
plus ten exact-capacity cases. Four legacy scheduler functions map to the current
worker and SQLite backlog tests. Installed-package validation remains pending.

Profile-switch review found that canonical Core IDs were incorrectly sent to
the legacy adapter registry. Boolean enable/disable updates now preserve the
approved profile configuration, retain CAS, and revoke its old grants. Tests
exercise automatic containment at the lease-renewal boundary with a short real
lease (not an immediate-stop claim). Compatibility controls now carry the
session's subject agent explicitly, allowing authorized operator close without
changing actor provenance or permitting foreign-agent access. Thirty related
source cases and all three shortened-lease containment cases passed. The CI
runner now emits test names without buffering and diagnostic stacks for long
tests, preserving the same complete regression selection and pass criteria.

Installed validation of both corrections passed 67 cases with unchanged inputs
(build/release-owner-installed, wheel SHA256
25ff95afce6ba7664d4090bc9b63230a84cb5b60a1ed223796721c4ec5241257).
This includes real Windows graceful/forced owner exit, independent recovery,
operator/subject provenance and foreign-actor rejection. Head 0288de5 is pushed;
complete CI run 37733739695 remains pending. The superseded c5d7747 campaign was
cancelled after preserving its completed job logs; it is not passing evidence.

Public operation-state review passed 51 installed-wheel cases with unchanged
inputs (build/release-states-installed-v2). REST and MCP distinguish queued
admission, uncertain wire submission, accepted receipt and captured completion.
The native Codex start event exposed a Core correlation defect: its derived
phase and active operation were not retained. Core 0.0.7 preserves both and
rejects foreign or idle start events. Its native bridge suite passed 44 cases.
Profile reenable retains CAS and requires a new grant; disabling a profile
after admission prevents the queued native write. Five historical functions
map to these state/configuration cases and the current I/O boundary case.

Final dependency validation caught and corrected the exported Core version and
Nexus inventory version constant. A rebuilt Nexus wheel then passed 19 installed
cases with unchanged inputs (build/release-final-core-integration-v2, Nexus
SHA256 546e8b17503c33041765c115d3bd490a699d5672dadae1351f24874a7f20e302,
Core SHA256 43e02485ce90e6dc58b69b761e0b013494e4526d4bf77716d6298064da904106,
Connector SHA256 38ad3909694ee83feb5cf9ef256bb3918ddd4902729cf6049eea8c3e98876832).
The I/O case witnesses provider secret resolution, native process creation,
native pipe writes and embedding TCP traffic outside a write transaction.
Core PR 32 (0.0.7) and Connector PR 45 (0.0.5) remain under CI/review; neither
is published by this evidence. Complete Nexus regression remains a release gate.

Shutdown review found a missing final publication boundary after native
containment. The owner now refreshes containment evidence, publishes retained
receipts/events, and proves session release before closing Core journals.
Unknown outcomes do not create terminal events or rewrite accepted receipts.
Superseded owners still contain their processes and leave publication to the
current owner. Storage failures retain journals and retry without native reopen.
The existing real-process signal test now uses the canonical Core journal and
a short configured shutdown budget. Windows source checks passed 18 shutdown
cases (three POSIX cases remain platform-skipped), 15 owner/recovery cases,
and the new final-publication failure/retry case.

The full 0288de5 CI stopped progressing in canonical boot teardown. Local
reproduction showed its synthetic factory was overwritten by server_runtime
after constructor injection, causing an attempt to launch the placeholder
candidate. Injecting at start preserves the boot behavior and all six boot
cases pass. Runs 37733739695 and 37737140833 were cancelled after preserving
failure/stack evidence; neither is passing evidence. Installed validation of
the shutdown and boot corrections remains pending.

Installed shutdown/boot validation passed 40 cases with three POSIX-only skips
on Windows and unchanged campaign inputs (build/release-shutdown-final-installed,
Nexus wheel SHA256 ade3d1461c4516b723778442dab64b0507baff40cda5cc3b4114900e2c2698b7).
This includes real graceful, forced and pre-binding owner termination, final
publication storage failure/retry, old-owner containment, and all six boot cases.
Core PR 32 and Connector PR 45 have merged to develop; their main promotions are
PRs 33 and 46. Core's macOS promotion rerun remains pending after two initial
failures; Connector's promotion checks passed. No new main tag is claimed here.

The no-write recovery review passed 12 source cases: REST/MCP exact-once release,
all six historical observation mutations, three corrupted Core proof variants,
and transactional rollback. Three historical functions now map to these paths.
Profile review passed 46 source cases plus an operator-revocation dispatch fence.
An operator can now stop an applied session after its profile/grant is revoked,
using the original lease identity solely for close/interrupt and rechecking the
current operator. Productive actions still require current consent. Late native
terminal output remains captured while publication is blocked. Four historical
profile functions map to these positive and negative canonical regressions.
Installed validation of this final recovery/containment group is pending.

Core PR 33 merged to main at a0d54c926830af46489bee83faf63f634d76a57b after
the macOS rerun and dependency SBOM passed. Tag v0.0.7 points to that main commit.
Connector PR 46 merged to main at bcb4ae5247116d192b8b808dcb19b11f8f5b3c3e
after its complete promotion campaign passed. Tag v0.0.5 points to that main
commit and depends on Core 0.0.7. Remote tag targets were verified directly.

Installed recovery/containment validation passed all 60 selected cases with
unchanged inputs (build/release-containment-final-installed). The complete
Nexus regression still has unresolved legacy behavior cases; this focused
campaign does not replace that release gate.

The real WebSocket Connector test exposed the corresponding containment gate
on revision-invalidated lanes. Current operator containment may now use a
disconnected productive lane only when its original ticket, channel, generation,
scope and expiry still validate; this does not permit lease renewal or a turn.
The remote five-action lifecycle and eight persisted transport-fence variants
passed, as did the ten bootstrap authority cases. Core/Connector code is unchanged.
The injected persistent receipt failure test now removes its SQLite trigger in
a finalizer before lifecycle teardown, preserving all live-failure assertions
and allowing final shutdown publication. Run 37740620039 was superseded and
cancelled; its Linux 3.12 shard exited 245 during a diagnostic dump in that test,
and Linux 3.11 shard 3 was waiting in fixture teardown. These are unresolved CI
evidence, not passing validation. The new installed campaign includes the entire
embedded dispatcher module to check its shutdown fault fixtures.

That campaign stopped at the historical-receipt restart fixture: its permanent
write fault now correctly prevents graceful publication from finishing. The
fixture explicitly cuts final publication to model its intended crash boundary,
then verifies replay without a provider. The missing-journal variant restores
its deliberately hidden evidence after proving the block and verifies recovery
without a second native open. Five source history/observer cases passed. The
event-restart fixture likewise freezes publication before shutdown and asserts
zero Server ingress before restart; all three active/inactive/archived variants
passed. Nine remaining resource-reconciliation cases passed separately.

One historical workspace-isolation function now maps to canonical public
broadcasts across two workspaces, exact envelopes, private prompt separation,
independent native close and later reopening of the still-connected binding.
That source case and the four existing identity cases passed. Installed package
validation of these combined changes remains pending. The legacy startup-error
redaction contract also remains pending: an exploratory untyped factory error
retains uncertain ownership and cannot use ordinary graceful fixture teardown;
that interrupted draft is not passing validation or a committed replacement.

The combined installed campaign passed all 50 cases with unchanged inputs
(build/release-remote-history-final-installed, wheel SHA256
1c8cc4e548684456b3dd8cd023878c14f1a6bf9317b5762ca2aa39cc6c96bd98).
Core's post-main campaign 37742009886 and Connector's 37742057942 both completed
successfully. Nexus run 37742873924 was superseded after preserving logs: its
Linux shard 1 reproduced the receipt-fault teardown fixed above; shard 3 had
advanced to 51% without the former boot teardown stall. No complete Nexus
regression success is claimed by this focused package validation.
