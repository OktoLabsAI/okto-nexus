# PR34 remediation — current implementation status

Updated2026-09-24. **IN PROGRESS — final gate NOT PASSED.** The full original P00–P12 scope remains active; no phase is VERIFIED solely from a selected green gate.

## Current branch and preservation

- All milestones committed/pushed through `d1e300c` on `feature/v0.2.0`; no merge/reset/force push.
- Package source version0.2.0; installed Nexus still0.1.10. Final build/reinstall remains pending.
- Protected pre-existing changes: the three generated dashboard files and `.nexus-policy-guardrail-test/`. Never stage them incidentally; frontend build must use a temporary output directory.
- Current schema061, surface56, identity24. No personal database is a fixture.
- PR34 was reread through GitHub during this continuation: OPEN, head `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`, base `27b06fe48b9f95b35c94f50827fea83d178f4e12`, branch `feature/harness-integrations`, unchanged from review. No PR currently targets head branch `feature/v0.2.0` according to the read-only query. No PR message/merge was performed.

## Exact resume point

Recovery-pressure milestone536b993 is committed/pushed; T-E2E-04 scoped PASS. No recovery campaign remains running.

Comparable benchmark milestone d1e300c is committed/pushed. Current synthetic latency is higher; measured overhead/guarantee differences remain in P12_COMPARABLE_PERFORMANCE.md.

WORK acceptance unit is complete locally: three selections47/46/25 PASS per platform,114 distinct nodes. New six-case test file covers losing-claim privacy, real-pipe delayed interrupt and unsupported work/sandbox profiles with conversation preserved. Every WORK01–11 mapping resolves to PASS on both platforms in P12_WORK_ACCEPTANCE.md and its index. WORK12 remains NOT_RUN for the complete attach/external authenticated channel stimulus. Production code is unchanged. No test/campaign processes remain running.

Next: lifecycle active-turn SIGTERM and fragmented UTF-8/pipe-pressure acceptance; finish original matrix mapping and remaining gates, then final committed-source suites, finding index, build/reinstall0.2.0. Keep native Pi/attach NOT_RUN under existing authorization. Do not repeat completed provider sends or migrations.

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

Backlog snapshot at this update: {"PASS": 81, "NOT_RUN": 48}. PASS means only the recorded scoped requirement evidence; it is not a passed final gate.
