# P12 — API assertion joins and current surface measurement

Source `e28adb6b708ee33b8d12d74b23cd9cbfd42c394a`, production unchanged during both selected runs. Terminal Windows79827: **107 PASS,2 POSIX attach SKIP,378.36s**; Linux71978: **109 PASS,516.01s**. Skips remain unexecuted; no provider rerun.

## Qualified requirements

- T-API-02: eight tool names exercised by authenticated HTTP MCP fixtures and equivalent REST lifecycle, shared live registry, current authorization, honest command admission and durable close/event replay. Full adapter qualification remains separate.
- T-API-03: cached registered handler rejects after disabling integration; endpoint administration also rechecks the flag; send/steer/interrupt/close cached replies and result reads are denied after grant revocation without additional native effects or intents.
- T-API-07: actual FastMCP schemas measured against original PR34 using isolated git-archive source and temporary homes, no processes/providers. Original revision34 publishes51 tools regardless of requested flag. Current revision56: OFF43 tools/40448 total characters/28315 cuttable; ON51 tools/47730 total/32201 cuttable. Exactly eight harness names, no per-adapter duplication. Compared to original ON45744 total/33689 cuttable: total grows1986 characters while cuttable falls1488. Current OFF→ON grows7282 total/3886 cuttable. Instrument token values are chars/4 proxies, not tokenizer counts; no new growth exemption added.
- T-LIFE-10: join to already executed native Claude2.1.281 at752cd72, not a new execution. The two-turn test asserts the same process survives, exactly one native session_id is observed, each terminal matches its canonical operation/attempt, and exactly two durable nonempty results/two consumed inbox deliveries exist. Setup/call/teardown all passed in the sanitized native manifest. Native model remains unobserved, Pi/attach remain NOT_RUN.

Index `evidence/p12-api-review-index.json` records exact node joins and source distinctions. Existing resources/schema descriptions were not changed by this review. Final resources/legacy/full-suite gate remains required.

## Commands

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_pr34_remediation.py tests/test_runtime_operation_authorization.py tests/test_runtime_admin_surfaces.py tests/test_harness_routes.py tests/test_harness_tools.py tests/test_runtime_commands.py tests/test_runtime_payload_boundaries.py tests/test_surface_metrics.py -q --junitxml=.git/pr34-evidence/api-review-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_pr34_remediation.py tests/test_runtime_operation_authorization.py tests/test_runtime_admin_surfaces.py tests/test_harness_routes.py tests/test_harness_tools.py tests/test_runtime_commands.py tests/test_runtime_payload_boundaries.py tests/test_surface_metrics.py -q --junitxml=.git/pr34-evidence/api-review-linux.xml
rtk proxy python plans/pr34-remediation/measure_surface.py d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397
```

Surface JSON is `evidence/p12-surface-e28adb6.json`; raw pytest XML stays under .git/pr34-evidence. No production change/live MCP smoke required.

## Newly reproduced gap, not hidden by this green gate

T-API-04 remains NOT_RUN: validate_runtime_payload currently rejects canonical versioned content blocks despite the spec. A new isolated authenticated Pi/MCP case failed with VALIDATION_ERROR (Windows1 FAIL6.58s), not an import error. Canonical input and explicit server-filled identity need implementation. Additional authorization-before-payload test already passed3 Windows cases; no authorization defect claimed. The new test remains separate from this committed-source review. T-API-01/05 and all other open rows are not promoted. Final gate remains NOT PASSED.
