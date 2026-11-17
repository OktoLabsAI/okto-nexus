# Conservative CLI / Connector / service / rollback traceability

PASS below is always limited to the stated boundary. SUBSET means useful
executed assertions leave part of the literal given/when/expected unproved.
NOT_RUN means no complete matching case was found; existing unexecuted source
tests are not counted as evidence.

The inspected antecedents are `pr02-local-connection-qualification.json`,
`pr02-session-intent-qualification.json`, `pr05-panel-onboarding-source-qualification.json`,
`pr06-catalog-convergence-qualification.json`, `pr06-connector-qualification.json`,
`pr08-installed-python-qualification.json` and its Nexus/Connector XML reports.
The Nexus installed run remains 187 PASS + 2 FAIL, with a separate corrected
2-case focal; it is not retrospectively 189/189. Connector's installed 52-case
run is PASS. The two Nexus failures concern related-page cursor test oracles,
not any scenario below. Later root-owned
`pr02-final-contract-focals.json` records 3 PASS / 11.36 s (`e3afe1`, commit
`06097a29`) covering CLI-01/05/07/15. The four new `pr07-service` invocations are
reported separately as 13 PASS / 3 fixture FAIL.

Paths beginning `test_` in the CLI rows below are under `tests/execution_r4/`.
Connector paths are relative to sibling `okto-nexus-connector/`.

| ID | Defensible outcome | Executed evidence and remaining acceptance |
|---|---|---|
| CLI-01 | PASS, synthetic integration | Root focal `test_terminal_multi_harness.py::test_single_observed_harness_needs_no_profile_and_existing_connection_offers_all_intents`: one observed inert Codex candidate, real parser/HTTP/SQLite Test/Finish, no --client/--profile and no profile prompt. Lifecycle/probe/provider peer remains fake. |
| CLI-02 | PASS, unit/store | `test_connection_choices.py::test_legacy_and_multiple_connections_preserved_without_rewrite`: project-hash and new profile both found; full store snapshot unchanged. |
| CLI-03 | PASS, unit/catalog | `test_destinations_homes_projects_and_operator_topologies_do_not_mix` and `test_canonical_connection_choices.py::test_local_shortcut_full_tuple_drift_is_not_merged_by_agent_or_binding_name`: same paths/names do not merge different destinations, homes or tuples. |
| CLI-04 | PASS, synthetic integration | `test_terminal_multi_harness.py::test_two_distinct_harnesses_share_project_keep_custom_a_and_recover_b_finish`: actual picker/parser/HTTP/SQLite adds Claude to Codex, distinct identity/profile, A bytes/role/permissions/custom model/binding/grants retained. No real provider. |
| CLI-05 | PASS, synthetic integration | Root CLI-01 focal now explicitly asserts Resume/Add/Cancel text for the same sole connection; Cancel leaves canonical snapshot/profile bytes/test count unchanged. |
| CLI-06 | PASS, CLI boundary | `test_connection_picker.py::test_resume_exact_connection_no_defaults_or_grants`: a/z are both Codex, answer 2 selects agent-z and preserves both profiles. HTTP/setup Flow is fake. |
| CLI-07 | PASS, CLI guard boundary | Root-strengthened `test_explicit_client_conflict_and_legacy_new_flag_do_not_overwrite`: PROFILE_CONFLICT plus actionable message, no overwrite or reservation. |
| CLI-08 | PASS, synthetic CLI/HTTP integration | Multi-harness Finish-loss case preserves same intent/agent and complete post-Finish snapshot, without additional Test; `test_connection_setup_recovery.py::test_recovery_matches_durable_receipt_without_reapplying` checks the actual receipt/result equality. |
| CLI-09 | SUBSET | `test_concurrent_additions_same_profile_cannot_overwrite` uses real lock, two threads and barrier with one winner. No two-terminal/process setup-commit race or bound on lock duration was executed. |
| CLI-10 | PASS for lost Finish; SUBSET for other unknown slots | Multi-harness case resumes an actual CLI Finish checkpoint without new intent. Generic picker unknown tests use fake Flow; real lost-cache refusal calls TerminalConnection rather than that same picker path. Do not generalize one Finish case to every unknown effect. |
| CLI-11 | PASS, CLI/parser boundary | `test_json_ambiguous_returns_selection_without_setup` checks structured selection_required with two choices, no review/apply, and no interactive input. |
| CLI-12 | SUBSET | Stable explicit --new-connection/--profile retry and changed-content conflict pass in `test_new_intent_retry_before_review_retains_agent_and_setup_id`, `test_after_review_response_loss_keeps_checkpoint_and_explicit_profile_compatibility`, and reservation tests. Their scripted HTTP/setup Flow is fake; the real Finish-loss integration is interactive, a different given/when. |
| CLI-13 | PASS for plan/status; unexecuted doctor branch | New installed `tests/test_terminal_connect_process.py` checks real absent-home connect --plan/work status with no home created; `nexus-passive` checks canonical service status without Popen. Nexus doctor with absent Server was not executed. Do not claim all command variants. |
| CLI-14 | SUBSET | `test_remote_human_metadata_exact_without_vault_or_client` isolates human/other operator metadata in the same directory and refuses wrong username, without vault/client access. It does not canonically resume against two remote operator/Server contexts. |
| CLI-15 | PASS, actual lock boundary | Root-strengthened `test_changed_addition_choices_refused_and_profile_busy_preserves_intent` holds a real profile guard, asserts PROFILE_BUSY/refused and unchanged bytes. It does not represent two real terminal lifetimes. |
| CONN-03 | SUBSET | `tests/unit/test_connection_choices.py::test_add_uses_new_operator_bootstrap_and_keeps_previous_identity_and_binding` preserves A; current-state refusals reject revoked/disabled/stale/pending bindings. No same-agent request on a second machine exercising complete machine policy was executed. |
| CONN-04 | PASS, CLI/unit boundary | `test_wizard_json_contract_refused_before_catalog_or_credentials[flags0/1]` refuses with VALIDATION_ERROR and makes any StateStore access fail. No credential prompt or hidden wizard. |
| CONN-05 | SUBSET | Nexus `test_remote_setup_integration.py::test_operator_and_connector_cli_complete_same_root_once` uses real HTTP/WSS/registration/realization and separates host/operator credentials. manager.start and IPC are injected; it does not close a CLI process and prove its daemon remains alive. |
| CONN-06 | SUBSET | `test_connection_catalog_remote.py::test_remote_canonical_alias_requires_workspace_and_preserves_remote_scope` preserves logical workspace, operator shortcut and absence of Server root; Connector folder-drift/physical-replacement cases refuse retargeting. No two real hosts with distinct folders were joined in one journey. |
| CONN-07 | PASS, synthetic integration | `test_remote_setup_integration.py::test_operator_and_connector_cli_complete_same_root_once[decision/apply/finish-race/...]` recovers same root/child IDs/receipt, imports identity once, asserts exact binding/grant/proposal/setup-commit counts and GET-only later observation. Native/host effects are not real. |
| SVC-01 | SUBSET | New actual process connect/reuse test preserves PID/generation after launcher exit, but its selected agent is missing. Multi-harness addition proves same-instance calls only through a fake ensure_running service. No joined additional-connection + real-supervisor case. |
| SVC-02 | SUBSET; complete process/UI case NOT_RUN | Qualified `test_terminal_work.py::test_leaving_interactive_cli_does_not_interrupt_or_close_service_owned_work[EOFError/KeyboardInterrupt]` preserves inert native work/control; lifecycle inspector is fake. New real process test has no admitted work. No real browser/CLI observer exit during admitted live work was executed. |
| SVC-03 | SUBSET; unavailable-remote case NOT_RUN | Early remote-new-flag refusal and new passive remote-target rejection show no local fallback for those invalid requests. Neither attempts a valid remote destination that is unavailable. |
| SVC-04 | PASS for inspected plan/status subset | New installed absent-home plan and canonical service status create no home/db/process. Connector's actual subprocess status/logs/doctor also leaves its absent allocation empty. Nexus doctor/checkpoint variants remain unexecuted; no broad all-command claim. |
| SVC-05 | Mocked contracts qualified separately; native lifecycle NOT_RUN | Four controls pass; three old login fixtures fail missing-parent proof and remain retained. Root subsequently corrected only the native-observation fixture boundary and added its absence negative: `login-fixture-qualification.json`, commit `4d51008`, 36 PASS / 1 oracle FAIL + corrected focal 1 PASS. This qualifies current injected-parent composition and preserves the real missing-proof refusal, not actual Windows task/login lifecycle. |
| SVC-06 | PASS for expired/revoked/valid grant + completed-history restart; unknown-active branch NOT_RUN | New actual Server replacement cases keep Connector task/identity/binding/profile/grant limits/old operations and receipts exact, refuse expired/revoked grants and run only explicit new work with the valid grant. Prior native work is already closed. No claim of active native session or OUTCOME_UNKNOWN work surviving. Old `connection_continuity[expired]` expires link tickets, not budget grants, and cannot substitute for this proof. |
| REL-04 | SUBSET; full upgrade/reopen NOT_RUN | Legacy profile reader is immutable and new process test accepts legacy service-context metadata while preserving settings through restart. Neither upgrades/reopens a prior browser plus profiles/checkpoints/setup IDs. Fresh wheel/Twine is not that scenario. |
| REL-05 | NOT_RUN | Presentation switches and read-only UI tests do not demonstrate rollback to classic presentation with admitted work and intact daemon/sessions/grants. |
| REL-06 | SUBSET; release rollback NOT_RUN | Generated shortcuts work via current explicit --profile/qualified picker fallback; profiles remain byte-identical. No previous-release executable was used to consume new shortcuts after actual rollback. |

The remaining complete lifecycle/remote/rollback journeys need additional
composed tests, not relabelling unit or package counts. Windows logout/reboot and
real provider campaigns were neither needed nor performed for this audit.
