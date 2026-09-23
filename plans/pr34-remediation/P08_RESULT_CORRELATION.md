# P08 — durable transport attempt/event correlation

2026-09-23, Windows. Parent SHA 30f340c, feature/v0.2.0. Additive migration 035.
Final gate NOT PASSED; P08 remains IN_PROGRESS.

Behavioral baseline RED: a real scripted Codex pipe peer completed a canonical
delivery, but outbox stayed SENT_UNCONFIRMED with no linked terminal. Command:
`.venv/Scripts/python.exe -m pytest tests/test_runtime_result_correlation.py -q --tb=short`
1 FAIL, 9.10s; evidence/p08-result-correlation-red.log. No absent-schema/import
failure is used as the behavioral reproduction.

EnvelopeConnector event-correlation contract v2 registers operation/attempt/owner
epoch before native send, strips any inbound correlation attributes, and adds only
locally registered provenance. Native adapters provide a delivery_event_phase
hook, keeping protocol names out of application services. Codex requires matching
native thread/turn; Claude uses its observed init/result boundaries on an exclusive
delivery lane; Pi uses agent_start/agent_settled (turn_end is intermediate).
Attach has no invented acknowledgement or terminal. Legacy extensions without a
phase hook stay unconfirmed. There is no native ID invented for Pi/Claude.

Migration 035 adds correlation to harness_events/results and native IDs plus
terminal_event_id to the existing outbox. The journal retains its framed v1
format with additive optional event fields; old records deserialize with defaults.
Existing migration runner rejects packages older than an applied schema version;
do not reverse migration 035 destructively.

Projection validates connection, session, attempt, epoch, owner lease and native
IDs before changing transport state. Observed start sets ACCEPTED/HARNESS_ACCEPTED;
matching terminal links durable event/result. Completion here does not complete a
handoff, approve publication or mark logical inbox work consumed. Historical or
unmatched terminals remain captured without authority over a new operation.

Pending scans now fence SENT_UNCONFIRMED/ACCEPTED without a terminal. Terminal
projection wakes dispatch after commit. Owner loss moves unfinished SENDING,
SENT_UNCONFIRMED and ACCEPTED to OUTCOME_UNKNOWN; runtime loss does likewise.
Neither path frees logical consumption or blindly retries. Completed attempts
are not downgraded on owner loss. Checkpoint reset/replay does not duplicate results.

Files/symbols: domain HarnessCommand/HarnessEvent and transport transitions;
EnvelopeConnector; phase hooks in Codex/Pi/Claude; HarnessSupervisor.send;
build_dispatcher; RuntimeEventIngress.recover; SqliteHarnessEventRepo;
SqliteRuntimeJournalRepo._project_attempt; SqliteRuntimeOutboxRepo.pending/acquire_owner;
migration 035; production result/outbox/native campaign tests.

Commands through rtk proxy:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_result_correlation.py tests/test_runtime_outbox.py tests/test_runtime_event_journal.py tests/test_runtime_shared_connection.py tests/test_runtime_contracts.py tests/test_runtime_event_buffers.py tests/test_runtime_process_ownership.py -q --tb=short`

69 PASS, 59.74s; evidence/p08-result-correlation-gate.log. Initial narrower gate
34 PASS is evidence/p08-result-correlation-progress.log. Includes actual REST,
canonical inbox/outbox, pipe transport, journal and projector; stale native turn
terminal cannot release a new lane; matching interrupt permits queued delivery.

Fresh REAL isolated campaigns with previously explicitly configured executable
and auth-source paths from NATIVE_CAMPAIGN.md (no personal sessions/settings):

- `pytest tests/test_runtime_native_campaign.py -q -k codex --tb=short`:
  2 PASS, 1 deselected, 22.13s; evidence/p08-result-correlation-codex.log.
- `pytest tests/test_runtime_native_campaign.py -q -k claude_code --tb=short`:
  1 PASS, 2 deselected, 11.58s; evidence/p08-result-correlation-claude.log.

Two-turn campaigns additionally assert terminal operation/attempt correlation and
durable outbox linkage. Active-close test remains a separate Codex scenario.
Fixture finally removes temporary auth copies. Pi/attach native NOT_RUN. Ruff PASS.
The final small follow-up excludes correlated Pi intermediate turn_end from result
creation and expands takeover/replay checks; those are covered by the 69-test gate,
not a new Pi native campaign.

Remaining: assembled output/artifacts, canonical consumption receipts, authorized
notifications, durable controls/expected-turn fences, managed handoffs/approvals,
causal budgets, POSIX ownership and boot/shutdown/recovery. While a managed delivery
is active, uncorrelated steer/new-turn injection is refused; interrupt/end remain
available. Restoring correlated steering is a required control-operation unit,
not an accepted final loss of that capability. No phase marked VERIFIED.
