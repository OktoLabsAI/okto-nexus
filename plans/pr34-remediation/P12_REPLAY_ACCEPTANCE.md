# Public replay pagination and error parity

2026-09-24; parent8ec25f54e076083d11557649c3e61a39fa78f1e5 plus source/test hashes. The RED parent fe2801e had identical routes.py; the intervening milestone changed only other tests/docs.

New test_runtime_replay_acceptance.py checks REST and MCP pages while a bounded worker appends after the first page. Sequences1..5 appear exactly once; cursor5 returns empty. Compacting the file journal preserves the projected SQLite replay at cursor0. Unauthorized readers get opaque denial at old/current cursors. Existing journal-retention tests prove an expired internal file cursor is rejected rather than silently skipping compacted records. Public projected cursors are retained by this implementation; file retention is not public replay deletion.

Four invalid cursor/limit cases exposed the REST replay call outside its OktoNexusError handler. MCP returned VALIDATION_ERROR; REST returned INTERNAL/HTTP500. The narrow correction catches that same domain error with the existing REST mapper. Authorization remains before replay validation, tested as403 for foreign callers. No schema, retention or cursor contract changed.

Initial Windows8081:2 PASS4 FAIL21.83s. Three failures manifested as a reset on the subsequent MCP request after REST's uncaught exception; one directly asserted500 versus422. Reordered only those test requests to run MCP first, without changing production. Windows3214:2 PASS4 FAIL20.27s, now all four failures directly prove REST500 versus422. Both raw XMLs remain locally under .git/pr34-evidence; the second RED has sanitized per-node evidence and source hashes.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=no --junitxml=.git/pr34-evidence/replay-fe2801e-red2-windows.xml tests/test_runtime_replay_acceptance.py
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=.git/pr34-evidence/replay-8ec25f5-windows.xml tests/test_runtime_replay_acceptance.py tests/test_runtime_event_journal.py tests/test_runtime_journal_retention.py tests/test_runtime_read_audience.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short --junitxml=.git/pr34-evidence/replay-8ec25f5-linux.xml tests/test_runtime_replay_acceptance.py tests/test_runtime_event_journal.py tests/test_runtime_journal_retention.py tests/test_runtime_read_audience.py
rtk proxy ruff check src/okto_nexus/adapters/inbound/http/routes.py tests/test_runtime_replay_acceptance.py
rtk git diff --check
```

Windows81443:26 PASS47.90s/Linux88716:26 PASS54.25s, both exit0. Ruff and diff-check PASS. Required isolated live stdio MCP smoke PASS exit0/LIVE E2E RESULT: PASS, using exactly the launcher in P12_PAYLOAD_BOUNDARIES.md; new log C:/Users/jpamb/AppData/Local/Temp/okto-pr34-live-smoke-v76a4d9n/result.log. No native provider campaign.

Persistent XMLs reduced with parent and source/test hashes; each mapped node and parameter must PASS on both. T-JRN-11 scoped PASS. No current processes. Full matrix, lifecycle pressure/leaks, comparative performance and release remain open.
