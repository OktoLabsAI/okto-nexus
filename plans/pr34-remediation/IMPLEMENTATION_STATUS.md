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

P01 containment tasks implemented, phase IN_PROGRESS pending its full gate; P02 contracts IMPLEMENTED; P03–P08 IN_PROGRESS; P09–P12 NOT_STARTED. No phase VERIFIED. No completion claims from historical PR counts. User explicitly approved the installed local Codex and subsequently Claude for real tests. Versions observed: codex-cli 0.155.1; Claude Code 2.1.277. Keep native tests in temporary project directories, preserve security controls, never pass the Nexus operator key. Attach requires a dedicated test session; never select a personal session. Pi native tests remain NOT_RUN by user decision.

Current: P03 approved endpoint/profile persistence and canonical presence; see P03_ENDPOINTS.md. Next dependency: scoped runtime grants and lifecycle verification. Remaining seven red regressions belong to later phases. No legacy producer may be switched to a private, unintegrated dispatcher. Update this file and `05_BACKLOG.json` per unit.

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
