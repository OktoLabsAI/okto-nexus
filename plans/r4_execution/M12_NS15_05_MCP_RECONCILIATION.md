# NS15.05 MCP and ledger reconciliation — 2026-10-02

The identity resource now publishes version 30, with MCP surface revision 63.
It describes executor inventory, realization consent, binding prepare/apply,
subject-authenticated intent resolution and durable operation submission.
Core owns version qualification and effective capabilities. The resource records
the actual remaining embedded-probe, inventory-refresh and browser limitations.

Removed old provider-version qualification claims and legacy profile/endpoint
creation instructions that could not establish R4 readiness. Retained endpoint
reads, connection self-service and outbox recovery are explicitly scoped to their
current compatibility behavior. Existing canonical endpoints still connect through
approved bindings; remote selection is path-free. No command was removed from the
product. MCP payload/open/steer/interrupt descriptions now match the R4 adapter:
text payload, stable idempotency key, subject identity and Core control targeting.

## Evidence

Source resource/surface checks: 22 passed. Installed wheel: 23 passed, including
actual FastMCP resource reads/cache versions, the closed twelve-resource set,
tool surface and packaged HTTP/OpenAPI. The runner verified all three installed
package trees against their wheels, ran outside the checkout with isolated Python
and recorded no changed campaign inputs. See
[campaign](evidence/ns15-mcp-resources/campaign.json),
[installed artifacts](evidence/ns15-mcp-resources/installed.json) and
[JUnit](evidence/ns15-mcp-resources/tests.xml).

Nexus development wheel SHA-256:
`ce6167fd17ea947ddaf278b21db22f9fcf049e2992052769051f695e260037ad`.
This wheel includes preexisting static assets and is not the final M13 artifact.
These checks verify documentation delivery, not native execution or browser use.

## Reused scenario evidence

Inspected the October 1 manifests, scenario entries and original JUnit reports:

- TR4-15-05, TN-38 and TN-39: `test_runs_20261001_ns15_05.json`,
  `evidence/ns15-05-r4.xml` (2 passes) and `evidence/ns15-05-legacy.xml`
  (53 passes). Scope is documentation unit contract, indexed/scoped 100,000-Agent
  authentication, bounded cache, revocation and credential-epoch behavior.
- TN-40: `test_runs_20261001_tn40.json` and
  `evidence/ns15-05-recovery.xml` (3 passes including the two NS15.04 cases).
  Scope is same-version snapshot recovery after backfill and a synthetic uncertain
  native effect, preserving policies/history and refusing unsafe restore.

These historical passes use Core .51 on Windows/Python 3.13. Preserve their exact
scope; they neither prove a fresh .53 campaign nor reverse migration or independent
hosts. The ledger already recorded these passes correctly; the newer operational
note incorrectly called their evidence missing and has been corrected.

NS15.05 remains PARTIAL for dashboard/dependency and final-artifact acceptance.
No G0–G3 gate is closed. M13 freeze and independent-host/platform/provider/fault
acceptance remain required.
