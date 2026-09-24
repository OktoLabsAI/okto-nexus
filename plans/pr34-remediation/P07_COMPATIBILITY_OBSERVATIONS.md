# P07 — native version observations, separated from caller metadata

Parent `217e02540e40392db948fae2d16a02f7c8687a0b`, feature/v0.2.0.
This unit supplies durable evidence for subsequent capability negotiation. It
does NOT complete the effective-capability or T-LIFE-12 gate.

## Implemented contract

The installed Codex0.156.1 initialize response was inspected using a temporary
empty HOME/CODEX_HOME, no copied authentication and no model turn. Its keys were
codexHome, platformFamily, platformOs and userAgent. The userAgent identifies the
Nexus client and native version (`okto-nexus/0.156.1 ...`), not `codex/0.156.1`.
The raw response must not become public metadata: it includes a private path.

CodexAppServerConnector now retains a bounded native_version projection from the
existing initialize response, with schema_version1 and capabilities_verified=false.
Unknown, oversized, differently prefixed and prerelease formats remain unobserved.
The complete user-agent, home path and arbitrary native fields are discarded.
No additional native call, status polling or subprocess is added to normal opens.

HarnessSession.compatibility_report is distinct from caller metadata. Additive
migration056 persists it on harness_sessions with an empty-object default for old
sessions; SqliteHarnessSessionRepo round-trips it. Session REST/MCP and authorized
RuntimeDiscoveryService reads expose the same report. User metadata with a fake
compatibility_report cannot overwrite that server-owned field. No agent profile,
grant or effective capability is elevated by a version observation.

Surface44, identity resource11. Descriptor capability_verification remains
not_probed. Other connectors retain empty reports pending their own evidence.
No destructive migration reversal, native replay, provider fallback or removal.

## Evidence

- New integration tests against archived parent217e025 reproduce the missing
  observation: HTTP open succeeds but report is {}, not the captured version.
  **1 FAIL in11.09s**. The first archive runner omitted HOME/USERPROFILE and failed
  fixture setup; that result is a runner error, not behavioral RED. The corrected
  runner used a fresh temporary HOME, PYTHONPATH pointing at archived src and
  `pytest -q -x -o pythonpath=<archive>/src tests/test_runtime_compatibility_observations.py`.
  No live store, branch reset or original code mutation was used for the archive.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_compatibility_observations.py -x`:
  initial4 PASS in15.92s. Tightened prerelease parsing after that run.
- Final `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_compatibility_observations.py tests/test_runtime_discovery.py tests/test_harness_codex_connector.py tests/test_runtime_operation_reconciliation.py tests/test_migrations.py tests/test_frente1_resources.py tests/test_feature_flags.py`:
  **128 PASS/1 SKIP in146.41s**, one existing Starlette/httpx warning. Includes
  revised migration53→56/repeatability, persistence, scoped discovery and flags.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_compatibility_observations.py tests/test_runtime_discovery.py`:
  **16 PASS in75.20s**.
- `rtk proxy ruff check src/okto_nexus/adapters/outbound/harness/compatibility.py src/okto_nexus/adapters/outbound/harness/codex.py src/okto_nexus/adapters/outbound/sqlite/harness_repo.py src/okto_nexus/application/runtime_discovery.py tests/test_runtime_compatibility_observations.py`: PASS.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py 217e025`:
  OFF43 tools/40448 chars; ON51 tools/47730 chars; both unchanged.
- Actual Codex0.156.1 two-turn test now asserts the version observation and its
  capabilities_verified=false limitation through the production open response:
  `rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ.update(OKTO_NEXUS_NATIVE_CAMPAIGN="codex",OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe",OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.codex/auth.json"); raise SystemExit(pytest.main(["-q","-rP","tests/test_runtime_native_campaign.py","-k","two_turns and codex"]))'`
  **1 PASS/7 deselected in19.11s**. Existing isolated fixture, login-only temporary
  copy removed in finally, sandbox/approval controls retained, no operator key in
  native environment. Pi/Claude/attach native NOT_RUN in this unit.

Next: actual effective-capability verification and enforcement, probes for other
adapters, remaining admin/cutover/backup and P12 final matrix. Final gate NOT PASSED.
