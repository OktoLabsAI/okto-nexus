# P07 — multiplexing through the production factory

Parent `8e7888a122b2b8a2d5deed59445663a2cee43726`, feature/v0.2.0.
Surface49, identity resource16, schema056 unchanged. Final gate NOT PASSED.

## Finding and correction

Existing shared-connection tests injected one native connector instance into the
factory. The normal factory created a new native instance for every open, so
the advertised Codex multiplexing was not reachable through production opening.

`construct_profile_connector` now configures an optional trusted reuse key on
`EnvelopeConnector`. The opaque digest covers canonical agent/workspace/adapter,
project root, profile identity/revision, resolved backend including environment,
required native request contracts and HITL mode. Secret resolution remains outside
SQLite write transactions. The digest and its material are never API/store fields.
The optional hook preserves existing extension contracts; no payload import or
product branch was added to the supervisor.

`HarnessSupervisor._open` selects an already ready matching multiplexing connector
under its existing lock and obtains the connection lifecycle scope before releasing
that lock. Final close cannot intervene between selection and scope acquisition.
The unused freshly constructed connector has not spawned a process. There is no
new cache, executor, polling loop or unbounded thread mechanism. The original
context guard still validates the selected connection. Nonmultiplexing adapters
keep separate instances. Simultaneous first opens may create separate connections;
subsequent/concurrent opens can reuse a ready one. No startup is speculatively shared.

The registry's control declarations and version checks are unchanged. This unit
qualifies actual Codex multiplexing, not every effective capability or all versions.

## Evidence

- Initial new fixture used disallowed extra command arguments and correctly failed
  profile validation:1 FAIL in4.25s. Not a behavior RED. The fixture now uses the
  approved `[executable, app-server]` contract: Python is its disposable synthetic
  peer executable and `app-server` is a fixture script in its temporary workspace.
  No factory, adapter class or native transport is monkeypatched.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_production_multiplex.py`:
  behavioral RED1 FAIL in4.77s: two compatible opens returned different connection
  IDs. After correction1 PASS in5.57s, sibling send and final stop included.
- Expanded production fixtures cover agent/workspace/profile/revision/resolved
  secret/HITL isolation, concurrent openings on an existing connection, distinct
  sessions, sibling survival and complete final owned shutdown.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_production_multiplex.py tests/test_runtime_shared_connection.py tests/test_runtime_session_recovery.py tests/test_runtime_boot.py`:
  **31 PASS in94.36s**.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_production_multiplex.py tests/test_runtime_shared_connection.py tests/test_runtime_session_recovery.py tests/test_runtime_boot.py`:
  **31 PASS in119.50s**. Synthetic peers only; no WSL provider invocation.
- Ruff on changed production/test modules: PASS.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_contracts.py tests/test_runtime_configuration_updates.py tests/test_runtime_effective_controls.py tests/test_feature_flags.py tests/test_frente1_resources.py tests/test_import_boundary.py`:
  **90 PASS in51.11s**, one existing Starlette/httpx deprecation warning.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py 8e7888a`:
  OFF43 tools/40448 characters; ON51 tools/47730 characters, unchanged.

## Real native campaign

The new `test_native_multiplex_uses_production_factory` uses the normal authenticated
serve/REST/MCP composition and installed Codex in a disposable project/config.
Only the already authorized login is temporarily copied and deleted on exit.
No personal settings, sessions, MCP servers or operator key enter the process.
No sandbox/approval downgrade, file-writing tool or speculative replay occurs.

Command (the executed wrapper additionally preserved redacted observations under
a unique temporary pytest basetemp and wrote the evidence JSON below):

```powershell
rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ.update(OKTO_NEXUS_NATIVE_CAMPAIGN="codex",OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe",OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.codex/auth.json"); raise SystemExit(pytest.main(["-q","--tb=short","-rP","tests/test_runtime_native_campaign.py","-k","native_multiplex"]))'
```

**1 PASS/14 deselected in13.55s**, Codex0.156.1: one process, distinct native threads,
three correctly correlated durable results, first close detached without killing
the sibling, another sibling turn succeeded, and final process stop was observed.
See `evidence/p07-native-production-multiplex.json`.

Native Pi and dedicated attach remain NOT_RUN. Broader effective-capability
verification, cutover/backup/restore, immutable full regression and P12 remain
pending; no phase is promoted to VERIFIED by this narrower evidence.
