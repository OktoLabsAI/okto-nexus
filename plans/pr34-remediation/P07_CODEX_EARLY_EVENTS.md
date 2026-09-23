# P07 — bounded Codex early notification attribution

Execution 2026-09-23, Windows; parent SHA bac6f71870a8326979e04aa4b569b0f036600302.
Branch feature/v0.2.0. No schema change. Final gate NOT PASSED.

The cache for notifications received before thread/start replies was unbounded
by both count and bytes. Unknown thread IDs could accumulate for the lifetime of
the connection. Two behavioral reproductions failed before the fix:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_codex_early_events.py -q --tb=short`

Result: 2 FAIL; evidence/p07-codex-early-events-red.log. Failure is missing bounded
rejection after actual notification ingestion, not a missing import or mock API.

codex.py now limits the connection-wide early cache to 128 events and 1 MiB of
serialized UTF-8 notification content. This is not an exact Python RSS limit.
EarlyEventLimitExceeded latches the fault; the native reader kills its owned
process, emits transport/dispatch_error without raw content, and releases pending
requests on exit. It neither retries nor fabricates a terminal event. All sessions
on that connection share the failure's blast radius. A failure during initial
opening propagates through startup rather than claiming a healthy session.

Registration releases cache accounting and replays through _on_notification under
the existing RLock, before later notifications can overtake replay. This also
restores early turn state; previously replay published events without updating it.

Changed symbols: EarlyEventLimitExceeded, _CodexTransport._read_stdout,
CodexAppServerConnector.start/_emit_for_thread/_early_event_size.
Tests: tests/test_runtime_codex_early_events.py. Existing production composition
used in integrated test: REST authorization, supervisor, native pipe transport,
owned process, journal and replay; only the external CLI is a scripted Python peer.

Validation command:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_codex_early_events.py tests/test_runtime_shared_connection.py tests/test_runtime_protocol_limits.py tests/test_runtime_event_buffers.py tests/test_runtime_event_journal.py tests/test_harness_codex_connector.py -q --tb=short`

75 PASS, 1 skipped in 42.90s; evidence/p07-codex-early-events-gate.log. Covers count
and byte pressure, early active-turn replay/accounting, and actual REST flooding
with owned-process reaping and a stable durable fault, without fake completion.
The skipped legacy native case is NOT_RUN.

Fresh REAL Codex campaign using the explicit executable and login-source paths
documented in NATIVE_CAMPAIGN.md, isolated temporary project/config/store:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_native_campaign.py -q -k codex --tb=short`

2 PASS, 1 deselected in 14.67s; evidence/p07-codex-early-events-native.log.
Canonical two-turn delivery and active-close interruption only. Authentication
copy cleanup remains in the fixture's finally block. This is not native unknown
thread pressure evidence: that fault is deliberately injected by the pipe peer.
Claude, Pi and attach native were NOT_RUN in this unit; previous scoped Claude
results remain historical evidence. Ruff for changed Python and git diff --check
PASS.

Remaining dependencies: Codex lifetime session bookkeeping, Claude pending-turn
admission, global shutdown budget, POSIX birth ownership, boot/recovery, durable
control and result correlation. P07 and aggregate pressure gate remain IN_PROGRESS
and NOT_RUN respectively. No approval, sandbox, identity or migration relaxation.
