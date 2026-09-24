# P12 — canonical conversational command input

Parent `1445470b0a5eb75a26dd611df1d12612135865b5` plus exact source/test hashes in `evidence/p12-canonical-payload-index.json`. Branch feature/v0.2.0. T-API-04 scoped PASS; final gate NOT PASSED.

## Change and logical contract mapping

`RuntimeControlService` now accepts the conversational input projection of DeliveryEnvelope v1: schema_version1, nonempty typed text content blocks, optional subject, conversation intent and boolean response_requested. At dispatch it builds the complete envelope with the persisted authenticated command actor, approved session recipient/workspace, server operation/root IDs and untrusted-content provenance. Canonical steering uses runtime_control intent. Payloads cannot set these authoritative fields, handoff/claim, runtime context, native options or artifact references; those workflows retain their canonical APIs. No new identity/profile or transport queue is introduced.

Legacy text/content aliases normalize to text; conflicting values fail. Existing v2 persisted content-alias request hashes remain valid without rewriting their rows or repeating effects, while content/target/context conflicts still fail. JSON-string objects follow the repository MCP coercion convention and are explicitly parsed by the shared validator for REST/internal parity; malformed/non-object input is rejected.64 KiB validation remains. Legacy native prompt representation is preserved; canonical input is rendered by each existing EnvelopeConnector. Authorization, current grants, ownership and attempt fences remain in the shared command use case.

Command response contract3, MCP surface57, identity resource25, schema still061. Updated version pins and operator guide include canonical input example, data/authority boundary and compatibility. No migration or private-store mutation.

## Verification and failures retained

- Original RED at e28adb6: Windows1 FAIL6.58s, authenticated canonical Pi/MCP rejected by old validator. Source/test hash retained.
- Independent pre-change authorization probe:3 PASS12.07s; no authorization defect claimed. Transient test hash was not recorded.
- Initial implementation: Windows12766 **13 PASS2 FAIL57.47s**, Linux96582 **13 PASS2 FAIL111.54s**. Eight canonical four-adapter/surface cases passed. Negative fixture incorrectly expected valid JSON-string rejection despite MCP coercion; REST error helper also assumed every validation response carried an ok field. Aligned parsing with repo convention and normalized the test helper's HTTP result.
- Expanded run: Windows77250 **33 PASS2 FAIL146.75s**, Linux40368 **33 PASS2 FAIL162.55s**. Only new delegated-actor tests failed: fixture supplied endpoint instead of endpoint_id, leaving grant scoped to Pi; product correctly denied Codex. An attempted shell replacement had failed before launch, so these failures are retained; corrected the test via apply_patch, without relaxing authorization.
- Confirmed new contract: Windows20800 **17 PASS79.40s**, Linux97079 **17 PASS87.47s**. Covers four synthetic adapter translations × REST/MCP, JSON-string retry, malformed/conflicting/authoritative payload rejection, alias normalization and persisted v2 hash compatibility, authorization-before-validation, and granted caller identity through actual owned Codex protocol process to correlated durable result. Synthetic attach does not qualify native cc-socks.
- Metadata/resources/imports: Windows32039 **31 PASS17.69s**, Linux10087 **31 PASS43.79s**; existing Starlette warning1 each.

Final production code was unchanged between expanded/metadata/confirmed gates; only the delegated fixture keyword changed after expanded. Their union is66 distinct passing nodes/platform, not a single66-test execution and not the full suite. Initial failures remain in separate per-node manifests. All handles terminal.

Ruff and git diff --check PASS. Required isolated `rtk proxy .venv/Scripts/python.exe scripts/live_client.py` exited0 in8.40s, LIVE E2E RESULT: PASS,43 baseline tools and temporary stores; raw logs not committed.

## Exact commands

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_canonical_payload.py --maxfail=1 -q --junitxml=.git/pr34-evidence/canonical-payload-red-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_canonical_payload.py::test_payload_validation_does_not_precede_session_authorization --maxfail=1 -q --junitxml=.git/pr34-evidence/canonical-auth-red-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_canonical_payload.py -q --junitxml=.git/pr34-evidence/canonical-payload-initial-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_canonical_payload.py tests/test_runtime_payload_boundaries.py tests/test_runtime_request_acceptance.py tests/test_runtime_operation_authorization.py -q --junitxml=.git/pr34-evidence/canonical-payload-final-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_comm_presets.py::test_no_comm_preset_mcp_tool_and_surface_revision_is_33 tests/test_feature_flags.py::test_nexus_info_features_identical_on_stdio_and_http tests/test_handoff_dependencies.py::test_ts11_surface_revision_feature_flag_and_budgets tests/test_health.py::test_ts8_surface_revision_ledger_and_budgets tests/test_memory.py::test_ts11_surface_revision_ledger_budgets_and_tool_set tests/test_verification.py::test_ts11_surface_revision_and_verify_description_budget tests/test_replay_marker.py tests/test_surface_metrics.py tests/test_frente1_resources.py tests/test_import_boundary.py -q --junitxml=.git/pr34-evidence/canonical-metadata-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_canonical_payload.py -q --junitxml=.git/pr34-evidence/canonical-payload-confirmed-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_canonical_payload.py -q --junitxml=.git/pr34-evidence/canonical-payload-initial-linux.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_canonical_payload.py tests/test_runtime_payload_boundaries.py tests/test_runtime_request_acceptance.py tests/test_runtime_operation_authorization.py -q --junitxml=.git/pr34-evidence/canonical-payload-final-linux.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_comm_presets.py::test_no_comm_preset_mcp_tool_and_surface_revision_is_33 tests/test_feature_flags.py::test_nexus_info_features_identical_on_stdio_and_http tests/test_handoff_dependencies.py::test_ts11_surface_revision_feature_flag_and_budgets tests/test_health.py::test_ts8_surface_revision_ledger_and_budgets tests/test_memory.py::test_ts11_surface_revision_ledger_budgets_and_tool_set tests/test_verification.py::test_ts11_surface_revision_and_verify_description_budget tests/test_replay_marker.py tests/test_surface_metrics.py tests/test_frente1_resources.py tests/test_import_boundary.py -q --junitxml=.git/pr34-evidence/canonical-metadata-linux.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_canonical_payload.py -q --junitxml=.git/pr34-evidence/canonical-payload-confirmed-linux.xml
rtk proxy .venv/Scripts/python.exe scripts/live_client.py
rtk proxy ruff check src/okto_nexus/application/runtime_control.py src/okto_nexus/adapters/inbound/http/routes.py src/okto_nexus/adapters/inbound/mcp/tools/harness.py src/okto_nexus/adapters/outbound/sqlite/runtime_commands_repo.py tests/test_runtime_canonical_payload.py
rtk git diff --check
rtk proxy python plans/pr34-remediation/measure_surface.py 1445470
```

Surface measurement `evidence/p12-canonical-payload-surface.json`: OFF unchanged43 tools/40448 total characters; ON51 tools/47828 total/32275 cuttable. Increase98 total/74 cuttable characters for inline canonical example; no growth exemption. Tokens are chars/4 proxies. Source/test hash distinguishes worktree changes from parent.

Next: remaining23 original matrix rows, final immutable-source suites, findings/operations/release audit and build/reinstall0.2.0. Native Pi and dedicated attach remain NOT_RUN; no provider reruns performed in this unit.
