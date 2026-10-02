# Deterministic boot budget verification — October 2, 2026

The historical Linux/Python 3.11 CI fixture required native startup to begin
within a 100 ms global budget. Authorization, database work and scheduling may
legitimately consume that budget before startup; `started.is_set()` was not a
valid invariant under load.

The boot-service test now controls only its module clock and injects an opener
that consumes the forwarded budget. It verifies the 100 ms allowance, the 30 s
cap, zero-budget refusal, stable endpoint order and deferral of the second
binding without another open. Production code and timeouts are unchanged.
The independent existing stuck-start/control test retains real thread blocking,
bounded slot exhaustion, quarantine and eventual cleanup assertions.

Windows/Python 3.13.1 installed verification passed **14 tests in 59.41 s** using
the existing Nexus wheel `d28a7a22cfa167a9598688fc7a31ace8e28eb484b5a901c6ff37be8b67dc6e91`.
All three installed package byte checks passed and campaign inputs were unchanged.
See [campaign](evidence/ci-boot-budget/campaign.json),
[installed checks](evidence/ci-boot-budget/installed.json) and
[JUnit](evidence/ci-boot-budget/tests.xml). An earlier source pass used a synthetic
error label; the final installed run uses the actual `INTERNAL_ERROR` category.
These are synthetic-peer checks, not provider or independent-host acceptance.

Historical CI run 36966572607 has now completed with failure: five failed cells
and one canceled Windows/Python 3.12 cell. The Windows/Python 3.11 log reports
45 failed, 3385 passed, 129 skipped in 6644.52 s. Beyond previously addressed
categories it reports NS14 inventory freshness under load, Pi pending-shutdown
transport behavior and native capture/projection isolation; these require
diagnosis against current code. Raw log is retained locally at
`C:/Users/jpamb/.codex/tmp/nexus-ci-36966572607-windows311.log`.

Current full hosted regression, dashboard completion, NS15.05 reconciliation,
final artifact freeze, independent-host acceptance and G0–G3 remain open.
