# P11 — shared endpoint/profile administration

Parent `e6983f2a62910a70fcda139ee31753b5be339210`, 2026-09-23,
branch `feature/v0.2.0`. Package 0.2.0, migration 052 unchanged, surface **39**.
No native provider calls were needed or made for this unit.

## Implementation and contract mapping

- `adapters/inbound/runtime_admin.py`: existing REST input models moved to a
  shared inbound module. Strict types, extra-field rejection and positive CAS
  revisions now apply identically to MCP and REST. Surface39 documents this
  compatibility change; security switches are never coerced from strings.
- `mcp/tools/harness.py::administer_endpoints`: the existing `harness_list`
  accepts endpoint/profile views and dispatches their existing administrative
  actions into the same EndpointService. No new per-adapter tools or application
  service duplicate. Input strings follow the existing JSON-object normalization.
  Authentication precedes argument/resource handling; secret-bearing validation
  input is not reflected in MCP errors.
- `EndpointService.profiles` and `SqliteEndpointRepo.public_profiles`: authorized
  redacted discovery, also available at GET /api/v1/harness/profiles. No secret
  resolution, command paths, environment values or secret reference names.
- Existing create, endpoint configuration CAS, boot and reconciliation retain
  their current shared authorization/revision/idempotency semantics. A retry on
  the other surface does not spawn or resend.
- `resources_docs.py`: identity resource v6 documents concrete actions/parameters.
  Operational subset documented in docs/harness-integrations/runtime-administration.md
  and linked from the older guide. Changelog and cached revision assertions updated.

## Executed evidence

`tests/test_runtime_admin_surfaces.py` runs real authenticated HTTP and mounted
MCP against an isolated store. It covers creation/listing/update/boot, CAS,
redaction, payload impersonation fields, ordinary-agent denial, cached tool after
feature disable, five invalid profile forms and cross-surface reconciliation retry.

- Initial `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_admin_surfaces.py -x`:
  **behavioral RED**, 1 failed in 4.44s: operator MCP creation rejected with
  `Maintenance requires artifacts view`. The route/service already existed.
- After implementation, `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_admin_surfaces.py`:
  **3 PASS** in 7.28s, before expanding invalid-input/reconciliation coverage.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_admin_surfaces.py tests/test_runtime_endpoints.py tests/test_runtime_boot.py tests/test_harness_routes.py tests/test_harness_tools.py tests/test_runtime_contracts.py tests/test_frente1_resources.py tests/test_import_boundary.py tests/test_surface_metrics.py tests/test_replay_marker.py`:
  initial **1 FAIL / 109 PASS / 2 SKIP**, 144.97s. Failure was the old identity
  resource version assertion (5, actual6). Corrected the cache-version expectation.
  Final repeated command, including the additional reconciliation case:
  **111 PASS / 2 SKIP**, 161.79s. The two platform skips are NOT_RUN on Windows.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_frente1_resources.py`:
  **12 PASS**, 3.32s.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_admin_surfaces.py tests/test_runtime_endpoints.py tests/test_runtime_boot.py tests/test_runtime_contracts.py`:
  **48 PASS**, 97.62s, before adding cross-surface reconciliation.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_admin_surfaces.py -k reconciliation_retry`:
  **1 PASS / 8 deselected**, 8.18s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_comm_presets.py::test_no_comm_preset_mcp_tool_and_surface_revision_is_33 tests/test_feature_flags.py::test_nexus_info_features_identical_on_stdio_and_http tests/test_handoff_dependencies.py::test_ts11_surface_revision_feature_flag_and_budgets tests/test_health.py::test_ts8_surface_revision_ledger_and_budgets tests/test_memory.py::test_ts11_surface_revision_ledger_budgets_and_tool_set tests/test_verification.py::test_ts11_surface_revision_and_verify_description_budget`:
  **6 PASS**, 2.85s; one existing Starlette/httpx deprecation warning.
- `rtk proxy ruff check src/okto_nexus/adapters/inbound/runtime_admin.py src/okto_nexus/adapters/inbound/http/routes.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py src/okto_nexus/application/endpoints.py src/okto_nexus/adapters/outbound/sqlite/endpoints_repo.py tests/test_runtime_admin_surfaces.py tests/test_runtime_relay.py tests/test_runtime_causality.py plans/pr34-remediation/measure_surface.py`:
  **PASS**. An initial E402 from the moved HTTP model import was corrected by
  placing it with the module imports.

## Actual resident surface measurement

`rtk proxy python plans/pr34-remediation/measure_surface.py e6983f2`:
the script archives the baseline source into a temporary directory and runs the
same live FastMCP measurement on baseline/current isolated stores, with flags OFF
and ON. No personal environment or provider is loaded; no native process starts.

| Metric (characters, existing instrument) | Baseline OFF | Current OFF | Baseline ON | Current ON |
|---|---:|---:|---:|---:|
| Tool count | 43 | 43 | 51 | 51 |
| Instructions | 5232 | 5232 | 5232 | 5232 |
| Tool docstrings | 6549 | 6549 | 7845 | 7838 |
| Parameter descriptions | 16534 | 16534 | 19015 | 19078 |
| Cuttable | 28315 | 28315 | 32092 | 32148 |
| Total | 40448 | 40448 | 47648 | 47711 |

Exactly eight harness names remain when enabled, zero when disabled. ON growth:
56 cuttable characters, 63 total characters; no growth exemption was added.
The instrument reports chars/4 token proxies, not tokenizer counts or byte sizes.

## Remaining dependencies

This is not full CRUD or full P11. Profile editing/disable, broader endpoint
editing, scoped safe discovery, effective capability/version probes, outbox
reconciliation/takeover, native input response parity, dashboard diagnostics,
cutover/rollback and the complete operator guide remain pending. Preserve UNKNOWN
operations until explicit reconciliation; never delete rows to simulate recovery.
P11 IN_PROGRESS; P12 NOT_STARTED; final gate NOT PASSED.
