# Core inventory format evolution

## Decision

Core 0.2.24.dev0 owns catalog format 2 and executor snapshot format 2.
The original R4 planning bundle remains preserved in `plans/contratos`.
The installed Core exposes the generated current inventory schema through
`get_executor_inventory_schema`; Nexus composes those definitions with the
application HTTP envelopes. Both consumers install the identical Core wheel.

This explicitly evolves the planning baseline's format 1. Control targeting
and exact-build control qualification affect selection, so they participate
in the inventory digest. They must not be appended to the old digest domain
while continuing to advertise the old format.

## Requirements retained

The v2 candidate evidence includes the planned support status, execution
platform, technical state and reasons, and nullable observed capability
report. Passive discovery publishes no observed session capability report.
It also includes qualification, containment, and qualified control actions.
The catalog carries targeting from Core's single adapter registry.
Neither implemented targeting nor qualified controls grant Nexus authority.

The Core generator retains the original planning schema definitions and
their source digest, generates the current closed inventory schema, and
includes it in the verified R4 manifest. HTTP inventory contract tests use
that installed schema, including a nonempty candidate snapshot, instead of
relaxing the original schema with unrestricted additional properties.

## Upgrade and history

Historical format 1 verification is explicit and preserves its original
bytes and digest. New publications require format 2. Retained inventory
cannot authorize a new realization, binding proposal, admission or send
after its Core format/version becomes incompatible. The host must refresh
inventory and resolve against its new revision. Existing result queries
and idempotent receipt recovery retain their original identities.

R4 execution remains gated independently. This change does not qualify a
provider, make a lane ready, or install a session lease.
