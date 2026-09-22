# P08 — journal and captured results checkpoint

Parent SHA: `93d5fab269e13aa766d970fb913554cb7376cc42`; branch `feature/v0.2.0`.
Implemented alongside the remaining P07 lifecycle work, as permitted by the
implementation plan. **Neither phase nor the final gate is complete.**

## Implemented production path

`build_service` composes `RuntimeEventIngress` and `FileRuntimeEventJournal` into
the supervisor used by REST, MCP and the serve dispatcher. Only the leased serve
owner starts the journal writer. Standalone stdio still forwards effects to that
owner. All journal reads, writes and fsync occur outside SQLite transactions.

The journal uses an exclusive OS writer lock, a store UUID, monotonically numbered
segments, bounded frame length, CRC32, an ordinal, stable event UID and per-session
sequence. Every record is fsynced before capture returns, including deltas; this
version trades batching throughput for a simpler durability boundary. Defaults:
1 MiB maximum record, 4 MiB segment target, 64 MiB retained bytes, sixteen records
per projector batch. Retention never deletes captured data to admit new output.
Quota/fsync failure stops new runtime admissions and sends. Startup truncates only
an incomplete final frame, counts that repair and rejects complete checksum
corruption, interior truncation, identity mismatch and segment/ordinal gaps.

Files use fixed generated names, regular-file/hardlink/reparse checks and owner
permissions. Redaction v1 removes known credential keys and Nexus/API/Bearer token
patterns before bytes are written. This is not a claim that arbitrary secrets in
natural-language model output can be detected. POSIX directory fsync is explicit;
power-loss qualification on each filesystem/platform remains pending.

Additive migration **033** introduces `runtime_journal_checkpoint` and
`runtime_results`. The projector atomically inserts the existing `harness_events`
row, captures a terminal result and advances the checkpoint. SQLite failure leaves
the journal pending for recovery. A result is initially `PENDING_AUTHORIZATION`:
capture does not authorize a message, task or handoff transition. Automatic legacy
broadcast of every terminal event is replaced on this production path; authorized
result publication/correlation remains a required next dependency, not a final
feature-disable workaround.

`HarnessEvent` now exposes its existing durable `event_id` and `sequence` through
replay and both surfaces. Event IDs detect conflicting replays. Canonical result
projection is idempotent even when a checkpoint is lost. Replay validates cursor
and bounded limits. Existing migrations 029–032 are unchanged. Managed SQLite
connections validate FULL-or-stronger synchronous mode without silently changing
the default configuration.

## Executed checks

- `.venv/Scripts/python.exe -m pytest tests/test_runtime_event_journal.py tests/test_pr34_remediation.py -q -k 'journal or replay_keeps or terminal_storage'`
  — **10 passed, 34 deselected**, `evidence/p08-journal-progress.log`.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_event_journal.py tests/test_runtime_process_ownership.py tests/test_runtime_outbox.py tests/test_runtime_grants.py tests/test_runtime_endpoints.py tests/test_pr34_remediation.py tests/test_import_boundary.py -q -k 'not expired_relay'`
  — **96 passed, 1 deselected**, 108.27s, `evidence/p08-integrated-gate.log`.
  The remaining excluded relay regression is explicitly pending P10.
- After adding checkpoint-loss and pagination cases:
  `.venv/Scripts/python.exe -m pytest tests/test_runtime_event_journal.py -q`
  — **10 passed**, `evidence/p08-journal-expanded.log`.
- Ruff on changed Python source/tests: PASS.

Tests use real files, fsync, OS file locks and disposable SQLite stores; projection
faults are injected around the actual UoW. Evidence includes real REST composition,
an unavailable event repository, rollback after result insertion, reopen/recovery,
duplicate checkpoint replay, equal text with distinct IDs, checksum damage,
incomplete tail, quota, fsync error, redaction, hardlink refusal, concurrent append
between replay pages and an instrumented no-fsync-inside-write-UoW check.

## Required follow-up / limits

- Complete process-kill cuts, scheduler pressure and recovery with open native
  turns. The current tests do not constitute the entire T-JRN matrix.
- Durable operation/native-turn/claim/root correlation, outbox outcome projection,
  result materialization from all delta shapes, artifacts and authorized
  notification intents are pending. A captured result does not yet mark a delivery
  consumed or a handoff complete.
- Publish watermark/repair/quota diagnostics, safe retention administration and
  storage-health recovery. Tail repair is counted internally, not yet surfaced in
  operator diagnostics. Bound all native adapter histories and queues as P07
  requires; the journal's own quota does not prove those buffers bounded.
- Finish lifecycle drain before releasing correlation, shared Codex connections,
  and stop-observed versus detached/unknown transitions. The existing legacy
  supervisor terminal-state path still needs replacement.
- Native replay deduplication is not invented: journal projection is idempotent,
  but a protocol without a stable native replay identity has no native-dedupe claim.

Real Codex and Claude stream two-turn results are separately documented in
`NATIVE_CAMPAIGN.md`. They do not close these pending gates.
