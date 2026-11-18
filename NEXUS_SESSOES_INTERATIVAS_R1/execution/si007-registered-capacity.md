# SI-007 shared capacity registry

The per-session step uses the existing RuntimeAvailabilityService to
resolve the authenticated host and route reserve, consume, lookup and
release. The registry checks ownership across awaited calls. The R4
operation remains under the existing outbox and pump.

A replacement during reservation leaves a durable original attempt for
reconciliation and discards the late host result. A later exact lookup
can retain definitive no-effect evidence. The fixture exercises the
existing registry's owner replacement with a processless host. The
capacity, cancellation and transcript suites passed 38 cases together.
This change adds no migration and leaves scheduler registration pending.
