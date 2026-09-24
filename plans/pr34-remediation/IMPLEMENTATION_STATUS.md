# PR34 remediation — current implementation status

Updated2026-09-24. **IN PROGRESS — final gate NOT PASSED.** The full original P00–P12 scope remains active; no phase is VERIFIED solely from a selected green gate.

## Current branch and preservation

- All implementation milestones committed/pushed through `39c5e6c` (authenticated external attach work) on `feature/v0.2.0`; no merge/reset/force push.
- Package source version0.2.0; installed Nexus still0.1.10. Final build/reinstall remains pending.
- Protected pre-existing changes: the three generated dashboard files and `.nexus-policy-guardrail-test/`. Never stage them incidentally; frontend build must use a temporary output directory.
- Current schema064, surface58, identity25. No personal database is a fixture.
- PR34 was reread through GitHub during this continuation: OPEN, head `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`, base `27b06fe48b9f95b35c94f50827fea83d178f4e12`, branch `feature/harness-integrations`, unchanged from review. No PR currently targets head branch `feature/v0.2.0` according to the read-only query. No PR message/merge was performed.

## Exact resume point

Recovery-pressure milestone536b993 is committed/pushed; T-E2E-04 scoped PASS. No recovery campaign remains running.

Comparable benchmark milestone d1e300c is committed/pushed. Current synthetic latency is higher; measured overhead/guarantee differences remain in P12_COMPARABLE_PERFORMANCE.md.

WORK acceptance milestone395d070 is committed/pushed: WORK01–11 scoped PASS,114 distinct fixture nodes per platform; WORK12 remains NOT_RUN.

Fragmented-pipe milestone3779e95 is committed/pushed: T-LIFE-11 scoped PASS,24 fixture nodes/platform, no production change.

Signal-drain milestonef12c169 committed/pushed: new actual serve active native turn + fsynced/unprojected delta scenario. Linux65323 terminal10 PASS69.88s includes actual SIGTERM; Windows3515 terminal7 PASS3 POSIX SKIP30.15s includes graceful counterpart. Final checkpoint equals closed journal watermark; captured delta survives once, exact owned process witnesses stop and unfinished turn stays OUTCOME_UNKNOWN. T-LIFE-03 scoped PASS; Windows POSIX tests remain unexecuted. Preparation expectations/marker-race corrections are retained in P12_SIGNAL_DRAIN.md. Production unchanged; no running handles.

Coverage review at f12c169:91 distinct fixture nodes/platform PASS; CONS05, DISP08, LIFE01/07/08/12 and PRES03 now have exact assertion-to-execution joins. TX03/TX04/CONS06 remain explicitly partial. See P12_COVERAGE_REVIEW_F12C169.md. All four run handles terminal; no running tests.

Request acceptance unit: new barrier-controlled REST/MCP concurrent send and immutable key/content/target/owner-context tests;9 PASS each platform. TX03/TX04 now scoped PASS, superseding the partial review above. Parent f49c82b plus test hash, no production changes; see P12_REQUEST_ACCEPTANCE.md. No running tests.

Delivery acceptance: TX01/DISP01/DISP02 scoped PASS; actual lost-wake deadline defect reproduced (1 FAIL), fixed earliest recovery wait and startup config interval, with bounded store-error retry delay. Final78 PASS each platform, Ruff/diff and isolated live MCP smoke PASS. See P12_DELIVERY_ACCEPTANCE.md; parent c976374 plus source/test hashes. No running tests.

Consumption acceptance unit complete: CONS02/04/06 and PRES01 scoped PASS; final49 PASS Windows201.95s/Linux191.18s, exact socket refusal before-write proof and unchanged inbox accounting. Unsafe mirror16-case boundary verified but positive observer stays NOT_RUN. Preparation timeout correction retained; source unchanged. See P12_CONSUMPTION_ACCEPTANCE.md. Both handles terminal; no running tests.

Projection commit crash unit: T-JRN-03/07 scoped PASS,8 distinct fixture nodes per platform, all four handles terminal. Real owner death after visible atomic projection/checkpoint commit and stronger test-only rewind preserve original result/attempt, receipt and publication exactly once. No native reconnect deduplication claim. See P12_PROJECTION_COMMIT_CRASH.md. No running tests.

API review complete: Windows107 PASS2 POSIX SKIP/Linux109 PASS, both terminal. API02/03/07 and historical approved native LIFE10 have exact joins; see P12_API_REVIEW.md. Canonical payload gap reproduced as VALIDATION_ERROR, new test uncommitted pending implementation. No running tests.

Canonical conversational command contract3 implemented: T-API-04 scoped PASS.17 final new contract cases/platform,66 distinct passing selected nodes including metadata/regression, required isolated live MCP smoke PASS. Preparation failures retained and corrected; all handles terminal. See P12_CANONICAL_PAYLOAD.md. No running tests.

Capture/receipt/worker acceptance complete: JRN10, CONS08 and DISP07 scoped PASS,7 distinct nodes/platform. Real pre-capture owner death remains UNKNOWN; recovered receipt ACK twice produces no cascade; stuck API slots remain bounded. All six handles terminal, no failures/skips, production unchanged. See P12_CAPTURE_AND_RECEIPTS.md. No running tests.

Binding/disabled acceptance: PRES02/API01 scoped PASS,4 cases/platform, both handles terminal. Actual stdio/HTTP flag-OFF baseline and per-binding native heartbeat/workspace eligibility verified. See P12_BINDING_AND_DISABLED.md. No running tests.

Settle/detach acceptance: LIFE09 scoped PASS on Windows/Linux protocol fixtures, LIFE06 scoped PASS on POSIX external socket fixture. Final Windows3 PASS9 POSIX SKIP/Linux12 PASS; preparation fixture ERROR/cleanup FAIL retained. All four handles terminal. See P12_SETTLE_AND_DETACH.md. Native Pi/attach remain NOT_RUN. No running tests.

Birth/identity acceptance: LIFE02/05 scoped PASS,4 cases/platform, both handles terminal. Real owner kill at registration boundaries reaps exact tree; simulated numeric PID substitution cannot target unrelated echo process. See P12_BIRTH_AND_PROCESS_IDENTITY.md. Production unchanged, no running tests.

Approval acceptance: T-TX-05 scoped PASS,1 case/platform, both terminal. Three concurrent decisions and a later repeated decision preserve exactly one native execution after HITL; none before. See P12_APPROVAL_ACCEPTANCE.md. Production unchanged, no running tests.

Pull/push race: T-CONS-01 scoped PASS,2 cases/platform, terminal. Canonical pull reaches actual SQLite contention before/after push reservation, no duplicated payload. HTTP-loop barrier preparation failures retained. See P12_PULL_PUSH_RACE.md. Production unchanged, no running tests.

Owner fencing: T-DISP-05/06 scoped PASS,9 distinct cases/platform, all handles terminal. Actual competing owners and accepted-but-uncaptured SENDING crash preserve one executor and unknown outcome. See P12_OWNER_FENCING.md. Production unchanged; fixture preparation failures retained; no running tests.

Audience/privacy: T-PRES-04 scoped PASS,2 cases/platform, terminal. Authenticated inbound/outbound exclusion applies to delivery and reverse result publication; captured output retained without private policy exposure. See P12_AUDIENCE_PRIVACY.md. Production unchanged, no running tests.

Producer acceptance: T-TX-06 scoped PASS,10 cases/platform, terminal. All listed producers have actual transaction/rollback assertions, including new REST steering coverage. See P12_PRODUCER_ACCEPTANCE.md. Production unchanged, no running tests.

Operation event states: T-API-05 scoped PASS,2 cases/platform, terminal. Pending/unconfirmed distinguish acceptance and durable terminal; actual push/replay correlation and outbound method observer prove no native status polling. See P12_OPERATION_EVENTS.md. Production unchanged, no running tests.

Capture admission: T-JRN-09 scoped PASS. Actual admission defect reproduced with4 clean behavioral failures; additive schema062 shares an owner-fenced journal health guard across REST/MCP/independent stdio and database triggers. Final9 new plus103 regression PASS/platform, Ruff/diff and isolated live MCP smoke PASS. See P12_CAPTURE_ADMISSION.md. All handles terminal; no running tests.

Composition acceptance T-E2E-06: Windows27096 terminal20 PASS1 POSIX SKIP188.71s/Linux35283 terminal21 PASS451.02s at a6a18b4, no tested source changes during runs. See P12_COMPOSITION_A6A18B4.md. No running handles.

Mirror observation implemented: T-CONS-07 scoped PASS. Additive schema063 and optional context v1 reuse the owner/bounded worker while retaining one inbox executor. Final13 cases/platform plus16 unsafe native mirror cases/platform; regression Windows78 PASS1 POSIX SKIP/Linux79 PASS, with separate pre-close-adjustment hashes. Actual REDs for missing observation, public-read failure and closed-session pending state retained. Required isolated MCP smoke PASS after the final production adjustment; all handles terminal. See P12_MIRROR_OBSERVATION.md.

External attach work configuration implemented after48a8ea2: EndpointService now approves only active same-agent/workspace Nexus session references, rejecting harness-owned presence and missing secrets atomically across REST/MCP. Configuration does not prove possession or enable managed work.30 fixture cases and54 selected regression nodes PASS each platform; isolated MCP smoke and static checks PASS, all handles terminal. Exact generations are recorded in P12_ATTACH_WORK_CHANNEL.md. Positive managed claim with a fresh post-update grant remains an explicit RED acceptance test, so T-WORK-12 is now FAIL (previously NOT_RUN). No native provider run. No schema/surface change yet.

External attach integration supersedes that preparatory RED: T-WORK-12 scoped PASS. See P12_ATTACH_WORK_INTEGRATION.md and its generation-specific manifests. Final operational gate Windows81 PASS1 POSIX SKIP/Linux82 PASS; writer/attach/migration gate Windows47 PASS1 POSIX SKIP/Linux48 PASS; broader pre-writer-fix regression384 PASS each platform, with exact hashes and overlaps retained. The older-writer bypass was reproduced and fixed with an additive capability fence. Retention FK failure and reopened-offer rejection refusal were also reproduced and corrected before publication. Completed final JUnit files were recovered; prior process exit codes were unavailable at resume. Required isolated live MCP smoke and static checks PASS; all handles terminal. No new installed-provider run.

Current run: Windows full suite at39c5e6c, tool handle51046, launch/status .git/pr34-evidence/full-39c5e6c-windows-launch.json, persistent output/XML in its recorded run_dir. One failure observed at tests/test_harness_claude_code_connector.py::test_events_iterator_delivers_promptly_not_on_a_poll_interval; await terminal traceback before diagnosis. Production/tests stay frozen. Linux full suite not started yet. Collect-only handle38805 completed0 with2755 nodes. No installed provider run during this regression.

Release preparation at39c5e6c: clean git archive, uv lock --check, npm ci, temporary TypeScript/Vite build, uv build, Twine wheel/sdist validation PASS. Wheel contains64 migrations, new external-work module, and byte-matched fresh dashboard. Record/artifact paths and hashes: .git/pr34-evidence/release-39c5e6c.json. Build handles88791/41684 terminal0. Global installation remains0.1.10; do not install as a passed release before resolving full-regression results.

Finding/evidence audit started in P12_FINAL_AUDIT.md and evidence/p12-final-audit-39c5e6c.json:15 findings and129 original matrix rows, all referenced paths checked. Full Ruff initially failed7 on obsolete diagnostic p11_writer_mode_probe.py; archived byte-identically as .py.txt (historical command explicitly labeled), then full Ruff PASS. No runtime/test changes during the suite.

Next: finish immutable full regression, diagnose failures, complete evidence/finding/phase reconciliation and approved native final qualification, then local reinstall0.2.0. The126 scoped PASS rows require a final evidence/finding join; three original rows remain NOT_RUN. The e388227/58ca69b review JSONs are only partial catalogues; do not assume missing entries lack implementation. Review actual test bodies and then run final immutable-source suites with persistent XML and per-node reduction. Finish finding index, operational/release audit, package checks and build/reinstall0.2.0. Native Pi/attach remain NOT_RUN per authorization; WORK12 external channel is fixture-qualified; installed native attach is not.

## Recent completed milestones

- `28d1078`: canonical catalogue and identity after post-spawn failures —48 PASS each platform.
- `6c710ea`: foreign/revoked persisted command replies —30 PASS each platform.
- `04446f7`: real owner crash after commit before wake —6 PASS each platform.
- `fe2801e`: REST payload validation500→422 correction —37 PASS each platform, live MCP smoke PASS.
- `8ec25f5`: foreign replay/results, native forged authority and grant revoked before terminal —36 PASS each platform.
- `e18cf69`: REST replay validation500→422 correction, cursor/ACL/retention —26 PASS each platform, live MCP smoke PASS.
- `bf5636c`: observed spawn/secrets/transport/model/loopback network outside writer UoWs —4 PASS each platform.
- `af53f82`: exact owner death under measured same-CPU pressure —2 warmup+6 measured cycles each platform; all exact process witnesses stopped and RSS/descriptor/thread bounds passed. See [P12_CRASH_PRESSURE.md](P12_CRASH_PRESSURE.md). This uses fresh stores and does not by itself qualify recovery-under-load.

Each unit document retains exact commands, parent SHA plus changed-file hashes, failures and scoped limitations. Historical aggregate counts do not replace current-node evidence.

## Remaining gates

1. Recovery-under-load T-E2E-04 complete with scoped evidence; preserve its limitations during final audit.
2. Complete original129-row assertion-to-evidence mapping, including exact remaining WORK, lifecycle active-turn SIGTERM and fragmented UTF-8/pipe-pressure stimuli. Many existing tests already cover portions; audit bodies before adding or promoting coverage.
3. Comparable before/after benchmark T-E2E-05 complete; retain published overhead and scope limits in final report.
4. Final committed-source Windows/Linux suites with persistent XML under `.git/pr34-evidence`; reduce per-node manifests before cleanup. Older full Linux58ca69b terminal summary lacks its lost XML and cannot populate node results. Later changes are not qualified by old full counts.
5. Final F01–F14/F15 finding→code→evidence report, operational documentation/readiness audit, packaging/lock checks and temporary frontend build, then local reinstall0.2.0.

## Native connector authorization and evidence

Codex and Claude local isolated campaigns at752cd72 ran with the user's authorization: Codex7 PASS and Claude6 PASS; see [P12_NATIVE_FRAMES.md](P12_NATIVE_FRAMES.md). No unnecessary provider reruns. Pi native is NOT_RUN by user decision; Claude attach native is NOT_RUN without a dedicated approved session. Fixtures preserve all four adapters but are not native qualification. Never reuse old LAN endpoints, personal sessions/configuration or inject the operator key into a subprocess.

## History and source of truth

- [05_BACKLOG.json](../../05_BACKLOG.json) retains all original tasks/tests and their execution statuses.
- [Historical status through af53f82](IMPLEMENTATION_HISTORY_TO_AF53F82.md) preserves the previous chronological status verbatim, including superseded resume points. Do not treat its old running handles or pending labels as current.
- Specs01–06 at repository root remain authoritative. Existing migration/capacity/fallback/identity mechanisms must not be reimplemented merely because an old historical paragraph called them pending.

Backlog snapshot at this update: {"PASS": 126, "NOT_RUN": 3}. PASS means only the recorded scoped requirement evidence; it is not a passed final gate.


## Current environment constraint

C drive reached0 free bytes during the external-work campaign, confirmed by independent SQLite WAL failure. Windows tests and the live MCP smoke now allocate new private temporary roots beneath .git/pr34-evidence on D (TEMP/TMP/TMPDIR plus pytest basetemp). Preserve XML and reduce manifests before any cleanup. Do not delete personal files or reuse old fixture stores. D had roughly580GB free at that observation. Linux campaigns completed successfully in their existing isolated WSL environment. Recheck storage before the final installation; do not mislabel disk-full failures as product regressions or silently omit them.
