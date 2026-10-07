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
