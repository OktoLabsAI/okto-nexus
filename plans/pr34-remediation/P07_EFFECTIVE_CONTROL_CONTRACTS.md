# P07 — session evidence for native steering and interruption

Parent `82f7c7774b183a380aec3f5089d18592775c759e`, feature/v0.2.0.
Surface48 / identity resource15 / schema056 unchanged. Final gate NOT PASSED.

## Implemented path

Two authenticated MCP regressions proved that Codex99.0.0 admitted steer/interrupt
solely from the connector declaration, despite having no known version contract.
The correction adds the pure `validate_effective_control` predicate to shared
RuntimeControlService admission, dispatch revalidation, and HarnessSupervisor's
internal send boundary. Missing evidence denies the control before creating a new
intent; a pending command whose evidence is invalidated is rejected before write.
Profile/grant/owner/expected-operation/turn checks remain additional requirements.
Idempotent retries still return the previously admitted operation without replay.

Server-owned session reports contain `compatible_controls` and
`control_contract_basis`. Product/version mapping remains at the adapter edge,
not in domain or application product branches. Exact version contracts cover
Codex0.156.1 and Claude2.1.281 (isolated native observations below) and Pi0.85.1
(existing wire fixtures and protocol reference, native campaign NOT_RUN).
Trusted processless extensions may report tested_protocol_contract without an
invented executable version. Payload metadata never supplies this report.

Pi now obtains a bounded owned --version observation before its normal get_state
readiness handshake. The same implementation bounds stdout, time and process-tree
cleanup for Pi and Claude; only format parsing differs. Trusted fixture injection
version_command is not a profile/API option. No new migration, secret resolution
inside SQLite, native status polling or permissive security profile was added.

The overall capabilities_verified flag stays false: these checks cover controls,
not all endpoint capabilities. Conversation, shutdown ownership, native requests,
managed work, replay and deduplication remain separate contracts. The broader
effective-capability gate is still pending.

## Fixture evidence

- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_effective_controls.py`:
  behavioral RED2 FAIL in12.82s: both unknown-version controls returned durable
  accepted command IDs. Corrected tests also assert REST parity, no control rows,
  no wire controls, forged metadata rejection and the direct supervisor guard.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_effective_controls.py tests/test_runtime_commands.py tests/test_runtime_compatibility_observations.py tests/test_runtime_claude_compatibility.py`:
  28 PASS in192.14s, before the additional three effective-control cases.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_effective_controls.py tests/test_runtime_commands.py tests/test_runtime_compatibility_observations.py`:
  20 PASS in144.26s, including dispatch invalidation and Pi version cases, before
  the late direct-supervisor assertion (subsequently exercised on Windows).
- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_effective_controls.py tests/test_harness_supervisor.py tests/test_harness_tools.py tests/test_harness_pi_connector.py tests/test_runtime_claude_compatibility.py tests/test_runtime_effective_requirements.py tests/test_import_boundary.py`:
  94 PASS/3 opt-in or platform SKIP in121.75s; one existing injected Pi death-path
  thread warning. This ran before the late direct-supervisor assertion.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_effective_controls.py tests/test_runtime_contracts.py tests/test_feature_flags.py tests/test_frente1_resources.py`:
  final71 PASS in28.89s; one existing Starlette/httpx warning.
- `rtk proxy ruff check src/okto_nexus/adapters/outbound/harness/compatibility.py src/okto_nexus/adapters/outbound/harness/pi.py src/okto_nexus/application/runtime_requirements.py src/okto_nexus/application/runtime_control.py src/okto_nexus/application/harness_supervisor.py tests/test_runtime_effective_controls.py tests/test_runtime_commands.py tests/test_harness_tools.py tests/test_runtime_compatibility_observations.py tests/test_runtime_native_campaign.py`: PASS.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py 82f7c77`:
  OFF43 tools/40448 characters; ON51 tools/47730 characters, unchanged.

The common application FakeConnector now explicitly reports its tested fixture
control contract. Real-pipe Codex/Claude production-composition tests supply native
version replies from their fixture peers; they do not bypass the new check.

## Native campaign and failures

`test_native_active_control_preserves_session` runs only with the existing explicit
native campaign configuration. It opens the installed CLI in a disposable project,
isolated configuration containing only an authorized temporary login copy, and
an isolated production Nexus owner. It observes native generation before issuing
a fenced operator control, waits for a durable result, checks process survival,
and observes owned shutdown. No sandbox, approval, model or provider controls are
disabled. Reply text is never used to complete a handoff.

Exact native commands use the existing explicit paths:

```powershell
rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ.update(OKTO_NEXUS_NATIVE_CAMPAIGN="codex",OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe",OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.codex/auth.json"); raise SystemExit(pytest.main(["-q","--tb=short","-rP","tests/test_runtime_native_campaign.py","-k","active_control and codex"]))'
rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ.update(OKTO_NEXUS_NATIVE_CAMPAIGN="claude_code",OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/.local/bin/claude.exe",OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.claude/.credentials.json"); raise SystemExit(pytest.main(["-q","--tb=short","-rP","tests/test_runtime_native_campaign.py","-k","active_control and claude_code"]))'
```

Observed sequence (each run used fresh operations; no uncertain replay):

1. Initial fixture mistake:2 Codex FAIL/12 deselected in12.25s, treating a string
   runtime_operations entry as an object. Corrected the fixture, not production.
2. Before enforcement:Codex2 PASS/12 deselected in33.54s; Claude2 PASS/12 deselected
   in22.55s. Redacted actual observations in p07-native-control-qualification.json:
   Codex0.156.1/Claude2.1.281, steer success/interrupt interrupted, process survival.
3. After enforcement with the original conversational inbox stimulus:Codex2 FAIL
   in66.00s (short refusal of untrusted story request completed before the intended
   control effect); Claude2 PASS in78.29s. These failures are retained, not PASS.
4. Changed the stimulus to an explicit operator administrative turn, since this
   campaign measures transport controls rather than model interpretation of inbox
   data. A3000-word Codex fixture gave1 FAIL/1 PASS in150.39s: steer did not produce
   a terminal within120s; interrupt passed. The1000-word diagnostic variant
   (`-k "active_control and codex and steer"`) also failed in131.20s. At that
   point the missing terminal had not yet been localized.
5. Claude's explicit1000-word administrative control campaign passed2/12 deselected
   in22.37s, preserving both result outcomes and session survival.

6. Redacted diagnostics reproduced the failure in132.73s. The disposable database
   recorded `failure_type=NativeEventOverflow`, `stop_observed=true` and lifecycle
   `outcome_unknown`. The native control response itself had no error. This was
   a Nexus capture/projection bottleneck, not evidence of a provider timeout.
7. Decoupled durable native capture from SQLite projection: the same Codex steer
   passed in55.42s with1269 text deltas and a durable terminal. Evidence:
   `evidence/p07-native-control-after-capture-fix.json`.
8. Final bounded batch projection and synchronous direct-capture compatibility:
   native Codex steer+interrupt2 PASS/12 deselected in75.68s; Claude steer+interrupt
   2 PASS/12 deselected in20.92s. Commands above, fresh disposable operations.

See P08_CAPTURE_PROJECTION_ISOLATION.md for the throughput correction and crash
regressions. Diagnostics retain protocol names/item types/response error codes
without content, credentials or arbitrary native fields. P12 remains incomplete.
Pi and dedicated Claude attach native campaigns remain NOT_RUN.
