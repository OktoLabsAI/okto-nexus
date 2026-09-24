# P06 — bounded transport capacity and agent-aware worker admission

Integrated above49fbfb4 on feature/v0.2.0, after both immutable-source43388c8 full
suites ended. Schema058, surface53, identity20. Final plan gate NOT PASSED.
P06_SCHEDULER_LANE_SELECTION.md and P06_OUTBOX_BACKPRESSURE_WIP.md preserve the
isolated development history; the main checkout is now authoritative.

## Reproductions and correction

1. Three pending entries A,A,B consumed a two-item scan with only endpointA.
   Corrected behavioral tests:2 FAIL7.48s before selecting one head per lane.
2. Two endpoints of the same agent could take both normal command-worker slots.
   Real-surface regression1 FAIL6.38s. Selection now ranks eligible work per agent.
3. SQL acceptance/result state could free quota while its transport call remained
   blocked. Actual production Codex/Python-peer regression1 FAIL12.20s: the healthy
   agent stayed pending. The owner now snapshots actual in-flight normal operations
   across both pools and resolves their represented agents inside the claim UoW.
   Native result, acceptance and call return remain distinct facts. Controls retain
   separate priority capacity; parallel inference remains available after writes return.
4. Outbox admission had no accumulated count/byte bound. Real message admission
   RED1 FAIL6.26s after raising the independent fixture causal-rate ceiling.
5. A writer-v1 producer still using the old enqueue SQL bypassed the new Python
   check. RED1 FAIL6.72s admitted the33rd delivery. The test runs that historical
   enqueue path on real canonical envelopes in production MessageService/UoW;
   it does not fabricate delivery FKs or pretend to run an old full server.

Migration058 now provides the authoritative INSERT capacity guard and a partial
index. The duplicate Python quota query was removed. SqliteRuntimeOutboxRepo maps
that guard's exact IntegrityError to QUOTA_EXCEEDED/runtime_delivery_backpressure.
The guard covers already-open writer-v1 producers even when their error diagnostic
predates this mapping. It counts unresolved push reservations, including uncertain
attempts, without evicting old work. Atomic message/claim/grant rollback, concurrent
last-slot admission, byte limits and explicit cancellation recovery are tested.

Limits:256 global,32 authenticated actor,32 represented recipient,128 workspace,
4MiB stored envelope bytes. No new queue, remote call, secret resolution or process
operation enters a SQLite write transaction. Upgrade preserves over-limit history
and blocks only new transport admission until authorized completion/recovery.

## Code and tests

- runtime_outbox_repo.pending / runtime_commands_repo.pending: eligible lane and
  agent selection, persistent unknown/active fences, current-worker exclusions.
- RuntimeDispatcher.normal_inflight_agents / RuntimeCommandDispatcher.normal_operations_inflight:
  actual occupied normal-call snapshots. No unbounded threads or status polling.
- migration058 + runtime_outbox_repo.enqueue: single store-level capacity guarantee.
- test_runtime_scheduler_fairness, test_runtime_worker_capacity,
  test_runtime_outbox_backpressure, test_runtime_capacity_writer_fence: production
  HTTP/MCP/SQLite and isolated real Python protocol pipes.
- test_pr34_remediation fixture: stdio uses the same source checkout as serve;
  try/finally now cleans up when setup fails, without relaxing its10-second deadline.
- Seven old surface51 assertion files updated to the actual surface53 contract.

## Executed stages (overlapping counts, never sum)

All commands use rtk proxy. Windows Python is .venv/Scripts/python.exe on main;
isolated development used that absolute interpreter with the other checkout cwd.
Linux Python is /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python via WSL Ubuntu.

- Isolated lane/command/outbox gate27 PASS84.96s; expanded lane3 PASS11.93s Windows,
  3 PASS15.51s Linux. Metadata correction9 PASS245 deselected5.01s.
- Isolated outbox/handoff initial32 PASS94.28s; corrected three backlog cases3 PASS15.78s.
- Expanded backlog selection initially63 PASS5 FAIL on each platform; all failures
  were stdio loading schema057 source against isolated schema058. Corrected source
  selection: **Windows68 PASS166.66s; Linux68 PASS203.05s**.
- SQL-only agent admission37 PASS118.44s, followed by the genuine occupied-worker
  RED described above. Actual call-fence gate: **Windows38 PASS135.47s; Linux38 PASS148.27s**.
- Integrated main selection before the store-level capacity guard:
  **Windows117 PASS268.92s; Linux117 PASS320.17s**.
  Exact suffix: `-m pytest -q --tb=short tests/test_runtime_scheduler_fairness.py tests/test_runtime_worker_capacity.py tests/test_runtime_outbox_backpressure.py tests/test_runtime_commands.py tests/test_runtime_outbox.py tests/test_runtime_production_multiplex.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_writer_contract.py tests/test_runtime_endpoints.py tests/test_migrations.py tests/test_harness_routes.py tests/test_frente1_resources.py`.
- Final store-guard selection: Windows20 PASS44.48s; Linux20 PASS59.59s:
  `-m pytest -q --tb=short tests/test_runtime_capacity_writer_fence.py tests/test_runtime_outbox_backpressure.py tests/test_runtime_writer_contract.py tests/test_migrations.py`.

The complete suite at43388c8 remains a failed aggregate (see P12_SUITE_43388C8.md),
even though its stale revision failures have selected corrections. The setup error
repassed unchanged but its original cause remains unproven. No timeout was increased.

PR34 refreshed again2026-09-24: stillOPEN/head d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397,
base27b06fe48b9f95b35c94f50827fea83d178f4e12. Installed binaries observed read-only:
Codex0.156.1, Claude2.1.281. No new model campaign claimed for this unit yet.

Next: final store-guard gates, milestone commit/push, proven-safe retry/backoff/
equivalent-endpoint fallback, remaining matrix/crash/performance audit and final
build/reinstall0.2.0. Pi and dedicated attach native remain NOT_RUN.

Final metadata gate:9 PASS245 deselected4.69s (one Starlette warning). Ruff and git diff --check PASS. Surface measurement versus49fbfb4: OFF43 tools/40448 chars/10112 estimated tokens; ON51 tools/47730 chars/11932 estimated tokens. No resident schema growth; revision52 to53 and identity19 to20. All test sessions for this milestone are terminal.
