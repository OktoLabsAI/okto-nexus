# P11 — revision-fenced configuration changes

Parent `3142b115bb0dd1dc97275de57c8d0b564ebb8901`, branch `feature/v0.2.0`,
2026-09-23. Package 0.2.0, additive migration **053**, surface **40**, identity
reference resource **7**. No personal store or native provider was used.

## Behavior and implementation

The existing administration exposed creation but did not support retiring/editing
profiles. `PATCH /harness/profiles/{id}` returned 404. Both REST and MCP now share
`EndpointService.update_profile` and the extended `update_endpoint` through the
same strict inbound models. IDs, Agent, adapter and workspace are immutable.
Deactivation is the logical retirement operation; referenced history is retained.

Profile config/secret_refs/inherit_ambient/enabled and endpoint public_config/
enabled/priority/selection_group/response_policy/consumption/profile_id can be
updated with a positive expected_revision. Omitted fields remain unchanged;
explicit objects replace their previous value. Validation preserves sandbox,
approval, adapter compatibility and bounded 64 KiB profile configuration. Profile
validation, including the registry callback, executes outside a writer transaction;
the final CAS rejects concurrent changes. No secret resolver or process is called.

Every successful edit atomically advances the revision, revokes affected grants
and disables previous boot approvals. Re-enabling configuration does not restore
old grants or boot. A running process retains its original profile revision and
cannot receive new sends under the edited profile. Operator interrupt/close are
still possible. Late terminals remain captured, with publication blocked when
their configuration authorization is no longer current.

Changing an endpoint's profile is refused while any linked session is not
stopped/detached, or an open request is RESERVED. This avoids treating matching
numeric revisions of two different profiles as the same session configuration.
Old endpoint grants are revoked on the successful swap. Unknown historic bindings
are not silently converted into a clean runtime; recovery or a fresh explicitly
approved endpoint remains necessary.

Migration 053 extends `runtime_access_audit` with resource_kind/resource_id,
old_revision/new_revision and changed_fields plus an index. There is no parallel
audit system and no raw config/secret values in the record. Create/update audit,
revocation and configuration commit together. EndpointService.diagnostics exposes
the latest 100 configuration changes to the operator. Existing mutation failures
leave the old configuration intact.

Files/symbols: application/endpoints.py (`update_profile`, `update_endpoint`,
`validate_profile`, `diagnostics`); sqlite/endpoints_repo.py
(`audit_configuration`, `invalidate_configuration`); shared runtime_admin.py
input models, REST routes, MCP `administer_endpoints`; migration053;
tests/test_runtime_configuration_updates.py. Operational steps and safe recovery
are in docs/harness-integrations/runtime-administration.md.

## Exact commands and observed results

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_configuration_updates.py -x`:
  **behavioral RED**, 1 failed in 3.88s: PATCH profile returned404 before editing
  existed. Failure did not depend on missing imports or assumed private mocks.
- Same file without `-x`, after implementation: **4 PASS**, 11.32s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_configuration_updates.py tests/test_runtime_admin_surfaces.py tests/test_runtime_endpoints.py tests/test_runtime_boot.py tests/test_runtime_grants.py tests/test_runtime_notify_targets.py`:
  **82 PASS**, 236.82s. This run preceded the additional migration/late-terminal/
  send-intent cases and operator diagnostic assertion below.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_configuration_updates.py tests/test_runtime_admin_surfaces.py tests/test_runtime_endpoints.py tests/test_runtime_boot.py`:
  **51 PASS**, 137.82s, before those additions.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_configuration_updates.py -k audit_upgrade tests/test_migrations.py`:
  **1 PASS / 20 deselected**, 1.80s; `-k` selects only the upgrade case, not the
  whole migration suite. A temporary schema52 store preserves an old audit record;
  upgrade is additive/idempotent, passes foreign-key check and admits no work.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_configuration_updates.py tests/test_migrations.py tests/test_frente1_resources.py tests/test_import_boundary.py`:
  **36 PASS**, 40.44s, including the full migration suite, diagnostic assertion,
  configuration rollback cut and changed resource cache version.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_configuration_updates.py -k late_native_terminal`:
  **1 PASS / 14 deselected**, 5.08s. Production Codex connector against a Python
  protocol peer; profile disable then interrupt preserves one exact durable
  terminal and blocks publication. This is not a real-model campaign.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_configuration_updates.py -k send_intent`:
  **1 PASS / 15 deselected**, 3.34s. Profile disabled after durable send-intent,
  before the production dispatch function; zero native writes. Existing recovery
  conservatively leaves OUTCOME_UNKNOWN, not an invented safe retry.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_configuration_updates.py`:
  **15 PASS**, 37.11s, includes all additions except the last send-intent case.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_configuration_updates.py -k send_intent`:
  **1 PASS / 15 deselected**, 8.32s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_comm_presets.py::test_no_comm_preset_mcp_tool_and_surface_revision_is_33 tests/test_feature_flags.py::test_nexus_info_features_identical_on_stdio_and_http tests/test_handoff_dependencies.py::test_ts11_surface_revision_feature_flag_and_budgets tests/test_health.py::test_ts8_surface_revision_ledger_and_budgets tests/test_memory.py::test_ts11_surface_revision_ledger_budgets_and_tool_set tests/test_verification.py::test_ts11_surface_revision_and_verify_description_budget tests/test_replay_marker.py tests/test_surface_metrics.py`:
  **16 PASS**, 3.34s, one existing Starlette/httpx deprecation warning.
- `rtk proxy ruff check src/okto_nexus/application/endpoints.py src/okto_nexus/adapters/inbound/runtime_admin.py src/okto_nexus/adapters/inbound/http/routes.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py src/okto_nexus/adapters/outbound/sqlite/endpoints_repo.py tests/test_runtime_configuration_updates.py`:
  **PASS**.

## Surface measurement and remaining gates

`rtk proxy python plans/pr34-remediation/measure_surface.py 3142b11` compares the
actual live schemas against a temporary Git archive of the parent. OFF remains
43 tools / total40448 / cuttable28315 characters. ON remains 51 tools (eight harness
tools), total47711→47718 and cuttable32148→32155: **7 additional characters**,
without a growth exemption. Resource depth is on demand, identity v7.

These tests do not constitute physical power-loss qualification or a native-model
campaign. Codex/Claude provider execution for this unit is NOT_RUN; Pi and dedicated
Claude attach native remain NOT_RUN by the established scope. Full operational
rollback/backup, effective capability negotiation, scoped discovery, outbox recovery,
native input surface parity, dashboard and complete operator guide remain pending.
P11 IN_PROGRESS; P12 and final build/install remain unfinished. Final gate NOT PASSED.
