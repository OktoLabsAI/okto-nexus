# PR-10 — reconciliation of retained DX-07 and SVC-12 evidence

Date: 2026-11-07. This is a documentary reconciliation of two stale ledger
statements, not a new implementation or qualification campaign. The task-level
status of both DX-07 and SVC-12 remains `IN_PROGRESS`. The fixed plan, milestones,
M1/M2 gates, campaign authorization and all inventories remain unchanged.

## DX-07: participant validation is implemented

The `participant_client_validation=NOT_STARTED` subfield conflicted with the
same task's later participant doctor evidence. It is now `IMPLEMENTED`, scoped
to the existing validation path; this is not a claim that every external client
or productive workflow has been qualified.

The [participant doctor report](pr04-participant-doctor.md) documents passive
profile/client-file inspection, separate authentication and environment checks,
and explicitly requested bounded MCP negotiation. Default diagnosis does not
read a credential, send HTTP, launch a process, repair configuration or advance
a checkpoint. An environment check proves only `doctor_process`; successful MCP
negotiation does not prove client reload, participation, handoff or model work.

The retained [installed JUnit report](pr04-participant-doctor-installed.xml)
contains **55 passed, zero failures/errors/skips**: 19 participant doctor cases,
21 participant init cases, 13 managed doctor CLI cases and two HTTP-only CLI
regressions. The reconciliation parsed the XML and checked these named cases:

- `test_passive_doctor_preserves_files_without_vault_http_process_or_recovery`
- `test_file_drift_does_not_hide_independent_authentication`
- `test_revoked_credential_is_not_repaired_or_used_for_mcp`
- `test_actual_tcp_mcp_is_not_agent_participation_or_model_work`

The report's SHA-256 is
`06ee1f7a0efaac8af8b4dd9075f255c5d8399d9ada41fde31b4341580f72c920`.
The original campaign used an installed Windows package, real TCP
FastAPI/auth/SQLite/MCP composition and fixture credentials; its vault was
synthetic. Existing later client-launch/removal evidence and its narrower
verified subscopes are preserved, without reopening or enlarging their claims.
Interactive TUI/GUI, OS-vault/client end-to-end qualification, real cooperating
clients/providers and the cross-host diagnostic contract retain their recorded
open gates.

## SVC-12: upgrades and diagnostics are not unstarted implementation

The stale limitation that controlled upgrades and passive diagnostics beyond
service logs remained unimplemented is replaced with the scope already
demonstrated by [reviewed environment upgrades](pr02-upgrade.md) and
[project doctor](pr03-project-doctor.md). The current task already records the
project doctor's installed subcontracts; they are not reclassified here.

Both hosts provide reviewed `service upgrade-plan` and `service upgrade-apply`
with canonical drain, generation/context checks, retained intent, interrupted
recovery and refusal of binary downgrade. The retained
[installed JUnit report](pr02-upgrade-installed.xml) contains **200 passed, zero
failures/errors/skips**. Named cases checked in that XML include:

- `tests.test_service_upgrade_process::test_reviewed_upgrade_between_installed_environments_preserves_database`
- `tests.test_connector_service_upgrade_process::test_reviewed_upgrade_between_installed_environments_preserves_journal`
- `tests.test_service_upgrade::test_lost_native_response_keeps_fence_and_recognizes_only_exact_effect`
- `tests.test_connector_service_upgrade::test_downgrade_and_unconfirmed_existing_runtime_are_refused`

The report's SHA-256 is
`d1f09ad1e7335a762f801c5daa3a95f01697ebce3c8c24f1a556c693f253ac16`.
The campaign includes actual replacements between disposable installed
environments, preserving the Server database and Connector ownership ledger.
Task Scheduler mutation effects were injected; native Core XML checks were
validate-only. This is not evidence of actual registered-task upgrade/restart,
login/logout/reboot, historical mixed-version migration failure recovery,
productive runtime work or POSIX qualification. Passive project diagnosis and
explicit bounded metadata checks also do not prove those service campaigns.

## Preserved boundaries

The two report counts describe their original suites and are not summed into a
new unique-case total. No historical XML was modified or rerun, and these
reports do not certify the current PR-10 wheel. The existing
[temporary Windows user-service campaign](../campaigns/windows-user-service.md)
and its authorization state are unchanged; its limited two-task scope would
not by itself complete SVC-12 or productive M1/M2.

Only the DX-07 subfield and explanatory evidence, the SVC-12 upgrade/diagnostic
limitation and explanatory evidence, and one history entry are reconciled in
the JSON. Other task statuses, DX-13's prior reconciliation, latest OBS-11/12
progress, milestones, scenarios, invariants, completion criteria, repositories,
campaigns, plan hash and global metadata are preserved. JSON comparison and the
scope checker verify that boundary; neither is product acceptance. No test
suite, provider or user service was executed, and no personal credential was
accessed in this review.
