# PR-02 — explicit recovery before detached bootstrap

Windows 11 `10.0.26300`, Python 3.13.1. Candidate versions remain Nexus `0.3.3`,
Connector `0.0.12`, Core `0.0.14`. Connector commit `496c7e5` is pushed.

Both hosts now expose `recover-start --expected-revision REVIEWED_REVISION`:
Nexus under `service`, Connector under `daemon` with the existing global state
selection. Status supplies the pending launch receipt revision. Recovery verifies
the selected instance and whole receipt while holding launch and lifetime locks
(home plus database for Nexus), then records `aborted_before_bootstrap`.

A delayed child rechecks that same receipt under the launch guard and exits
before application bootstrap. Recovery never starts a replacement, signals a PID,
adopts a process, changes a native task or clears runtime state. The next start is
explicit. A live/unknown owner, installed supervisor, different revision or launch
already past bootstrap is refused and retained. Concurrent lock/revision changes
produce uncertainty instead of repeating a stale stopped observation.

Lost persistence responses are confirmed by repeating the same expected revision.
The full original receipt is reconstructed for that confirmation; an externally
edited recovered receipt cannot be silently accepted. Repeated recovery does not
rewrite the receipt. Missing selected state remains absent. Nexus status/recovery
can still select the retained launch when its saved interpreter is unavailable;
the saved context is preserved, not upgraded implicitly.

## Evidence

- **68 Nexus tests and 81 Connector tests passed** in the initial source campaign,
  covering lifecycle controls, recovery and actual detached processes.
- After final diagnostic refinements, **41 Nexus tests and 11 Connector recovery
  tests passed**. Ruff and whitespace checks pass for all changed Python files.
- **124 tests passed on the final wheels in a fresh venv outside the checkout**.
  Imports of all three distributions were asserted under its site-packages.
  Tests cover revision conflicts, owner/launcher locks, unrelated live PID
  metadata, installed-supervisor refusal, response loss, repeated recovery,
  missing interpreter and actual CLI/late-child processes.
- Both actual lifecycle campaigns begin with an interrupted pending selection,
  recover it, then run three concurrent starters. They confirm one owner,
  reject an old delayed child after the new generation is ready, reuse, restart
  and finish with canonical `DRAINED`. No identities/providers are configured.
- All **412 Nexus and 111 Connector Python payloads** match their final wheel
  bytes without missing/extra files. Core remains the same coordinated artifact.
  Nexus CI Connector wheel and manifest are updated.

The fresh installed environment is
`C:\Users\jpamb\AppData\Local\Temp\r3-recovery-7y1xk4l3\venv`.
It contains both final wheels, Core and Nexus `serve-lite` dependencies. Tests
were copied outside the repositories and run with `python -I -m pytest tests -q
--tb=short`, with asyncio mode auto and no source checkout on the import path.

Nexus copied files: `test_service_launch_recovery.py`, `test_service_start.py`,
`test_service_process.py`, `test_user_service_installation.py`. Connector copied
files: `test_launch_recovery.py`, `test_service_readiness.py`,
`test_user_service_lifecycle.py`, `test_detached_service_lifecycle.py`.

JUnit: `pr02-launch-recovery-nexus.xml`, `pr02-launch-recovery-connector.xml`,
`pr02-launch-recovery-nexus-final.xml`, `pr02-launch-recovery-connector-final.xml`,
`pr02-launch-recovery-installed.xml`. Artifact hashes and comparison counts:
`pr02-launch-recovery-wheels.json`.

## Scope still open

This completes the explicit pending detached-launch recovery subset. It does not
prove productive crash reconciliation, grant/claim recovery, external shutdown,
native login supervision, upgrade or M1. SVC-02/03/08/10/11, PR-01/02 and the full
R3 plan remain IN_PROGRESS. No lifecycle schema, data migration or Core runtime
authority changed. Existing runtime reconciliation remains mandatory after a
launch that already entered bootstrap.

The native temporary-task campaign is still awaiting the requested authorization.
Its original reviewed snapshot and installed candidates remain unchanged. No task
was registered or mutated in this milestone. POSIX and real provider campaigns
remain NOT_RUN. Controlled upgrade and general native-definition reconciliation
are the next lifecycle implementation gaps.

Rollback must preserve the recovered receipt until the operator explicitly
starts again. Deleting receipts or restoring a pending token can re-enable a late
launch and is not a supported rollback operation. No binary/database downgrade
is implied by this recovery command.
