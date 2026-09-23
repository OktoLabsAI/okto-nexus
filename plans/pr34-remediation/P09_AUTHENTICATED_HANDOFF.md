# Authenticated handoff identity

Parent `c67e7dc`, branch `feature/v0.2.0`, 2026-09-23. P09 remains IN_PROGRESS.

A real HTTP MCP request reproduced an additional F02/F07 boundary defect:
the creator's API key plus `agent_id` naming the claimant completed the
claimant's handoff. The authenticated test expected PERMISSION_DENIED but
observed `ok=true`, `status=VERIFYING`. Claim generations alone cannot repair
identity impersonation. The test uses the production app, middleware, MCP
serialization and canonical service, not a direct mock of authentication.

`HandoffService._require_actor` now obtains the adapter-provided authenticated
request context and revalidates the active canonical agent and credential hash
inside each operation's UoW. Create, list, claim, get, complete, verify, reject
and cancel share this enforcement. No operator impersonation is implicit.
The same `build_service` wires MCP and REST. Legacy cooperative unauthenticated
stdio retains its existing trust contract; it does not obtain runtime control
authority from this change. Session-trust requirements remain additive.

HITL create interception captures the original creator's credential binding
(hash only). Canonical approval execution rechecks that binding and normal
creation policies; it does not treat the deciding operator as the creator.
Key rotation/deactivation blocks the deferred creation. Existing historical
cooperative approvals without an authenticated binding retain their original
internal execution contract; they do not create runtime grants.

Evidence:

- Behavioral RED: `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_handoff_epochs.py -k authenticated --tb=short`:
  **1 FAIL / 2 deselected in 1.84s**, forged complete accepted.
- Final Windows: `rtk proxy .venv/Scripts/python.exe -m pytest -q
  tests/test_runtime_handoff_epochs.py tests/test_hitl.py tests/test_handoff.py
  tests/test_verification.py tests/test_handoff_dependencies.py
  tests/test_import_boundary.py --tb=short --maxfail=4`:
  **212 PASS in 35.22s**. Includes all eight spoofed verbs, both verification
  surfaces, original creator approval success and refusal after key rotation.
- Linux: `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus --
  /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q
  tests/test_runtime_handoff_epochs.py tests/test_hitl.py --tb=short --maxfail=3`:
  **25 PASS in 17.79s**.
- Ruff: PASS. One existing Starlette/httpx deprecation warning. Native provider
  execution: NOT_RUN. No new migration in this unit.

Next dependencies remain managed claim/grant/dispatch and restricted runtime
bootstrap, then native approvals, P10-P12. This unit closes impersonation; it
does not claim that a scoped runtime credential or managed work dispatch exists.
