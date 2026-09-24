# Owner death between canonical commit and wake

2026-09-24; feature/v0.2.0; parent6c710ea1e300f0acad26e42a94f33ff233e1cba4 plus changed-test hashes. No production changes.

T-TX-02 now has the exact process stimulus. A disposable production HTTP owner accepts message_create over MCP with the integration explicitly enabled and a conversation endpoint approved. Only dispatch selection is held before the cut, so it cannot race the post-commit observation. The real admission transaction persists message, delivery and outbox. Before calling the actual wake function, a separate read transaction observes all three records, then os._exit(76) kills the entire owner. The caller does not resend after its connection is lost.

The parent proves the process exited at that cut and reads the PENDING operation with no attempt and no native spawn/write. A fresh production owner on the same temporary store recovers that operation, opens a synthetic Codex protocol process on demand and reaches ACCEPTED plus a terminal event. It preserves the operation ID and single original delivery; native wire records show exactly one send. Foreign keys remain valid. An exact process witness confirms the recovered owner's child is reaped on shutdown. No account, installed provider, external endpoint or operator credential is passed to the peer.

Initial Windows50785:1 FAIL20.48s because the fixture endpoint defaulted to explicit response policy; no outbox intent existed, so the post-commit wake cut was never reached. Set response_policy=conversation explicitly. Next:1 FAIL4.94s because Windows reported the expected abrupt disconnect as httpx.ReadError rather than RemoteProtocolError; handle both, with exit-code and durable-store assertions still mandatory. Windows78124:1 PASS9.12s. These are fixture corrections, not product REDs.

The shared relay process fixture adds a cut only for message_commit; existing journal-terminal, committed-child and accepted-child cuts retain their behavior. Expanded regression runs both the new test and existing cross-process relay restart module.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=.git/pr34-evidence/commit-crash-6c710ea-windows.xml tests/test_runtime_commit_crash.py tests/test_runtime_relay_process_restart.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short --junitxml=.git/pr34-evidence/commit-crash-6c710ea-linux.xml tests/test_runtime_commit_crash.py tests/test_runtime_relay_process_restart.py
rtk proxy ruff check tests/test_runtime_commit_crash.py tests/runtime_relay_process_fixture.py
```

Ruff PASS. Terminal results and per-node manifests recorded below. This is a real process crash at a controlled cut, not a scheduler-pressure/SIGKILL campaign or a benchmark. Full lifecycle/load/performance gates remain separate.

Expanded Windows54399:6 PASS71.30s/Linux24226:6 PASS122.99s, both exit0. Persistent XMLs reduced; mapped node verified PASS on both, with parent and changed-file hashes. Existing relay crash/restart cases remain green. T-TX-02 scoped PASS; no production change.
