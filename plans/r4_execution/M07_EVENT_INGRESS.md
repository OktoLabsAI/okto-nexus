# M07 — Durable event ingress through the authenticated WSS lane

The Nexus WSS owner now accepts the existing Core R4 event.batch contract. Ingress checks the exact current channel, canonical session/binding/agent, active agent revisions and admitted unexpired binding lane inside the storage transaction. The bootstrap ticket is also reverified by the WSS owner. A referenced operation must belong to the same canonical session and binding. The first accepted event pins the session stream epoch; later epochs are refused.

Events use stable session/epoch/sequence identity independent of connection identity. Complete canonical event bodies and SHA-256 digests are retained in execution_event_ingress. Matching duplicates are idempotent; conflicting content is refused. The public Core event reducer determines the contiguous watermark from verified durable rows and the incoming batch. Events, stream identity and watermark commit atomically. Only after transaction exit can the WSS owner send event.ack. A gap at sequence zero produces no fabricated positive ACK.

The stored pending window follows the Core reducer's 256-sequence bound. Each batch remains within the Core 1 MiB frame and 128-event limit, and individual canonical events are limited to 64 KiB. Old duplicates outside the reducer's recent window are checked directly against durable storage before reduction. Projection progress remains separate: ingress never advances projected_through or waits for a UI subscriber.

This advances NS10.01 / TR4-10-01 and the event-frame portion of NS08.04. The named normative acceptance scenario, including disconnect injection on both sides of commit and canonical projection, is not yet fully qualified. NS10.01 is not marked DONE.

## Evidence and scope

The public onboarding/bootstrap test attaches the lane through HTTP/WSS, opens the technical native runtime, publishes the opening receipt, sends sequence 2 before 1, and observes ACK 2 only after both durable rows exist. Replaying sequence 1 returns ACK 2 without a duplicate row. The five-action remote owner and existing reconciliation/control cases remain in the installed regression campaign.

Focused SQLite tests cover missing/wrong scope, unknown operation, changed epoch, expired lane, revoked ticket, old owner generation, inactive agent, oversize event, excessive gap, conflicting replay and a watermark-write failure. The failure rolls back inserted events and cannot return an ACK. A 300-event test recreates the connection factory, replays an old duplicate and rejects corrupted persisted content.

No schema change is needed: the R4 expansion migration already contains the canonical ingress and watermark tables. Tests use the current migrated database. This does not qualify a full upgrade/rollback campaign.

The [installed runner](run_event_ingress_installed.py) verifies installed/source/wheel bytes for all three packages before the focused Nexus suite. [Artifacts](evidence/event-ingress-artifacts.json) retain the unchanged Connector and Core hashes. [Results](test_runs_20260930_event_ingress.json) record the campaign.

## Remaining work

Automatic Core-to-WSS event publication and replay/ACK handling in Connector, embedded event publication, projection into public history/UI, decision/input consumers, retention/pressure qualification and nonzero-watermark reconciliation remain pending. This increment provides the real Server ingress caller; it does not claim an automatic end-to-end event pipeline. Pi/Codex/Claude acceptance, M00–M13 and G0–G3 retain their full criteria.
