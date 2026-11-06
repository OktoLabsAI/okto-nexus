# PR-05 — internal coordination receipt persistence

Date: 2026-11-06. Fixed R3 plan unchanged. This increment prepares DX-10 for
participant coordination and PR-05; it does **not** expose safe replay through
message/handoff tools or the CLI yet. PR-04 cooperation and full R3 remain open.

## Implemented contract

- Migration 159 adds a minimal receipt keyed by persisted Server installation,
  authenticated-actor scope supplied by the use case, workspace, operation and
  `client_request_id`. The ID grammar is bounded ASCII; the operation vocabulary
  is `message_create` / `handoff_create`.
- Explicit hash builders cover normalized target, content and relevant context,
  including session provenance, explicit effective trace, reply behavior,
  verification and dependencies. They have no credential parameters. Raw inbound
  requests must not be passed as hash inputs; normalization remains the canonical
  use case's responsibility. Generated traces are not request intent.
- The repository uses only the caller's active write UoW, with no nested
  connection, commit, network or process. Lookup precedes effects; recording
  follows the canonical resource/approval creation in the same transaction.
  Recording a second resource for an existing intent conflicts and rolls back
  the caller's transaction. The repository cannot itself authorize a caller.
- Receipts store references and hashes, not body/payload copies, secrets or
  authorization grants. An approval receipt can advance to the created object
  only with the original approval ID, matching actor/workspace/action, approved
  state and matching resource scope. Its original deadline is preserved.
- Retention is fixed at 30 days from first recording. Replay lookup rejects a
  mismatched hash, expired receipt or a clock preceding creation. Receipt reads
  distinguish pending, approved-awaiting-execution, rejected, archived, missing
  approval, created, resource-removed and expired. Creation does not prove work
  completion or delivery. Missing resources cannot be substituted within the
  window. References deliberately do not cascade with resource deletion.
- The existing bounded retention service and `admin prune` include expired
  receipts, with readonly dry runs and per-table batch budgets. Message retention
  may remove a message earlier; its receipt remains a tombstone until expiry.
  Pending approval references also expire without deleting/deciding the approval.
  After pruning, absence is not proof that an old request never committed.

## Validation

Final validation passed **73 source tests and 104 installed tests** (overlapping
suites), plus one actual installed CLI invocation. The initial source report
has 66 passes/one architecture failure; the first installed report has 84
passes/two fixture-path failures. Both are preserved, with the initial wheel.

Final wheel: `okto_nexus-0.3.3-py3-none-any.whl`, SHA-256
`8f63b5d594d8359611eccede133e293fb55a7e3b12bcfa988bcb0e5b5c91e372`.
All 451 Python files, seven static assets and 159 SQL resources match source
bytes. The isolated campaign is
`C:\Users\jpamb\AppData\Local\Temp\r3-coordination-receipts-hny1f969`;
the final wheel/venv are in its `final` directory. Adjacent XML/JSON files
retain the test and artifact metadata.

Tests use real migrated SQLite databases and canonical repository composition,
with an explicitly test-only submit driver. They exercise:

- rollback before/after receipt recording for messages and handoffs;
- eight racing independent connection factories, one canonical object/receipt;
- process termination with `os._exit` immediately before/after commit and
  recovery from a new connection without another canonical object;
- request hash conflict; actor/workspace/operation/installation separation;
- pending approval reuse, transaction rollback during resolution, immutable
  approval correlation/deadline and rejection of missing/rejected/archived or
  expired approval execution;
- actual message pruning before receipt expiry; resource-removed tombstone;
- exact expiry boundary, dry-run passivity, two-row bounded prune batches;
- upgrade from schema 158 to 159 preserving messages, approvals and installation;
- secret-free receipt columns, explicit semantic inputs and malformed input refusal.

The initial source run found an existing application-layer `sqlite3` import in
the post-commit binding policy refresh. It was removed: all refresh exceptions
now preserve the committed/activation-pending outcome and original cause. The
existing HTTP recovery test covers OSError, SQLite OperationalError and
RuntimeError, including a later policy disable and a revoked grant; replay
does not regrant. The architecture test now scans the imported package, making
its scope correct both in source and an installed wheel. Initial failed reports
and the corresponding first wheel metadata are retained separately.

Installed validation uses a fresh venv, `python -I`, copied tests outside the
checkout and the built wheel. Python, static and all SQL resources are compared
byte for byte. The actual installed `okto-nexus admin prune --dry-run` also
bootstrapped an isolated home at schema 159 and reported the receipt window.
No provider inference, personal credential/configuration or service registration
was used. Connector/Core did not change.

## Remaining integration gates

DX-10 remains **IN_PROGRESS**. Message/handoff create, their MCP schemas and
approval execution have not yet been connected to these primitives. Before
advertising retry, integration must revalidate current authenticated actor and
visibility before lookup, preserve original approved authority and session
provenance, hash normalized intent before generated context, and finalize the
receipt with canonical inbox/outbox/events/accounting in the same transaction.
The current approval path has separate decision/execution/result transactions;
its crash recovery must be completed and tested through the real use cases.

The thin facade still needs request-ID checkpointing before transmission,
authenticated recovery by the same ID, old-Server capability diagnostics and
refusal of automatic replay outside the original window. Correlated wait and
optional directed-message/handoff cooperation remain unimplemented. These
requirements are unchanged parts of DX-08/09/10/11, not new acceptance targets.
Current authorization, runtime outbox/accounting, transport loss and CLI behavior
are not certified by this repository-level campaign.
