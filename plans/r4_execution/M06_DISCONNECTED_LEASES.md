# M06 — Preserve granted leases after transport loss

## Change

The automatic Connector control owner previously called executor shutdown immediately after its WSS connection ended. It now retains that executor's Core runtimes and stores while their already-installed leases remain active. The transport is fenced, operation consumers stop, and accepted producers are joined; no new effect or lease renewal is authorized through the disconnected connection.

The host observes each selected runtime through public Core inspection. Expired, revoked, closed or durably released runtime states permit normal cleanup. Unknown lease observations and inspection failures retain ownership. An explicit daemon stop releases this wait and invokes the existing shutdown policy. Cleanup remains an owned task when its caller stops waiting.

This changes transport-loss cleanup, not the Core lease calculation or Server grant policy. It neither creates a new native runtime nor adopts an old process into another connection.

## Verification

- Real Core tests install a short correlated lease, disconnect the execution owner and verify that native shutdown is not called while the lease is active.
- Expiry proceeds to cleanup; explicit stop also proceeds, including after cancellation of the cleanup observer.
- An injected inspection failure is retried without an early native close.
- Unknown lease observations do not authorize cleanup, and another executor is not inspected.
- A failed inspection waits for all other started inspections before returning; retries do not leave those tasks behind.
- A real HTTP/WSS test obtains a five-second lease from the Server, opens a session and submits a turn. After link loss, it observes a live native peer before the monotonic deadline and cleanup after that deadline.
- That integration case retains exactly one opening, one native turn and two canonical operations; no outbox attempt is repeated.
- The [installed campaign](test_runs_20260930_lease_disconnect.json) verifies wheel/source/installed byte equality and records the Connector and Nexus regressions.

## Remaining work

The runtime is retained through the current lease, but this increment does not transfer a live session to a replacement connection. Reconnection currently waits for retained cleanup; sessions lacking a canonical close receipt can remain in reconciliation afterward. Durable release evidence and live-session reconciliation/adoption remain required. Unknown observations intentionally keep cleanup pending until evidence changes or the operator explicitly stops the daemon.

Native peers and readiness qualification in these tests are fixtures. Actual process-kill, provider/platform/independent-host, pressure, embedded lifecycle and final acceptance remain pending. The same Core 0.2.35.dev0 and Nexus production wheels are retained. No milestone or G0–G3 gate is closed.
