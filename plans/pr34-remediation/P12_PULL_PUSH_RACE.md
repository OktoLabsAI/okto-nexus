# P12 — canonical pull/push contention

Parent `d8e237d37d2fa1430df05c12d6cd95f4fe251934` plus per-generation test hashes in `evidence/p12-pull-push-index.json`. Production unchanged.

T-CONS-01: authenticated HTTP-mounted MCP message creation pauses its real SQLite writer transaction immediately before or after SqliteRuntimeOutboxRepo.enqueue reserves the already-created logical delivery. An independent worker invokes the actual InboxService built by the production MCP composition, using the same repositories/database. SQLite trace proves its BEGIN IMMEDIATE reaches the competing writer while admission is paused; the pull future cannot complete. After commit it returns no payload. Exactly one push operation and one synthetic peer send exist; the same logical delivery remains push-owned with zero inbox attempts and no pull lease. A subsequent authenticated MCP pull also receives nothing. No reservation, SQL result or consumer response is mocked.

This is a deterministic canonical use-case concurrency test, not two simultaneously executing HTTP handlers and not a native-provider campaign. The extra worker is test-only; production concurrency is unchanged.

Preparation: initial Windows2 FAIL21.59s/Linux2 FAIL38.51s did not reach the pull barrier. Moving the pause after authentication still yielded Windows2 FAIL23.33s/Linux2 FAIL37.03s: the held synchronous MCP handler blocks its event loop, preventing the second HTTP call from entering. The final test invokes the wired canonical pull independently to reach real SQLite contention. These are test-scheduling failures, not product regressions; no authentication or locking was relaxed. All four failure manifests retain their own source generation hash.

Exact chronological commands:
```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_pull_push_race.py -q --junitxml=.git/pr34-evidence/pull-push-race-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_pull_push_race.py -q --junitxml=.git/pr34-evidence/pull-push-race-linux.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_pull_push_race.py -q --junitxml=.git/pr34-evidence/pull-push-final-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_pull_push_race.py -q --junitxml=.git/pr34-evidence/pull-push-final-linux.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_pull_push_race.py -q --junitxml=.git/pr34-evidence/pull-push-verified-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_pull_push_race.py -q --junitxml=.git/pr34-evidence/pull-push-verified-linux.xml
rtk proxy ruff check tests/test_runtime_pull_push_race.py
rtk git diff --check
```

Final terminal exit0: Windows65191 **2 PASS13.03s**, Linux50087 **2 PASS17.85s**. Ruff PASS; no final failures/skips. Raw XML under .git/pr34-evidence, sanitized per-node records in index.

Original matrix117 PASS/12 NOT_RUN; final gate NOT PASSED. Continue remaining matrix, final immutable-source suites, findings/release audit and reinstall0.2.0. Native Pi/attach remain NOT_RUN.
