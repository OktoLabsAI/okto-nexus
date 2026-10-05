# M01 control targeting and inventory conformance

Status: **IN_PROGRESS**. This increment does not close M01 or G0.

## Changes

Core publishes `ControlTargeting` from its single adapter registry, exposes
public lookup/validation, and uses the same validation before admitting a
native control. Actual run/turn identity remains checked at the write frontier.
Codex steer requires a turn ID; Pi uses the observed current run and reports
next-turn-boundary timing. Claude stream steer and unqualified attach
controls remain unsupported.

Catalog and executor snapshot format 2 bind targeting and exact-build control
qualification into the inventory revision. Unknown builds receive no qualified
control actions. Historical format 1 remains explicitly readable with its
original hash. Current publications cannot silently reuse that evidence.

HTTP conformance exposed missing planned fields in the earlier partial
inventory. Core now includes support status, execution platform, state,
reasons and a nullable capability report. Passive discovery has no observed
session capability report. A closed inventory schema is generated from the
preserved planning definitions plus the explicit v2 evolution and included
in the verified R4 manifest. Both builder and verifier enforce it.

Nexus preserves the Core targeting metadata and checks the current schema
and Core version on publication and before realization, proposal, intent,
admission and dispatch. A changed inventory cannot produce an operation
after resolve. The atomic-admission test now uses an actual Core projection
instead of a skeletal evidence object. It remains a synthetic authority test.

Connector consumes catalog v2, negotiates the matching snapshot format and
uses the same vendored wheel. The Nexus vertical contract test now supports
an installed Connector; its successful run imported Connector from
`site-packages`, without a sibling source override. It still uses ASGI and a
technical native peer, with operations supplied by the fixture. It does not
prove the product dispatcher, daemon, provider or separate hosts.

The version decision and historical behavior are recorded in
[ADR 0002](../../docs/adr/0002-core-inventory-format-evolution.md).

## Artifact

Core `0.2.24.dev0`, identical wheel in all three repositories:
`49254567dc23a15e4868e1ff3e489d24893ba264dff381d173337be74143cc3b`.

R4 manifest:
`sha256:a316cfb1575c9d926c10dcf5ee3192979651aa7db0efb145fab7635094816f03`.

Published Core commit: `8aa60dd`. Published Connector commit: `77cec29`.
The enclosing Nexus commit records its pin, lock, integration and this evidence.

R4 remains `development-partial`, `R4_BUNDLE_EXECUTABLE=False`.
Nexus execution readiness remains false. The earlier local 0.2.24 candidate
was superseded before publication after HTTP conformance found the schema
mismatch; only the hash above is the handoff artifact.

## Verification

The machine-readable execution summary is
[test_runs_20260929_targeting.json](test_runs_20260929_targeting.json).
Counts represent individual runs, not additive requirement coverage.

- Core full Windows/Python 3.13.1 suite: 875 passed, 74 skipped.
- Installed Core directed targeting, inventory, schema, runtime and native
  bridge suite: 131 passed.
- Connector full suite with the final installed Core: 238 passed, two skipped.
- Nexus R4 suite: 41 passed and one optional cross-application skip; the
  skipped vertical case subsequently passed with Connector installed.
- Final Nexus ingress/admission/vertical regression after the version fence:
  seven passed, including the installed Connector case.
- Clean-wheel verification, isolated imports, exact source/wheel comparison,
  R3/R4 generator checks and Nexus frozen lock/sync passed.

The first Core regression exposed a test matching an error's code against
its human message and a public API documentation omission; both were fixed.
The first Nexus regression exposed the inventory v1/v2 schema mismatch;
the projection/schema implementation was corrected before its final run.

Three preexisting Core warnings remain: the intentionally faulted legacy Pi
reader and two unawaited test-native close coroutines. Platform/provider
skips are not passes. No real provider or multi-host qualification was run.

## Remaining work

Complete the M00 criterion-level audit and measured budgets. Continue M01
with grant/context installation, renewal, revocation and all effect/error
paths in both installed hosts. Then connect canonical authority, onboarding
and dispatcher execution in M02–M06. Product gates remain open.
