# P08 — materialized output and canonical consumption

2026-09-23, Windows, feature/v0.2.0. Parent SHA 924c3ef. Additive migration 036.
P08 IN_PROGRESS; final gate NOT PASSED.

Baseline behavioral reproduction used the existing correlated native pipe path:
outbox had a terminal, but the logical delivery stayed unread/reserved. Command
`.venv/Scripts/python.exe -m pytest tests/test_runtime_result_correlation.py -q -k terminal_is --tb=short`:
1 FAIL, 1 deselected, 3.37s; evidence/p08-consumption-materialization-red.log.

Native adapter delivery_output hooks normalize supported text deltas/snapshots.
EnvelopeConnector strips inbound derived fields and uses these local hooks.
Journal redaction now covers output_text before filesystem persistence, using the
same explicitly bounded secret-pattern policy as native payload redaction.
Migration 036 stores optional normalized event text/snapshot and derived result
text, truncation marker and source-event count. Projector materialization streams
rows in sequence and caps derived UTF-8 text at 1 MiB. Source journal/events remain
durable; truncation is explicit. A complete final snapshot replaces prior deltas.
This materializes supported textual output, not arbitrary native file artifacts.

RuntimeEventIngress invokes InboxService.consume_runtime_terminal inside the
same UoW as event/result/checkpoint projection. SqliteMessageDeliveryRepo performs
CAS requiring matching push reservation, accepted outbox attempt, correlated
runtime_result and exact terminal event. Existing inbox receipts are reused with
ack_source=native_terminal, ack_level=HARNESS_ACCEPTED, human_read=false and
operation/event IDs. Legacy `read` status here means runtime processing observed;
it is not proof of human reading, successful task execution or handoff completion.
Receipt messages remain non-executing logical inbox notifications, preserving the
core receipt-loop guard. Replaying cannot create duplicate consumption/receipts.

Symbols/files: three native delivery_output hooks; EnvelopeConnector;
HarnessEvent optional fields; FileRuntimeEventJournal.append; migration 036;
SqliteHarnessEventRepo; SqliteRuntimeJournalRepo._materialize_output;
SqliteMessageDeliveryRepo.mark_runtime_processed and port; InboxService internal
consumption/receipt helpers; RuntimeEventIngress callback; build_service wiring.

Commands via rtk proxy:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_result_correlation.py tests/test_runtime_event_journal.py tests/test_inbox_service.py tests/test_receipts.py tests/test_runtime_outbox.py tests/test_import_boundary.py -q --tb=short`

75 PASS, 57.85s; evidence/p08-consumption-materialization-gate.log. Earlier narrower
57 PASS in 14.09s recorded in evidence/p08-consumption-materialization-progress.log.
Tests include two native pipe turns, concurrent next-lane admission, stale terminal,
checkpoint reset, failure after receipt creation rolling back the entire projection,
successful later journal recovery, and 1.2 MB native text with explicit 1 MiB derived
truncation. Normalized secret-like fixture text is absent from persisted segments.

Fresh REAL isolated native campaigns using the explicit paths/configuration in
NATIVE_CAMPAIGN.md (auth cleanup in fixture finally):

- `pytest tests/test_runtime_native_campaign.py -q -k codex --tb=short`:
  2 PASS, 1 deselected, 20.71s; evidence/p08-consumption-materialization-codex.log.
- `pytest tests/test_runtime_native_campaign.py -q -k claude_code --tb=short`:
  1 PASS, 2 deselected, 12.92s; evidence/p08-consumption-materialization-claude.log.

Two-turn campaigns now require nonempty untruncated result text and two consumed
push deliveries, in addition to identity/transport/journal checks. Pi and attach
native NOT_RUN. Ruff passed on changed application/adapter/test paths.

Remaining: authorized result publication, artifact integration, durable controls,
scoped bootstrap/claims/approvals, persistent causal budgets, administration and
retention. POSIX birth ownership and global shutdown/boot recovery are still open.
No managed handoff completion, native control campaign or full-matrix claim.
