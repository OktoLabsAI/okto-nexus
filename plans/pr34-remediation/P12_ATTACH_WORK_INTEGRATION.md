# P12 external attach work integration

T-WORK-12: scoped PASS. Final release gate remains unpassed. Parent49ebd0e plus exact source/test/migration hashes per generation are recorded in evidence/p12-attach-work-integration-index.json. This unit follows the configuration groundwork in P12_ATTACH_WORK_CHANNEL.md; that document's historical RED is now superseded by the integrated gate below.

## Implemented path and authority

RuntimeWorkService.authorize/enqueue/revalidate reuses the existing authenticated agent key, canonical session secret, endpoint configuration revision, execute_work grant and handoff claim_epoch. ExternalWorkChannel enforces strict session possession even in trust_mode=open. The actor must be the represented agent: this external route requires self-claim; the full-duplex connectors retain their existing explicit delegation support. A configured reference by itself is never authority. structured_result_v1 is refused for external attach.

Migration064 adds external_session_id (FK RESTRICT), a SHA256 fingerprint of the existing high-entropy session credential, external_acked_at and external_completion_action to runtime_handoff_bindings, plus external_completed_at to the existing delivery_outbox. It does not create another work queue, agent identity, credential issuer, native result or journal terminal. The raw secret remains only in the existing canonical session store/client context. The next migration number was064 after inspecting063; this unreleased migration evolved only against disposable fixture stores during this unit.

The actual serve dispatcher revalidates the persisted proof and current canonical work policy before calling the connector outside the writer UoW. A trusted HarnessCommand.external_work_channel flag selects the verified conversation transport for attach; it is never decoded from native text or a public payload. Native effective managed_work/events stay false. The four existing adapter implementations and control capabilities remain intact. The authenticated external Nexus client is configured separately; no Nexus key or session secret is placed in the native envelope or child environment.

InboxService.ack now passes existing session proof into the same application work service, which verifies actor, key binding, approved session, credential fingerprint, grant/revision, current claim and creation/work policies. SqliteMessageDeliveryRepo.mark_external_work_ack atomically consumes the original push reservation. Canonical read events and sender receipts include ack_source=authenticated_nexus_call, ack_level=AGENT_ACK and human_read=false. Repeated authorized ACK produces no extra receipt, including after external completion. This does not invent native acceptance or polling.

The existing handoff_complete/reject façades pass their already-present proof parameters into HandoffService. The canonical transition requires the current external binding and explicit prior ACK. Receipt, outcome facts and canonical transition share the original UoW; verifier/claimant separation stays in the existing core. An internal HandoffService without an authenticated context/runtime work service cannot bypass the external completion check. Conversation output or a native turn ending does not complete this work.

An authenticated return does not require a live native connection. A narrow private access option bypasses native quarantine availability only for an already-bound external response, never new dispatch; key/session/grant/policy/enable/revision/claim checks remain required. The detach/quarantine test exercises real detach plus simulated persisted owner-loss health. It is not evidence of a new full operating-system owner-kill campaign. Older owner/recovery campaigns remain separately scoped in their own evidence.

External completion releases transport capacity/lane blocking through external_completed_at. Native terminal_event_id stays null. The existing outbox owner-recovery and native-close projection do not turn an already externally completed operation back into unknown native work. No ambiguous operation is replayed automatically. A fresh authorized canonical message can use the released lane.

## Older-writer defect and additive fence

The first working integration exposed an upgrade boundary defect: an already-open connection advertising only nexus_runtime_writer_v1 could execute the old claimant/epoch-fenced handoff transition and bypass the new proof contract. The clean RED test changed real SQLite state and failed because the expected incompatibility error was absent; it did not fail on an import or assumed mock behavior.

ConnectionFactory now registers nexus_runtime_external_work_v1. Migration064 adds narrow triggers for external-bound CLAIMED -> COMPLETED/VERIFYING/REJECTED transitions and external delivery consumption by writers lacking that capability. pragma_function_list avoids invoking an unknown function. Existing v1/unbound work and the global writer fence are preserved. The marker identifies compatible application code; it is not user authentication and cannot be supplied through MCP/REST payloads. Restart old writers with the updated binary; do not add SQL markers manually to bypass this boundary.

The final three legacy-writer cases prove all completion destinations and ACK are refused, followed by successful authenticated completion using the real current composition. A raw database administrator remains outside the remote caller threat model, as with the existing writer contract.

## Public contract and operation

Surface58, identity25, schema064. No new public tool or generic task orchestrator was added. Session parameter descriptions explicitly require proof for managed external attach, while retaining optional legacy open-mode sessions. Their descriptions are shorter; no artificial growth-budget exemption was added.

harness_get(operation_id) exposes external_work separately from native result_durable/result. The public handoff operation binding includes external ACK/completion facts. Discovery exposes only configured/authentication-required/native_ack=false for the external channel, without its session ID or secret. This projection is configuration, not evidence that an external client is currently alive.

Operational sequence:

1. Enable integration and attach explicitly on a supported platform. Use an operator-approved external target and existing canonical agent/workspace.
2. The agent opens its own authenticated Nexus session and keeps its returned secret private in its client context.
3. The operator pins nexus_work_session_id on that attach endpoint. Configuration edits revoke old grants; issue the new execute_work grant after the edit.
4. That same authenticated agent claims the canonical handoff with endpoint/grant/idempotency key and approved session proof.
5. After receiving the envelope, the separately configured Nexus client calls inbox_ack for its message_id, then handoff_complete or handoff_reject with the exact claim_epoch and the same proof. Required evidence and verification remain canonical.
6. Distinguish socket write (SENT_UNCONFIRMED/TRANSPORT_WRITE), authenticated Nexus receipt (AGENT_ACK), external work completion and native result capture. The last is absent for attach.

Closing the separate Nexus session, rotating its secret/key, revoking a grant, changing policy/configuration or changing the claim can block later work transitions. Preserve history and use the existing explicit reconciliation/recovery procedure; never fix an unknown send by replaying it. Detaching does not terminate the external process. Disabling/removing a closed configuration reference remains possible as qualified in the prior unit.

## Evidence and limits

All exact commands/argv, environment overrides, generation hashes, per-node results and suite times are in the integration index and referenced sanitized manifests. Raw XML/logs stay under .git/pr34-evidence because failure output can contain fixture secrets.

- Preparation history retained: initial positive admission1 PASS; an incorrect claim_epoch test-response path1 FAIL then corrected1 PASS; expanded16 PASS; socket generation Windows16 PASS1 POSIX SKIP/Linux17 PASS; initial regression104 PASS Windows.
- The first authority run failed on actual C drive exhaustion (free=0). An independent SQLite WAL health probe also failed. Tests were redirected to newly allocated D directories through TEMP/TMP/TMPDIR and pytest basetemp; no personal files were deleted. Subsequent authority Windows22 PASS1 POSIX SKIP/Linux23 PASS.
- Final admission/return generation before the narrow writer fix: Windows30 PASS1 POSIX SKIP; broad Windows384 PASS207.96s. Combined Linux415 PASS358.44s includes31 attach cases plus those384 regression nodes. Those counts are not added together as independent tests. One existing Starlette deprecation warning was observed in each broad run.
- Legacy writer RED:1 FAIL4.48s, incorrect completion actually admitted by SQLite before the fix.
- Final writer/attach/migration gate: Windows59737 terminal0,47 PASS1 POSIX SKIP113.67s; Linux64199 terminal0,48 PASS147.40s. These carry the post-fix source hashes. T-WORK-12 maps specifically to31 attach cases (one POSIX-only) and three writer-fence cases; remaining nodes cover migrations/writer compatibility.
- Required real stdio MCP smoke after the writer-fence change: terminal0,LIVE E2E RESULT: PASS in a fresh D temporary store. Ruff on all changed Python files and git diff --check PASS. All handles are terminal.

The POSIX case uses the real ClaudeCodeAttachConnector and real Unix socket against an owned disposable protocol peer, plus authenticated production HTTP/MCP. It is not a session of the installed Claude application and does not qualify a native provider/version. Installed native Codex/Claude campaigns remain historical at their recorded SHA; no provider was invoked in this unit. Native Pi and dedicated native attach stay NOT_RUN under the user's stated scope. Final immutable-source full suites, finding/release audit and build/reinstall0.2.0 remain required.

## Retention and reopened-offer recovery — final integrated generation

Two additional development-generation defects were reproduced before publication. Retention attempted to delete a closed canonical session referenced by external work and failed with a real foreign-key violation (retention-red:1 FAIL). Both count_closed_before and prune_closed_before now exclude sessions referenced by runtime_handoff_bindings.external_session_id. The audit identity remains durable while unrelated expired sessions are still deleted; a closed session cannot authorize a return. Retention regression:36 PASS on each platform.

After explicit operator recovery, the old external binding incorrectly blocked the recipient from rejecting a reopened OPEN offer (recovery-red:1 FAIL, actual PERMISSION_DENIED). HandoffService._authorize_external_work_return now applies the external proof guard only to the current CLAIMED handoff. Canonical rejection of a reopened direct offer works without reusing the old session; the old operation is not replayed or completed. These are defects in the unpublished integration generation, not retroactive findings against parent49ebd0e.

Final operational selection: Windows81 PASS1 POSIX SKIP175.379s; Linux82 PASS205.295s. Completed JUnit files were recovered at resume; tool handles62939/68018 were no longer available, so no independently recovered process exit code is asserted. The manifests carry final source hashes and exact per-node results. T-WORK-12 now joins31 attach plus5 writer/retention/recovery cases. Earlier selected results remain generation-specific.

Required isolated real stdio MCP smoke was repeated after these final production changes: exit0, LIVE E2E RESULT: PASS. Ruff executable on all changed Python files and git diff --check passed. An attempted python -m ruff invocation could not run because Ruff is installed as a separate executable, not in the project venv; the executable check then passed. No installed provider was invoked. No tests remain running at this milestone.
