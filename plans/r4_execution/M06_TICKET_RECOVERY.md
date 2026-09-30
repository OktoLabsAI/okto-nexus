# M06 — Durable binding ticket recovery

## Implemented behavior

The Connector persists a ticket issuance intent before HTTP. A separate schema-1 SQLite database stores non-secret scope, an authority snapshot digest, the original logical intent, the credential request ID, an optional replacement ID and request creation time. It never stores the canonical agent key or derivative ticket secret.

Lane startup, receipt recovery and event recovery use this same acquisition service. A lost response is retried using the exact persisted request. Only a validated HTTP 409 material-unavailable response permits preparing a replacement request with a new credential request ID and the original logical intent. Persistence uses a compare-and-swap check before replacement and before returning received material. Current profile, binding and identity checks surround asynchronous work.

Server replacement rules remain unchanged: a bound, revoked, expired, differently scoped or differently authorized ticket cannot be explicitly replaced. Unrelated active ticket conflicts do not trigger replacement. A local expiration hint can select a fresh issuance request, but the Server decides whether that request is permitted; it does not create or extend authority. Returned material receives a monotonic deadline anchored before HTTP.

Each acquisition performs at most two HTTP requests. Further material loss leaves a persisted request for a subsequent recovery pass. Storage is bounded to 4,096 authority contexts and 4,096 SQLite pages, with full synchronous commits and metadata integrity checks.

## Verification

- HTTP contract tests validate typed material-loss metadata and reject malformed IDs, incorrect stages, effect flags and non-409 recovery responses.
- Store/service tests cover exact request replay after a lost response, replacement ID continuity, restart-compatible persistence, stale compare-and-swap, corruption, failure before HTTP, changed authority, expiration hints and live-bound replacement refusal.
- Two new real HTTP/WSS cases shut down and recreate the daemon with the same disk state and no retained ticket cache. They recover an undelivered event and a committed event with a lost ACK.
- Both integration cases verify the old ticket is revoked, its replacement preserves the original logical intent, only one event row exists, and native work remains one opening plus send/steer/interrupt and close.
- No Server expiry injection or manual recovery invocation is used in these two new cases.
- Installed artifacts and regression results are recorded in [the campaign manifest](test_runs_20260930_ticket_recovery.json). The runner compares source, wheel members and installed bytes for all three packages from an external working directory.

## Limits and next work

The daemon recreation tests run in the same test process after an orderly shutdown. They do not qualify an operating-system crash or a still-connected predecessor. The native provider is a technical peer and readiness is supplied by the fixture. Legacy in-memory ticket intents cannot be reconstructed; unrelated active ticket conflicts remain refused until Server policy permits fresh issuance.

Active-session ownership adoption, full authority rotation, embedded event publication, public event projections, disk/pressure qualification, process-kill tests, provider/platform/independent-host acceptance and migration remain pending. This increment does not close any M00–M13 milestone or G0–G3 gate. The Core and Nexus production wheels are unchanged.
