# PR-02 — reviewed environment upgrades

Windows 11 `10.0.26300`, Python 3.13.1. Candidate versions remain Nexus
`0.3.3`, Connector `0.0.12`, Core `0.0.14`. Core commit `57fa815`
and Connector commit `d82d941` are pushed. The full R3 plan and PR-02 remain in progress.

Both hosts provide `service upgrade-plan --python TARGET --output NEW_FILE`
and `service upgrade-apply --plan-file FILE --expected-revision SHA256`.
The plan retains old/new contexts, installed package and Core fingerprints,
interpreter identity, source generation, installation receipts and native export.
It changes no runtime state. The target must be an installed wheel environment
with the component's exact Core pin; stable releases are ordered and binary
downgrade is refused.

Apply requires the reviewed generation's canonical DRAINED report, its latest
successful run marker when available, free lifetime ownership and launch
exclusion. Nexus holds both home and database exclusions. A changed environment,
context, native definition, receipt, pending launch or newer/unconfirmed run is
preserved and refused. Foreground exceptions after a DRAINED report leave the
latest run unconfirmed. Legacy sources without a run marker require preparation
while running and subsequent canonical stop with their matching CLI.

The context becomes the first atomic retained intent and startup fence. No
multi-file intent gap precedes it. Native action replacement preserves principal,
triggers, enablement and unrelated settings. It uses UPDATE only, preserves the
principal ACL and suppresses registration triggers. These flag semantics follow
[Microsoft TASK_CREATION](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/ne-taskschd-task_creation)
and [TaskFolder.RegisterTask](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskfolder-registertask).
The registration description stays historical; the confirmed receipt records the
new logical definition and complete observed native export.

Every persistence boundary and native response-loss scenario is exercised with
injected effects. Repeat accepts only the retained plan and exact action result;
an external edit made during interruption remains a conflict. The task token,
Server database claim and control latch are published behind the fence. Context
activation occurs last. Old queued launches cannot reuse their token. A completed
repeat verifies the result without another native update.

The upgrade does not start, migrate, stop or signal a process. The completed
journal states `migration_state: not_run_by_upgrade`. Explicit start invokes
canonical bootstrap/reconciliation in the selected target; it checks installed
payload identity before bootstrap. Source references remain available for
reviewed recovery, without claiming that binary rollback is safe after migration.

## Validation

- Core: **17 passed**, including native XML validation without registration.
- Initial focused source campaigns: **125 Nexus and 94 Connector passed**.
- Final focused source campaigns: **51 Nexus and 42 Connector passed**.
- Final installed campaign: **200 passed, zero skips/failures/errors**, including both actual environment replacements.
- Ruff and whitespace checks pass for the changed files.
- JUnit: `pr02-upgrade-core.xml`, `pr02-upgrade-nexus.xml`, `pr02-upgrade-connector.xml`, `pr02-upgrade-nexus-final.xml`, `pr02-upgrade-connector-final.xml`, `pr02-upgrade-installed.xml`.

The clean validation and target environments are:
`C:\Users\jpamb\AppData\Local\Temp\r3-upgrade-q21vxv1g\validation` and
`C:\Users\jpamb\AppData\Local\Temp\r3-upgrade-q21vxv1g\candidate`.
All package origins were asserted below the validation environment's
site-packages. Tests were copied outside the checkouts and invoked with
`python -I -m pytest tests -q --tb=short`.
`R3_UPGRADE_TARGET_PYTHON` selects the separate installed candidate.

The two real upgrade campaigns start a disposable instance, prepare/save the
plan while it runs, refuse application while owned, drain, apply, repeat,
explicitly start from the second environment and drain again. Server database
and Connector ownership-ledger bytes do not change during apply. Configuration
remains unchanged; the new generation uses the retained target context.
Both additional detached lifecycle campaigns exercise concurrent starters,
late-child rejection, reuse, restart and matching drained run markers.

The initial Nexus installed campaign found that a cold package fingerprint took
about 20 seconds and exceeded the original 20-second subprocess timeout. The
bounded limit is now 60 seconds, timeout has a stable actionable diagnostic, and
apply performs one target inspection under exclusion. Final installed results
below supersede that failed initial run.

The installed suite includes the two upgrade tests, both detached process tests,
host installation/recovery/start tests and the focused upgrade suites from both
repositories. `pr02-upgrade-wheels.json` records hashes and exact source payload
comparison: 415 Nexus, 114 Connector and 130 Core Python files, no missing/extra
Python payloads. Coordinated Core wheels are identical in both consumers; Nexus
also vendors the tested Connector wheel with its updated manifest.

## Remaining acceptance

SVC-09 and SVC-T25/26 remain IN_PROGRESS. This evidence does not qualify actual
Task Scheduler update/restart, login/logout/reboot, historical mixed-version
migration failures, productive runtime work or POSIX. Task update effects are
injected; native Core XML checks are validate-only. Task Scheduler cannot provide
an atomic fingerprint-conditional update against an independent external editor;
strict pre/post comparisons preserve uncertainty instead of adopting a mismatch.
Old independently invoked foreground binaries that ignore these guards remain
outside this cooperative upgrade protocol.

The original temporary native-task campaign is still awaiting its previously
requested authorization, with its original plan and environment unchanged.
No personal service or real registered task was created/updated here. General
definition reconciliation, Server doctor and productive/native lifecycle campaigns
remain open. R3 M1 and all downstream DX/ATN/OBS acceptance remain open.
