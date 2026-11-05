# PR-03 — login startup in the local project review

Local connect can include user login startup in the same exact project review. The existing installer and lifecycle perform controlled drain, user-task registration or enablement, and supervised start only after canonical setup is committed. A separate durable host checkpoint recovers partial installation before ordinary startup, preserving the original setup ID, binding, grant and model-test result. Unapproved login choices can be declined; later disable/uninstall is not undone by reconnect. 8 focused source tests and 30 existing connection regressions passed. An initial installed run exposed a concurrent startup metadata wait gap; three focused source checks passed after correction. The final installed campaign passed 169 tests on the 431-file Nexus wheel, including both existing and newly created project identity startup reviews. Native registration/process effects in the new connection tests are injected. Actual login/logout/crash qualification, Connector initial-review integration and complete productive M1 remain open.

`connect --start-at-login` adds a concrete startup plan to the selection already
covered by the project review hash. It identifies the effective user, Server
instance/home/database, resolved interpreter/cwd and a digest of the retained
execution context. The human review describes the controlled stop and supervisor
transition. Environment values, task ownership tokens and provider secrets are
not copied into this plan. The existing native installer performs its read-only
preflight and refuses a changed or foreign definition.

Canonical Finish remains the authority for project identity, binding, policy and
grant. After that commit, `login_start_operation` records authorized intent before
any native effect. The existing ServiceLifecycle/ServerInstallation implement the
drain, install/enable and start. These effects are deliberately not represented as
one distributed transaction. An incomplete host transition reports
`login_start_pending` with `setup_state: configured`; an uncertain checkpoint write
reports a possible effect. Reopening the same profile recovers the host operation
before ordinary startup without repeating the model test, Finish or grant.

An already configured binding can review startup alone. `--no-start-at-login`
removes an unapproved initial or startup-only choice, while an approved/installed
integration requires its explicit service control command. Reconnect does not
reinstall or reenable a later disabled/removed task. Pending recovery rejects
conflicting explicit project choices before native effects. Remote operator
topology rejects this local startup option before attempting local lifecycle.

## Validation

- `pr03-login-start-existing.xml`: **30 passing** existing local-connect and remote
  operator regressions (123.96 seconds), before final display/decline refinements.
- `pr03-login-start-source.xml`: **8 passing** focused cases (47.48 seconds), before
  final startup-only cancellation and pending-conflict assertions.
- `pr03-login-start-installed.xml`: **169 passed**, no failures/errors/skips,
  using the final installed artifact and updated tests. Includes initial review,
  decline/on-demand, context drift, drain timeout, lost native checkpoint,
  startup-only review/cancellation, disabled-task enablement, later-disable
  preservation, remote topology refusal, setup/identity/policy/receipt regressions,
  service installation/readiness/inspection, detached process lifecycle and
  pending launch recovery.
- `pr03-login-start-identity.xml`: **2 passing** installed cases for the same
  startup review with an existing identity and with a newly created project
  identity, on the initial candidate before the metadata wait correction. Both
  are included in the final broad installed run. Reports overlap and are not
  summed as distinct coverage.
- `pr03-login-start-installed-initial.xml`: **150 passed, 1 failed**. The real
  concurrent-process campaign exposed immediate refusal on
  `INSTANCE_METADATA_UNAVAILABLE`. The lifecycle now only re-inspects within its
  existing deadline, without another start or any inference of process absence.
  Persistent unreadability remains unknown with an explicit timeout. Three
  focused source checks passed in `pr03-login-start-metadata.xml`; the final
  installed campaign reruns both deterministic checks and the real process case.
  The failed disposable instance was independently observed stopped after cleanup.
- Ruff E9/F passes all touched Python modules and the new tests. Installed console
  help includes both startup choices. Fixed R3 scope and whitespace are checked
  before commit.

Campaign: `C:\Users\jpamb\AppData\Local\Temp\r3-login-start-sfce5iuk`.
Imports are verified under `python -I` from a fresh environment, with tests and
fixtures copied outside checkout. All **431/114/130** Python payloads match source
bytes. Nexus SHA-256:
`2927d9aaecd263d5fd6a0843567ea723c649e0c1fc00161271de68cd51a50961`.
Hashes for all three packages are retained in `pr03-login-start-wheels.json`.
Connector `0.0.12` and Core `0.0.14` source and vendored pins are unchanged.

The new integration tests use real terminal/setup HTTP handlers and SQLite setup
receipts/grants, the real lifecycle orchestrator and installer receipt code, and
disposable fake Task Scheduler/process observations. They prove ordering and
recovery with one setup test/binding/grant/task, not actual native login behavior.
Existing installed tests additionally exercise real detached processes and native
TASK_VALIDATE_ONLY preflight. No Task Scheduler registration, personal service,
real provider credential, paid inference, package release or merge is performed.

## Remaining acceptance

The local review/checkpoint subscopes are verified. DX-T37 stays IN_PROGRESS until
the Connector's initial wizard offers the corresponding host-local choice.
Actual Windows login/logout/crash/credential qualification remains NOT_RUN under
the unchanged isolated campaign approval request. POSIX native integration remains
unqualified. New remote identity/setup, real productive local/remote M1, participant
initialization, preset evolution, dashboard introduction and later ATN/OBS fronts
remain open; none is replaced by this partial milestone.
