# EV-INDEX — Phase 4 campaign consolidation

Captured: 2026-09-20. Commit under review: `b661538` (`feature/harness-integrations`).
Built by reading every file in `docs/harness-integrations/evidence/` directly — not from the
stage summaries handed to this task, which do not reconcile with the evidence (see "Deltas from
the stage summaries" below).

Legend: **PASSED** = committed evidence file with real captured output proves the case.
**FAILED** = committed evidence proves the case's literal claim does NOT hold (a real,
reproduced defect or a falsified claim — not a flake). **NOT-APPLICABLE** = a capability the
case exercises does not exist on this connector, by frozen design, with the reason stated.
**UNRUN** = the task's own definition is "no evidence file exists." This index extends that by
one case (INT-05/H-CX): an evidence file DOES exist, but it self-reports that the one piece of
proof INT actually requires — a real-binary capture — was not taken, only a capability-flag
assertion and a fake-based ordering test. Treating that as UNRUN rather than PASSED is the
stricter, evidence-rule-consistent reading; it is called out explicitly here so it is not
mistaken for a zero-evidence case.

Granularity: INT and RES are written `{H}`-per-case in the plan, so this index gives one row per
(case × harness) rather than collapsing harnesses together — collapsing hides exactly the rows
that differ by harness (e.g. RES-A2 passes for pi, fails for codex and claude-code stream).

H-PI = pi 0.85.1, H-CX = codex 0.144.6, H-CC = Claude Code stream-json (D7a),
H-CA = Claude Code cc-socks attach (D7b).

---

## INT — Integration suite (32 rows: 8 cases × 4 harnesses)

| Case ID | Status | Evidence file | Note |
|---|---|---|---|
| INT-01 (H-PI) | PASSED | EV-PI-INT-001-live-real-pi.md | Real binary, handshake 0.959s |
| INT-02 (H-PI) | PASSED | EV-PI-INT-001-live-real-pi.md | |
| INT-03 (H-PI) | PASSED | EV-PI-INT-001-live-real-pi.md | |
| INT-04 (H-PI) | PASSED | EV-PI-INT-001-live-real-pi.md | 12 push lines, 0 client writes, machine-checked |
| INT-05 (H-PI) | PASSED | EV-PI-INT-001-live-real-pi.md | Real tool call, NEXT_TURN_BOUNDARY confirmed live |
| INT-06 (H-PI) | PASSED | EV-PI-INT-001-live-real-pi.md | settle-before-ack confirmed live |
| INT-07 (H-PI) | PASSED | EV-PI-INT-001-live-real-pi.md | Both halves: no built-in resume (by design) + `extra_args` escape hatch proven; session_id cosmetic mismatch on reconnect disclosed |
| INT-08 (H-PI) | PASSED | EV-PI-INT-001-live-real-pi.md | Real SIGKILL, 10ms detection |
| INT-01 (H-CX) | PASSED | EV-CX-001-int-cases.md | Raw capture + `test_live_against_real_codex_lan_box` |
| INT-02 (H-CX) | PASSED | EV-CX-001-int-cases.md | |
| INT-03 (H-CX) | PASSED | EV-CX-001-int-cases.md | |
| INT-04 (H-CX) | PASSED | EV-CX-001-int-cases.md | `client_initiated=0`, machine-checked over 45.71s |
| INT-05 (H-CX) | **UNRUN** | EV-CX-001-int-cases.md | Evidence file self-labels "PARTIAL": capability flag + fake-ordering test only; live steer capture against the real binary explicitly NOT taken (disclosed gap, time-budget). INT requires real-binary proof — not met. |
| INT-06 (H-CX) | PASSED | EV-CX-001-int-cases.md | Caveat disclosed: interrupt fired pre-content-stream, not genuine mid-stream cancel |
| INT-07 (H-CX) | PASSED | EV-CX-001-int-cases.md | Verbatim `-32600 thread not found` on fresh process |
| INT-08 (H-CX) | PASSED | EV-CX-001-int-cases.md | 6 existing tests, all green |
| INT-01 (H-CC) | PASSED | EV-CC-003-int-wire-trace-and-lifecycle.md | |
| INT-02 (H-CC) | PASSED | EV-CC-003-int-wire-trace-and-lifecycle.md | |
| INT-03 (H-CC) | PASSED | EV-CC-003-int-wire-trace-and-lifecycle.md | |
| INT-04 (H-CC) | PASSED | EV-CC-003-int-wire-trace-and-lifecycle.md | 4-turn trace, 1 interrupt, zero stray client writes |
| INT-05 (H-CC) | PASSED | EV-CC-003-int-wire-trace-and-lifecycle.md | Real IMMEDIATE steer confirmed |
| INT-06 (H-CC) | PASSED | EV-CC-003-int-wire-trace-and-lifecycle.md | Minor finding disclosed: `end()` immediately after `interrupt()` with no intervening turn → real exit(1), 3/3 reproducible |
| INT-07 (H-CC) | PASSED | EV-CC-003-int-wire-trace-and-lifecycle.md | Stable session_id across turns proven; no process-restart resume exists at all (stated as genuine gap, not silently assumed) |
| INT-08 (H-CC) | PASSED | EV-CC-003-int-wire-trace-and-lifecycle.md | Incl. 2 new tests this session (unknown-verb) |
| INT-01 (H-CA) | PASSED | INT-01-02-08-claude-code-attach-real-session.md | Real live interactive session, dedicated disposable pid |
| INT-02 (H-CA) | PASSED | INT-01-02-08-claude-code-attach-real-session.md | Send-half proven via tmux capture-pane; receive-half N/A per capabilities. New finding: CC 2.1.278 now gates cross-session inbound behind an operator approval prompt — not in ADR D7b |
| INT-03 (H-CA) | NOT-APPLICABLE | INT-01-02-08-claude-code-attach-real-session.md | `send_only=True`, no inbound channel of any kind — nothing to trace fidelity against |
| INT-04 (H-CA) | NOT-APPLICABLE | INT-01-02-08-claude-code-attach-real-session.md | No read loop exists to poll with (trivially true, not tested) |
| INT-05 (H-CA) | NOT-APPLICABLE | INT-01-02-08-claude-code-attach-real-session.md | `steer_timing=None`; no steer verb on this transport |
| INT-06 (H-CA) | NOT-APPLICABLE | INT-01-02-08-claude-code-attach-real-session.md | No interrupt verb on this transport |
| INT-07 (H-CA) | NOT-APPLICABLE | INT-01-02-08-claude-code-attach-real-session.md | `observes_session_end=False`; connector never spawns anything to reconnect to |
| INT-08 (H-CA) | PASSED | INT-01-02-08-claude-code-attach-real-session.md | All 4 sub-cases incl. real abrupt child death (tmux kill) |

## RES — Resilience suite (40 rows: 10 cases × 4 connectors)

| Case ID | Status | Evidence file | Note |
|---|---|---|---|
| RES-A1 (H-CA) | PASSED | RES-claude-code-attach.md | Existing test cited |
| RES-A2 (H-CA) | **FAILED** | RES-claude-code-attach.md | Case demands each consumer receive the FULL stream. Measured: 5,260 trials, zero loss/hang/raise, but the deque **partitions** across concurrent consumers rather than broadcasting to both — the literal requirement does not hold. Evidence file itself calls this "a documented deviation from the broadcast framing." Not reachable via the current supervisor (send_only connectors are always drained synchronously by one caller) — same "latent, not fixed" framing as the H-CC/H-CX RES-A2 failures below. |
| RES-A3 (H-CA) | PASSED | RES-claude-code-attach.md | Structural: zero blocking primitives in the module |
| RES-A4 (H-CA) | PASSED | RES-claude-code-attach.md | 2 new tests |
| RES-B1 (H-CA) | NOT-APPLICABLE | RES-claude-code-attach.md | No reader loop exists (send-only, no inbound channel). Nearest analogue (malformed registry/key-file JSON, NUL-byte path) is tested and passes. |
| RES-B2 (H-CA) | NOT-APPLICABLE | RES-claude-code-attach.md | No reader thread exists |
| RES-B3 (H-CA) | PASSED | RES-claude-code-attach.md | Same structural check as RES-A3 |
| RES-C1 (H-CA) | PASSED | RES-claude-code-attach.md | Justified against EV-CC-001's captured wire bytes |
| RES-C2 (H-CA) | NOT-APPLICABLE | RES-claude-code-attach.md | No interrupt/abort verb exists on this transport |
| RES-C3 (H-CA) | PASSED | RES-claude-code-attach.md | 3 fakes that genuinely reject/drop |
| RES-A1 (H-CC) | PASSED | EV-CC-004-res-class-a-shutdown-and-fanout.md | Existing test |
| RES-A2 (H-CC) | **FAILED — real defect** | EV-CC-004-res-class-a-shutdown-and-fanout.md | Single shared `queue.Queue`; two concurrent consumers split (not duplicate) a 7-event stream, 3/3 runs. Frozen module, reported not fixed. Reachability audited: latent — `harness_supervisor.py` only ever starts one pump thread per connector, so not reachable through today's own wiring, but a real, unguarded port-contract violation. |
| RES-A3 (H-CC) | PASSED | EV-CC-004-res-class-a-shutdown-and-fanout.md | Structural, with 2 disclosed narrow exceptions (justified, not hazards) |
| RES-A4 (H-CC) | **FAILED — real defect** | EV-CC-004-res-class-a-shutdown-and-fanout.md | `start()`'s `OSError` path never sets `_closed_event`; `events()` loops forever after a failed start. 100%-reproducible, 3/3 runs. Frozen module, reported not fixed. Reachability audited: latent (supervisor never calls `events()` after a `start()` failure), but a real defect at the connector's own API boundary — the exact pattern the sibling `pi.py`'s "C3 fix" exists to prevent. |
| RES-B1 (H-CC) | PASSED | EV-CC-005-res-class-b-and-c.md | Existing test (shape-drifted stream_event) |
| RES-B2 (H-CC) | PASSED | EV-CC-005-res-class-b-and-c.md | Structural (single `try/finally`) + 2 existing tests |
| RES-B3 (H-CC) | PASSED | EV-CC-005-res-class-b-and-c.md | 3 bounded calls, ~20s worst case bound |
| RES-C1 (H-CC) | PASSED | EV-CC-005-res-class-b-and-c.md | New: first raw wire capture for this connector, field-by-field justified. One divergence disclosed: fake never reproduces the real binary's post-interrupt-end exit(1); sits unasserted inside a currently-green test |
| RES-C2 (H-CC) | PASSED | EV-CC-005-res-class-b-and-c.md | Fake's ack-then-result ordering matches the real capture |
| RES-C3 (H-CC) | PASSED | EV-CC-005-res-class-b-and-c.md | 4 genuine failure-capable fake scenarios |
| RES-A1 (H-CX) | PASSED | EV-CX-002-res-cases.md | 2 existing tests |
| RES-A2 (H-CX) | **FAILED — real defect** | EV-CX-002-res-cases.md | New test FAILS in the suite (`total=5, A=5, B=0`), 3/3 isolated re-runs, identical every time (deterministic starvation, not a coin-flip race). Same one-shared-queue defect class as H-CC. Frozen module, reported not fixed. |
| RES-A3 (H-CX) | PASSED | EV-CX-002-res-cases.md | New structural source-parsing test |
| RES-A4 (H-CX) | **FAILED — real defect** | EV-CX-002-res-cases.md | New test FAILS in the suite. `transport.close()` sets the transport's own private flag, never the connector's `_closed_event`; `events()` never terminates after a failed `start()` with no explicit `close()`. 3/3 isolated re-runs, deterministic. Frozen module, reported not fixed. |
| RES-B1 (H-CX) | PASSED | EV-CX-002-res-cases.md | Both case-specified shapes (empty method, array params) covered by existing tests |
| RES-B2 (H-CX) | PASSED | EV-CX-002-res-cases.md | New, truly-concurrent test (child-death path) |
| RES-B3 (H-CX) | PASSED | EV-CX-002-res-cases.md | Same structural test as RES-A3 |
| RES-C1 (H-CX) | PASSED | EV-CX-002-res-cases.md | Justified against 3 new raw captures (turn, interrupt, thread-not-found) |
| RES-C2 (H-CX) | **FAILED — divergence found** | EV-CX-002-res-cases.md | Case requires the fake to emit the REAL interrupt ordering. Real capture: ack + `turn/completed(interrupted)` together. The fake's handler acks and then emits **nothing further** — it never completes the interrupted turn at all, so no test can currently observe correct-or-wrong post-interrupt ordering. This is an omission, not an inversion (narrower than Pi's original C1), but the case's literal requirement ("emits the REAL ordering") is not met — the fake doesn't emit that state transition at all. Disclosed, not fixed (out of this pass's time budget per the evidence file). |
| RES-C3 (H-CX) | PASSED | EV-CX-002-res-cases.md | 3 existing fail-modes + 1 new (rejected initialize) |
| RES-A1 (H-PI) | PASSED | EV-PI-RES-001-resilience-cases.md | New sequential-recall test |
| RES-A2 (H-PI) | PASSED | EV-PI-RES-001-resilience-cases.md | Pre-existing fan-out fix (C2), re-run and confirmed |
| RES-A3 (H-PI) | **FAILED — defect confirmed** | EV-PI-RES-001-resilience-cases.md | `self._proc.wait()` at `pi.py:371`, no timeout, in `_read_stdout`'s `finally`. Reachable via a real exception mid-loop (see RES-B1) against a healthy child. Explicitly **supersedes EV-REV-003's earlier downgrade** of this same line ("not a genuine hang risk") — that downgrade assumed the loop could only exit via clean EOF; it can also exit via an uncaught exception, which lands on the same unbounded wait. |
| RES-A4 (H-PI) | PASSED | EV-PI-RES-001-resilience-cases.md | Pre-existing C3 fix, re-run and confirmed |
| RES-B1 (H-PI) | **FAILED — CRITICAL defect confirmed** | EV-PI-RES-001-resilience-cases.md | A syntactically-valid, deeply-nested JSON array (`RecursionError`, not `json.JSONDecodeError`) escapes the reader loop's only guard, lands on the unbounded `proc.wait()` above, and wedges every current and future `events()` consumer forever with no error surfaced anywhere. 30s continuous observation: never self-recovers; `is_alive()` stays `True` throughout, actively misleading. Frozen module, reported not fixed. |
| RES-B2 (H-PI) | PASSED (with a stated gap) | EV-PI-RES-001-resilience-cases.md | Passes for the exit path it actually tests: two concurrent consumers both observe shutdown on a guarded child-death exit (new test, cited). It does NOT independently prove the property for the RES-B1 exit path (uncaught-exception-mid-loop), where by construction no shutdown signal is ever sent — the evidence file states this plainly as a corollary of RES-B1, not as a fourth separate defect. Counted as PASSED here (not FAILED) so the RES-A3/B1/B3 root cause is not booked four times in the totals; the gap is real and is fully captured under RES-B1/A3/B3 below. |
| RES-B3 (H-PI) | **FAILED — defect confirmed** | EV-PI-RES-001-resilience-cases.md | Same line 371 as RES-A3 |
| RES-C1 (H-PI) | PASSED | EV-PI-RES-001-resilience-cases.md | Cited (EV-REV-003) + independently reconfirmed live this session |
| RES-C2 (H-PI) | PASSED | EV-PI-RES-001-resilience-cases.md | Cited (EV-REV-003, the C1 fix) |
| RES-C3 (H-PI) | PASSED | EV-PI-RES-001-resilience-cases.md | 5 existing fail modes + 1 new (RES-B1's own trigger) |

## SYS — System suite (10 rows)

| Case ID | Status | Evidence file | Note |
|---|---|---|---|
| SYS-01 | PASSED | EV-SYS-002-boot-and-registration.md | Honest note carried from EV-SYS-001 F-02: signal is `schema_version=29`, no dedicated `"harness"` field, matching the repo's own `/info` convention |
| SYS-02 | PASSED | EV-SYS-002-boot-and-registration.md | All 4 kind/substrate combos on one real hub, D3 registration confirmed for all 4 |
| SYS-03 | **FAILED — falsified as worded** | EV-SYS-003-target-grammar-gap.md | Plan claims "a message routed via the existing target grammar reaches each harness." Empirically false: `message_create` reports success (`delivered_count:1`) but the pi child's own wire trace gained zero bytes. Static grep confirms zero call sites from the target-grammar resolver into `HarnessSupervisor.send`. A different, working mechanism exists (direct `session_id` addressing via `POST /harness/sessions/{id}/send`) but that is not what the case asked for. This also undercuts UAT-05 (see below). |
| SYS-04 | PASSED | EV-SYS-004-005-009-multiharness-round-trip.md | Durable, replayable records with correct content for pi/codex/claude_code-stream. N/A for cc-socks attach by design (no harness→hub direction on that transport) — hub→harness half proven instead |
| SYS-05 | PASSED | EV-SYS-004-005-009-multiharness-round-trip.md | Externally-observable half (wire trace, all 3 full-duplex harnesses, zero client-initiated writes in every push window) machine-checked. In-process fan-out is stated honestly as unobservable from outside this phase (no external push surface ships yet) and is instead carried by the SYS-06/SYS-07 structural proofs |
| SYS-06 | PASSED | EV-SYS-006-no-sleeppollwaiter-structural.md | Real transitive import-closure over 90 modules (0 hits) + targeted grep, both structural not timing |
| SYS-07 | PASSED | EV-SYS-007-durability.md | Code-ordering (publish before persist, unconditional) + real subscriber-crash exercise + real `BEGIN EXCLUSIVE` DB-lock contention against the live server. Disclosed: the "a write that ACTUALLY fails past its busy-timeout" branch was not forced to fire empirically, only verified by code reading |
| SYS-08 | PASSED | EV-SYS-008-isolation.md | Real SIGKILL to pi's child; hub stayed up, both siblings completed fresh real turns afterward. Disclosed nuance: the killed session's terminal status reads `ENDED`, not `ERRORED` — an unexpected crash and a graceful close currently look identical from the outside |
| SYS-09 | PASSED | EV-SYS-004-005-009-multiharness-round-trip.md | 3 harnesses, distinct prompts, fully concurrent, zero cross-talk in either direction |
| SYS-10 | PASSED | EV-SYS-010-clean-shutdown.md | Targeted (12 original descendant pids) + broad `ps` sweep, both clean after group SIGTERM |

## REG — Regression suite (7 rows)

| Case ID | Status | Evidence file | Note |
|---|---|---|---|
| REG-01 | **FAILED — as worded** | this file + EV-CX-002-res-cases.md | Real, reproduced run this session: **2 failed, 1822 passed, 4 skipped** (160.80s). Baseline arithmetic, accounted for: EV-SYS-001's own independently-reproduced reference was 1810 passed/4 skipped; `git diff` shows exactly 14 new `def test_` functions added across the four connector test files this Phase-4 campaign touched (4 + 2 + 5 + 3); 1810 + 14 − 2 (the two that fail) = **1822**, matching exactly — the delta is fully explained, nothing unaccounted for. The plan's bar is "zero pre-existing failures." The 2 failures are not flakes or regressions in unrelated code — they are two tests the codex-connector agent deliberately committed *failing*, each asserting a specific real defect (RES-A2, RES-A4 above) in the FROZEN `codex.py`. Read charitably this is "0 accidental regressions, 2 intentional defect-witness failures"; read against the plan's literal "zero...failures" text, the gate is red. Also flagged: **inconsistent convention across the three connector-owning agents** — codex committed failing assertions; claude-code-stream explicitly declined to (its own EV-CC-004 states why) and used scratchpad repro scripts instead; pi wrote a test that *passes* while proving the same class of defect via instrumentation. All three are legitimate under "do not fix frozen code," but the resulting suite-level number is genuinely ambiguous as a result, not a reporting error. |
| REG-02 | PASSED | this file | `tests/test_http_parity.py` — 5 passed together with REG-03 |
| REG-03 | PASSED | this file | `tests/test_import_boundary.py` — passed |
| REG-04 | PASSED | this file (full-suite run) | `tests/test_serve_lock.py` (5 tests) ran clean inside the full 1822-passed run; no dedicated evidence file exists for it, confirmed by direct collection |
| REG-05 | PASSED | this file (full-suite run) | Replay suite (`test_replay_cli.py`, `test_replay_domain.py`, `test_replay_harness.py`, `test_replay_http.py`, `test_replay_marker.py`) ran clean inside the full run; no dedicated evidence file exists, confirmed by direct collection |
| REG-06 | PASSED | this file | `uv run ruff check .` → All checks passed |
| REG-07 | PASSED | EV-SYS-001-phase35-real-socket.md | Real SQLite file, 3 sequential `MigrationRunner.apply()` calls (empty→29, idempotent-same-factory, idempotent-fresh-factory) |

## UAT — User Acceptance suite (7 rows)

| Case ID | Status | Evidence file | Note |
|---|---|---|---|
| UAT-01 | PASSED | EV-UAT-01-02-03-two-turn-conversations.md | Real pi, real 2-turn conversation, same session, public HTTP surface only |
| UAT-02 | PASSED | EV-UAT-01-02-03-two-turn-conversations.md | Real codex, LAN box. First attempt failed on a scratch-config setup bug (disclosed, root-caused, not a connector defect), re-run passed |
| UAT-03 | PASSED | EV-UAT-01-02-03-two-turn-conversations.md | Real claude, stable session_id across 2 turns |
| UAT-04 | PASSED | EV-UAT-04-cc-socks-inject-real-session.md | Real injection into a dedicated, disposable interactive session; end-to-end proof after approving CC's own approval gate |
| UAT-05 | **FAILED — as worded** | EV-UAT-05-target-grammar-asymmetry.md | Case asks whether an operator addresses a harness THROUGH the target grammar (input direction). Empirically falsified, independently reproducing SYS-03. The OUTPUT direction (harness activity delivered via the grammar through `notify_target`) genuinely works — a real, useful finding — but is not what the case asked. Net: "first-class agent" holds for output, not for input. |
| UAT-06 | PASSED | EV-UAT-06-graceful-degradation.md | Simulated real cc-socks registry breakage: fails in 13ms with an actionable error; primary D7a path unaffected on the same hub immediately after |
| UAT-07 | **FAILED — as worded** | EV-UAT-07-documentation-gap.md | Zero operator-facing documentation exists anywhere under `docs/`, `README.md`, or `CHANGELOG.md` for this feature. The fair "kinds endpoint + live MCP tool schema" version gets further but surfaces a materially FALSE claim in shipped tool text (`_P_HARNESS_AGENT_ID` tells operators to use the target grammar — the exact claim SYS-03/UAT-05 falsified) and omits the backend-selection safety gap (below) entirely. |

---

## Totals

| Suite | PASSED | FAILED | NOT-APPLICABLE | UNRUN | Total |
|---|---|---|---|---|---|
| INT | 26 | 0 | 5 | 1 | 32 |
| RES | 28 | 9 | 3 | 0 | 40 |
| SYS | 9 | 1 | 0 | 0 | 10 |
| REG | 6 | 1 | 0 | 0 | 7 |
| UAT | 5 | 2 | 0 | 0 | 7 |
| **Total** | **74** | **13** | **8** | **1** | **96** |

The RES FAILED count (9) is not 9 independent defects: pi's 3 FAILED rows (RES-A3, RES-B1,
RES-B3) are three views of ONE root cause (`pi.py:371`'s unbounded `proc.wait()`, reached via the
`RecursionError` gap), stated as one defect in the defect register below, not three. The other 6
FAILED rows (H-CC RES-A2/A4, H-CX RES-A2/A4/C2, H-CA RES-A2) are five genuinely distinct findings.

No case in this campaign has zero evidence — the UNRUN count (1) is INT-05/H-CX, which has an
evidence file that explicitly discloses its own real-binary proof is missing, not a case nobody
looked at. Every FAILED row above is a reproduced defect or an empirically falsified claim with
committed real output, not a guess.

## Deltas from the stage summaries handed to this task

The task's own stage summaries (INT 15P/3F, 14P/3F, 16P/2F, 12P/0F; SYS 7P/1F; UAT 5P/2F) do not
reconcile against the evidence files read directly for this index. Stated as fact, not theory:

- Summed, the four INT stage numbers give 57 passed / 8 failed across 65 rows — neither the row
  count (65) nor the failed count (8, where this index finds 0 FAILED in INT; every INT defect
  this index found lives in RES) matches this index's INT table (32 rows, 26P/5NA/1 UNRUN, 0
  FAILED). The two suites cannot be reconciled from the summary numbers alone with the information
  available in this task; this index does not guess why and instead reports its own count, built
  from the evidence files directly, as the instruction requires.
- SYS "7P/1F" undercounts against this index's 10-row SYS table (9 PASSED / 1 FAILED, SYS-03) —
  SYS-04 and SYS-05 both have real, dedicated evidence files this index credits as PASSED that the
  7-count total does not appear to include.
- UAT "5P/2F" matches this index's UAT verdicts exactly (5 PASSED; UAT-05 and UAT-07 FAILED).

This index is built from the evidence files, not the summaries, per the task's own instruction.

## Process nit (not a status, worth recording)

The plan's own exit criteria say a struck case "carries a written justification in this file"
(`plans/harness-integrations/01-test-plan.md`). H-CA's five struck INT cases (INT-03..07) and its
three struck RES cases (RES-B1, RES-B2, RES-C2) carry their justification only in the evidence
files, not in the plan itself — the plan was never amended to record the strikes. Not scored as a
case status above; flagged here because the exit criteria technically require it.
