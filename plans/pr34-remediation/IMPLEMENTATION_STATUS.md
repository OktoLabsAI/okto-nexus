# PR #34 remediation — execution status

Started 2026-09-22, Windows / PowerShell. **IN PROGRESS; final gate NOT PASSED.**

## Baseline

- Local and GitHub HEAD: `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`.
- GitHub base / local merge-base: `27b06fe48b9f95b35c94f50827fea83d178f4e12`.
- Baseline branch: `feature/harness-integrations`. User subsequently directed all development, milestone commits and pushes to `feature/v0.2.0`; created from the unchanged reference HEAD while preserving working changes. Package bumped to 0.2.0.
- Existing changes preserved: three generated dashboard files; `.nexus-policy-guardrail-test/`; six user-supplied specification files at repository root.
- Latest migration: 029. No user database opened or migrated.
- Instructions inspected: CLAUDE.md, CONTRIBUTING.md; no AGENTS.md discovered in repository or ancestor directories.
- Specification precedence: current remediation package supersedes historical frozen-port / no-thread / no-MessageService-change restrictions. CLAUDE.md's claims of no CI and main-only development are stale (repository has .github and this authorized PR branch).

## P00 — baseline recorded

Baseline, defect register, contract map and 20 failing behavior regressions committed and pushed in 63c9623. See BASELINE.md for exact counts and evidence.

Commands/results:

- `git status --short --branch`, `git rev-parse HEAD`, `git merge-base HEAD origin/main`, `gh pr view 34 --json headRefOid,baseRefOid,headRefName,url`: reference unchanged.
- `.venv/Scripts/python.exe -m pytest --collect-only -q`: **FAIL**, 1830 collected, one Windows collection error (`os.geteuid` in test_claude_code_attach_connector.py); evidence `evidence/p00-collection.log`. This is baseline portability failure, not a remediation regression reproduction.
- `.venv/Scripts/python.exe -m pytest -q --ignore=tests/test_claude_code_attach_connector.py`: completed: 1814 passed, 13 failed, 4 skipped; evidence `evidence/p00-baseline.log`. Exclusion is explicit; excluded tests remain NOT_RUN.

## Pending gates

P01 containment tasks implemented, phase IN_PROGRESS pending its full gate; P02 contracts IMPLEMENTED; P03–P08 IN_PROGRESS; P09–P11 IN_PROGRESS; P12 IN_PROGRESS. No phase VERIFIED. No completion claims from historical PR counts. User explicitly approved the installed local Codex and subsequently Claude for real tests. Versions observed: codex-cli 0.155.1; Claude Code 2.1.277. Keep native tests in temporary project directories, preserve security controls, never pass the Nexus operator key. Attach requires a dedicated test session; never select a personal session. Pi native tests remain NOT_RUN by user decision.

Current resume point (2026-09-24): effective-capability intersection implemented above575c8c28ab6c4543ad8dc5b0b64949d5f735fea6; schema057, surface52, identity19. See P02_EFFECTIVE_CAPABILITIES.md. Final sharing guard Windows26 PASS/Linux26 PASS; expanded profile/extension/reference Windows27 PASS/Linux27 PASS; final UI2 PASS. Real Codex0.156.1 and Claude2.1.281 each4 PASS with redacted evidence. Direct admission/dispatch/native writes enforce descriptor/probe/profile intersection. Next: immutable-SHA full regression, matrix/stress/performance audit, build/reinstall0.2.0. Prior full suite2296 PASS/4 FAIL/117 SKIP remains failed despite selected fixes. Protected local assets untouched. Pi/dedicated attach native NOT_RUN; final gate NOT PASSED.

Milestones pushed: 8307965 (0.2.0), 63c9623 (P00 baseline), 613b64f (P01 containment). P02 commit: 8207e7b; evidence: P02_CONTRACTS.md.

P03: migration 030, profiles/endpoints, canonical runtime presence and isolated child environments implemented. 19 tests PASS (evidence/p03-gate.log). Seven later-phase regressions remain outstanding. Native Codex/Claude/Pi/attach NOT_RUN so far. All phase statuses use backlog vocabulary; IMPLEMENTED does not imply VERIFIED.

P03 checkpoint pushed: dc67cdd. P04 scoped grants/control checkpoint: parent dc67cdd; 59 selected tests PASS plus two concurrency/opacity tests PASS. Actual authenticated stdio subprocess tested; native harnesses remain NOT_RUN. See P04_AUTHORIZATION.md for exact commands and pending gates. Next: transactional canonical delivery/transport operations (P05).

P04 checkpoint pushed: 2fb9f59. P05/P06 checkpoint: migration 032, transactional transport intents and inbox exclusion, bounded serve-owned dispatcher, IPC wake, authenticated stdio owner proxy and idempotent open. See P05_P06_DURABLE_DELIVERY.md: 77 selected tests PASS, one additional owner-proxy PASS, 176 canonical tests PASS. Three legacy regressions still pending. No native connector/model execution yet. Next: process ownership/lifecycle (P07), then durable event/result projection (P08); pending gates remain explicit.

P05/P06 checkpoint pushed: 62ef22b. P07 process ownership unit: Windows atomic Job launch in all three spawning adapters, bounded startup/control helpers and cancellation, Codex EOF handshake release. Eight ownership tests PASS, including actual REST composition and three abrupt fixture owner kills. See P07_PROCESS_OWNERSHIP.md for failing intermediate checks, platform limits and pending gates. Next: shared-connection lifecycle, POSIX ownership and durable event journal. Native campaigns remain without accepted results.

P07 process checkpoint pushed: 93d5fab. P08 journal unit: additive migration 033,
production journal-first capture and atomic event/result/checkpoint projector.
96 integrated tests PASS (one P10 relay regression deselected), plus 10 expanded
journal tests PASS. See P08_EVENT_JOURNAL.md for commands, partial coverage and
remaining correlation/publication/retention/lifecycle dependencies.

Native update: REAL Codex 0.155.1 and Claude Code 2.1.277 each passed two turns
through production serve/MCP/inbox/outbox/journal, preserved canonical identity,
and reaped their managed process. Temporary login copies removed. See
NATIVE_CAMPAIGN.md and evidence/p07-native-observations.json. These supersede
historical NOT_RUN statements only for those two basic flows. Native steer,
interrupt, HITL, multiplexing and load scenarios remain unverified; Pi and Claude
attach native remain NOT_RUN. No merge or final-gate claim.

P08/native checkpoint pushed: 0ad7c0f. Subsequent P07/P08 unit fixes shared Codex
process lifetime and session event fanout, reuses connection_id, and adds migration
034 for native versus Nexus event origin. Close transitions/presence now project
from durable lifecycle records; detach is not fabricated ENDED. Behavioral RED
reproduced the shared-process kill before correction. Gate: 189 passed, 9 skipped,
1 P10 relay case deselected; expanded/presence gate: 34 passed. See
P07_SHARED_LIFECYCLE.md. Next dependencies: active-turn stop/settle, native buffer
limits, POSIX ownership/boot recovery, operation correlation and scoped work/HITL.
These fixture runs do not replace or expand the earlier native campaign claims.

Shared-lifecycle checkpoint pushed: ab7d56c. Attach platform unit now rejects
unsupported POSIX operations before effects and reports the platform contract
without removing the adapter. See P07_ATTACH_PLATFORM.md: 13 passed, 57 POSIX
fixtures NOT_RUN on Windows; full collection succeeds (2011 tests). Native attach
remains NOT_RUN. Next: bounded native readers/buffers and remaining P07 recovery.

Attach-platform checkpoint pushed: fdfc994. Native framing unit bounds stdout
frames and stderr chunks in all three managed adapters. Three behavioral RED
reproductions corrected; expanded checks include a durable fault through actual
REST composition. Gate: 104 passed, 9 skipped, 1 known injected Pi warning. See
P07_PROTOCOL_LIMITS.md. Native history/subscriber buffers, active-turn close,
POSIX ownership and boot/recovery remain pending; final gate NOT PASSED.

Bounded-framing checkpoint pushed: 866753a. Subsequent Codex active-close unit
interrupts an observed active turn and awaits its matching terminal before
unsubscribe. Shared-thread fixture proves sibling survival and stale-terminal
quarantine; real isolated Codex active-close campaign PASS (one test, 5.39s).
See P07_CODEX_ACTIVE_CLOSE.md. Turn/start correlation, durable controls, buffers,
POSIX ownership and remaining matrix gates are still pending.

Active-close checkpoint pushed: 1780f15. Request-ordering unit now registers
Codex native correlation before writes and fences pending/active turn admission;
close waits for pending turn identity under the same deadline. Two behavioral
REDs corrected. Gate: 45 passed, 4 skipped; REAL Codex two-turn plus active-close
campaign: 2 passed, 1 deselected (18.04s), isolated auth copies removed. See
P07_CODEX_REQUEST_ORDERING.md. Native histories/queues and general durable
controls/correlation, POSIX ownership and boot/recovery remain pending.

Request-ordering checkpoint pushed: 2b6b3a9. Native stream v2 unit bounds all four
event histories and the three managed fanout paths, makes expired replay/overflow
explicit and records uncertain lifecycle with a failure type. Integrated gate:
169 passed, 9 skipped, 1 P10 case deselected, 1 known Pi warning. Fresh REAL native
campaigns: Codex 2 passed (two turns + active close); Claude stream 1 passed (two
turns). Temporary auth copies removed. See P07_EVENT_BUFFERS.md. Remaining native
early-event/turn bookkeeping, durable control/result correlation, POSIX ownership
and boot/recovery are explicitly unfinished. Final gate still NOT PASSED.

2026-09-23: bounded-stream checkpoint bac6f71 followed by Codex early-event cache
limits (128 notifications / 1 MiB), explicit connection failure and ordered replay
that restores native turn state. See P07_CODEX_EARLY_EVENTS.md: 2 behavioral REDs;
integrated gate 75 PASS, 1 skipped; fresh REAL isolated Codex campaign 2 PASS,
1 deselected. Other native bookkeeping, POSIX ownership, boot/recovery and durable
control/result correlation remain unfinished. No final-gate promotion.

Early-event checkpoint pushed: 075ea86. Subsequent Codex lifetime thread admission
caps native start attempts at 64 per connection before effects, including uncertain
starts. Concurrent real-pipe regression RED then corrected; 45 PASS, 1 skipped;
expanded tests 6 PASS. See P07_CODEX_THREAD_ADMISSION.md. Native campaigns NOT_RUN
for this subsequent unit. Claude pending admission and remaining P07/P08 gates
still pending. User supplied RTK.md on this date; shell commands now use rtk.

Thread admission checkpoint pushed: 7e3e774. Claude stream admission now bounds
pending turns plus steer reservations at 32, rejecting replacement before any
interrupt when full. See P07_CLAUDE_ADMISSION.md for fixture correction, behavioral
RED, integrated gate 45 PASS / 7 skipped, and fresh REAL isolated Claude two-turn
campaign 1 PASS / 2 deselected. POSIX ownership, shutdown/boot/recovery and durable
control/result correlation remain pending. P01 summary reconciled with backlog:
tasks implemented, phase still IN_PROGRESS. No final-gate promotion.

Claude admission checkpoint pushed: 30f340c. P08 attempt correlation unit adds
migration 035, event correlation v2, matching native start/terminal projection,
exclusive lane fencing and conservative recovery of accepted/unconfirmed sends.
See P08_RESULT_CORRELATION.md: behavioral RED; 69 integrated PASS; fresh REAL
Codex 2 PASS and Claude stream 1 PASS. Logical consumption, materialized output,
publication and durable controls remain pending; no final-gate promotion. WSL
Ubuntu was inspected read-only: Python 3.10.12 with pidfd_open; no POSIX ownership
implementation/test or native provider use occurred in WSL.

Attempt correlation checkpoint pushed: 924c3ef. Migration 036 adds normalized,
redacted text fragments and bounded result materialization. Canonical InboxService
consumes only a correlated terminal's push reservation and emits explicitly labeled
runtime-processing receipts, atomically with result/checkpoint. See
P08_CONSUMPTION_MATERIALIZATION.md: behavioral RED; 75 integrated PASS; REAL isolated
Codex 2 PASS and Claude 1 PASS. Publication, artifacts, durable controls and all
later gates remain pending; next lifecycle work is POSIX birth ownership.

Consumption/materialization checkpoint pushed: 920faee. Linux birth ownership now
uses a per-connection subreaper with owner pidfd and cleanup proof; serve no longer
launches its historical PID scanner. See P07_LINUX_OWNERSHIP.md: real orphan RED;
6 standalone Linux component PASS, Windows regressions/platform gates PASS with
explicit skipped cases. WSL Python 3.10 component evidence does not qualify full
Nexus Linux composition (requires >=3.11), which remains NOT_RUN. Managed platforms
declared Windows/Linux; external guardian kill yields unknown, not observed stop.
Full shutdown/boot/recovery and later phases remain pending; no final gate passed.

Linux ownership checkpoint pushed: e482655. Coordinated shutdown now retains the
owner heartbeat and journal through bounded runtime drain, rejects late admission
and refuses contending serve startup. Wake generations replace Event.clear. See
P07_COORDINATED_SHUTDOWN.md: behavioral RED; 55 integrated PASS; REAL isolated Codex
2 PASS and Claude stream 1 PASS. Next: restart journal/session reconciliation and
stable endpoint boot. P09-P12 and final gate remain unfinished.

Coordinated shutdown checkpoint pushed: fd75ef1. Migration 037 freezes the journal
recovery boundary per new owner, allowing exact old-attempt durable results to
recover without native replay or accepting late old-owner events. See
P07_RESTART_JOURNAL.md: two behavioral REDs, 60 integrated PASS. Native campaigns
NOT_RUN for this unit. Next: stale sessions, owner epoch stamping and stable boot.
Linux Python 3.13 provisioning began in isolated temporary directories; full Linux
composition remains NOT_RUN until its tests execute. No final-gate promotion.

Journal restart checkpoint pushed: 3c0eb84. Supported WSL CPython 3.13.12 composition
now ran: 215 PASS / 12 skipped / 1 known injected Pi warning / 2 subtests PASS,
including all four fixture connector suites and production delivery/recovery.
Fixed standalone-Python pidfd wrapper absence, guardian pipe copies masking EOF,
and structured runtime-open persistence errors. See P07_LINUX_COMPOSITION.md for
initial failures and exact evidence. Native providers NOT_RUN for this unit.
Windows compatibility inventory stopped at 20 failures after 764 PASS; legacy
harness tests need current canonical identities/approved profiles/authorization.
Final gate still NOT PASSED. Next: adapt legacy regressions, stale session epoch
reconciliation and stable endpoint boot; P09-P12 remain unfinished.

Linux composition checkpoint pushed: 17cb43b. Legacy MCP/REST/supervisor tests
now use canonical identities/approved profiles and authenticated serve. Found and
fixed discarded non-Claude substrate plus stale MCP descriptions. See
P11_LEGACY_SURFACE_COMPATIBILITY.md: 59 PASS / 2 POSIX skips, Ruff PASS. Native
providers NOT_RUN for this unit. Next: stale session epoch reconciliation and
stable boot, then durable controls and remaining P08-P12. Final gate NOT PASSED.

Surface compatibility checkpoint pushed: 6b1358d. Migration 038 makes every
production open reserve logical STARTING before construction; readiness is fenced
by owner epoch, deadline and approved revisions. Restart after journal recovery
invalidates stale readiness/presence and quarantines unfinished bindings. See
P07_SESSION_RECOVERY.md: two REDs, 21 PASS core, expanded 100 PASS / known P10
relay FAIL / fixture teardown ERROR; fixture corrected and 5 focused PASS. Native
providers NOT_RUN. Next: explicit endpoint reconciliation and stable approved boot.
Final gate NOT PASSED; P09-P12 still pending.

Session recovery checkpoint pushed: 2f760b0. Migration 039 adds operator-approved
boot bindings, narrow owner-scoped boot authorization, global native-start budget
and explicit audited endpoint reconciliation. Failed native starts persist
quarantine; lost-reply idempotency remains usable. See P07_APPROVED_BOOT.md:
51 PASS initial integration; final 29 PASS Windows and 15 PASS Linux. Native
providers NOT_RUN for this unit; native boot and attach dedicated session remain
external validation. Next: durable prioritized controls/expected-turn fencing;
publication/artifacts and P09-P12 still pending. Final gate NOT PASSED.

P07/P08 durable administrative command unit (parent 90ec3cc): migration 040, shared transactional admission and grant consumption, bounded priority workers, idempotency and expected-turn fences, command result recovery and authorized operation reads. Contract v2 makes close asynchronous. See P07_DURABLE_COMMANDS.md for evidence and compatibility. Fresh native campaigns: Codex 0.156.1 two cases PASS; Claude 2.1.280 one case PASS. Native steering/HITL, Pi and dedicated attach NOT_RUN. P08 publication/retention, P09-P12 remain pending; final gate NOT PASSED.

Durable commands checkpoint pushed: 0eeb749. P08 retention unit above it adds explicit operator compaction through shared REST/MCP service, deleting only projected journal segments while preserving SQLite events/results. Manifest crash cuts and quota recovery tested on Windows/Linux; see P08_JOURNAL_RETENTION.md. Result publication/artifacts, database retention and remaining P09-P12 gates still pending. No final gate PASS.

Journal retention checkpoint pushed: 41c3322. P08 publication unit above it: migration 041, private correlated replies through canonical MessageService/guardrails/approvals, transactional idempotency and current binding revalidation. Fixed approval-rejection notice launching a native turn (behavioral RED reproduced). Windows 110 PASS, Linux 13 PASS, additional strict/disabled case PASS. See P08_RESULT_PUBLICATION.md. Artifact publication remains pending; no native campaign or final gate claim for this unit. Next: complete P08 artifacts/operational recovery, then P09-P12 in backlog order.

Canonical publication checkpoint pushed: 0490a05. P08 artifact unit above it adds migration 042, explicit private readers in the existing artifact catalog, durable prepared bytes and atomic catalog/message/result linkage. Shared artifact storage moved outside SQLite writers with revalidation. Publication has one bounded worker and preserves wakes/owner shutdown. Two behavior REDs corrected; final Windows 128 PASS, Linux 24 PASS. See P08_RESULT_ARTIFACTS.md. Next: explicit unpublished artifact/reservation recovery and remaining P08 gates, then P09-P12. No native provider or final-gate claim for this unit.

P08 maintenance checkpoint pushed: 08b5fb1. P09 claim-generation foundation adds migration 044 and surface revision 36. Reproduced stale same-agent complete/reject after reclaim; fenced CAS and MCP/REST/dashboard now carry generation. Windows integrated 329 PASS; frontend type check and Ruff PASS. See P09_CLAIM_EPOCH.md. Next: managed claim/grant/dispatch and restricted bootstrap, then native HITL and P10-P12. No final gate passed.

Authenticated handoff checkpoint committed and pushed: e054720. Local Codex 0.156.1 schema and Claude 2.1.280 help inspected without model calls; see P09_NATIVE_PROTOCOL_SURVEY.md. Native approval bridge remains unimplemented. No test or phase status promoted by schema inspection.


Scoped discovery unit above28ca542: see P11_SCOPED_DISCOVERY.md for exact commands, behavioral RED, fixture corrections, native limits and code mapping. T-API-06 fixture projection PASS; no aggregate phase verification.


Native input dashboard unit above43e06cc: P11_NATIVE_INPUT_DASHBOARD.md records exact browser commands and RED, 6 PASS, backend48 PASS, screenshot and native-model NOT_RUN limits. Existing generated static files preserved; temporary builds only. P11-T03 remains IN_PROGRESS and aggregate T-API-08 NOT_RUN.

2026-09-23 continuation: target routing checkpoint5c661fa pushed. ADR0004 amended above it; documentation links checked. That inventory has since terminated; its reduced/redacted manifest is evidence/p11-complete-suite-inventory.json. The raw XML was removed after reduction. No full-suite PASS yet.

Cutover audit on feeb14d: authenticated feature-OFF stdio successfully committed one unread, unreserved delivery against the active feature-ON owner, with zero outbox rows. This confirms missing store-wide writer enforcement; P11_CUTOVER_AUDIT.md and evidence/p11-writer-mode-audit.json preserve the reproduction. Combined journal/artifact backup/restore also remains unproven. Historical session15489 terminated with2296 PASS/4 FAIL/117 SKIP; see P12_SUITE_FEEB14D.md. Writer contract and combined restore subsequently implemented in c27223b/2785c65.

2026-09-24: effective-capability milestone43388c8 committed/pushed. Complete Windows exec60009 and Linux exec87041 are running at this immutable implementation/test SHA; both already show failures, final reports pending. See P12_REMAINING_GATE_AUDIT.md for exact result paths, newly reproduced lane-selection defect and remaining safe-retry/backlog/fairness/stress gates. Narrow scheduler correction is isolated in detached D:/Projetos/Techridy/okto_nexus_scheduler_worktree, not yet integrated or committed. Do not change main implementation/tests before both full suites terminate.

Scheduler worktree update: selected Windows27 PASS84.96s; expanded blocked-lane production tests3 PASS11.93s Windows and3 PASS15.51s Linux. Seven stale surface51 pins corrected only in isolated checkout; selected9 PASS5.01s. Owned Python-peer cycle campaign: Windows12 measured+2 warmup cycles PASS,13 stable threads,243-248 handles,~178 KiB Python allocation growth; Linux campaign pending. These source/test/script changes remain isolated and uncommitted until main full suites finish. See that worktree plans/pr34-remediation/runtime_cycle_campaign.py and evidence/p12-owned-cycles-windows.json. No native model or general crash/performance gate claim.

Cycle campaign is now terminal on both platforms: Linux12 measured+2 warmups PASS,13 threads/13 FDs stable,~165 KiB Python allocation growth. Evidence and campaign script copied into main for preservation; scheduler SQL/test corrections remain isolated. P06_SCHEDULER_LANE_SELECTION.md records exact commands, fixture failures and scope. Only full Windows60009/Linux87041 suites remain live; do not restart them. Local installed uv tool is still okto-nexus0.1.10; final rebuild/reinstall0.2.0 remains pending.

Isolated P06 update: outbox count/byte/actor/recipient/workspace limits implemented with additive index migration058, not yet integrated. See P06_OUTBOX_BACKPRESSURE_WIP.md for REDs and fixture corrections. Expanded gates Windows90836/Linux80706 are live; previous63 PASS5 FAIL on each platform were mixed-checkout stdio children, now fixed in fixture environment. Agent-level normal-worker fairness has a new confirmed RED in test_runtime_scheduler_fairness.py -k one_agent; it remains uncorrected. Full main suites60009/87041 remain live. Only docs may change main until both terminate.

Windows full suite60009 terminal:2328 PASS8 FAIL119 SKIP1 ERROR,1945.37s. Manifest and analysis P12_SUITE_43388C8.md. Eight stale revision pins corrected only in scheduler worktree; startup-error targeted rerun1 PASS2.89s, root cause not proven. Linux full87041 is still live; main source freeze continues. Corrected backlog gates90836/80706 terminal:68 PASS166.66s Windows/68 PASS203.05s Linux. Agent scheduling initial37 PASS118.44s followed by genuine early-result/occupied-worker RED1 FAIL12.20s; actual in-flight agent fencing now implemented in isolated worktree, selected Windows42902/Linux99075 running. No new native model campaign.
