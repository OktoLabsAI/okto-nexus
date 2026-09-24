# P12 external attach work channel — implementation in progress

Parent: 48a8ea2124f0efc08b78a116891253fd0f011a79 on feature/v0.2.0. Configuration is implemented; T-WORK-12 is FAIL: the positive managed admission acceptance reproducer is now executed and fails. The positive claim/ACK/complete route is not yet implemented or qualified. Native attach remains NOT_RUN without a dedicated approved session.

## Contract and current code

EndpointService.validate_public_config accepts nexus_work_session_id only for attach. This public value is a reference, never a credential. EndpointService.validate_work_session_reference checks, inside the existing configuration writer transaction, an active canonical session of the endpoint agent and workspace, with a stored secret, no closed timestamp, and no harness-owned presence reference. Errors do not disclose the selected session. Create/update reuse this check across REST and MCP; operator authorization, revision CAS, audit and grant invalidation remain unchanged. No schema migration is needed for this reference in existing public_config.

Updating the reference or explicitly enabling an endpoint rechecks its session. Disabling an endpoint remains possible after that session closes; null removes the reference. No connector is constructed by configuration, no execution is enqueued, and native attach managed_work/events remain false. Configuring this reference alone does not enable managed work. Do not describe this preparatory milestone as a usable external work channel.

## Behavioral evidence

The initial acceptance reproducer on the parent reached actual authenticated REST and failed at endpoint PATCH with VALIDATION_ERROR (HTTP422): the new public reference was not supported. This is an unimplemented acceptance contract, not an existing security bypass.

Configuration tests run actual HTTP/MCP composition with fixture peers only: four positive create/update/surface cases; 24 opaque, atomic invalid-reference cases (unknown, foreign agent, foreign workspace, closed, absent secret, harness-owned presence); two recovery/authorization cases. The first two test preparations failed on a nonexistent outbox intent column and the optional error.details key; these are test preparation failures, not product defects. Their manifests and exact generation hashes are retained.

An intermediate end-to-end retry after configuration still used the old grant. Existing EndpointRepo.invalidate_configuration correctly revoked that grant; this intermediate PERMISSION_DENIED is not evidence of a new product defect. The final RED generation issues a fresh grant after configuration and still fails at RuntimeWorkService authorization (Managed handoff execution is not authorized). This is the missing positive admission capability to implement next, not a false claim of unsafe execution.

Exact run commands, hashes and per-node outcomes are in evidence/p12-attach-work-config-index.json. Raw XML remains in .git/pr34-evidence because failure output can contain fixture credentials. No provider, personal session or LAN endpoint was used.

## Next implementation dependency

Reuse the agent key, canonical session secret, execute_work grant and handoff claim_epoch. Never invent native ACK or emit a synthetic terminal event. Implement these as one coherent admission/return contract before permitting managed attach execution:

1. Strictly prove the approved session at authenticated self-claim, even in trust_mode=open; compare actor to represented agent. Bind the session and a nonsecret credential fingerprint to the canonical runtime_handoff_bindings in the next additive migration (current schema063). Reject structured native result completion for attach. Configuration alone must not authorize dispatch.
2. Revalidate endpoint/grant revisions, current credential/session and canonical claim before sending. Keep secrets out of the envelope, journal and child environment. Pass trusted command-side authority to QualifiedConnector; no payload field can opt into external work. Native capability reports stay unchanged.
3. Extend the existing InboxService.ack path with authenticated external binding checks and atomic consumption/AGENT_ACK receipt, idempotently. Existing session_id/session_secret parameters already exist on inbox_ack. No private parallel delivery queue, fake native terminal or second receipt implementation.
4. Pass existing proof parameters from handoff_complete/reject façades into canonical HandoffService and require the current external binding/grant/claim before transition. Validate returning work independently of native process liveness; a restart must not invent loss of a separately authenticated Nexus session. Do not bypass revocation, policy, endpoint enable/revision or authenticated actor checks. Verification remains separate.
5. Add positive claim/transport/ACK/complete and negatives for spoofed/revoked/closed/foreign/stale proof, repeat ACK, cancellation, owner restart and no blind replay. Prove real Unix-socket fixture plus independent Nexus client on POSIX; native dedicated attach is still NOT_RUN. Public operation inspection must distinguish external Nexus ACK/work outcome from native result durability.

Useful composition points: RuntimeWorkService.authorize/enqueue/revalidate; HandoffService.handoff_claim/complete/reject; MCP handoff.py build_service; inbox.py build_service and ack; SqliteSessionRepo in adapters/outbound/sqlite/identity_repo.py; verify_session_credentials in application/identity.py (call within the existing UoW, not SessionTrustGuard.require which opens another writer); QualifiedConnector.send and HarnessCommand trusted fields; delivery dispatch composition must be located from its actual module before edits.

After WORK12: full immutable committed-source suites with persistent XML, finding-to-code/evidence report, final operational/release/package checks and local reinstall0.2.0. Pi native and dedicated native attach keep their explicit external limitations. Final gate has not passed.

## Completed execution summary for the configuration milestone

- Configuration third generation: Windows56785 terminal0,30 PASS84.30s; Linux80069 terminal0,30 PASS100.83s.
- Selected unchanged endpoint/profile/handoff/import regression: Windows40860 terminal0,54 PASS140.73s; Linux57654 terminal0,54 PASS153.38s. These 54 nodes do not include the new configuration tests or the known RED admission reproducer.
- Final positive admission reproducer: terminal1,1 FAIL5.32s, exact Managed handoff execution is not authorized response with a newly issued grant. Initial/incorrect-grant generations remain in the index, without presenting them as independent defects.
- Required isolated stdio MCP live smoke: terminal0,LIVE E2E RESULT: PASS. No raw credential-bearing output committed.
- Ruff on all three changed source/test files and git diff --check PASS. All handles terminal; no running test process remains.
- Working source schema063/surface57/identity25 unchanged. This is a preparatory configuration milestone with explicit RED acceptance, not a completed T-WORK-12 gate or release qualification.
