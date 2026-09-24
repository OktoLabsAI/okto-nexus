# P07 — attach protocol contract before effects

Parent `90f673e807da9664325cd4f0c25afb46f51cb0ab`, branch `feature/v0.2.0`.
Surface47 / identity resource14 / unchanged schema056. Final gate NOT PASSED.

## Finding, implementation and compatibility

`ClaudeCodeAttachConnector._check_peer_protocol` admitted missing/null protocol
values; Python equality also admitted boolean true and float1.0 as protocol1.
`send` did not revalidate a registry's changed protocol after start. Five real
Unix-socket fixture regressions reproduced these behaviors. No personal session,
provider or historical socket/token was used.

The shared probe/start check now requires `type(peerProtocol) is int` and exact
value1. Every send re-reads the external registry and applies the same check
before opening/writing the socket. An unknown wire format is refused with the
existing protocol_mismatch/protocol_drift diagnostic; there is no permissive
missing-field fallback. This explicitly supersedes the historical connector test
that accepted absent protocol as a merely unverified warning.

The session's server-owned compatibility_report records the observed protocol,
bounded optional semantic native version, `transport_contract=cc_socks_peer_1`,
and `ack_level=NONE`. It contains no bearer token, socket path or arbitrary
registry fields. Migration056 and existing REST/MCP persistence are reused.
`capabilities_verified=false` and no compatible native approval requests remain
honest: local registry/socket preconditions do not establish native acceptance.

Existing protocol1 conversational injection is preserved. Authenticated production
REST opens a real fixture attach connector; MCP reads its persisted report and
submits a durable send; the real Unix peer receives the framed content. Transport
state stays SENT_UNCONFIRMED without a durable result, steering/interrupt are
rejected, and close returns detached without killing the external test process.
The negative REST/MCP case leaves no persisted ready session or socket connection.

## Evidence

All Linux commands use the supported isolated WSL Python3.13 environment:

```powershell
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_attach_compatibility.py
```

- Behavioral RED:5 FAIL/2 PASS in4.02s. Null/boolean/float/missing values admitted;
  changed protocol did not prevent send. Existing string1 and integer2 rejection
  already passed. These are behavior failures, not missing imports.
- After correction, the above suite plus `tests/test_claude_code_attach_connector.py`
  returned64 PASS in7.40s (before the two authenticated composition cases).
- First expanded composition attempt:1 FAIL/8 PASS in15.52s because a misplaced
  test assertion referenced an undefined local connector after completing the
  valid send/detach flow. Ruff also caught this; it was fixed. This is a test
  editing error, not a second product regression reproduction.

```powershell
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_attach_compatibility.py tests/test_claude_code_attach_connector.py tests/test_runtime_protocol_compatibility.py tests/test_runtime_attach_platform.py tests/test_runtime_contracts.py tests/test_runtime_commands.py
```

Final Linux integrated result: **97 PASS in73.05s**. Real disposable AF_UNIX peer,
actual production owner/dispatcher/authentication/journal composition, no models.

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_attach_platform.py tests/test_runtime_attach_compatibility.py tests/test_runtime_contracts.py tests/test_import_boundary.py
```

Windows:17 PASS/9 POSIX SKIP in1.80s. These skips are NOT_RUN on Windows, not PASS
or NOT_APPLICABLE. Windows attach remains explicitly unsupported before effects.

Final Windows platform/surface gate:
`rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_attach_platform.py tests/test_runtime_contracts.py tests/test_runtime_protocol_compatibility.py tests/test_feature_flags.py tests/test_frente1_resources.py`:
**75 PASS in26.07s**, one existing Starlette/httpx deprecation warning.

`rtk proxy ruff check src/okto_nexus/adapters/outbound/harness/claude_code_attach.py tests/test_runtime_attach_compatibility.py tests/test_claude_code_attach_connector.py`: PASS.

`rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py 90f673e`:
OFF43 tools/40448 characters; ON51 tools/47730 characters, unchanged.

## Remaining work

This establishes the strict attach wire precondition, not native receipt or a
full effective-capability gate for all adapters. Remaining controls/version
negotiation, administrative parity, cutover/backup and P12 full regression/native
advanced campaigns are still pending. Native Pi and dedicated attach remain
NOT_RUN under the current user-authorized scope. No live store was migrated.
