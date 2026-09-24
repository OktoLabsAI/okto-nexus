# Canonical identity and failed startup acceptance

2026-09-24; feature/v0.2.0; parent e3326adcea286a297ae7a86c82d1633052dee3ac plus the test-file hashes in evidence/p12-identity-failure.json. Production unchanged.

T-ID-05: actual REST and MCP reject unknown capabilities before changing the canonical profile; both accept registered skills. Runtime opening and closing an existing agent preserve every profile field and the complete capability catalogue. Authentication activity last_seen_at is excluded from the cross-actor snapshot because authentication legitimately updates it.

T-ID-06: actual Codex transport launches an owned disposable Python peer. Successful handshake is followed by invalid initial session state or an injected SQLite failure after the real session insert, on REST and MCP. Each case waits on the exact Popen handle to prove process termination, finds no runtime session/presence or ghost identity, checks foreign keys, and proves the repeated open key does not spawn again. The separate handshake-timeout production REST case now compares every worker identity column and total agent count. Recovery tests cover existing startup/restart fences. No native provider calls or account configuration.

Initial Windows85961: 5 FAIL16.10s from comparing the authenticated actor's last_seen_at, after the process-reap assertions already passed. This was an invalid fixture assertion, not a product defect. Fixed that comparison and used the actual capability_names table rather than a guessed logical name; no table error was observed. Windows44962 then 5 PASS16.45s. The final timeout identity assertions were added before the expanded selections below.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=.git/pr34-evidence/identity-e3326ad-windows.xml tests/test_runtime_identity_failure_acceptance.py tests/test_runtime_process_ownership.py::test_rest_owner_start_timeout_has_no_running_session tests/test_runtime_session_recovery.py tests/test_capability_catalog.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short --junitxml=.git/pr34-evidence/identity-e3326ad-linux.xml tests/test_runtime_identity_failure_acceptance.py tests/test_runtime_process_ownership.py::test_rest_owner_start_timeout_has_no_running_session tests/test_runtime_session_recovery.py tests/test_capability_catalog.py
rtk proxy ruff check tests/test_runtime_identity_failure_acceptance.py tests/test_runtime_process_ownership.py
```

Windows52884: 48 PASS48.41s, exit0, one existing Starlette/httpx deprecation warning. Ruff PASS. Linux execution pending at document creation; terminal outcome recorded below. This scoped gate does not qualify load, performance, native campaigns or the complete plan.

Linux51026: 48 PASS69.93s, exit0, same deprecation warning. Both persistent XMLs reduced; each mapped node and all its parameters required to exist and PASS on both. Sanitized manifests include parent SHA and changed-file hashes. T-ID-05/06 scoped PASS. No live test processes remain.
