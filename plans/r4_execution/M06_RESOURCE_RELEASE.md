# M06 — Reconcile durably released resources

## Implemented

Core 0.2.36.dev0 exposes OwnedSlotState and owned_slot_state(SessionKey) on both public SQLite ownership stores. The query returns no record, an active reservation, or a retained release fact. Scope includes Server, executor and session; the original opening operation is preserved. It does not infer liveness from missing rows and does not grant takeover authority.

The existing release row is read without a database migration. Release still occurs only through the existing trusted Core lifecycle after proven non-effect or observed stop. The reusable ledger conformance checks now cover the new query and release persistence after reopening.

project_r4_resource_release correlates the released slot, durable claim, successful opening receipt and persisted Core/wire hash binding. Its digest identifies that exact opening and owner generation. It is a correlation marker carried by the authenticated executor report, not a signature or independent process proof.

Connector reconciliation can report that released resource after lease cleanup even when no canonical close operation was requested. Missing reservations, active reservations, failed/uncertain openings and mismatched identities do not produce a released claim. The existing close-receipt path remains supported.

Nexus validates the release marker against its canonical original opening receipt, operation/session relationship and owner generation before closing session lifecycle and lease state. It creates no close operation, receipt or outbox attempt. Transport readiness still requires the remaining receipt, ownership and event-watermark checks.

## Verification

The [installed campaign](test_runs_20260930_resource_release.json) records all three package hashes and test results. The runner compares package source, wheel members and installed bytes from an external working directory.

- Core tests distinguish missing, active and released records, retain release facts across reopening, reject incorrect scope/corrupt release values and validate opening correlation.
- Public slot-ledger conformance exercises the new state query.
- Nexus negative cases change release digest, opening hash, session, stage or owner generation; readiness remains refused.
- Real HTTP/WSS integration opens a session, submits one turn, loses the link and respects the granted lease through expiration. After Core releases the resource, automatic reconnect reaches control readiness and marks the session closed.
- The integration retains exactly two canonical operations and two receipts, one native opening, one native turn and no repeated outbox attempt. No synthetic close operation is inserted.
- The exact same Core wheel is included in Nexus and Connector vendor directories.

## Limits

This qualifies confirmed release after lease cleanup, not transfer of a live process into a replacement connection. Live-session adoption, uncertain process ownership, actual process-kill recovery, full rotation, event projections, embedded lifecycle and final migration/provider/platform/independent-host acceptance remain open.

The transport integration uses a technical native peer and fixture readiness. Existing user UI assets are included in the Nexus wheel without new UI acceptance. No M00–M13 milestone or G0–G3 gate closes in this increment.
