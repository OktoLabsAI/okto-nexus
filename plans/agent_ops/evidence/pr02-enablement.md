# PR-02 — selected Windows task enablement

Windows 11 `10.0.26300`, Python 3.13.1. Candidate versions remain Nexus `0.3.3`,
Connector `0.0.12` and Core `0.0.14` on their existing feature branches.

Both hosts expose enable/disable for the owned selected task. Nexus uses
`service enable|disable --user`; Connector uses `service enable|disable` with
its global state-directory selection. These operations neither start nor drain
an active generation. The queued scheduled entry checks disabled state before
bootstrap. Start refuses a disabled stopped task without detached fallback.
Status separates enabled login policy from process availability. Disabling
remains available with an unavailable saved interpreter; enabling validates it.

Hosts persist intent before the native mutation. Repeating the same operation
can confirm its observed result without repeating the effect. The opposite
transition remains refused while an intent is pending. Core's pure comparison
accepts only the intended Settings/Enabled difference; command, privilege,
principal, trigger and unknown-setting edits remain conflicts. No foreign task
or external enabled edit without our matching intent is adopted. Lost native
responses and a changed definition retain explicit uncertainty.

The native adapter uses
[RegisteredTask.Enabled](https://learn.microsoft.com/en-us/windows/win32/taskschd/registeredtask-enabled).
Fingerprint checks are immediate preflights, not atomic OS CAS against another
editor. Nexus now also uses thread-scoped COM initialization/cleanup, with only
plain observations crossing that boundary, matching the Connector host design.

## Validation

- **12 Core definition tests passed**, including native TASK_VALIDATE_ONLY for
  a disabled proposal and absence before/after. A first invocation selected the
  previously installed Core; rerunning with `-o pythonpath=src` exercised the new
  source. No product test failure was hidden by that import correction.
- **67 Nexus tests passed**: user-service installation/controls, lifecycle and
  passive logs. Includes native validate-only preflight from a worker thread.
- **62 Connector tests passed**: selected service controls, readiness,
  installation and architecture boundaries.
- **90 coordinated tests passed from a fresh venv outside the checkout**, with
  all three final wheels installed. The copied test set includes both hosts'
  real concurrent detached launch, reuse, restart and drain, plus the new
  enablement contracts using fake native mutations. Imports of all three
  distributions were asserted under this venv's site-packages.
- Wheel comparison found **412 Nexus, 109 Connector and 130 Core Python files**
  identical to source, without missing/extra payloads. All 130 Core Python files
  pass the existing import-boundary audit. Both consumers contain the identical
  Core wheel. `uv.lock` retains the same local wheel path and version; it has no
  per-file hash for this source. Nexus CI manifest is updated.
- Ruff passes on every changed Python file. Scope and whitespace checks run
  before commit.

Artifacts: `pr02-enablement-core.xml`, `pr02-enablement-nexus.xml`,
`pr02-enablement-connector.xml`, `pr02-enablement-installed.xml` and
`pr02-enablement-wheels.json`.

The source commands were:

```text
Core: python -m pytest -o pythonpath=src tests/test_user_service_definition.py -q --tb=short
Nexus: python -m pytest tests/test_user_service_installation.py tests/test_service_logs.py tests/test_service_start.py -q --tb=short
Connector: python -m pytest tests/unit/test_user_service_lifecycle.py tests/unit/test_service_install.py tests/unit/test_service_readiness.py tests/unit/test_boundaries.py -q --tb=short
```

The fresh venv installed the Nexus wheel with `serve-lite`, the Connector/Core
wheels and pytest. `python -I -m pytest` ran only copied tests in a disposable
directory: Nexus `test_service_start.py`, `test_user_service_installation.py`,
`test_service_process.py`; Connector `test_user_service_lifecycle.py` and
`test_detached_service_lifecycle.py`.

## Remaining acceptance and rollback

SVC-05/08/10/11/12 and PR-02 remain open. Actual registration, enabled-property
mutation, login/logout/crash and credential/provider campaigns are NOT_RUN.
The tests above do not claim those OS effects: every mutation uses a fake task
backend, while native tests only read/validate. General definition/context
reconciliation, upgrade, interrupted pre-spawn recovery, remaining passive
diagnostics and productive M1 use still require implementation/qualification.

No schema or NXL revision changed; no task or package was published/installed
personally. A pending enablement intent must be confirmed by the matching
version before discarding receipts or rolling the integration back. Existing
canonical drain and ownership rules remain mandatory when changing supervisor.
