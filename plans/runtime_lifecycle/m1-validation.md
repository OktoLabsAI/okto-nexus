# M1 — Early process birth

Date: 2026-10-16. Core implementation: `8520deb`; Connector integration: `3aa841c`.
M0 Nexus baseline: `5181605`. The running user installation has not been replaced
by M1; wheels were installed into an isolated validation environment.

## Implementation

The Core records the original opening claim's owned process identity before
Pi/Codex protocol negotiation and before Claude startup returns. Storage waiting
stays in that opening's worker while the event loop and other sessions proceed.
Post-spawn recording failure/timeout remains uncertain and cannot be reported as
safe to retry. The process remains owned for containment. Authority is checked
again after recording, before handshake. No uncertain slot release was relaxed.

This closes the long handshake-before-birth window. It does not close the short
spawn-before-birth-commit window; durable launch intent and producer fencing are M2.

## Evidence

- Core source regressions: **39 passed**, focused on birth, opening/factory and
  prewrite behavior (`build/runtime-lifecycle-m1-regression.xml` in Core).
- Core installed wheel: **10 passed** covering the three adapters, storage failure,
  timeout, cancellation, draining and independent openings; **1 additional passed**
  for a real subprocess peer that does not answer Pi readiness. Its birth remains
  queryable during the wait and after containment. Evidence in Core:
  `build/runtime-lifecycle-m1-installed.xml` and `build/runtime-lifecycle-m1-handshake.xml`.
- Connector with installed Core: **43 passed** (execution owner and daemon),
  `build/runtime-lifecycle-m1-installed.xml` in Connector.
- Nexus initial installed campaign: **82 passed, 2 failed**. Tests covered embedded
  dispatch, interrupted opening fences and reconciliation. Evidence:
  `build/runtime-lifecycle-m1-installed-evidence/campaign.json` and `tests.xml`.
  This failed campaign is retained; it is not reported as an all-green gate.
- All installed files matched their wheels; `pip check` passed. Core wheel hash
  `d2799bb6249c28fca5e56d9e17862ca1b3f72b15a59c5f9e2d15d509a0d2da8f`
  is identical in Nexus and Connector vendors.

## Nexus triage

1. `test_local_owner_renews_installed_lease`: a 2-second lease entered
   `LEASE_REVALIDATION_REQUIRED`; the close was refused with session reconciliation
   required. This is a timing/renewal observation, not evidence of a birth-record
   failure. The focused rerun also failed. A causal comparison using the verified
   M0 Core wheel (before M1; no birth callback) reproduced the same failure and
   recovery error. Thus M1 did not introduce this failure; the underlying cause
   remains an open high-priority M3 finding (L1), not a waived final gate.
2. `test_restart_recovers_historical_receipt_without_provider[False]`: the test
   checked readiness immediately after startup while asynchronous recovery still
   had the agent blocked. Read-only inspection afterward found the close receipt
   persisted as SUCCEEDED and the session CLOSED. The focused rerun passed.
   L2 remains tracked for deterministic observation of asynchronous recovery.

Focused recheck: **1 passed, 1 failed**,
`build/runtime-lifecycle-m1-targeted-recheck.xml`. M0 comparison: **1 failed**,
`build/runtime-lifecycle-m0-lease-comparison.xml`. Baseline wheel SHA256:
`5bfda0a72de6d57fd638172bf5b955842565a8917b08456dacc0f42dc7dfbc36`.
No TTL, assertion, timeout or production renewal rule was changed to obtain a pass.

The user reported another agent terminating Nexus processes during this work.
There is no evidence establishing that as the cause of these test failures.
A later CPU sample was 79.5%; it is context, not proof of causality.

## Qualification limits

Tests above use synthetic protocol peers, including real owned subprocesses on
Windows. They are not real-provider UI tests or Linux/macOS qualification. Real
Pi/Claude/Codex tests through the Nexus UI are required at UI-A/UI-B/UI-C in the
plan, per the user's requested cadence for large milestones.

M1 is complete as the scoped early-birth technical checkpoint. The integrated
availability qualification is not complete; L1/L2 and the real UI gates remain
explicitly open. Core and Connector commits are pushed. This file's creation
commit is the corresponding Nexus integration checkpoint.
