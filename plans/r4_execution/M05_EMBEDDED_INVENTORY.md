# M05 — Serve-owned embedded inventory

Status: partial P5.1 foundation. M05 and G1 remain open.

Historical increment: the RECOVERING-only behavior and Core .38 evidence below
describe this original campaign. Current serve startup can reach CONTROL_READY
through the [embedded dispatcher](M05_EMBEDDED_DISPATCH.md). Correlated passive
refresh now has an [embedded consumer and newer package evidence](M10_INVENTORY_REFRESH.md).
Consult [current acceptance status](IMPLEMENTATION_STATUS.md) for remaining work;
the original evidence and limitations below are preserved.

## Implemented path

With harness integrations enabled, the real serve lifespan acquires the existing exclusive store owner before starting an embedded inventory owner. The embedded executor is tied to that owner and a new generation. Core discovery runs outside database transactions. Complete candidates remain on the Nexus host; only the public Core path-free snapshot reaches inventory storage and HTTP views.

Publication revalidates the store owner's live epoch, the embedded identity, exact owner and generation, and revocation in the write transaction. A new serve owner publishes a higher sequence; current and previous snapshots are retained. Discovery refreshes every 30 seconds. A failed publication removes the process-local freshness proof.

Authenticated active agents can read the embedded inventory and runtime options through the existing public routes. Remote inventory remains scoped to its registering agent. This increment leaves the embedded executor RECOVERING and runtime options unavailable for new execution: automatic inventory is not evidence that local dispatch, reconciliation or a lease is ready.

Shutdown drains discovery/publication before clearing freshness and conditionally disconnecting its own generation. Canceled startup, refresh or cleanup observers do not cancel retained producers. A stale cleanup cannot overwrite a successor generation.

## Verification

The tests exercise the real application lifespan and public HTTP inventory/runtime-options routes. Discovery supplies a technical candidate or an empty candidate set; no binding, operation, session or control lane is seeded. Agent credentials are fixture setup, so this is not full onboarding acceptance.

Directed cases cover restart with stable executor identity and increasing generation/sequence, two-snapshot retention, owner/generation/revocation refusal, canceled refresh and cleanup observers, path-free responses, zero WSS tickets/sessions, and no Core runtime store creation.

A new venv installs the built Nexus wheel with serve-lite and the same Core 0.2.38 wheel. Dependencies are resolved by pip under constraints from the working environment. The isolated runner verifies both Connector module lookup and distribution metadata are absent; it does not simulate absence by blocking imports. Source/wheel/installed bytes are compared. pip check must pass.

## Remaining fixed-plan work

Complete approved local realization/configuration persistence, public selection and consent, owner-aware local readiness, canonical dispatcher/lease application, receipts/events, renewal/recovery and native tools. Then exercise the full local cycle without Connector and the real-provider journeys specified by DELIVERY_PLAN.md. No execution readiness flag is promoted by this increment.

The Nexus wheel includes preexisting user UI asset edits; these files are neither committed nor accepted as UI delivery here. Core and Connector production code and their published commits remain unchanged.

## Installed results

- Nexus affected regression: 55 passed, no skips or failures.
- Fresh installation without Connector: 13 passed, no skips or failures. These cases overlap the 55-case regression and are not added as distinct coverage.
- pip check: no broken requirements.
- Core 0.2.38: fb4c8df70a66b9d9df7729fee5cbff453b591d31.
- Connector: cba635a714f0f0c998badf4f075713a22b862d7d, unchanged.
- Nexus: the commit containing this document.

[Results](test_runs_20260930_embedded_inventory.json),
[artifacts](evidence/embedded-inventory-artifacts.json),
[isolated package inventory](evidence/embedded-inventory-isolated-installation.json),
[runner](run_embedded_inventory_installed.py).
