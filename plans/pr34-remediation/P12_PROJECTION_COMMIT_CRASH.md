# P12 — projection commit crash and stable event replay

Source `a7353b0fc1857d66d4589d2b82a0047760917fc8` plus changed file hashes in `evidence/p12-projection-commit-index.json`. Production unchanged; branch feature/v0.2.0.

## Contract mapping and evidence

T-JRN-03: the logical external checkpoint in the plan maps to `runtime_journal_checkpoint`, committed in the same SQLite transaction as canonical projection, result and processing receipt. Production cannot split these commits. The process fixture waits for the real recover call to return, reads committed state from an independent UoW, closes it, writes a marker outside SQLite, then terminates the real owner with os._exit(77). Result publication alone is held until restart. The owned native protocol process is witnessed dead before recovery.

Two variants restart the actual Nexus composition on the same store: normal committed checkpoint and a deliberately rewound checkpoint on the stopped disposable store. The latter forces the stronger replay stimulus even though ordinary production cannot create that split. Both preserve one event, original result ID/text/attempt, one processing receipt and one publication, with no second native process or send. T-JRN-07 is qualified for replay of the same stable Nexus event_uid after restart, including exact original attempt correlation. This does not claim native reconnect/resume support, native reference deduplication or deduplication of newly captured wire frames: capture mints a fresh event UID.

## Commands and outcomes

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_projection_commit_crash.py -q --junitxml=.git/pr34-evidence/projection-commit-initial-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_projection_commit_crash.py -q --junitxml=.git/pr34-evidence/projection-commit-initial-linux.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_commit_crash.py tests/test_runtime_relay_process_restart.py -q --junitxml=.git/pr34-evidence/projection-commit-regression-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_commit_crash.py tests/test_runtime_relay_process_restart.py -q --junitxml=.git/pr34-evidence/projection-commit-regression-linux.xml
rtk proxy ruff check tests/runtime_relay_process_fixture.py tests/test_runtime_projection_commit_crash.py
rtk git diff --check
```

All four process handles terminal exit0: initial Windows49437 **2 PASS17.41s**, Linux52386 **2 PASS31.51s**; regression Windows90174 **6 PASS73.66s**, Linux73965 **6 PASS115.92s**. Eight distinct fixture nodes per platform; Ruff PASS. No native provider campaign, no production migration or contract change. Sanitized per-node manifests and exact requirement joins are in the index; raw XML stays under .git/pr34-evidence.

Next: remaining matrix, immutable-source full suites and release gates. Final gate remains NOT PASSED; native Pi and attach remain NOT_RUN.
