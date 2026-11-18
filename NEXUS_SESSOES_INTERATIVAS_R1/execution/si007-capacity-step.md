# SI-007 per-session capacity step

The internal per-session step composes durable request preparation, the
registered host's capacity port, canonical R4 staging and consumption
reconciliation. It recovers a staged claim first. A fresh request commits
before the first host call. A retry uses the same request and observation
identity. The operation hash is committed before consumption reaches the
host. The shared outbox remains the productive send path.
An existing unlinked request is observed before preparing a newer FIFO
head. A missing observation retains the original attempt. A replacement
connection on the same executor can inspect an earlier reservation and
record definitive unconsumed expiry. Reservation and consumption remain
bound to the original connection generation and boot.

Migration 173 records an exact release or unconsumed expiry for a
pre-admission attempt. The original input survives with its receipt and
no operation ID. An operation already linked to the attempt uses the
staged reconciliation path instead. A different executor, connection
generation or boot identity requires reconciliation before progress.

The combined regression passed 83 cases across the interaction, R4 and
dispatch-pump suites. The processless host cases
observe the request in SQLite before reservation, confirm the staged
operation before consumption, and preserve a refusal with no created
operation when the reservation expires first. Additional cases cover the
replacement owner's historical lookup and a missing original observation.
NS-09 separately tests the
canonical grant, lease and R4 writer against a synthetic runtime.

This step has no service registration or public entry point. Remaining
work includes the production host registration and capability checks,
reconciliation of old owners and revoked pending authority, queue
controls, user surfaces and native qualification. Migrations are confined
to development/test databases at this point.
