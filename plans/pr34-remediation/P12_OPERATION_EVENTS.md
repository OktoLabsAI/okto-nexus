# P12 — operation states, pushed facts and public replay

Parent `d178ddf3fe2f933bb83c4b59fda6346ee53de749` plus exact test hash in `evidence/p12-operation-events-index.json`; production unchanged.

T-API-05 has two complementary paths through actual authenticated surfaces. First, pause the bounded command worker before execution: admission returns operation_id, PENDING, durable=true and external_acceptance=not_observed, with no peer send yet. Release the worker, wait for its real execution/commit return and read once: SENT_UNCONFIRMED, no observed acceptance and no durable result. The synthetic peer wrote once but emitted no confirmation.

Second, send TRIGGER_HOLD to an actual owned synthetic Codex protocol process. The test waits on the production subscriber registry callback after durable projection, then inspects ACCEPTED/harness_accepted without a result. Authenticated interrupt targets the exact operation/native turn; a pushed terminal event precedes the single final inspection with result_durable=true. Public MCP replay retains started and terminal with matching operation/attempt, event IDs and nonzero sequences. After handshake, an observer around the actual native writer records exactly turn/start and turn/interrupt: no status/read polling. Subscriber callbacks never query or wait; test waits are outside production callbacks and SQLite UoWs.

Transport state ACCEPTED plus a durable correlated terminal/result is the existing final-result representation; the test does not invent a DONE state or conflate interrupted terminal output with completed handoff. The first path covers unconfirmed transport, while the second covers observed native facts. This is not a native-provider campaign or a claim that all Nexus reads use streaming.

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_operation_events.py -q --junitxml=.git/pr34-evidence/operation-events-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_operation_events.py -q --junitxml=.git/pr34-evidence/operation-events-linux.xml
rtk proxy ruff check tests/test_runtime_operation_events.py
rtk git diff --check
```

Terminal exit0: Windows81774 **2 PASS10.50s**, Linux61548 **2 PASS16.52s**, no failures/skips. Ruff PASS. Per-node manifests in index; raw XML under .git/pr34-evidence.

Original matrix122 PASS/7 NOT_RUN. Final gate NOT PASSED. Remaining: mirror observer, journal/storage exhaustion, external authenticated attach work, native E2E01/02, final actual-composition join/report, full suites and release/reinstall0.2.0.
