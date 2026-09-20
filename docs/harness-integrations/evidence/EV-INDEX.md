# EV-INDEX — corrected for Phase 5 (`c3a6b42`)

Captured: 2026-09-20. Commit under review: `c3a6b42` (`feature/harness-integrations`), the tip of
the Phase 5 "close the Phase 4 failures" pass. This supersedes the Phase 4 index (preserved at
`b661538`/`e4b2fe7`, git-history-only now) which was STALE at HEAD: it predates the Phase 5 commit
that closed 13 of its FAILED rows and its 1 UNRUN row.

This index was built by (1) reading every changed file in the `c3a6b42` diff against `e4b2fe7`,
(2) reading the new/updated evidence files, and (3) INDEPENDENTLY RE-TESTING every one of the 14
previously-failing cases myself — not by trusting the six agents' reports. Three findings below
come from my own live reproduction, not from the committed evidence files:

- **RES-B1 (H-PI), the critical case** — reproduced live via a route the new unit test does NOT
  take: writing a 60,000-deep balanced JSON array directly to the real `pi` child's stdin pipe
  (not through `_PiTransport.request()`). Result: `RecursionError` surfaced as a `line_error`
  event, `is_alive()` stayed `True` throughout, and a genuine subsequent push event
  (`{"type": "push", "kind": "queue_update"}`) was delivered 1 second later. Confirms the reader
  thread survives and keeps delivering. No unbounded `self._proc.wait()` remains anywhere in
  `pi.py` (`grep -n "\.wait("` — every call site now carries a `timeout=`).
- **SYS-03/UAT-05** — the committed evidence (`EV-SYS-003-FOLLOWUP-target-grammar-fix.md`) only
  live-reproduces the `direct` strategy against a real hub/real pi child (event count 7→11). The
  task explicitly requires testing `direct` AND at least one of `capability`/`role`/`tag`; that
  second live test was missing. I ran it myself: real `okto-nexus serve` (port 8392), a real `pi`
  child (backend `zai/glm-5.3`), a second agent identity (`sys03role_probe`) sending
  `message_create` with `{"strategy": "role", "role": "reviewer"}` — event count went 0 → 12, with
  real `turn_started`/`output_delta`/`turn_completed` events, confirming the fix is not
  `direct`-only.
- **EV-OPS-001 (orphaned harness children on unclean server exit)** — NOT touched by the Phase 5
  diff (`git diff --stat e4b2fe7..HEAD` has zero hits for `serve`/`signal`/`main`, and no new/
  changed evidence file exists for it). I tested it directly anyway, since the task asked for a
  real result either way: real `serve`, real live `pi` session (PID 9458, PPID = the serve
  process's PID 9205), then `kill -9` on the serve process. Result THIS run: no orphan — PID 9458
  was gone within 2s, not reparented to `launchd`. This differs from EV-OPS-001's original finding
  (two `pi --mode rpc` children survived 1.5h, PPID=1), but that finding was against a PATH-shim
  wrapper (`python3 .../bin/pi`) built because `harness_open` lacked backend selection at the
  time — the shim no longer exists now that backend selection landed. My result is consistent with
  "the real `pi` binary notices its stdin pipe break (EOF) when the parent dies and exits itself,"
  which is incidental self-cleanup, NOT a deliberate reap by `okto-nexus serve`. Nothing in the
  code guarantees this (no SIGCHLD/atexit/process-group-kill logic was added), so a differently-
  timed kill (e.g., mid-turn, mid-write) or a future harness binary that doesn't watch stdin could
  still orphan. **Scored NOT-APPLICABLE-TO-THIS-RUN below, not PASSED** — see SYS-10 row.

Legend unchanged from Phase 4: **PASSED** = committed evidence (or, where noted, my own live
reproduction this session) proves the case. **FAILED** = proven not to hold. **NOT-APPLICABLE** =
capability doesn't exist on this connector, by design, reason stated. **UNRUN** = no evidence
file exists.

H-PI = pi 0.85.1, H-CX = codex 0.144.6, H-CC = Claude Code stream-json (D7a),
H-CA = Claude Code cc-socks attach (D7b).

---

## Rows changed since Phase 4 (the 14 originally-failing cases)

| Case ID | Phase 4 status | Phase 5 status | Evidence | Note |
|---|---|---|---|---|
| INT-05 (H-CX) | UNRUN | **PASSED** | EV-CX-001-int-cases.md + EV-CX-001-raw_capture_steer.jsonl | Real live steer capture against the real codex binary now taken; steer landed genuinely mid-stream (t=11.72s into a counting turn), full re-ack→item/completed(steered)→reasoning→completed ordering captured |
| RES-A2 (H-CC) | FAILED — real defect | **PASSED** | EV-CC-004-res-class-a-shutdown-and-fanout.md | Per-consumer subscriber queues + `_event_history` backlog replace the single shared queue (mirrors pi's earlier C2 fix); code read confirms broadcast, not partition; covered by suite |
| RES-A4 (H-CC) | FAILED — real defect | **PASSED** | EV-CC-004-res-class-a-shutdown-and-fanout.md | `start()`'s `OSError`/thread-start-failure paths now set `_closed_event` unconditionally; `events()` terminates |
| RES-A2 (H-CX) | FAILED — real defect | **PASSED** | EV-CX-002-res-cases.md | Same shared-queue→per-consumer fan-out fix ported to codex.py; new test passes in the suite |
| RES-A4 (H-CX) | FAILED — real defect | **PASSED** | EV-CX-002-res-cases.md | Same `_closed_event` fix ported to codex.py |
| RES-C2 (H-CX) | FAILED — divergence | **PASSED** | EV-CX-002-res-cases.md | Fake's interrupt handler now emits `turn/completed(status="interrupted")`, matching the real capture's ack+complete ordering |
| RES-A3 (H-PI) | FAILED — defect confirmed | **PASSED** | pi.py `_wait_for_exit_bounded` + my own live repro (see above) | Every `proc.wait()` call site now bounded (`timeout=`), escalates SIGTERM→SIGKILL like `close()` |
| RES-B1 (H-PI) | FAILED — CRITICAL | **PASSED** | pi.py `_process_line`'s broad `except Exception` backstop + my own live repro (see above) | Deeply-nested-JSON RecursionError now caught by a second, broader except clause (`on_line_processing_error`), reader loop continues; confirmed live via raw stdin injection, a route the new unit test does not take |
| RES-B3 (H-PI) | FAILED — defect confirmed | **PASSED** | Same fix as RES-A3 (same line) | |
| SYS-03 | FAILED — falsified as worded | **PASSED** | EV-SYS-003-FOLLOWUP-target-grammar-fix.md (direct, live) + my own live repro (role, live) | New `InboxDeliveryNotifier` port + `HarnessSupervisor._on_inbox_delivery` forwards `message_create` deliveries to a live harness session's connector via the existing `send()`; verified for TWO strategies against a real hub/real pi child, not just `direct` |
| UAT-05 | FAILED — as worded | **PASSED** | Same fix as SYS-03 | Same forward mechanism closes the input-direction gap UAT-05 found |
| UAT-07 | FAILED — as worded | **PASSED** | docs/harness-integrations/operator-guide.md (397 lines, new) | Real operator-facing doc now exists; `_P_HARNESS_AGENT_ID`'s docstring rewritten to state the true, qualified post-fix behavior instead of the pre-fix false claim; doc points to EV-INDEX.md for proof rather than asserting unverified claims |
| REG-01 | FAILED — as worded | **PASSED** | This file's own full-suite run | `timeout 900 uv run python -m pytest -q` → **1857 passed, 4 skipped, 0 failed**, reproduced by me this session, matching the task's own reference number exactly |
| RES-A2 (H-CA) | FAILED — measured partition | **STILL FAILED — NOT TOUCHED** | RES-claude-code-attach.md (unchanged) | `claude_code_attach.py` (cc-socks) was NOT modified by the Phase 5 diff (`git diff --stat e4b2fe7..HEAD` has zero hits for this file). The deque-partition defect is exactly as Phase 4 left it. Same "latent, not reachable via the current supervisor" caveat as before still applies, but this is NOT one of the 13 the task's six agents actually closed — it was left open and Phase 5's own commit message ("close the Phase 4 failures") overstates this by omission. |

**Correction to the task's premise:** the task states "Six agents just reported closing 14
failures." Verified count: **13 of the 14** are genuinely closed (with the two caveats above: the
SYS-03/UAT-05 fix's live proof needed a second strategy test, which I supplied; EV-OPS-001 is a
15th, separately-tracked open item, not one of the 14, and was never claimed fixed). RES-A2 (H-CA)
— the deque-partition defect in Claude Code's cc-socks attach connector — remains open. This is a
real, checkable gap in the "14 closed" claim, not a rounding issue.

---

## Everything else (unchanged from Phase 4, still holds at `c3a6b42`)

All PASSED/NOT-APPLICABLE rows not listed above are carried forward unchanged; Phase 5 touched
only the connectors/files listed in its own diffstat (`claude_code_stream.py`, `codex.py`,
`pi.py`, `harness_supervisor.py`, `ports.py`, `messages.py`, `inbox_notifier.py`, the MCP
`harness.py`/`messages.py` tool composition roots, `routes.py`, `surface_metrics.py`, plus tests
and docs) and nothing else in the application regressed (full suite: 1857 passed, 4 skipped,
0 failed — see Totals). The full Phase 4 tables (INT 32 rows, RES 40 rows, SYS 10 rows, REG 7
rows, UAT 7 rows) are reproduced below with the 13 corrected rows folded in and re-totaled.

### INT — Integration suite (32 rows)

Unchanged from Phase 4 except INT-05 (H-CX), corrected above. 26 PASSED, 5 NOT-APPLICABLE (all
H-CA structural non-capabilities), **1 → now PASSED** (INT-05/H-CX). **New total: 27 PASSED, 5
NOT-APPLICABLE, 0 UNRUN.**

### RES — Resilience suite (40 rows)

Phase 4: 28 PASSED, 9 FAILED, 3 NOT-APPLICABLE. Phase 5 fixed 8 of the 9 FAILED rows (RES-A2/A4
H-CC, RES-A2/A4/C2 H-CX, RES-A3/B1/B3 H-PI — the last three being one root cause, counted once in
the defect register). **RES-A2 (H-CA) remains FAILED — not touched.** **New total: 36 PASSED, 1
FAILED (RES-A2/H-CA), 3 NOT-APPLICABLE.**

### SYS — System suite (10 rows)

Phase 4: 9 PASSED, 1 FAILED (SYS-03). Phase 5 fixed SYS-03, verified for two target-grammar
strategies (direct + role), not just the one the committed evidence covered. **New total: 10
PASSED, 0 FAILED.**

Separately tracked, NOT one of the 10 plan rows: **EV-OPS-001** (orphaned children on unclean
server exit) remains genuinely open — no code change addresses it, and my own live retest (SIGKILL
to a live server with a live pi session) did not reproduce THIS run's orphan, but nothing
guarantees it can't recur (see note at top of this file). SYS-10 itself still only proves the
explicit-close teardown path, exactly as Phase 4 disclosed; it was never split into two cases as
EV-OPS-001 recommended.

### REG — Regression suite (7 rows)

Phase 4: 6 PASSED, 1 FAILED (REG-01, "2 intentional defect-witness failures"). Phase 5's fixes
also removed the two failing defect-witness tests' failure condition (the defects themselves are
fixed, so the tests that asserted them now pass instead of fail). **New total: 7 PASSED, 0
FAILED.** Reproduced directly this session:

```
$ timeout 900 uv run python -m pytest -q
1857 passed, 4 skipped, 2 warnings in 155.12s (0:02:35)
$ timeout 200 uv run python -m pytest -q tests/test_http_parity.py tests/test_import_boundary.py
5 passed in 0.68s
$ uv run ruff check .
All checks passed!
```

This EXACTLY matches the task's own reference point ("1857 passed, 4 skipped, 0 failed at
c3a6b42"). One pre-existing warning is a `PytestUnhandledThreadExceptionWarning` from
`test_res_b2_reader_exit_signals_shutdown_even_if_on_child_exit_itself_raises` — an intentional
test of `pi.py`'s own exception-in-callback backstop, not a failure; the warning is the test
deliberately triggering the exact condition it's proving is survived.

### UAT — User Acceptance suite (7 rows)

Phase 4: 5 PASSED, 2 FAILED (UAT-05, UAT-07). Phase 5 fixed both. **New total: 7 PASSED, 0
FAILED.** UAT-07 spot-checked directly (see "Docs" section of the verdict below) — the guide is
usable, not narrated, and does not claim behavior that doesn't exist.

---

## Totals (c3a6b42, corrected)

| Suite | PASSED | FAILED | NOT-APPLICABLE | UNRUN | Total |
|---|---|---|---|---|---|
| INT | 27 | 0 | 5 | 0 | 32 |
| RES | 36 | 1 | 3 | 0 | 40 |
| SYS | 10 | 0 | 0 | 0 | 10 |
| REG | 7 | 0 | 0 | 0 | 7 |
| UAT | 7 | 0 | 0 | 0 | 7 |
| **Total** | **87** | **1** | **8** | **0** | **96** |

Remaining open items, ranked:

1. **RES-A2 (H-CA)** — cc-socks attach's `events()` still partitions (not broadcasts) across
   concurrent consumers. Not touched by Phase 5. Same "latent under today's wiring" caveat as
   before, but a real port-contract violation if a future caller ever registers two concurrent
   consumers on one attach session.
2. **EV-OPS-001** — no deliberate child-reaping logic exists in `serve`'s shutdown path. My retest
   this session did not reproduce an orphan for a SIGKILL against an idle live session with the
   real `pi` binary, but this is incidental (stdin EOF causes `pi` to self-exit), not a guarantee —
   untested: mid-turn kill, mid-write kill, SIGTERM vs SIGKILL, and the codex/claude_code
   connectors under the same scenario. SYS-10 was never split as EV-OPS-001 itself recommended.

---

## Evidence quality spot-check (adversarial sample, 4 files: 1 INT, 1 SYS, 1 UAT, 1 RES)

- **EV-CX-001-int-cases.md (INT)** — the new `EV-CX-001-raw_capture_steer.jsonl` capture is real
  captured wire bytes with monotonic timestamps (t=11.725 steer write, t=11.7255 ack, t=34.9964
  item/completed with steered content) — not narrated. The file's own conclusion ("steer literally
  raced the first content chunk and still landed mid-stream") is exactly what the timestamps show,
  not an overreach.
- **EV-SYS-003-FOLLOWUP-target-grammar-fix.md (SYS)** — real captured `harness_event_list` output
  before/after (7→11), with the new events' native kinds listed. Conclusion is properly scoped to
  what was tested: explicitly states only `direct` was live-verified and disclosed `tag`'s
  pre-fix-failure was inferred, not independently captured. This IS the honest disclosure pattern
  the task's rule 6 asks for — the one gap (no live capability/role/tag rerun) is exactly what I
  closed independently above, not a fabricated claim.
- **EV-UAT-07 fix (docs/harness-integrations/operator-guide.md, UAT)** — read start-to-finish.
  Followed the "attach a pi session and send a turn" walkthrough manually against my own SYS-03
  live-test session; the documented `harness_open`/`harness_event_list` call shapes match what the
  live server actually returned, field for field. Not narrated — it reads as instructions an
  operator could execute verbatim.
- **EV-PI-RES-001 / pi.py's RES-B1 fix (RES)** — the code comments make a specific, falsifiable
  claim ("RecursionError... confirmed live") and my own independent repro (different route,
  different injected payload) reproduces the same behavior. No overreach found in this sample.

No new instance of the EV-REV-003/SYS-10 "conclusion exceeds the test" pattern was found in this
sample, beyond the EV-OPS-001 gap already tracked above (which the evidence itself does NOT
overclaim — EV-OPS-001 was written as an explicit, disclosed open finding, not a false PASS).

---

## VERDICT

**The DoD is met for 3 of the 4 harnesses' full-duplex paths, and NOT fully met overall.** Plain
language:

- **No-polling**: TRUE, both directions. Structural grep across the entire harness path (pi,
  codex, claude_code stream, the new `InboxDeliveryNotifier`) found zero `time.sleep` loops and
  zero `SleepPollWaiter` usage; the only bounded waits are `Queue.get(timeout=...)` used to
  re-check a shutdown flag, which is not polling by the task's own stated distinction — no event
  is ever missed by that timeout, only idle-wait re-checks happen on it.
- **Native, non-polling communication with pi, codex, and claude_code (stream)**: TRUE, and the
  previously-broken target-grammar routing (`direct`/`capability`/`role`/`tag` reaching a live
  harness) now genuinely works — verified against a real hub, a real pi child, and two different
  target strategies (not just the one the shipped evidence covered).
- **claude_code (cc-socks attach)**: the send-half works and is well-evidenced; RES-A2's
  fan-out-partition defect in this connector was NOT touched by this fix pass and remains exactly
  as broken as Phase 4 found it. It is currently unreachable through the real supervisor (only one
  consumer is ever registered today), so it is not a live operator-facing bug today — but it is a
  real, uncorrected defect in a connector the DoD names as one of the "3 harnesses."
- **Evidences / full system / integration / regression / UAT test cases with undisputable
  evidence**: largely TRUE now. 87 of 96 plan rows are genuinely PASSED with real captured output
  (not narrated), including a fresh, reproduced 1857/4/0 full-suite run and my own independent
  re-verification of the two most consequential fixes (RES-B1's RecursionError wedge, and the
  SYS-03/UAT-05 target-grammar routing) via routes the shipped tests did not themselves exercise.
  One case (RES-A2/H-CA) is honestly FAILED, not swept under a green table.
- **EV-OPS-001 is real and still open.** It sits outside the plan's 55 named cases (it was found
  by a process sweep, not a test), so it does not move any row in the table above to FAILED, but
  it is a genuine, unresolved resource-leak risk under the exact "server exits with a live
  session" scenario an operator will eventually hit.

**What remains, ranked:**
1. Fix `claude_code_attach.py`'s RES-A2 fan-out defect (per-consumer queues, same pattern already
   applied to pi/codex/claude_code-stream).
2. Add deliberate child-reaping to `serve`'s shutdown path (signal handler or `atexit` sweep over
   tracked harness PIDs/process groups) so EV-OPS-001 stops depending on each harness binary's own
   incidental EOF-handling behavior, and split SYS-10 into the two cases EV-OPS-001 itself asked
   for.
3. (Minor, disclosed, not a gate item) `surface_metrics.py`'s `harness_backend_h1_h2` ledger entry
   (1680) is stale after the `_P_HARNESS_AGENT_ID` docstring's latest rewrite; low priority.

**What a reviewer should spot-check first:** RES-A2 (H-CA) in `RES-claude-code-attach.md` (confirm
it's genuinely untouched — `git diff e4b2fe7..HEAD -- src/okto_nexus/adapters/outbound/harness/claude_code_attach.py`
returns nothing), and EV-OPS-001's open status (confirm no shutdown-signal-handling code exists in
`serve`'s entrypoint that this index missed).
