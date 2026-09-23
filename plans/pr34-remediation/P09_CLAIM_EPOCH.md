# Canonical claim generation fence

Parent `08b5fb1`, branch `feature/v0.2.0`, 2026-09-23. P09 IN_PROGRESS;
this is the claim-fencing foundation, not completed managed dispatch/bootstrap.

Confirmed behavioral defect: after lease expiry and reclaim by the SAME agent,
the old unfenced complete/reject call changed the new work's state. Before
implementation, `rtk proxy .venv/Scripts/python.exe -m pytest -q
tests/test_runtime_handoff_epochs.py --tb=short` produced **2 FAIL in 0.55s**
(`DID NOT RAISE`), using only the pre-existing public service calls.

Migration 044 adds `handoffs.claim_epoch` without rewriting previous migrations
or historical payloads. Existing rows with a claimant start at 1, unclaimed
rows at 0; pre-migration execution generations cannot be reconstructed.
Atomic claim increments the generation. Verification failure also increments
it for rework. Claim/get/verify responses expose it. Complete/reject and verify
CAS predicates include it, with strict positive integer validation in the
canonical service. Omission remains compatible only with generation 1.

Surface revision 36 adds optional `claim_epoch` to the existing MCP verbs and
REST verification body. After reclaim/rework callers must send the generation
of their actual work/delivery. They must not copy the latest generation onto
an old result. The dashboard list and verifier submission carry the observed
generation. No tool alias or task orchestrator was introduced. Permissions,
eligibility, dependency checks, evidence/verification routing and the ban on
self-verification still run in the existing service. Rework notifications
contain the new generation. No native terminal completes a handoff.

Tests:

- Initial canonical selection after implementation: **71 PASS in 7.99s**.
- Verification/dependency selection initially had **4 FAIL / 114 PASS**:
  rework callers needed their returned generation; two snapshots still
  expected surface 35. Callers/snapshots updated for the versioned contract.
- Integrated gate command and output: `evidence/p09-claim-epoch-gate.log`,
  **329 PASS in 38.53s**. Includes handoff, verification, dependencies, auth
  surfaces, metadata revision, feature flags, memory/health and import rules.
- New tests include authenticated HTTP MCP claim/complete, REST and MCP stale
  verification rejection, valid rework completion and forbidden self-verify.
  Initial transport fixture mistakes (host allowlist, missing required
  visibility) were corrected; final focused **3 PASS in 1.92s**.
- `rtk proxy npx tsc -b --pretty false` in `frontend`: PASS. This type check
  does not rebuild/overwrite the user's generated static files.
- Ruff changed Python modules: PASS. Native models: NOT_RUN for this unit.
- Linux: `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus --
  /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q
  tests/test_runtime_handoff_epochs.py tests/test_verification.py
  tests/test_handoff.py --tb=short --maxfail=3`: **130 PASS in 34.75s**.

Next: bind canonical claims to scoped grants and one dispatch; prevent lease
expiry from reassigning uncertain managed execution; bootstrap restricted
runtime identity and preserve late native evidence; native HITL. P10-P12 and
final qualification remain outstanding. Claim generation is a fence, not an
authentication credential or evidence of native cancellation.
