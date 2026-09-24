# Remaining gate audit at 43388c8

2026-09-24. This is an execution audit, not a replacement plan. All original
P00–P12 requirements remain in scope. Final gate NOT PASSED.

## Full regression in progress

Main implementation/tests frozen at43388c8 while complete Windows and Linux suites
run. Only documentation/audit scripts may change in the main checkout meanwhile.
Native campaigns and browser opt-ins are disabled for these generic suites; they
have separate explicit evidence. No skipped test is promoted to PASS.

- Windows exec60009; raw XML destination
  `C:/Users/jpamb/AppData/Local/Temp/okto-suite-43388c8-ig2ypr3u/results.xml`.
- Linux exec87041; raw XML destination
  `/tmp/okto-suite-43388c8-linux-jwz04l1v/results.xml`.
- Command for each: `<platform Python> -m pytest -q --tb=short --junitxml=<destination>`.
  Wrapper sets OKTO_NEXUS_NATIVE_CAMPAIGN empty, CODEX_LIVE/CLAUDE_LIVE/UI_CAMPAIGN0.
- Runs overlap on the same physical host. Do not use their elapsed times as
  comparable performance benchmarks. Preserve any failure before focused reruns.
- Both runs already show failures; final counts/tracebacks remain pending.

## Confirmed additional dispatcher defect

`audit_dispatch_fairness.py` creates approved synthetic Pi sessions for two agents
through production HTTP. With the dispatcher quiesced, authenticated MCP messages
enqueue two deliveries for agentA and one for agentB. `pending(limit=2)` returns
bothA rows. `scan_once` subsequently deduplicates their endpoint, wasting a worker
slot instead of admitting B in the same pass. This is a selection-stage defect;
no wall-clock starvation/pressure measurement is claimed.

Evidence: `evidence/p12-dispatch-fairness-red.json`, FAIL at43388c8.
The same shape affects repeated pending close commands with distinct idempotency
keys: the control query also truncates before per-lane selection.

Development isolated at `D:/Projetos/Techridy/okto_nexus_scheduler_worktree`, detached
43388c8, no commits there. Behavioral tests initially had a fixture mistake:
quiescing admission also denied close. Pausing only dispatcher scans preserved
authorization. A second fixture issue used the default same close idempotency key;
distinct keys now reproduce two pending commands. Corrected RED:2 FAIL7.48s.
The fix selects the oldest pending row per endpoint/lane before LIMIT. Selected Windows gate (scheduler fairness, runtime commands, runtime outbox):
27 PASS84.96s. Additional blocked-call integration is running on Windows/Linux. Main remains unchanged until full suites finish.
This narrow fix does not by itself complete aggregate fairness/per-agent quotas.

## Open implementation/verification dependencies

| Requirement | Current evidence and remaining work |
|---|---|
| T-ENDP-05, T-DISP-11 | `RuntimeDispatcher` currently handles proven-not-sent as REJECTED; repository dispatch selects only PENDING. RETRY_WAIT exists in the schema but no scheduled transport backoff/fallback implementation was found. Reproduce approved equivalent-endpoint safe fallback; implement bounded retry scheduling preserving operation identity/attempt evidence. Never replay an uncertain write. |
| T-DISP-09 | Lane truncation defect above. Worker pools are globally bounded, but agent-level scheduler fairness still needs adversarial multi-endpoint verification. Admission root quotas are not a substitute for active worker fairness. |
| T-DISP-10 | `SqliteRuntimeCommandRepo.enqueue` has count/byte/actor/recipient/workspace bounds. `SqliteRuntimeOutboxRepo.enqueue` has no equivalent pending-byte/count bound; causal rate limits do not bound accumulated backlog. Add logical-delivery-safe backpressure and test admission/recovery. |
| T-E2E-04/05 | Repeated leak/crash-pressure sample and same-configuration before/after percentiles remain NOT_RUN. Existing bounded-worker/crash fixtures are useful partial evidence, not this campaign. |
| T-E2E-01/02 | Native Pi and dedicated attach remain NOT_RUN by user/configuration limits. Do not claim four-native-connector qualification from Codex/Claude evidence. |
| T-E2E-03 | Preserve/classify full native frame traces without credentials or private content; show no nominal status polling. Existing event-driven implementation alone is not a new trace measurement. |
| Matrix bookkeeping | 129 rows:17 PASS,112 NOT_RUN before this audit. Many historical selections cover parts of those rows. Map exact stimuli/acceptance to test nodes and executed SHA before promoting any row; partial coverage must remain explicit. |
| Final delivery | Full-suite corrections, remaining gates, immutable-SHA acceptance evidence, build/reinstall0.2.0, final finding map and readiness report. No merge. |

Backup/restore and store-wide writer contract were implemented and tested in
2785c65/c27223b; effective capabilities in43388c8. Do not repeat their historical
pending labels as current implementation gaps. Conversely, selected green suites
do not establish that the remaining rows are satisfied.
