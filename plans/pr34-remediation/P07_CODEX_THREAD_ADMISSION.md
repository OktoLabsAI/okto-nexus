# P07 — bounded lifetime Codex thread admission

2026-09-23, Windows, feature/v0.2.0. Parent SHA 075ea86. No migration.

Codex kept ended-thread attribution intentionally, so deleting old mappings to
limit memory would misclassify late events as unowned startup notifications.
The connector now admits at most 64 lifetime thread/start attempts per connection.
The existing startup lock reserves each slot before native IO. Rejections use
CONFLICT with reason connection_thread_capacity. Existing sessions remain usable;
new sessions need a fresh connection. No existing prompt is replayed automatically.
Unknown outcomes consume capacity: a timeout is not evidence of no allocation.
An early-event overflow also rejects subsequent starts before more native IO.

This bounds local thread/session attribution and concurrent startup bookkeeping,
not a provider's total remote storage. It complements the supervisor's stricter
live runtime cap and the native history/queue limits. Startup-handshake failure
before any thread/start attempt does not consume a thread slot.

Symbols: CodexAppServerConnector.__init__/start; _THREAD_START_LIMIT.
Tests: tests/test_runtime_codex_early_events.py. Eight concurrent fixture callers
attempt 80 real pipe handshakes; exactly 64 writes reach the scripted native peer.
A second real-pipe test withholds 63 replies after one successful session and
proves uncertain starts do not recycle slots or leak pending request entries.

Commands/results:

- `.venv/Scripts/python.exe -m pytest tests/test_runtime_codex_early_events.py -q -k admission --tb=short`:
  behavioral RED, 1 FAIL (80 sessions admitted instead of 64), 4 deselected;
  evidence/p07-codex-thread-admission-red.log.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_codex_early_events.py tests/test_harness_codex_connector.py tests/test_runtime_shared_connection.py -q --tb=short`:
  45 PASS, 1 skipped in 35.61s; evidence/p07-codex-thread-admission-gate.log.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_codex_early_events.py -q --tb=short`:
  expanded 6 PASS in 6.68s; evidence/p07-codex-thread-admission-expanded.log.

Commands after receiving the user's RTK.md instruction run through rtk proxy.
All peers are temporary Python subprocesses, not model calls. Native campaigns
NOT_RUN for this subsequent unit; previous native results have their own SHA.

P07 remains IN_PROGRESS. Next dependencies: Claude pending-turn admission,
global shutdown budget, POSIX birth ownership, boot/recovery and durable control
and result correlation. Full matrix/final gate NOT PASSED.
