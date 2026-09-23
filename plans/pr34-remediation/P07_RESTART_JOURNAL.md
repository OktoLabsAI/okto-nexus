# P07/P08 — Recover captured attempts across owner changes

2026-09-23. Parent fd75ef1, feature/v0.2.0. Additive migration 037.
Partial restart work; phase/final gates remain open.

Two behavioral REDs showed a terminal already fsynced in the journal losing its
operation linkage after takeover changed ACCEPTED/SENT_UNCONFIRMED to UNKNOWN.
The cuts block database projection at native started or terminal; no missing API
or fabricated peer acknowledgement is involved. See evidence/p07-restart-red.log.

The dispatcher opens the exclusive journal without projecting, persists a frozen
store-id/watermark boundary for its new epoch, then recovers batches before
admitting dispatch. The projector can reconcile an exact previous operation,
attempt, session, connection and native turn within that boundary. It does not
authorize the old worker to write or execute again. A captured start is still
required before a terminal; already accepted native IDs survive partial recovery.
Matching results materialize and consume the canonical delivery atomically with
the existing receipt. Captured acceptance without a terminal returns to UNKNOWN.

The boundary can be set only once per owner epoch. A late old-attempt terminal
beyond it stays uncorrelated/UNKNOWN, with its event/result still retained. Every
batch renews the current owner's lease. Recovery has a 30-second startup budget;
failure preserves the checkpoint and fails startup instead of enabling effects.
No process, filesystem read or credential resolution occurs inside the write UoW.

Migration 037 adds recovery_store_id/recovery_watermark to the existing owner row;
no new execution queue or duplicate Operation table. Changed symbols:
RuntimeDispatcher.start; RuntimeEventIngress.start(recover=False);
SqliteRuntimeOutboxRepo.set_recovery_boundary/finish_recovery;
SqliteRuntimeJournalRepo._project_attempt. Journal and envelope format remain v1.

Evidence:

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_restart.py --tb=short`
  before correction: 2 FAIL, 5.71s, both with terminal_event_id=None after takeover.
- Expanded restart plus outbox/journal tests: 30 PASS, 40.30s (interactive run).
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_restart.py tests/test_runtime_shutdown.py tests/test_runtime_wake_generation.py tests/test_runtime_outbox.py tests/test_runtime_shared_connection.py tests/test_runtime_process_ownership.py tests/test_runtime_result_correlation.py tests/test_runtime_event_journal.py tests/test_import_boundary.py`
  — 60 PASS, 95.12s; evidence/p07-restart-gate.log.
- Ruff on changed Python files and `git diff --check`: PASS.

Restart tests use actual composition, SQLite, journal and disposable Codex JSON-RPC
pipes, including 40 output fragments across projection batches. They explicitly
close the fixture process before opening a new composition: these are durable-cut
recovery tests, not a claim that a new SIGKILL campaign ran. The late-event case
suppresses lifecycle observation to model an abrupt old-owner exit, then checks
that an event outside the persisted boundary cannot complete the operation.
No provider/model campaign in this unit: native Codex/Claude/Pi/attach NOT_RUN here.

Next: stale runtime session/owner epoch reconciliation, endpoint quarantine and
stable boot. Historical protocol_ready rows still require this next step; no
session liveness or prompt resume is inferred from replay. Native real crash cuts,
recovery administrative UX and full migration/compatibility matrix remain pending.
