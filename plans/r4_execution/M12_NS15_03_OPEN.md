# NS15.03 canonical opening — October 1, 2026

Existing REST and MCP `harness_open` calls with an explicit canonical endpoint
now admit `runtime.start` through the existing R4 resolver and dispatcher. The
subject must hold current endpoint authority and provide a stable idempotency
key. Local path, native kind, managed mode and optional role must match the
approved realization and canonical identity. Per-call backend, metadata,
notification and PID overrides are rejected. No legacy connector is constructed.

The MCP connections `connect` action also recognizes canonical endpoints and
uses their approved binding without a legacy catalog lookup. This path carries
no filesystem path and delegates realization selection to R4. The older
path-bearing `harness_open` request is accepted only for a locally recorded
realization; remote callers use the path-free canonical connect or R4 API.
Admission returns the durable operation DTO, whose scope contains the session
ID. It does not assert that the native process has already opened.

The technical tests exercise public REST and MCP open, path-free MCP connect,
idempotent replay, durable receipts and canonical close. Sentinels forbid legacy
construction/preparation. Negative cases cover mismatched subject, kind, path,
attach mode, runtime overrides, missing key, revoked grant, disabled endpoint and
unqualified protocol readiness. Core production readiness is unchanged; the
native peer is synthetic. The campaign does not qualify a remote provider.

The prior canonical command/read regression suite, embedded dispatch, local
realizations and legacy authorization are rerun on the installed wheel. The
three installed packages are byte-checked against their immutable artifacts;
the Nexus nonstatic source is also compared with its wheel. No schema, Core
artifact or Connector change is included.

NS15.03 remains partial: implicit legacy selection, boot, delivery, connection-key
opening and event projection consumers still require cutover before deleting
the native loaders/codecs. Domain and historical recovery remain present.
Normative TR4-15-03, M12 and release gates are not closed by this increment.
