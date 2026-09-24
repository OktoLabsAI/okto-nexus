# P07/P09 — bounded Claude version observation and native requirements

Parent `bffb03f89af4e4fb961296031a9c69249e3a3480`, branch `feature/v0.2.0`.
Surface46 / identity resource13; schema056 unchanged. Final gate NOT PASSED.

## Implementation and contract

`compatibility.claude_version_observation` runs the approved executable's
`--version` before the stream process, outside SQLite writers, in its approved
working directory and sealed environment. The same Windows Job/Linux guardian
owns the probe from birth. It waits up to three seconds before reading, bounding
output by the OS pipe; flooding also times out. It reads at most1025 bytes only
after tree-stop observation, retains no raw output, and closes the pipe. Timeout
kills/waits the owned tree and fails startup before any stream/model request.

`ClaudeCodeStreamConnector.start` copies the redacted observation into the server
session report. The existing EnvelopeConnector requirement check runs before
canonical readiness/presence. Unknown/malformed versions satisfy no mandatory
native request; forged metadata has no authority. Failed-open retry does not
spawn again. Basic profiles without native requirements retain their behavior.
`version_argv` is trusted constructor injection for real-process protocol fixtures,
not an API/profile option or agent-controlled command.

Exact2.1.280 contract: Write/Edit/Bash/AskUserQuestion, referring to the existing
P09 protocol fixtures and native campaigns. The installed executable had updated
to2.1.281: the first mandatory Write open correctly failed before work. Fresh
isolated qualification then passed Write denial and AskUserQuestion explicit
input. Only those two methods were added for2.1.281. Edit/Bash remain unverified
for that version. No semver range, sandbox claim or general capability grant was
added. `capabilities_verified` remains false.

The opt-in `test_native_contract_qualification` permits qualification of an
installed update using a profile without mandatory native requests; this is an
existing supported profile, not a security bypass. It preserves the same native
approval bridge, canonical handoff, explicit operator decision, sandbox defaults,
isolated authentication and lifecycle assertions. Its additional environment
switch prevents it running accidentally in the regular native campaign.

## Commands and observed results

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_claude_compatibility.py`:
  behavioral RED1 FAIL in0.28s: start returned an empty report. After implementation,
  initial10 PASS in8.73s, including malformed/unknown/flood/timeout and authenticated
  REST/MCP required-contract tests. One later2.1.281 case is in the final gate.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_claude_compatibility.py tests/test_harness_claude_code_connector.py tests/test_runtime_claude_approvals.py`:
  41 PASS/7 native-opt-in SKIP in104.54s; selected before the extended new suite.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_claude_compatibility.py`:
  initial10 PASS in14.03s.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_claude_compatibility.py tests/test_runtime_claude_approvals.py tests/test_runtime_native_inputs.py`:
  final39 PASS in129.39s, including2.1.281 fixture.
- `rtk proxy ruff check src/okto_nexus/adapters/outbound/harness/compatibility.py src/okto_nexus/adapters/outbound/harness/claude_code_stream.py tests/test_runtime_claude_compatibility.py tests/test_runtime_native_campaign.py`: PASS.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py bffb03f`:
  OFF43 tools/40448 characters; ON51 tools/47730 characters, unchanged.

Native commands (no token values; approved local login copied into a disposable
test configuration; no settings, hooks, personal sessions or MCP servers copied):

```powershell
rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ.update(OKTO_NEXUS_NATIVE_CAMPAIGN="claude_code",OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/.local/bin/claude.exe",OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.claude/.credentials.json"); raise SystemExit(pytest.main(["-q","-rP","tests/test_runtime_native_campaign.py","-k","approval_denial and claude_code"]))'
```

Initial1 FAIL/7 deselected in6.01s: native_requirements_unverified, correctly
rejected2.1.281 while only2.1.280 was known. No task submission. A read-only version
inspection confirmed `2.1.281 (Claude Code)`.

```powershell
rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ.update(OKTO_NEXUS_NATIVE_CAMPAIGN="claude_code",OKTO_NEXUS_QUALIFY_NATIVE_CONTRACT="1",OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/.local/bin/claude.exe",OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.claude/.credentials.json"); raise SystemExit(pytest.main(["-q","-rP","tests/test_runtime_native_campaign.py","-k","contract_qualification"]))'
```

Qualification:2 PASS/8 deselected in33.35s. Fresh operations, no replay of the
failed open. Canonical denial and explicit answer blue reached the native peer.

```powershell
rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ.update(OKTO_NEXUS_NATIVE_CAMPAIGN="claude_code",OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/.local/bin/claude.exe",OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.claude/.credentials.json"); raise SystemExit(pytest.main(["-q","-rP","tests/test_runtime_native_campaign.py","-k","claude_code and (approval_denial or question_roundtrip)"]))'
```

Mandatory-contract campaign after qualification:2 PASS/8 deselected in35.33s.
Both tests observe stopped processes, unchanged security controls, no denied
fixture write and canonical SENT_UNCONFIRMED reply state (not a fabricated ACK).
Temporary login copies are removed by fixture teardown.

An expanded pytest command initially referenced nonexistent
`tests/test_runtime_claude_inputs.py`: no tests ran; not a behavior RED or PASS.
It was corrected to `tests/test_runtime_native_inputs.py` in the final selection.

## Limits / next dependency

Final Windows integration command:
`rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_claude_compatibility.py tests/test_runtime_effective_requirements.py tests/test_runtime_profile_requirements.py tests/test_runtime_compatibility_observations.py tests/test_runtime_claude_approvals.py tests/test_runtime_native_inputs.py tests/test_runtime_contracts.py tests/test_import_boundary.py tests/test_feature_flags.py tests/test_frente1_resources.py`:
**122 PASS in160.61s**, one existing Starlette/httpx deprecation warning.

This closes Claude explicit native-request version matching, not all effective
capability negotiation. Remaining dimensions/adapters, administrative parity,
cutover/backup and full P12 immutable-SHA regression/native controls remain pending.
Pi and dedicated Claude attach native tests remain NOT_RUN under the user's scope.
No personal store migration, merge or local reinstall occurred in this unit.
