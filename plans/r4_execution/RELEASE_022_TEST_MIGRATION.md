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

Review the remaining historical execution scenarios by contract, migrate missing
R4 behaviors, retain service/history tests, then run the complete installed matrix.
Do not merge PR #49 or create v0.2.2 until that gate passes. Harness support is not
being retired: Core still provides Pi, Codex, Claude stream and Claude attach.
