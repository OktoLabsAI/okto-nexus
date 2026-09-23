# P09 — explicit native request requirements

Parent `6cb0f89`, 2026-09-23. Migration 048 and surface revision 38 unchanged.

Approved profile config now accepts `required_native_requests` (contract v1): a
unique list of at most 32 names. Names must match the adapter's implemented input
contract exactly. Codex examples: `item/commandExecution/requestApproval` and
`item/fileChange/requestApproval`. Claude examples:
`control_request:can_use_tool/Write`, `/Edit`, `/Bash`. The slash suffix makes the
restricted tool coverage explicit. A broad `can_use_tool` requirement does not
pretend all tool permissions or input flows are implemented.

`runtime_requirements.validate_native_requirements` is pure validation, reused by
EndpointService profile creation, RuntimeAccessService for effects, both production
RuntimeDeliveryPlanner compositions and the last preconstruction boundary. Checks
run without secret resolvers/process/network calls inside the transaction. A
descriptor/profile cannot manufacture a supported capability. Current HITL flag
is rechecked, including existing sessions and managed claim/grant admission.

Unsupported profile requirements deny opening or executable claims. Conversation
delivery can stay in the canonical inbox or use a compatible authorized endpoint;
no second queue or implicit claim is created. Compatible profiles without the
new optional field preserve their existing semantics. Declaring requirements is
an operator choice; this field does not inspect task prose or promise a native
sandbox. Full input/elicitation support remains subsequent P09 work.

## Evidence

Behavioral RED on parent (an isolated persisted profile with an unmet input
requirement): `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_profile_requirements.py -x`
returned **1 FAIL, 3.57s**: REST opened a runtime with status 200 instead of denying
before spawn. An earlier test-authoring call used the wrong fixture signature
and failed **1 FAIL, 6.66s**; it is not the behavioral reproduction.

Implementation checks found two test expectations to correct: validation errors
use HTTP 422 (not 400), and no-dispatch message responses omit runtime_operations
rather than return an empty list. Neither required weakening production behavior.

- Windows expanded command: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_profile_requirements.py tests/test_runtime_endpoints.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_grants.py tests/test_runtime_boot.py`:
  **66 PASS, 1 FAIL, 147.86s**; sole failure was that optional-field expectation.
- Linux expanded command: `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_profile_requirements.py tests/test_runtime_endpoints.py tests/test_runtime_handoff_dispatch.py`:
  **41 PASS, 1 FAIL, 95.60s**, same expectation.
- Corrected targeted Windows `-k rechecked -x`: **1 PASS, 7 deselected, 3.91s**.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_messages.py tests/test_message_delivery.py tests/test_surface_metrics.py tests/test_tools_surface.py`:
  **71 PASS, 14.90s**. Covers legacy messages and published tool surface after
  sharing the registry in the message composition.
- Ruff changed files: **PASS**.

No native/model calls made for this unit. The installed Codex generated additional
input/elicitation JSON schemas into a disposable directory for the next unit;
schema availability alone is not a completed input integration or native PASS.
P09 and the final gate remain IN_PROGRESS/NOT PASSED.

Corrected complete new suite: `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_runtime_profile_requirements.py`: **8 PASS, 26.90s**. Linux counterpart `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_runtime_profile_requirements.py`: **8 PASS, 31.23s**. No production changes after the expanded runs; only the optional-field test assertion changed.
