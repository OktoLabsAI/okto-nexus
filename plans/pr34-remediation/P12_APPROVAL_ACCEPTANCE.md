# P12 — pending approval and repeated decisions

Parent `8cd0da5c36703dc29ede5de778015f412adb3268` plus exact new test hash in `evidence/p12-approval-acceptance-index.json`. Production unchanged, feature/v0.2.0.

T-TX-05: real authenticated MCP message creation under caller HITL policy returns pending approval. Independent SQLite reads find neither the requested message nor any executable outbox intent; the actual owned synthetic Codex protocol process has no turn/started event. Three concurrent authenticated operator REST decisions synchronize at a barrier: one approves, two receive CONFLICT. The approved canonical message produces one correlated durable native result. A subsequent approval also conflicts; another dispatcher scan preserves exactly one original message, one transport operation, one result and one observed native turn/started. Conflict on repeated decisions is the existing canonical approval contract, not a replay of the effect.

The fixture uses the production HTTP/MCP composition and actual connector/subprocess, with synthetic protocol output and temporary storage. It does not call the real Codex provider or qualify crash recovery between the approval decision and its executor.

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_approval_acceptance.py -q --junitxml=.git/pr34-evidence/approval-acceptance-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_approval_acceptance.py -q --junitxml=.git/pr34-evidence/approval-acceptance-linux.xml
rtk proxy ruff check tests/test_runtime_approval_acceptance.py
rtk git diff --check
```

Terminal exit0: Windows1 PASS5.77s; Linux1 PASS14.81s (handle62461 polled to exit0). No failures/skips. Ruff PASS. Raw XML retained under .git/pr34-evidence; sanitized per-node manifests linked by index.

Remaining original matrix:116 PASS/13 NOT_RUN. Final gate NOT PASSED; remaining cases, final immutable-source suites, findings/release audit and reinstall0.2.0 still required. Native Pi and dedicated attach remain NOT_RUN.
