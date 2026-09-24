# P12 — per-binding presence and disabled baseline

Parent `d7c0ab2474f40b23910296152867b5f951cc402a` plus two test hashes in `evidence/p12-binding-disabled-index.json`. Production unchanged, feature/v0.2.0.

T-PRES-02: two approved runtimes represent one canonical worker in distinct real temporary workspaces. Existing envelope isolation/continuation tests remain. After closing only the first binding, an actual native fixture output event through its sibling's event stream updates only the sibling presence heartbeat. The first remains closed with unchanged heartbeat. Authenticated broadcast then resolves no recipients/operations in the closed workspace and exactly the worker/one operation in the active sibling workspace, bound to its exact runtime/workspace. Pending work is not misreported as native completion.

T-API-01: fresh flag-OFF production HTTP app plus an actual authenticated Nexus MCP stdio subprocess on the same isolated store. Both expose exactly43 matching baseline tools and matching resource URIs, no harness names. Canonical stdio message_create still commits one logical inbox delivery. All eight equivalent REST harness entrypoints deny admission with403/PERMISSION_DENIED. No fake peer is constructed, no dispatcher is started, and runtime session/command/outbox tables remain empty. The required stdio process is not a native harness process. Disabled recovery of old runtime history is a separate existing rollout scenario, not prohibited by this fresh-store assertion.

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_binding_acceptance.py tests/test_runtime_disabled_acceptance.py -q --junitxml=.git/pr34-evidence/binding-disabled-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_binding_acceptance.py tests/test_runtime_disabled_acceptance.py -q --junitxml=.git/pr34-evidence/binding-disabled-linux.xml
rtk proxy ruff check tests/test_runtime_binding_acceptance.py tests/test_runtime_disabled_acceptance.py
rtk git diff --check
```

Terminal exit0: Windows19074 **4 PASS27.44s**, Linux25439 **4 PASS34.67s**. No failures/skips; Ruff/diff PASS. Exact joins and sanitized per-node results in index; raw XML retained under .git/pr34-evidence. No production change/new live MCP smoke requirement and no installed provider use.

Next: remaining18 original rows; final immutable-source suites, findings/operations/release audit and build/reinstall0.2.0. Pi/attach native remain NOT_RUN. Final gate NOT PASSED.
