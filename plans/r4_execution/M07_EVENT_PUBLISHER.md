# M07 — Automatic Connector event publishing and durable ACK recovery

The Connector execution owner now registers each opening stream before calling Core open. After receipt publication, it ensures one publisher task for the stream. The task reads the public finite Journal.events port, never the Runtime.events follower. Empty or partially filled snapshots return promptly; pages are bounded at 128 events and 768 KiB, with a 64 KiB limit per canonical event. Complete batches remain below the existing Core 1 MiB wire limit.

The R4 connection's single reader correlates event.ack by the exact binding, agent, session, epoch and current connection/generation. Each batch retains its own target. An older ACK cannot satisfy a later batch, an ACK above the written range is refused, and a late valid duplicate does not fence unrelated operations. A timeout leaves the event batch retryable; it never retries a runtime operation. Lane identity/deadline is rechecked before sending and on acceptance.

## Durability and ownership

A separate schema-1 event database persists immutable stream identity, a metadata checksum, remote_acked and core_applied. It uses FULL synchronization, a 4,096-stream limit and a 4,096-page physical limit. Stream registration failure prevents native opening. Payloads remain in the Core journal rather than a second Connector payload log.

A verified Server ACK is persisted before applying it through Journal.acknowledge_events. The applied cursor advances only after that call succeeds. A failure before or after the Core write retries the same acknowledgment, without another network batch. A recreated publisher can recover the persisted difference.

Each stream has one retained publisher task. Finite reads, sends and ACK application failures retry without waiting for another event. Stop cancels the retry wait and retains any current producer through caller cancellation; it cannot re-enable a stopped publisher. Per-owner stream capacity defaults to the existing 64-session bound. Runtime operation producers and event producers have distinct ownership.

## Reconciliation

A confirmed closed stream with nonzero events may now reconcile when the Connector's remote and Core-applied cursors both equal the public Core contiguous watermark and no events remain beyond that prefix. The Server independently checks its committed contiguous watermark, epoch and gap state. It never accepts a larger or smaller reported watermark as equivalent.

This extends the previous closed-session reconciliation path. Active ownership remains fenced. A stream with unacknowledged events during reconnect still needs the recovery-phase attach/publisher integration; it cannot become ready merely because a local registry row exists.

## Verification

Connector tests cover finite snapshots of 0/1/127/128/129 events, read/send/Core-ACK/progress-write failures without new events, recreation from persisted ACK progress, canceled stop waiters, conflicting/corrupted stream identity, registration failure before native open, exact batch targets, stale/cross-stream ACKs, and late valid duplicates interleaved with runtime operations.

The Nexus HTTP/WSS integration injects a technical native text event after a canonical turn. The automatic publisher persists it on the Server, receives the ACK and encounters an injected first Core ACK failure. The second application succeeds with one Server event row, unchanged five runtime operations and unchanged native verb counts. The closed-session variant reconnects through a fresh Core host and reconciles the confirmed nonzero stream. Five Server cases independently check exact/mismatched watermarks, epoch and gap state.

[Installed campaign](test_runs_20260930_event_publisher.json), [artifact hashes](evidence/event-publisher-artifacts.json), [runner](run_event_publisher_installed.py). The same unchanged Core 0.2.35.dev0 wheel is used by both consumers. Package/source/installed bytes are compared before tests.

## Requirements and remaining work

This advances NS10.02–NS10.04 and closed-stream NS08.03, with the NS10.01 ingress from the previous increment. The normative acceptance cases and dependencies remain open. It does not close NS10 or M07.

Pending work includes recovery-phase publishing of unacknowledged streams, active-session adoption, automatic embedded publishing, decision/input and public history/UI projections, retention/pressure, full migration/rollback, authority rotation, provider/platform and independent-host acceptance. The full DELIVERY_PLAN.md scope M00–M13 and gates G0–G3 is unchanged.
