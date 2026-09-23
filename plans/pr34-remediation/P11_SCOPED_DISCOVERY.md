# P11 — authorized canonical runtime discovery

Parent `28ca5423f6ce931b0257736f910024e47bb3864f`, feature/v0.2.0,
2026-09-23. Surface41, identity reference8, package0.2.0; no migration.

## Implementation and contract mapping

`RuntimeDiscoveryService.list` groups authorized endpoints beneath their existing
canonical agent_id and skill_names. MCP `harness_list(view="bindings")` and REST
`GET /api/v1/harness/bindings` use the same helper/context and application service.
An actual separately authenticated stdio process returns the same persisted view
as HTTP. No new per-adapter tool or identity is introduced.

RuntimeAccessService.authenticate validates an active current key binding or the
existing trusted local/operator context even when no endpoints are visible. Each
candidate then passes the shared discover authorization against current grant,
expiry, key, profile, agent, feature flag, permission and reachability. No grant
returns an empty list, not operator authority. A discover grant cannot send or
control a session. The grant repository can now constrain its indexed candidate
query by endpoint, avoiding scanning every actor grant per visible endpoint.

Only selected public binding fields, bounded session facts and canonical skill
names are returned. Paths, private config, environment/secret references, arbitrary
metadata and notify_target are absent. Descriptor capabilities are explicitly
`declared_capabilities`, with `capability_verification=not_probed`. The attach
descriptor remains partial. `current_owner_ready_record` checks persisted ready
lifecycle, owner epoch/lease and enabled current profile; process_liveness remains
not_probed. No native polling, secret resolution, process creation or write UOW
is used for discovery. Effective binary-version negotiation remains pending.

Endpoint limit1..100, default50, cursor after_endpoint_id, only visible IDs returned
as next_endpoint_id. The candidate scan is bounded at1000 and requires a narrower
agent_id on overflow without a full visible page. Each endpoint has at most10
latest sessions with sessions_has_more. Agent IDs are filters, never credentials.

Code: application/runtime_discovery.py; application/runtime_access.py.authenticate;
sqlite/runtime_grants_repo.py.candidates; MCP tools/harness.py request_context,
discover_bindings and guard; HTTP routes.py runtime_bindings. Tests:
tests/test_runtime_discovery.py. Operator instructions:
docs/harness-integrations/runtime-administration.md.

## Commands and actual results

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_discovery.py -x`:
  initial test setup failed because its fixture secret reference was intentionally
  unavailable; explicit disposable FIXTURE_SECRET added. Re-run before production
  edits: **behavioral RED**,1 failed in3.81s, a valid discover grant still received
  PERMISSION_DENIED from the operator-only harness_list. After implementation:
  **4 PASS**,7.74s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_discovery.py tests/test_runtime_grants.py tests/test_runtime_admin_surfaces.py tests/test_runtime_configuration_updates.py`:
  **50 PASS**,106.36s. Expanded discovery11 cases; before the later skill_names
  projection assertion and partial attach addition.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_discovery.py`:
  **11 PASS**,23.40s, includes skill_names and actual stdio/HTTP equivalence.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_discovery.py tests/test_runtime_grants.py`:
  **25 PASS**,68.06s, includes the skill_names assertion.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_discovery.py -k partial_attach`:
  initial **1 FAIL**,3.90s, fixture had attach flag disabled; the Linux counterpart
  likewise **1 FAIL**,10.05s. These are fixture setup failures, not new production
  defects. Explicitly enabled the flag for discovery only, no native open.
  Corrected Windows **1 PASS /11 deselected**,3.92s.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_discovery.py -k partial_attach`:
  corrected **1 PASS /11 deselected**,6.55s. Disabling attach again removes its
  projection through current shared authorization.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_comm_presets.py::test_no_comm_preset_mcp_tool_and_surface_revision_is_33 tests/test_feature_flags.py::test_nexus_info_features_identical_on_stdio_and_http tests/test_handoff_dependencies.py::test_ts11_surface_revision_feature_flag_and_budgets tests/test_health.py::test_ts8_surface_revision_ledger_and_budgets tests/test_memory.py::test_ts11_surface_revision_ledger_budgets_and_tool_set tests/test_verification.py::test_ts11_surface_revision_and_verify_description_budget tests/test_replay_marker.py tests/test_surface_metrics.py tests/test_frente1_resources.py tests/test_import_boundary.py`:
  **31 PASS**,8.86s; one existing Starlette/httpx deprecation warning.
- `rtk proxy ruff check src/okto_nexus/application/runtime_discovery.py src/okto_nexus/application/runtime_access.py src/okto_nexus/adapters/outbound/sqlite/runtime_grants_repo.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py src/okto_nexus/adapters/inbound/http/routes.py tests/test_runtime_discovery.py`:
  **PASS**. `rtk git diff --check`: **PASS**.
- `rtk proxy python plans/pr34-remediation/measure_surface.py 28ca542`:
  actual archived parent vs worktree OFF unchanged43tools,total40448,cuttable28315;
  ON unchanged51tools/eight harness names,total47718,cuttable32155→32158 (+3).
  No growth exemption; only on-demand identity reference content expanded.

## Coverage and remaining dependencies

T-API-06 safe unified declared-capability projection PASS (fixture/native-peer-free
read semantics); T-AUTH/T-API-02/03/07 receive scoped evidence, not aggregate gate
promotion. No real-model connector execution in this unit. Pi and dedicated
Claude attach native remain NOT_RUN. Codex/Claude prior native campaign evidence
is unchanged. Effective capability probes, unknown-delivery reconciliation,
native input parity, dashboard/guide/ADR completion, P12 full campaign and final
build/install remain pending. P11 IN_PROGRESS; final gate NOT PASSED.
