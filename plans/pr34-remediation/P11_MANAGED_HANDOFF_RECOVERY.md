# P11 — explicit managed handoff recovery

Parent: `fe6c5c101c151aa9ee705a8ff53da266c1bf086a`; implementation worktree on
`feature/v0.2.0`. No native provider invoked in this unit. Final gate NOT PASSED.

## Behavior and mapping

`RuntimeOperationMaintenanceService.run(action="recover_handoff")` shares operator
authorization, active owner, exact attempt snapshot, idempotency and runtime-stop
guards across REST, MCP HTTP and authenticated stdio owner proxy. Exact handoff ID
and claim epoch plus explicit duplicate-risk acknowledgement are required.
`HandoffService.recover_runtime_claim` performs the canonical CLAIMED→OPEN CAS and
scoped `handoff.recovered` event in the same SQLite transaction as the audit and
attempt fence. No external call, secret resolution or process starts in this UOW.

The same handoff is reopened without sending work. Its old work envelope remains
reserved; it never becomes a conversational pull delivery. Transport state and
ACK remain facts, even when a native terminal did not complete the canonical work.
The endpoint is quarantined and grants/boot approvals revoked. A new explicit
claim increments the epoch. Late structured results stay durable but cannot finish
that new claim. VERIFYING and terminal canonical handoffs cannot be reopened.
Historical reconciled bindings no longer pin later unmanaged claims indefinitely.

Migration055 is additive. It extends migration054's audit with canonical_action,
handoff_id and claim_epoch. Logical API action recover_handoff maps to the existing
transport classification abandon_command plus canonical_action=reopen_handoff.
This preserves the old CHECK enum and old idempotency request hashes; it does not
create another audit mechanism or work queue. Surface43 / identity resource10.
The diagnostic UI labels the bound operation Managed handoff execution.

## Executed evidence

- Behavioral RED: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_handoff_recovery.py -x`
  returned 1 FAIL in4.11s, HTTP422 Invalid operation maintenance fields, before
  adding the new action. No missing-import failure or correction-assuming mock.
- Initial integrated selection: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_handoff_recovery.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_work_results.py tests/test_migrations.py`
  returned65 PASS in157.51s, one existing Starlette/httpx warning. Subsequent cases
  expanded canonical state and late terminal coverage.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_handoff_recovery.py`
  returned13 PASS in34.29s. The late-terminal fixture initially referenced a closed
  in-memory session (1 FAIL/1 PASS); corrected to read its durable connection ID,
  then the focused late case passed. This fixture error was not a product defect.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_handoff_recovery.py`
  returned13 PASS in52.11s (before adding the stdio case).
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_handoff_recovery.py -k stdio`
  returned1 PASS/13 deselected in9.10s. Actual authenticated Nexus subprocess;
  disposable fixture operator key never passed to a native peer.
- `rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ["OKTO_NEXUS_UI_CAMPAIGN"]="1"; raise SystemExit(pytest.main(["-q","tests/test_runtime_diagnostics_dashboard.py"]))'`
  returned7 PASS in59.92s. Isolated Edge, production HTTP, temporary frontend build.
- `rtk proxy node node_modules/typescript/bin/tsc --noEmit` in frontend: PASS.
- `rtk proxy ruff check src/okto_nexus/application/runtime_operation_maintenance.py src/okto_nexus/application/handoff.py src/okto_nexus/application/runtime_work.py tests/test_runtime_handoff_recovery.py tests/test_runtime_diagnostics_dashboard.py`: PASS.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py fe6c5c1`:
  OFF unchanged (43 tools,40448 chars). ON51 tools, total47714→47730 chars,
  cuttable32172→32188 after including recover_handoff in the facade description.
  No additional tools.

Coverage includes concurrent identical decisions, changed-idempotency rejection,
stale handoff/claim/attempt, missing risk acknowledgement, ordinary-agent denial,
feature-OFF recovery, transaction rollback, old claim completion fencing, historical
lease expiry, late structured terminal, and native protocol fixture terminal versus
canonical completion. Real Codex/Claude recovery campaigns remain NOT_RUN here.

## Separate full-suite inventory

The earlier complete inventory ended2240 PASS/6 FAIL/92 SKIP in1424.36s. It ran
across changing worktree imports and is not an immutable-SHA final gate. All six
failures were obsolete shutdown fixtures (unauthenticated open, then Windows
cleanup using POSIX-only APIs). Their six leftover fixture servers were identified
only from this run's exact temporary lock files and validated by cwd, command and
creation time before termination. No harness child had opened. See the redacted
`evidence/p11-complete-suite-inventory.json`; raw XML removed after reduction.
Next dependencies: migrate those shutdown tests, effective probes, remaining
cutover/backup/admin parity and P12. Pi and dedicated attach native remain NOT_RUN.

Final expanded integration: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_handoff_recovery.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_work_results.py tests/test_migrations.py tests/test_frente1_resources.py tests/test_surface_metrics.py` returned **86 PASS**, one existing Starlette/httpx warning, in189.20s.
