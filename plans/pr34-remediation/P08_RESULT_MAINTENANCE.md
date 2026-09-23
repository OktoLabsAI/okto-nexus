# Result artifact maintenance and integrated runtime gate

Parent `b7b88aa`, branch `feature/v0.2.0`, 2026-09-23. Migration 043 is
additive. Final remediation gate remains NOT PASSED.

`RuntimeMaintenanceService.artifacts` provides the same operator-authorized
case through REST `POST /api/v1/harness/artifacts` and MCP
`harness_list(view="artifacts", maintenance={...})`. The stdio facade forwards
to the actual owner. An empty request inspects bounded result metadata,
reservations and pending maintenance; captured output is not returned.

Mutations require `action`, `idempotency_key` and a nonempty audit `reason`:

- `quota`, with `quota_bytes`, changes the persisted global reservation limit
  (256 KiB through 1 GiB; default 64 MiB). Agent and workspace limits are one
  quarter and one half respectively. Existing reservations prevent unsafe
  decreases. More endpoints do not increase an agent's quota.
- `cleanup`, with `result_id`, accepts only blocked/review-required unpublished
  artifacts with no catalog or publication reference. It commits an intent,
  deletes only the exact trusted artifact/staging paths outside the SQLite
  writer, then releases the reservation and advances artifact generation.
  Failure leaves a recoverable pending intent and retains the reservation.
  Inspect pending maintenance and repeat the same key to reconcile absence.
  Old completed cleanup requests cannot remove a later generation.
- `retry`, with `result_id`, returns blocked/review-required publication to
  canonical authorization. It does not replay the native operation, bypass
  policy, approve an approval or retry published results.

Authorization is repeated in the mutation transaction. Filesystem cleanup
checks containment and reparse/symlink boundaries. Published artifacts and
unrelated staging paths are preserved. Recovered staging for the exact result
is collected before preparation by the actual bounded publication worker;
owner lease and source binding are revalidated. Captured text remains durable
through cleanup and publication denial.

Evidence and exact commands (all process peers are fixtures):

- `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_result_maintenance.py --tb=short`: **4 passed in 13.90s**.
  Covers cleanup crash/retry/generation, abandoned staging, REST/MCP auth,
  quota recovery, approval rejection and one native execution throughout.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_endpoints.py tests/test_runtime_wake_generation.py
  tests/test_runtime_result_maintenance.py tests/test_runtime_result_publication.py
  tests/test_runtime_shutdown.py --tb=short`: **37 passed in 99.22s**
  (before the fourth maintenance case was added).
- Full Windows runtime selection: Python expands sorted
  `Path("tests").glob("test_runtime_*.py")`, invokes
  `.venv/Scripts/python.exe -m pytest -q <expanded paths> --tb=short --maxfail=6`,
  with `OKTO_NEXUS_NATIVE_CAMPAIGN=""` and all three legacy native live flags
  set to `0`. Initial run: **185 passed, 2 failed, 3 skipped**. Failures were
  an obsolete synchronous-close assertion and a wake test replacing the real
  dispatcher with incomplete private composition. Tests now await the durable
  close operation and use the actual owner. Final run: **188 passed, 3 skipped
  in 342.33s**. Expanded command and outputs are in
  `evidence/p08-runtime-maintenance-{integrated,final}.log`.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus --
  /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q
  tests/test_runtime_result_maintenance.py tests/test_runtime_artifact_durability.py
  tests/test_runtime_result_publication.py tests/test_runtime_shutdown.py
  --tb=short --maxfail=3`: **28 passed in 101.13s**.
- Ruff check of all changed Python modules: PASS.

Native provider campaigns and machine power-loss tests: NOT_RUN in this unit.
The integrated selection is not the complete acceptance matrix: canonical
handoff/bootstrap/HITL (P09), causal continuation (P10), remaining public
administration/UI (P11), qualification and build/install (P12) remain required.
Database history and deduplication fences are retained; this is not a history
purge API. No user database has been migrated or native operation replayed.
