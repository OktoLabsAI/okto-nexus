# Home states R1 — implementation and qualification checkpoint

**Delivery is not fully qualified or approved for default. Human evaluation
has not started.** The selected local functional/context flows have now been
reviewed against source, installed and browser evidence. Additional supported
functional/security/compatibility checks remain before the human invitation;
a reproduced unnamed menu control has been corrected and packaged in R8;
its accessible name and expanded state are verified in the actual R8 browser. The whole
plan's remaining qualification is explicit. Following the user's clarification about other
processes on this shared machine, performance timings are diagnostic and
non-blocking for this local delivery; no further tuning is required solely
to chase these numbers.

## Candidate and preserved work

Nexus is version0.3.7 on `feature/v0.3.7`. The current frozen R8 runtime source is
`6eaa325ea3ddf1dec1b03475b27f373211c81e53`, wheel
`fc2afcccdf55236db21071a132a353a13cf1c56399767ea5223a69e50162902e`.
The R7 source `01b0de385398950ac4547aa8a5dcbc29473c12cb` and its wheel
`18c948b49844c7c551360732970fdc2ba91cba50075b73c1a7472571775d7681`
remain immutable predecessor evidence. The draft stacked
PR is [140](https://github.com/OktoLabsAI/okto-nexus/pull/140), based on
`feature/v0.3.6` to preserve the existing UI and Quick Connect work.

The initial [baseline](baseline.md) records fetched main refs, branch/HEAD,
working tree, versions and drift without resetting the checkout. The six
original plan inputs remain frozen under `../input`. Core0.0.14 and
Connector0.0.13 remain pinned to the same exact wheels and their repositories
are read-only for this Home change. No personal installation was modified.

## Implemented behavior

Home retains Active, Needs you and Results. The backend correlates the
complete authorized connection/session/operation relation before filtering
and pagination. Productive independent work keeps a harness in Active with
its request separately in Needs you. A fully blocked harness incorporates
its requests in Needs you. Completion creates a delivery, without moving the
harness itself into Results. Unknown coverage cannot prove idle or absence.

Working uses actual current committed started/progress facts while Core may
still report a SUBMITTED receipt. The existing server/executor/binding/
workspace/workspace-binding/agent/session/owner/epoch authority fences remain.
The correction uses the actual committed-ingress contract rather than a
projected-through field that has no producer. A committed stream failure
invalidates productive proof. No protocol, native receipt or Core state was
changed to make the reader pass.

Results keeps execution outcome, task state, verification and cleanup
separate. Verification requires the current delivery/claim's canonical
verdict. A successful turn, free text, a COMPLETED label alone or an external
report cannot manufacture verified work. Historical and uncertain outputs
remain inspectable only through their exact authorized targets.

Context panels and drafts survive identical polling and late presentation
negotiation. Identity/project/authorization changes still clear protected
state. The shared operator composer exposes Chat and Ask for work while
preserving its canonical message/handoff kinds and permissions. Existing
controllers, read-only event terminal, decision receipts and recovery paths
are reused. No parallel Harnesses/Executions/Sessions destination was added.

Read optimizations are scoped to Home: complete batched progress proofs,
deterministic identity-hash reuse, shared metadata without rendering a
discarded page, canonical tie sorting only for equal IDs, and a request-local
complete authorized result-attention index with legacy fallbacks. They do not
cache authority or freshness across reads/principals or weaken resource limits.

## Executed evidence

The new R8 source fixes a reproduced shell accessibility defect: the icon-only
header menu had no accessible name in the real R7 browser AX tree. It now has
the name Application menu and exposes its actual expanded state. The original
checkout's404Node cases, TypeScript and Vite build pass with unchanged inputs.
Its new bundle is `index-Cyg0aKfe.js`; CSS remains `index-Bh2ghaTD.css`. A fresh
R8 package passes build/install/base-Core/local-lite/Connector/Twine/pip-check,
audit and actual HTTP/MCP smoke (54tools, two synthetic identities). All1829
source pins and1031 payload files remain unchanged; owned processes exited
normally and physical absence was checked. The separate
[R8 browser naming cut](remaining-qualification-r7-next/experience-batch/naming-r8/qualification.json)
passed five focal checks: actual AX Application menu, expanded false/true/false,
zero browser POST and zero page errors. It used zero runtime sessions or
operations and ended normally with physical absence and no payload drift.
This resolves the earlier real defect; complete keyboard/AT qualification
remains separate.
R7 prefixes and the original failing AX capture remain immutable. No Python
behavior changed.

[Raw-byte comparison](package-hst-r8/runtime-equivalence-vs-r7.json) proves
equality of1024 nonstatic Nexus/Core/Connector files, equal Python/dependency
versions and unchanged packaging/lock inputs. The326+7 installed predecessor
tests therefore support only that unchanged backend. They were actually run
on R7; no pytest run on R8 or browser equivalence is claimed. Third-party
dependency versions were compared, not all dependency file bytes.

| Layer | Observed scope | Evidence |
|---|---|---|
| Final source selection |321PASS,0failure/error/skip; source/test drift0 |[source qualification](source-tests/r7-home/qualification.json)|
| Final installed selection |326PASS,0failure/error/skip/not-run;1828pins/1031payload files and copied helpers unchanged |[installed qualification](package-hst-r7/installed-qualification.json)|
| Frontend |404Node cases plus TypeScript/Vite on the original checkout; actual packaged assetsCefKJTtn/Bh2ghaTD |[frontend qualification](frontend-r6-original/qualification.json)|
| Package |fresh wheel/sdist/build/install/audit/pip-check/CLI smoke and actual HTTP/MCP54tools/two synthetic identities |[package](package-hst-r7/qualification.json), [live smoke](package-hst-r7/live-qualification.json)|
| Fresh final browser |21PASS: Working/independent request/full block/exact request-result sessions/partial source/logout;0POST |[R7 browser](browser-hst/r7-functional-report.md)|
| Post-build supplement |7sourcePASS and7actually installedPASS, separate cuts;1828base+1exact additional test/1031payload files unchanged |[supplement](installed-supplement-r7/qualification.json)|
| Recovery and paging |Same accepted decision after lost response; stale second-screen409; one durable write admission; actual paging409/current200 in the same panel |[scoped captured predicates](browser-hst/nextcuts-report.md)|
| History and drafts |9history assertions;8draft/auth positives plus captured real UI401 proof; wrapper/late-observer errors retained |[scoped follow-up](browser-hst/remaining-report.md)|
| Earlier browser transitions |Actual canonical answer202, later exact terminal/output, draft focus, capability negotiation,360px and composer intents; individual predecessor failures/limits retained |[R5/R6 report](browser-hst/r5-r6-final-report.md)|
| Performance |10measured cuts; candidate5PASS/3FAIL at500ms, baseline0PASS/2FAIL;20samples/route |[R7 matrix](performance-hst/persistent-r7-final/qualification.json)|
| Diagnostic |3separate GETs; fast path925projections actually used; no p95 inference |[R7 profile](performance-hst/profile-r7-final/qualification.json)|
| Useful DOM observation |N=1,2725.6ms; actual v2 IDs/project/columns/counters match canonical HTTP; shared-machine diagnostic/non-blocking |[DOM observation](performance-hst/large-dom-r7-final/qualification.json)|

Source, Node, installed package, browser, inert protocol and actual provider
layers are distinct. No suite count promotes an untested complete scenario.
All these owned runtime/test processes ended normally with the individual
guards and limitations recorded in their cuts. An unanswered native request's
bounded close can remain unconfirmed even when its outer owner drained and
physical absence was verified; the report does not equate those observations.

The post-build supplement exercised private sibling proofs under filtering,
failed/cancelled partial capture, three same-claim artifact references,
off-page seen/retention/no inbox ACK, forged targets, JSON minimization and
decision denial after a negative SQL revocation fixture. The initial E16
seed violated the one-runtime-result-per-operation constraint; its6PASS/1FAIL,
original test bytes and runner remain preserved. The corrected fixture uses
three distinct operation keys for one logical work/claim and explicitly
asserts that the selected result is older than24h. It passed seven cases on
source and the frozen installed runtime. These are historical read fixtures
and bounded API layers, not full adversarial browser or native lifecycle
qualification; the literal scenarios retain their missing clauses.

The additional browser evidence is not included in the21-check regression
count. Its original failures remain: a losing-tab storage assumption, two
earlier context prerequisites, a RuntimeSession field assumption, a wrapper
status-label mismatch and an observer attached after logout. Completed
captures independently establish the literal recovery/paging/history/draft
predicates; they do not make every enclosing runner green. One earlier
context owner needed its own CTRL_BREAK containment after a100s drain bound
and exited3221225786, with data preserved and physical absence confirmed.
Later owners drained normally within180s. No cleanup authority/TTL was renewed.

## Regressions and outstanding gates

The raw observations exceed the reference targets in several cuts. Mixed100 V2 p95 measured
876.423/927.279ms, and its overview was29.06% slower than the paired baseline
in this window. OPEN100 V2 measured497.934/489.176ms with little margin.
First-HTTP responses below2s are not first-useful DOM. The
[correction plan](performance-hst/r7-correction-plan.md) is retained as a
deferred option. Earlier R6 and first-R7 observations remain available.
The [shared-machine interpretation](performance-hst/shared-machine-interpretation.md)
records the user's direction: these measurements do not block local acceptance
and do not establish a causal code regression. Only our readers were sequenced;
unrelated machine load was not controlled. Reference targets remain unchanged
and no production-performance pass is inferred.

The [116-scenario audit](remaining-qualification-review-r7.md) records the
unexecuted clauses and partial layers rather than treating every test count
as qualification. The [ledger](../NEXUS_HOME_ESTADOS_LEDGER_R1.json) remains
authoritative for individual task/scenario status. After the subsequent literal
reviews it has44PASS,63NOT_RUN,1FAIL and8BLOCKED. The current failure is the
R7 menu's actual missing accessible name; R8 source is fixed but its new
installed/browser validation is pending. Partial browser/native clauses
remain NOT_RUN. This is not a whole-plan completion or default approval.

The [contract blockers](contract-blockers-r6-review.md) remain precise:
independently admissible queued work lacks its required producer proof;
updating the same native question is not supported end-to-end; suspension
proof is method/adapter specific; causal answer-application/resume ACK is
absent. Conservative unknown/awaiting-confirmation behavior is implemented;
inventing queue, pause or resume proof would violate the plan. Expanding
Core/protocols is outside this reader change.

Real provider-family and remote-topology campaigns were not authorized for
this plan and were not run. Actual screen-reader and native200% browser zoom
qualification remain unexecuted. The prior UI-R1 novice-user gate, Quick
Connect UNKNOWN usage/QC031 and broader regression NOT_GREEN are retained.
CI status is a separate remote observation, not inferred from local passes.
At the checkpoint, the GitHub connector reported source run
[44161118859](https://github.com/OktoLabsAI/okto-nexus/actions/runs/44161118859)
and evidence-commit run
[44167762093](https://github.com/OktoLabsAI/okto-nexus/actions/runs/44167762093)
as queued, without a conclusion. An empty combined-status response is not a
passing check. The [repository checkpoint](repo-checkpoint-r7.json) records
refetched main refs, unchanged dependency pins and clean Core/Connector trees.
No real user accepted this delivery on their own behalf or through automation.

## Effects, migration and rollback

There is no database migration, service recreation, directory remapping,
grant renewal or checkpoint rewrite. New handoff verification evidence adds
delivery-reference metadata through existing events; historical receipts and
hashes are not rewritten. GET projection stays passive: no provider probes,
turns, decisions, claims, grants or artifact-content filesystem reads.
Existing authentication telemetry is separate from productive effects.

Rollback uses the existing browser-local operational Home setting to select
classic Home. It changes presentation, preserving daemon, CLI, MCP, global
bell, identities, native sessions, decisions and retained results. A whole
daemon restart is not presented as an individual connection recovery action.
The full active-work rollback scenario still needs its literal isolated
qualification; documentation is not execution evidence. No reset, clean,
force-push, release, deployment, merge or default activation was performed.

## Next gate

The selected recovery/isolation/context follow-ups are reviewed. Finish the
additional supported functional/security/compatibility increments and confirm
the R8 menu correction in its new installed browser before inviting a participant.
The useful-DOM
observation and shared-machine limitation are already recorded above. No
further performance-only optimization round is required for this local delivery.
Then invite the participant for the representative supported local flows using the
neutral [human script](human-usability-preparation.md), while keeping the
remaining technical qualification explicit.
Provision a fresh temporary fixture after availability is confirmed; do not
start a short-lived question or renew its authority while waiting for a user.
