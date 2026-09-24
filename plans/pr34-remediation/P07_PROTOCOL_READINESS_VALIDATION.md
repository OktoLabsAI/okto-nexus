# P07 — reject incompatible readiness replies

Parent `27b6526`, `feature/v0.2.0`; this is partial T-LIFE-12 coverage, not
completion of binary-version/effective-capability negotiation.

## Reproduction and correction

Through the actual authenticated production HTTP/open composition, a real Python
Pi RPC fixture answered get_state with success=false. Nexus returned HTTP200,
RUNNING and protocol_ready and created canonical presence. This proved only that
the pipe exchanged a message, not successful protocol readiness.

PiRpcConnector.start now requires success exactly true and object-shaped data.
The existing startup failure path reaps the owned child, terminates the event
iterator and leaves the endpoint quarantined. A false, string-typed success or
array-shaped data produces a bounded protocol_incompatible diagnostic, without
copying native error payloads into the response. The test opens another adapter
after the failure to prove isolation rather than globally disabling the feature.

CodexAppServerConnector.start now validates thread/start's object/thread/string
identity before inserting session/correlation maps. Empty, nonstring, missing,
whitespace-only or over256-character IDs are incompatible. No turn is dispatched
for a failed open. This does not claim deduplication, resume, version negotiation
or verification of advanced capabilities merely from a successful handshake.

## Exact evidence

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_protocol_compatibility.py -x`:
  behavioral RED1 FAIL in3.57s, Pi rejected get_state still published protocol_ready.
- Initial correction run `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_protocol_compatibility.py tests/test_harness_pi_connector.py tests/test_harness_codex_connector.py`:
  62 PASS/3 FAIL/2 SKIP in38.61s. The three failures were a fixture log that had
  never been created (no turn was sent), after the intended rejection assertions
  already passed. Added explicit fixture method logging, preserving the assertion
  that no turn/start appears. One known deliberately injected Pi thread warning.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_protocol_compatibility.py`:
  6 PASS in18.48s.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_protocol_compatibility.py`:
  6 PASS in18.48s.
- `rtk proxy ruff check src/okto_nexus/adapters/outbound/harness/pi.py src/okto_nexus/adapters/outbound/harness/codex.py tests/test_runtime_protocol_compatibility.py`: PASS.
- Actual installed **Codex0.156.1** two-turn campaign:
  `rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ.update(OKTO_NEXUS_NATIVE_CAMPAIGN="codex",OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe",OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.codex/auth.json"); raise SystemExit(pytest.main(["-q","-rP","tests/test_runtime_native_campaign.py","-k","two_turns and codex"]))'`
  returned1 PASS/7 deselected in14.64s. Isolated project/store/native configuration,
  existing fixture copies only the authorized login and removes it in finally.
  No Nexus operator key goes to the native subprocess; sandbox/approvals retained.
  Version observed using --version with only OS/path/temp environment variables.

Pi native, Claude stream and dedicated Claude attach native NOT_RUN in this unit.
No migration or surface-schema change. Next: full effective capability/version
contract, remaining administrative/cutover/backup gates and final P12 acceptance.

Final integrated command: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_protocol_compatibility.py tests/test_harness_pi_connector.py tests/test_harness_codex_connector.py tests/test_runtime_session_recovery.py tests/test_runtime_boot.py` returned **80 PASS/2 SKIP**, one known injected Pi thread warning, in69.69s.
