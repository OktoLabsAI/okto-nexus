# Persisted operation authorization acceptance

2026-09-24, feature/v0.2.0, parent28d107829c89557b0fac2ee2ebf8f2a76494f7c8 plus new test-file hash. Production unchanged.

The new tests use the production HTTP/MCP application. An owned Codex transport with a disposable Python protocol peer produces a real durable private result. The operator can repeat its key and retrieve the same operation. A different authenticated actor cannot reuse that key or inspect the result. Known and nonexistent operation IDs have identical complete denial envelopes on both surfaces. One command and one result remain persisted.

Four further cases admit send/steer/interrupt/close under a narrow caller grant, await dispatch, and positively recover the cached command reply before revocation. Revoking the grant through REST then blocks that same persisted key and operation read on both surfaces, without a new command or peer effect. Steer/interrupt are bound to a real pending synthetic turn. No native provider campaign.

Windows initial single case:1 PASS5.36s; expanded new module32406:5 PASS17.56s. Ruff PASS. No product RED or production changes.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=.git/pr34-evidence/operation-28d1078-windows.xml tests/test_runtime_operation_authorization.py tests/test_runtime_commands.py tests/test_runtime_grants.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short --junitxml=.git/pr34-evidence/operation-28d1078-linux.xml tests/test_runtime_operation_authorization.py tests/test_runtime_commands.py tests/test_runtime_grants.py
rtk proxy ruff check tests/test_runtime_operation_authorization.py
```

Terminal expanded outcomes and sanitized per-node manifests follow. This qualifies T-AUTH-12 for command keys and operation results; other audience and publication requirements remain separate. No final-gate promotion.

Windows30311:30 PASS112.47s/Linux75530:30 PASS121.96s, both exit0. Persistent XMLs reduced and all mapped parameters matched PASS on both. Parent/new-test hash in p12-operation-authorization.json. T-AUTH-12 scoped PASS. Separate crash-fixture development is not part of this qualification.
