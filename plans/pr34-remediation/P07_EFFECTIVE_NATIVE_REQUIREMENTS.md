# P07/P09 — required native contracts and cancel-only approvals

Parent `0e305d3ba8c26572cbccde326f8e3de5e364b436`, feature/v0.2.0.
Surface45 / identity resource12, schema056 unchanged. Final gate NOT PASSED.

## Integrated behavior

Profile required_native_requests already restricted the adapter declaration and
HITL flag. A production HTTP regression proved that an unrecognized runtime99.0.0
still became protocol_ready for such a profile. EnvelopeConnector now validates
the required subset against server-owned runtime evidence inside the bounded
startup worker, before canonical readiness/presence or any turn. Failure ends
only its logical session and cancels the birth-owned startup scope. Exact failed
open retries do not spawn again. Caller metadata cannot satisfy the requirement.

The current request-contract allowlist is exact Codex0.156.1, referencing the
installed schema documented in P09_NATIVE_PROTOCOL_SURVEY.md and the existing
Nexus input/approval handlers. It covers command/file approvals, requestUserInput
and form elicitation. It is neither a semver compatibility range nor authority.
compatible_native_requests and native_request_basis distinguish this narrow
contract match from capabilities_verified, which remains false. Unsupported
versions, or adapters without equivalent evidence, cannot satisfy explicit native
requirements; profiles without such requirements retain their existing behavior.
Other capability dimensions/adapters still need their effective probes.

The real native campaign then exposed a separate protocol-shape defect: Codex
offered accept, an execpolicy-amendment alternative, and cancel, without decline.
The bridge rejected that valid request before canonical HITL. The adapter now
accepts a request only when one-shot accept and a supported negative choice exist.
Canonical decline maps to native decline when available, otherwise cancel. The
adapter never selects an amendment or session-wide grant for ordinary approval.
Authority revalidation can force this same negative mapping. Audit decision
remains canonical decline, with original native choices retained in request_payload;
SENT_UNCONFIRMED remains a write observation, not a fabricated native ACK.

## Evidence and intermediate failures

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_effective_requirements.py -x`:
  behavioral RED1 FAIL in5.75s, unknown99.0.0 returned HTTP200/protocol_ready despite
  mandatory native approval contract. Initial correction2 PASS in9.11s.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_effective_requirements.py tests/test_runtime_profile_requirements.py tests/test_runtime_compatibility_observations.py`:
  initial13 PASS/1 FAIL in45.57s: older flag test used a FakeConnector without any
  runtime evidence. Migrated that test to a real versioned Python JSON-RPC fixture,
  preserving its HITL revocation/claim/inbox assertions. Corrected14 PASS in37.65s.
- The corresponding Linux command using the standard WSL Python prefix returned
  14 PASS in61.12s. Later expanded Linux command below supersedes that scope.
- Before cancel correction, expanded Windows requirements/approvals/contracts/
  import-boundary selection returned41 PASS in102.21s. This did not include the
  subsequently added cancel-only cases and did not prove actual native approval.
- Actual installed Codex0.156.1 native approval campaign failed twice:1 FAIL/7
  deselected in17.54s, then1 FAIL/7 deselected in16.79s with redacted request-shape
  instrumentation. Native method was item/commandExecution/requestApproval;
  bridge returned false for choices accept/extended/cancel. No fixture write;
  temporary authentication copies removed. These are failures, not NOT_RUN/PASS.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_native_approvals.py -k cancel_only -x`:
  behavioral RED1 FAIL/13 deselected in10.94s, approval never reached canonical
  queue. After adapter correction, `-k cancel_only` returned2 PASS/13 deselected
  in10.66s (one-shot acceptance and cancellation, no amendment). Added revocation
  variant: `-k revoked` returned1 PASS/15 deselected in7.06s.
- Native campaign after correction (fresh isolated operation, not replay):
  `rtk proxy .venv/Scripts/python.exe -c 'import os,pytest; os.environ.update(OKTO_NEXUS_NATIVE_CAMPAIGN="codex",OKTO_NEXUS_TEST_EXECUTABLE="C:/Users/jpamb/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe",OKTO_NEXUS_TEST_AUTH_SOURCE="C:/Users/jpamb/.codex/auth.json"); raise SystemExit(pytest.main(["-q","-rP","tests/test_runtime_native_campaign.py","-k","approval_denial and codex"]))'`
  **1 PASS/7 deselected in17.43s**. Same mandatory native request profile, actual
  canonical human rejection, preserved sandbox/approvals. Test copy and fixture
  marker both absent afterward. No operator key in the native process.
  Redacted before/after observations: evidence/p07-required-native-contract.json.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_effective_requirements.py tests/test_runtime_profile_requirements.py tests/test_runtime_compatibility_observations.py tests/test_runtime_native_approvals.py`:
  **29 PASS in129.30s**, before the late added revocation variant.
- `rtk proxy ruff check src/okto_nexus/adapters/outbound/harness/compatibility.py src/okto_nexus/adapters/outbound/harness/envelope.py src/okto_nexus/adapters/outbound/harness/codex.py src/okto_nexus/application/runtime_requirements.py tests/test_runtime_effective_requirements.py tests/test_runtime_profile_requirements.py tests/test_runtime_compatibility_observations.py tests/test_runtime_native_approvals.py tests/test_runtime_native_campaign.py`: PASS.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py 0e305d3`:
  OFF43 tools/40448 chars; ON51 tools/47730 chars; no resident schema growth.

Native Pi, Claude stream and dedicated attach NOT_RUN in this unit. No full phase
promotion: other effective capabilities/versions, remaining administrative parity,
cutover/backup, advanced native campaigns and immutable-SHA P12 gate remain pending.

Final Windows integration: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_effective_requirements.py tests/test_runtime_profile_requirements.py tests/test_runtime_compatibility_observations.py tests/test_runtime_native_approvals.py tests/test_runtime_native_inputs.py tests/test_runtime_contracts.py tests/test_import_boundary.py tests/test_runtime_boot.py tests/test_frente1_resources.py tests/test_feature_flags.py` returned **125 PASS**, one existing Starlette/httpx warning, in214.64s (before the late revocation variant, separately passed above).

Extension check: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_pr34_remediation.py -k additional` returned **3 PASS/34 deselected in7.70s**. Processless registered adapter composition remains usable without a native requirement hook.
