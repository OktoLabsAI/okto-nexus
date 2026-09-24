# Workspace isolation and continuation affinity acceptance

2026-09-24, feature/v0.2.0, parent475d5e5. Source review found missing exact
stimuli for T-ENDP-02 and T-ENDP-03. Existing fallback tests cover unsafe retry
and compatible versions, but neither two simultaneously active workspaces nor
priority changes while controlling the original operation. No production
defect is asserted from those coverage gaps.

New test_runtime_binding_acceptance.py uses actual HTTP/MCP authentication,
endpoint administration, canonical inbox/outbox, dispatch and presence. The
external Pi-shaped connector is synthetic; this does not qualify native Pi.

- One canonical Agent opens two runtimes in different temporary projects.
  Distinct message markers reach exactly the correct peer; each persisted
  operation and envelope carries the matching workspace/session. Closing the
  first binding closes only its presence; the other remains active.
- A new lower-priority endpoint becomes higher priority while the first
  operation remains unconfirmed. Both REST and MCP steer/interrupt carry its
  expected operation and execute only on the original peer/session. A new
  canonical message selects the newly preferred endpoint, proving priority
  mutation was effective rather than ignored.

Initial Windows27536:3 PASS13.26s, before the final positive new-message selection
assertion. Ruff PASS. Expanded final Windows23654:36 PASS138.42s/Linux19794:36 PASS140.50s, both exit0:

```text
rtk proxy python -X utf8 -c "from pathlib import Path; Path('.git/pr34-evidence').mkdir(exist_ok=True)"
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=.git/pr34-evidence/binding-475d5e5-windows.xml tests/test_runtime_binding_acceptance.py tests/test_runtime_endpoint_fallback.py tests/test_runtime_effective_capabilities.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short --junitxml=.git/pr34-evidence/binding-475d5e5-linux.xml tests/test_runtime_binding_acceptance.py tests/test_runtime_endpoint_fallback.py tests/test_runtime_effective_capabilities.py
```

The new JUnit paths are persistent task files in the local Git directory. Reduce
them to sanitized per-node manifests after completion; never commit raw captured
logs. No existing implementation/test changed during these executions. Platform
durations overlap and are not performance benchmarks. No provider was invoked.

Reviewed existing T-ENDP-06: test_error_text_after_native_write_cannot_enable_endpoint_fallback
performs a simulated write then raises misleading busy text. OUTCOME_UNKNOWN has
no next binding/deadline and the available alternative peer receives no call.
T-ENDP-07 is covered by effective-capability tests with unknown/missing versions,
profile restrictions, actual on-demand native fixture frames showing no turn/start,
and rejected reuse of an unqualified shared connection. Positive qualified
multi-turn and safe fallback remain in the expanded selection.

Identity catalogue/start failures and full exact authorization cases still need
further review or acceptance stimuli. Do not promote them from this unit. Final
original matrix/crash/load/performance/build/install gates remain unfinished.


Both persistent XML files were found and reduced successfully to sanitized
p12-binding-windows.json and p12-binding-linux.json. Each manifest records the
parent SHA plus new test-file hash, not an immutable full-source run. Every
mapped node/parameter for T-ENDP-02/03/06/07 was matched against both manifests
and required PASS. The mapping and final hash are in p12-binding-acceptance.json.
Native/browser campaigns were not selected; default reducer labels were corrected
to describe that exact selection. No native campaign or full-matrix claim follows.
Ruff PASS. No live test processes remain.

Reduction commands (PLATFORM is windows or linux):

```text
rtk proxy python -X utf8 plans/pr34-remediation/summarize_pytest_evidence.py .git/pr34-evidence/binding-475d5e5-PLATFORM.xml 475d5e5b03b816084b7aa54cec829a80b6a9d7f0 PLATFORM plans/pr34-remediation/evidence/p12-binding-PLATFORM.json --limitations "Parent SHA plus new acceptance file hash recorded in binding unit evidence; not an immutable full suite. Actual HTTP/MCP and synthetic peers only; overlapping platform timings are not benchmarks."
rtk proxy ruff check tests/test_runtime_binding_acceptance.py
```
