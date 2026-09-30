# M07 — Replay pending events before reconnect readiness

The Connector now scans its persisted stream registry during R4 negotiation. A dedicated temporary socket owner attaches the required binding lane, replays finite Core journal batches, and applies the resulting ACKs before the reconciliation report is produced. It has no runtime operation or lease API. Only after reconciliation accepts readiness are its validated lane projections transferred to the normal single reader.

The registry scan is namespace-scoped and uses a stable rowid high water with pages of 128, at most 32 pages per pass. Batch work has an explicit 4,096-batch budget. Completed ACK progress remains durable when another recovery pass is required. An existing remote/Core cursor difference is applied locally before requesting network authority or reading another batch.

## Authority and ownership

Each stream must match a currently approved local binding and canonical identity. The approved origin is checked before credential resolution. Binding, identity, registration and deadline are rechecked across asynchronous steps and each batch. Expired or changed authority cannot publish facts or promote readiness.

The daemon retains still-valid in-memory lane tickets through a connection loss. Receipt and event recovery share the scoped authority map, including newly issued proofs when a later publication fails. Recovery does not extend the original deadline. Tickets remain out of the new stream database and logs.

A lane attached during recovery is adopted before the normal connection reader starts. The daemon does not perform a second conflicting attachment on that socket. The temporary recovery owner is disabled when ownership transfers. Negotiation cancellation retains its recovery tasks and keeps HTTP/Core resources alive until their pending work settles.

A failed recovery hook cannot produce an invented empty reconciliation report. Retry cycles remain bounded. Native operations are never invoked from this path.

## Verification

Two additional real HTTP/WSS cases exercise the automatic daemon:
1. A native event is journaled but publication fails before reaching the Server.
2. The Server commits the event and its ACK is lost before Connector progress is saved.

After the same daemon loses its connection, it reconnects, reuses current authority, republishes the stable event when needed, applies the Core ACK and reaches readiness. Both cases end with one Server event row and the same five canonical operations, one native open and three native controls/turn calls. They do not inject credential expiry or manually invoke the recovery service.

Focused tests cover persisted ACK application after a Core write failure, no second ticket for that local obligation, identity change during ticket issuance, namespace/high-water paging and transfer before immediate operation dispatch with one reader. Fixture corrections added the new attachment-query port to the fake connection and initialized the fixture host directory; production checks were preserved.

[Installed campaign](test_runs_20260930_event_recovery.json), [artifact hashes](evidence/event-recovery-artifacts.json), [runner](run_event_recovery_installed.py). Only the Connector wheel changes; Nexus production code and Core 0.2.35.dev0 retain their prior artifacts. All three installed/source/wheel byte sets are verified before pytest.

## Remaining requirements

This advances NS10.04 and the closed-session recovery part of NS08.03. Active ownership adoption, full ticket/lease rotation, automatic embedded publishing, decision/input/history/UI projections, retention/pressure, migration/rollback and provider/platform/independent-host acceptance remain open.

Cold daemon restart with unavailable material for an unexpired ticket remains pending: the new process must not silently replace an active proof or invent its original credential intent. Fresh issuance remains subject to existing Server replacement rules. Warm reconnection evidence is not cold-restart qualification.

The full DELIVERY_PLAN.md scope, M00–M13 and G0–G3 criteria are unchanged. No milestone or gate is marked complete.
