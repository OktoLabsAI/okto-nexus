# Latest follow-up — native connections enabled by default

Runtime source372b47c sets feature_harness_integrations and feature_harness_attach
true in both NexusConfig and the CLI/environment resolver. Explicit false in
stored settings, environment or CLI remains authoritative. No approval or
per-agent permission was removed. Test-only lifecycle/expectation corrections
are recorded in [evidence/default-native-connections.json](evidence/default-native-connections.json).

Qualification: broad selected regression256 PASS /4 FAIL /2 SKIP; the four stale
test fixtures/expectations were corrected and affected files rerun:30 PASS /2
SKIP. The combined scope covers260 distinct PASS /2 SKIP; not a single green
full-suite run. Live stdio51 tools, lock, build/Twine and isolated packaged
HTTP/MCP smoke PASS. Ruff retains862 baseline diagnostics; native providers
NOT_RUN. Updated wheel is in .git/pr34-evidence/default-native/dist-final.

Local rollout remains NOT_APPLIED: the running installed server and personal
store were not changed. Update/restart to apply the build; explicit stored false
is not automatically cleared. Protected local static files remain unchanged.

The earlier follow-up below retains its original source/result boundaries.

# Current follow-up — agent connection management

IMPLEMENTED_AND_SCOPED_VERIFIED on feature/v0.2.0. Runtime and packaged dashboard
source: 12d352c; test-only Windows snapshot correction: 3ca5c55. Both committed
and pushed. Baseline c692722. See [AGENT_CONNECTIONS.md](AGENT_CONNECTIONS.md)
and [evidence](evidence/agent-connections.json).

- Default key expiry 24 hours; global/per-agent expiry, allowed connection
  methods, scoped native-opening keys, shared REST/MCP authorization and Agents UI.
- Final affected HTTP/MCP/browser/settings/authorization suite: 85 PASS at12d352c.
- Full Windows: 2653 PASS / 1 FAIL / 122 SKIP. The sole fixture failure was a
  transient Windows snapshot read denial; fixed at3ca5c55, 20 PASS across10
  independent reruns. Full execution began at0646a56 while later changes landed;
  no immutable final-HEAD full-suite PASS is claimed. All test runs finished.
- Live stdio, TypeScript/Vite, final wheel/sdist/Twine and final wheel with
  installed production dependencies: PASS. Full Ruff retains862 baseline
  diagnostics; new modules/helper pass. Native providers NOT_RUN this follow-up.
- New wheel: .git/pr34-evidence/agent-connections/dist-12d352c. Local rollout
  NOT_APPLIED: pre-existing installed serve (observed PID16312) and personal store
  preserved. Follow the documented shutdown/backup/update/restart procedure.
- Three pre-existing static working-tree files remain byte-identical and dirty;
  .nexus-policy-guardrail-test remains unrelated. Clean checkout/package contains
  the new dashboard. No personal provider configuration used or merge performed.
- No remaining implementation task in this follow-up. Local rollout and fresh
  real-provider qualification are explicit remaining operational steps. Original
  native Pi/attach exclusions below are not converted into PASS.

Prior delivery below is historical, not qualification of this follow-up.

# PR34 remediation — completed authorized delivery

Branch: `feature/v0.2.0`; installed version: **0.2.0**.
Runtime/test implementation: `ff905c433e1a92ae35993b2189919f75ad07dd51`.
No validation run remains active. No merge/tag/publication performed.

The [final report](P12_FINAL_AUDIT.md) and its
[generated evidence](evidence/p12-release-report.json) cover all129 original
requirements and15 findings: **127 scoped PASS /2 NOT_RUN**.

## Completed

- Integrated implementation,35 additive migrations030–064, four preserved
  adapters, canonical identity/inbox/handoff and shared authorization.
- Full Windows2637 PASS/121 SKIP (49697 exit0); full Linux2714 PASS/44 SKIP plus2
  passing subtests (19457 exit0). Original Windows base/diff plus explicit CRLF
  equivalence retained;543 source files unchanged after run. Linux checkout clean.
- Real approved Codex7 PASS and Claude stream6 PASS atff905c4; separate dashboard
  15 PASS. No native status queries, unclassified outbound trace or overflow.
- Final sequential comparative benchmark Windows30445/Linux17569 both exit0,
  six rounds and120 measured turns per revision/platform. Higher synthetic latency
  is published, not hidden. Existing load campaigns retain original SHA/scope.
- Corrected package built and locally installed.267 package files match wheel;
  Python/serve extra and69 non-Nexus dependency versions preserved. Installed
  actual MCP and feature-ON HTTP synthetic-peer smokes PASS. No personal DB opened.
- Generated122 node-based execution joins plus7 explicit campaign/report routes,
  original partial classifications and per-platform skips retained. All63 task
  reviews and13 phase statuses reconciled in the backlog.

## Only remaining qualification — deliberately NOT_RUN

- T-E2E-01: three installed providers concurrently; Pi native was excluded by user.
- T-E2E-02: native Claude attach requires a dedicated approved interactive session.

P07-T02, P07-T06 and P12-T02 remain IMPLEMENTED pending that external native
qualification. Other60 tasks VERIFIED in recorded scope. P07/P12 phase status
remains IMPLEMENTED; the unrestricted four-native gate is **NOT PASSED**.
The authorized implementation/local-test delivery is complete; fixtures do not
turn those native exceptions into PASS or NOT_APPLICABLE.

A future campaign must obtain explicit environment/session configuration and use
fresh isolated fixtures. Do not repeat approved real sends, migrations, full
suites or installation merely because an old historical paragraph says pending.
There is no pending code task within the authorized scope.

## Protected local work and artifacts

Preserve the three pre-existing modified generated HTTP static assets and
`.nexus-policy-guardrail-test/`; none is staged or overwritten. Builds used clean
Git archives and temporary frontend output. Raw XML/logs are private because they
may contain fixture credentials. Corrected wheel/sdist paths/hashes are recorded
in `evidence/p12-release-ff905c4.json`; local install in
`evidence/p12-installed-release-ff905c4.json`.

Authoritative sources: original specs01–06, [backlog](../../05_BACKLOG.json),
[final audit](P12_FINAL_AUDIT.md), [operator evidence index](../../docs/harness-integrations/evidence-index.md).
Historical status is archived in IMPLEMENTATION_HISTORY_TO_336357A.md and
IMPLEMENTATION_HISTORY_TO_AF53F82.md. Their pending labels/handles are superseded.

Final report/operational documentation belong to the final milestone on this
branch; use `git log -1` for its commit identity. All authorized changes are
committed/pushed at delivery; the protected unrelated files remain local. No merge.
