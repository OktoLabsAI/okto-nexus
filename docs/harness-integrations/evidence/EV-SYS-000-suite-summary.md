# EV-SYS-000 — SYS suite summary (SYS-01..10)

Captured 2026-09-20, 17:58–18:06 -03. One real `okto-nexus serve` subprocess, real ephemeral TCP
port, real `pi` 0.85.1 / real `codex` 0.144.6 / real `claude` 2.1.278 binaries, throughout — no
TestClient, no fakes, no mocks anywhere in this suite. Detailed evidence and raw captures are in
the per-case files below; this is the index and the headline finding.

## Headline finding (report, not fixed — see EV-SYS-002)

The `harness_open` surface (HTTP + MCP) has **no backend-selection parameter**. Opening a
`kind="pi"` session through it with zero external configuration sends real turns to pi's global
default provider, `local-mac` → `192.168.31.222` — a box this task explicitly forbids touching.
This suite avoided it entirely through external environment/PATH configuration of the ONE `serve`
subprocess it controls (never a source change, never `~/.pi/agent/settings.json`,
`~/.codex/config.toml`, or the operator's own shell/PATH) — full mechanism in EV-SYS-002. This is
a genuine composition-root gap worth fixing in a later phase (`_default_connector_factories` /
`HarnessSessionOpenBody`, both non-frozen), left unfixed here per the task's own instruction to
report rather than patch production code from inside a test-writing task.

## Verdicts

| Case | Verdict | Evidence file |
|---|---|---|
| SYS-01 (info reflects harness support) | **PASS** (honest F-02-precedent note: signal is `schema_version=29`, no dedicated field) | EV-SYS-002 |
| SYS-02 (all 4 connectors, one hub, simultaneously) | **PASS** | EV-SYS-002 |
| SYS-03 (routed via the EXISTING target grammar) | **FAILED as worded** — empirically falsified; direct session-id addressing works instead, demonstrated separately | EV-SYS-003 |
| SYS-04 (harness → hub durable record) | **PASS** for pi/codex/claude_code-stream; **N/A** for claude_code-attach (no harness→hub direction exists on that transport, by design) | EV-SYS-004-005-009 |
| SYS-05 (end-to-end no-polling, both directions, timestamps) | **PASS** on the externally-observable half (wire trace, machine-checked zero client-writes in every push window); in-process fan-out stated honestly as unobservable from outside, carried by EV-SYS-006/007's structural proof instead | EV-SYS-004-005-009 |
| SYS-06 (`SleepPollWaiter` not in path, structurally) | **PASS** — real transitive import-closure check + grep/call-site check | EV-SYS-006 |
| SYS-07 (durability: publish never gated by persist) | **PASS** — code ordering + real subscriber-crash exercise + real SQLite `BEGIN EXCLUSIVE` contention experiment against the live server | EV-SYS-007 |
| SYS-08 (isolation: one child dying doesn't take down the hub/siblings) | **PASS** (disclosed nuance: a killed child currently reaps to `ENDED`, not `ERRORED`) | EV-SYS-008 |
| SYS-09 (concurrency: no cross-talk) | **PASS** — three real harnesses, distinct prompts, fully concurrent, zero cross-talk | EV-SYS-004-005-009 |
| SYS-10 (clean shutdown, zero orphans) | **PASS** — targeted + broad-sweep `ps` checks, both clean | EV-SYS-010 |

## What could not be run, and why

Nothing in the SYS-01..10 list was skipped outright. SYS-03 was run and its literal claim
disproven (that is a result, not a gap). SYS-05's in-process-fan-out half has no external
observation point in this phase (disclosed, not glossed over — see EV-SYS-004-005-009). SYS-07's
"a write that actually FAILS past its busy-timeout" branch was exercised by code reading only, not
forced to fire empirically in the one real-contention experiment run (disclosed in EV-SYS-007,
not overclaimed).

## Safety notes

- `192.168.31.222` was never sent a request by this suite (verified: pi's `get_state` handshake
  probe is zero-inference/local-only, and every subsequent pi spawn's trace confirms `--provider
  zai` took effect before any turn was sent).
- The three pre-existing REAL interactive Claude Code sessions on this machine (pids 92180, 3523,
  87357 — genuine ongoing work) were never touched; the D7b attach substrate used a fresh,
  dedicated, throwaway `tmux`-spawned session (pid 60906) created and torn down entirely within
  this evidence run.
- No git write operations were performed. No frozen file (`domain/harness.py`, the
  `HarnessConnector`/`HarnessSubscriberRegistry` Protocols, or the four connector modules) was
  modified. No non-frozen production file was modified either — the composition-root gap above
  was worked around externally (PATH/env on one subprocess), not patched.
