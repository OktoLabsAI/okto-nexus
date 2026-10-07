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
