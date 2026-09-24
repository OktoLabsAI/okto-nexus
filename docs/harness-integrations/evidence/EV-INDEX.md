# EV-INDEX — refreshed at `caae163`

Historical PR evidence only. For the0.2.0 remediation use the [current evidence index](../evidence-index.md). The captures and totals below are not rerun results, current setup instructions, or authorization to reuse the recorded accounts, LAN endpoints or interactive sessions.

Captured: 2026-09-20 (refreshed; superseding the prior version of this file captured at `1cc8522`,
preserved in git history). Commit under review: `caae163` (`feature/harness-integrations`, PR #34).
This is a **stale-index refresh**, not a new audit pass: it updates the `1cc8522` snapshot below
for the two commits that landed after it, `ec6937b` and `caae163`, both of which are
**documentation-only changes here** — no plan-row status in the Totals table moved, because the
work both commits did (cc-socks breakage probe, SIGKILL orphan watchdog, harness-to-harness relay
depth cap) was tracked in the `1cc8522` index's own "Separately tracked items (outside the 96 plan
rows)" section, not as named plan rows. What changed is that section, plus this file's own header
and reproduced-suite numbers, plus the VERDICT's stated limitations. See "Rows changed since
`1cc8522`" and "Separately tracked items" below.

The `1cc8522` snapshot itself (RES-A2 (H-CA) closure, EV-OPS-001 closure for clean-exit/SIGINT/
SIGTERM, send_only drain fix) was independently re-verified in that session and is carried forward
unchanged here; this refresh does not re-run those three closures, only the two commits after them.

This index was built by (1) reading the single-commit diff `3ce68d8..1cc8522`
(`serve.py`, `claude_code_attach.py`, `harness_supervisor.py`, plus three test files — 6 files,
715 insertions, 121 deletions), (2) reading the corrected evidence files
(`RES-claude-code-attach.md`, `EV-OPS-001-uat-orphan-children.md`), and (3) INDEPENDENTLY
RE-TESTING every one of the three closures myself, not by trusting the commit message:

- **RES-A2 (H-CA)** — ran
  `tests/test_harness_claude_code_connector.py::test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream`
  directly (1 passed). Confirms `events()` is now a broadcast snapshot over an append-only
  `_event_history` guarded by `_history_lock` (`claude_code_attach.py:288-304`, `:815-849`), not
  the old shared-deque drain. Two concurrent consumers each get the full stream
  (`kinds1 == kinds2` assertion), park-before-send choreography rules out a thread-start-race
  false pass.
- **EV-OPS-001** — read `tests/test_serve_harness_shutdown_reap.py` BEFORE running anything (it
  explicitly documents why a real `pi` binary cannot prove this: `pi` self-exits on stdin EOF
  regardless of whether the fix works, so a real-`pi` test passes both before and after the fix).
  It uses a fake `pi` stub that blocks forever until signalled, PPID-walk-based orphan detection
  (`ps -A -o pid=,ppid=,command=` snapshot, never a name grep), and signals the serve PID alone
  (never the process group). Ran it directly: `3 passed` — clean exit, SIGINT, and SIGTERM cases
  all confirmed no orphan (fake `pi` child either dead or not reparented to PPID=1 within the
  timeout). `serve.py` previously had no `signal.signal()` call at all — uvicorn's own signal
  capture re-raised SIGTERM against `SIG_DFL`, which never runs Python `finally` blocks; the fix
  installs a SIGTERM handler so the re-raise converges on the same reap-bearing teardown path as
  SIGINT/clean exit. **SIGKILL is NOT covered, by definition** — no code in the killed process can
  run in response to an uncatchable signal; this was never claimed fixed.
- **send_only drain (regression exposed by the RES-A2 fix)** — ran
  `tests/test_harness_supervisor.py::test_send_only_connector_delivers_each_event_exactly_once_across_multiple_sends`
  directly (1 passed): 3 `send()` calls → exactly 3 persisted events, exactly 3 published events.
  That committed test does not itself assert the inbox-notification count, so I additionally wrote
  and ran a standalone script (scratchpad only, not committed) reusing the same fixtures and
  asserting `message_deliveries` row count after 3 sends: **3**, not 9 — confirmed independently,
  not just read off the commit. Mechanism: a per-session cursor
  (`harness_supervisor.py:143-153`, `send_only_events_handled`, tail-sliced at `:527-540`) so each
  broadcast-snapshot event is handled by the supervisor exactly once regardless of how many times
  `events()` is re-read.

Also reproduced independently in the `1cc8522` session:

```
$ timeout 900 uv run python -m pytest -q
1861 passed, 4 skipped, 2 warnings in 154.27s (0:02:34)
$ timeout 200 uv run python -m pytest -q tests/test_http_parity.py tests/test_import_boundary.py
5 passed in 0.43s
$ uv run ruff check .
All checks passed!
```

That EXACTLY matched the task's own reference point at the time ("1861 passed, 4 skipped, 0
failed at `1cc8522`"). The one warning present (`PytestUnhandledThreadExceptionWarning` from
`test_res_b2_reader_exit_signals_shutdown_even_if_on_child_exit_itself_raises`) is the same
pre-existing, intentional one the `3ce68d8` index already disclosed — a test deliberately
triggering an exception-in-callback path and proving it's survived, not a failure.

**Reproduced independently in THIS refresh, at `caae163`:**

```
$ timeout 600 uv run python -m pytest -q tests/test_serve_harness_sigkill_reap.py \
    tests/test_harness_target_grammar.py tests/test_harness_supervisor.py
43 passed in 6.84s
$ timeout 900 uv run python -m pytest -q
1884 passed, 4 skipped, 2 warnings in 166.15s (0:02:46)
```

This matches the task's own reference point for `caae163` ("1884 passed, 4 skipped, 0 failed"),
and matches the +23-tests / +4 delta the `ec6937b` (1880, +19 over `5cdf548`'s 1861) and `caae163`
(1884, +4 over `ec6937b`) commit messages themselves report. The same pre-existing thread-exception
warning is still present and is the same intentional one, unrelated to this branch's Phase 6 work
— confirmed by re-reading the traceback, which still points at
`test_res_b2_reader_exit_signals_shutdown_even_if_on_child_exit_itself_raises`'s own injected
`RuntimeError`. `ruff check .` was not re-run in this documentation-only refresh (no source or test
file changed); the `1cc8522` session's clean ruff result and the fact that `caae163`'s own commit
message independently reports "ruff clean" are both carried forward as unverified-by-this-session
claims, not restated as if freshly measured.

Legend unchanged: **PASSED** = committed evidence (or, where noted, my own live reproduction this
session) proves the case. **FAILED** = proven not to hold. **NOT-APPLICABLE** = capability doesn't
exist on this connector, by design, reason stated. **UNRUN** = no evidence file exists — a case
with no evidence file is UNRUN even if the surrounding narrative implies otherwise.

H-PI = pi 0.85.1, H-CX = codex 0.144.6, H-CC = Claude Code stream-json (D7a),
H-CA = Claude Code cc-socks attach (D7b).

---

## Rows changed since `3ce68d8` (all landed by `1cc8522`; unchanged by `ec6937b`/`caae163`)

| Case ID | `3ce68d8` status | `1cc8522` status | Evidence | Note |
|---|---|---|---|---|
| RES-A2 (H-CA) | FAILED — measured partition | **PASSED** | `RES-claude-code-attach.md` (corrected, history preserved) + `tests/test_harness_claude_code_connector.py::test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream` | Append-only `_event_history` + lock-guarded snapshot replaces the shared-deque drain, mirroring the three sibling connectors' earlier fan-out fix. Re-verified live this session, not read off the commit message. |

No other of the 96 plan rows changed. `3ce68d8`'s 87 PASSED and 8 NOT-APPLICABLE rows are carried
forward unchanged — the `1cc8522` diff touches only `serve.py`, `claude_code_attach.py`,
`harness_supervisor.py`, and their three test files; nothing else in the application changed
(full suite re-run above confirms no regression elsewhere).

---

## Separately tracked items (outside the 96 plan rows)

These were never plan rows (found by process sweep / by a fix exposing a second defect / by a
task brief calling out prior open limitations, not by a named test case), so they do not move any
row in the Totals table below, but the task requires reporting them honestly rather than letting a
clean gate imply they're gone.

1. **EV-OPS-001 (orphaned harness children on unclean server exit)** — **CLOSED for clean exit,
   SIGINT, and SIGTERM** since `1cc8522` (re-verified live in that session). **As of `caae163`,
   also has a best-effort, independent SIGKILL watchdog**
   (`src/okto_nexus/adapters/inbound/cli/harness_orphan_watchdog.py`, spawned by `serve.py` in its
   own session so a signal to `serve` never reaches it): a first version shipped at `ec6937b` and
   was found PARTIAL by an adversarial pass (a reparenting race in the poll loop's final
   iteration, ~10-13% leak rate under CPU load, 0% in isolation — see
   `EV-OPS-001-uat-orphan-children.md`'s post-`caae163` status update for the mechanism); `caae163`
   closed it by re-checking `os.getppid()` both before AND after the process snapshot and
   discarding a snapshot that straddled the reparenting flip, evidenced by a failing-first
   reproduction plus 30/30 clean runs under synthetic all-core load (a separately-cited 25/25 run
   at 2x CPU oversubscription is a distinct measurement, not the same number restated). **This is
   evidence the fix works under the tested conditions, not proof the SIGKILL race is categorically
   closed** — a watchdog is best-effort by construction (disclosed one-poll-interval detection
   window, and the watchdog process itself is not immune to being killed or losing the reap race).
   See "SIGKILL" under Limitations below for the full, non-rounded-up statement.
2. **send_only drain duplication (regression the RES-A2 fix exposed, not present before it)** —
   **CLOSED** since `1cc8522`, per-session cursor added, re-verified live including the
   inbox-notification count the committed test itself does not assert. Worth naming explicitly:
   this was a defect that did not exist until the RES-A2 fix changed `events()`'s contract from
   destructive-drain to broadcast-snapshot — a caution about assuming a fix is "purely additive"
   when it changes a shared contract three call sites depend on. Unchanged by `ec6937b`/`caae163`.
3. **cc-socks (H-CA) breakage detection** — **CLOSED at `ec6937b`.** Five independently-built
   adversarial fixtures (protocol mismatch, a registry missing its `kind` field, a malformed-JSON
   key file, a missing registry, an unreadable registry) each produced a DISTINCT, attributable
   reason code, mapped into `protocol_drift`/`no_session`/`permission` buckets. The probe
   deliberately never implies delivery proof — see "cc-socks is ack-less" under Limitations, which
   this closure does not touch. No dedicated `EV-CC-0xx` evidence file was added for this probe;
   the evidence is the commit message plus the (uv-run-verified-green) test suite, cited that way
   rather than pointed at a file that does not exist.
4. **Harness-to-harness relay depth cap (previously: relaying blocked outright)** — **CLOSED at
   `caae163`, with a disclosed floor.** `ec6937b` found the existing elapsed-time TTL
   (`relay_depth_ttl_s`, default 30s, reset on every hop) meant any cascade paced slower than the
   TTL — the realistic case, since agent turnaround routinely exceeds 30s — never accumulated
   depth and the cap never fired (verified: 8 consecutive hops against a cap of 2, all
   unblocked). `caae163` replaced elapsed-time-since-last-hop with CHAIN IDENTITY:
   `_LiveSession.relay_chain_id` / `relay_chain_started_at` (`harness_supervisor.py`) persist for
   the life of a chain and are set once, at the chain's first hop; the one remaining time signal,
   `relay_chain_max_age_s` (1800s default), is now checked against total CHAIN AGE, not
   inter-hop gap, so it cannot fire mid-cascade but still lets a long-finished chain stop
   poisoning a new conversation between the same pair. Evidence: failing-first (8 hops at 0.15s
   against a 0.05s TTL and cap of 2 — previously 8 forwarded / 0 blocked, now blocked), plus a
   regression guard proving a genuinely new conversation between the same pair is not wrongly
   blocked; 37/37 across 5 runs, and this refresh's own re-run of
   `tests/test_harness_target_grammar.py` (which carries the relay tests) passed clean. **Disclosed
   floor, not an oversight:** a cascade paced slower than `relay_chain_max_age_s` (1800s) PER HOP
   still eventually re-mints a fresh chain and escapes the cap — the same failure shape as the
   original TTL defect, just at a much longer period. Closing that needs a request-scoped
   conversation id threaded through `MessageService`; it was not built here.

---

## Totals (unchanged since `1cc8522`; `ec6937b`/`caae163` did not touch a plan row)

| Suite | PASSED | FAILED | NOT-APPLICABLE | UNRUN | Total |
|---|---|---|---|---|---|
| INT | 27 | 0 | 5 | 0 | 32 |
| RES | 37 | 0 | 3 | 0 | 40 |
| SYS | 10 | 0 | 0 | 0 | 10 |
| REG | 7 | 0 | 0 | 0 | 7 |
| UAT | 7 | 0 | 0 | 0 | 7 |
| **Total** | **88** | **0** | **8** | **0** | **96** |

All 96 named plan rows are now PASSED or NOT-APPLICABLE. Zero FAILED, zero UNRUN.

---

## Evidence quality spot-check (carried forward from the `1cc8522` pass — RES-A2/H-CA and EV-OPS-001)

- **`RES-claude-code-attach.md`** — the original file's RES-A2 verdict ("partition... is the
  documented, by-design behaviour") was itself the failure mode this project has repeatedly
  flagged: a conclusion presented as a design decision when it was an unexamined defect. That
  framing is exactly why the defect survived a six-agent Phase 5 pass whose explicit mandate was
  closing FAILED rows — nothing in the file told a reader it needed fixing. Corrected in place
  during the `1cc8522` session with a preserved-history annotation (not erased) per that task's
  explicit instruction; the correction states plainly that the prior verdict was wrong and why.
- **`EV-OPS-001-uat-orphan-children.md`** — status-updated line by line, not declared closed
  wholesale, during the `1cc8522` session; the SIGKILL gap was stated as a structural limitation
  (not an oversight) directly beside the closed items. **This refresh found one place that same
  file had gone stale in the other direction**: its "Required follow-up" list still called the
  standalone PPID-based reaper "still genuinely open, not attempted" after `caae163` built exactly
  that (`harness_orphan_watchdog.py`) — corrected in this pass with a post-`caae163` status-update
  block, same shape as the existing post-`1cc8522` one, history preserved.
- **`tests/test_serve_harness_shutdown_reap.py`** — read start-to-finish before trusting it, during
  the `1cc8522` session. Its own module docstring pre-empts the exact false-pass risk that task's
  brief warned about (the real `pi` binary self-exiting on stdin EOF) and explains, with evidence,
  why the fake stub is necessary to prove anything. This is the honest-disclosure pattern rule 6
  asks for, reproduced correctly rather than papered over.

No new instance of the EV-REV-003/SYS-10/RES-claude-code-attach "conclusion exceeds the test"
pattern was found in the `1cc8522` pass beyond the RES-claude-code-attach.md defect itself. This
refresh found exactly one instance of the adjacent pattern — a stale "still open" claim outstaying
the fix that closed it — in EV-OPS-001, corrected above.

---

## VERDICT

**The user's Definition of Done, verbatim:** *"nexus now running with native integrations into
all 3 of the above mentioned harnesses, no polling, just native-ish communication with each,
evidences, full system level test cases, integration level test cases, regression test cases,
User Acceptance test cases, all with associated evidences that are undisputable."*

**Is it met? Yes, with one named, load-bearing exception a reader must know about (SIGKILL), and
one structural note on the DoD's own harness count.**

- **"All 3 of the above mentioned harnesses"** — the task brief itself names four connectors (pi,
  codex, Claude Code stream-json / H-CC, Claude Code cc-socks attach / H-CA) across three
  underlying harness *products* (pi, codex, Claude Code — Claude Code has two connector shapes,
  full-duplex stream and send-only socket attach). Every one of the four connectors is now
  PASSED across INT/RES/SYS with no open defect. If "3 harnesses" is read as the three products,
  this is unambiguously met. If a reader insists on treating H-CC and H-CA as two separate things
  making it "4," the DoD is still met per-connector — this is a counting-convention note, not a
  gap.
- **No-polling**: TRUE for event delivery, with one new, disclosed exception this refresh
  re-checked by grep across the harness adapter tree for `time.sleep`: alongside the readiness-
  banner poll in `serve.py` and the bounded lock/WAL-retry backoffs in the SQLite adapter (neither
  "polling a harness for events"), `caae163`'s new `harness_orphan_watchdog.py` has its own
  `poll_interval_s`-gated loop (`time.sleep(poll_interval_s)`, default 1s). That IS a poll loop,
  by construction — it is polling OS process state to detect `serve`'s death, not polling a
  harness for events, so it does not touch D1's actual constraint (no `SleepPollWaiter` on the
  harness event path); every connector's own event delivery is still push-based (`Queue.get()`
  blocking waits or broadcast-snapshot reads). Worth naming rather than silently excluding: a
  reader auditing "no polling" for the whole codebase should know this loop exists and why it is
  outside D1's scope.
- **Native, non-polling communication with all four connectors**: TRUE, and now also includes
  cc-socks' breakage-detection closure (`ec6937b`) — every distinguishable failure mode now maps
  to an attributable reason code, though see "cc-socks is ack-less" below.
- **Evidences / full system / integration / regression / UAT test cases with undisputable
  evidence**: TRUE. 88 of 96 plan rows PASSED, 8 NOT-APPLICABLE with stated reasons, 0 FAILED,
  0 UNRUN — unchanged by `ec6937b`/`caae163`, whose closures were tracked outside the 96 plan
  rows (see "Separately tracked items" above). This refresh's own reproduced full-suite run at
  `caae163`: 1884 passed, 4 skipped, 0 failed, matching the task's own reference point exactly.
  `http_parity`/`import_boundary` were carried forward green from the `1cc8522` session (not
  re-run in this documentation-only refresh, since neither test file nor any source it exercises
  changed). Every claim in this refresh is backed by either a command this session ran and read
  the output of, or an explicit citation to the commit message / evidence file it was carried
  forward from — never presented as freshly measured when it was not.

**Limitations a reader should know, stated plainly, not buried:**

1. **SIGKILL orphaning is now covered by a best-effort watchdog, not proven categorically
   impossible.** `caae163` closed the reparenting-race defect an adversarial pass found in
   `ec6937b`'s first version of `harness_orphan_watchdog.py` (a standalone process, independent
   of `serve`, that reaps `serve`'s descendants via PPID walk after detecting `serve`'s own death
   through `os.getppid()`). Measured by the closing work (not re-run in this
   documentation-only refresh): 25/25 clean under verified CPU contention (2x
   oversubscription, wall time inflated 1.33-1.81s vs 1.13s unloaded), plus a separate 30/30
   clean run under 18 synthetic all-core busy loops — against a prior defect rate of ~10-13%
   under load. **Read that plainly: 0/25 against a ~10-13% prior rate is consistent with the true
   residual rate now being below roughly 11% at 95% confidence — that is evidence the fix works,
   it is NOT proof the race is categorically closed.** A watchdog is best-effort by construction:
   it has a disclosed one-poll-interval detection window (default 1s — a child spawned and
   `serve` SIGKILLed inside the same interval can be missed, per the module's own docstring), and
   the watchdog process itself is not immune to being killed or losing the reap race. Do not round
   this up to "fixed."
2. **cc-socks (H-CA) rides an undocumented, reverse-engineered wire protocol** (recovered from a
   binary's own log strings, per `EV-CC-001-cc-socks-external-inject.md`), not a published API.
   `claude_code` stream-json (H-CC) is the PRIMARY, documented path; cc-socks attach is
   attach-only upside on top of it. Anthropic changing that protocol in a future Claude Code
   release would silently break this connector with no upstream compatibility guarantee. `ec6937b`
   closed detection of that breakage (five adversarial fixtures, five distinct attributable reason
   codes) — it did not, and cannot, make the protocol itself stable.
3. **cc-socks is ack-less.** A successful send through cc-socks is NOT proof of delivery, and no
   breakage probe can make it so — the protocol has no acknowledgment mechanism to probe. This is
   a structural property of the wire protocol, not a gap the breakage-detection work in (2)
   closes.
4. **The harness-to-harness relay depth cap has a disclosed floor.** `caae163` replaced the
   elapsed-time TTL `ec6937b` found broken (any cascade paced slower than 30s never accumulated
   depth) with a chain-identity cap keyed on `relay_chain_id`/`relay_chain_started_at`, checked
   against `relay_chain_max_age_s` (1800s) as total chain age rather than inter-hop gap. A
   cascade paced slower than 1800s PER HOP still eventually re-mints a fresh chain and escapes the
   cap — the same failure shape as the original defect, just at a much longer period. This is a
   disclosed floor, not an oversight; closing it needs a request-scoped conversation id threaded
   through `MessageService`, which was not built here.

**What a reviewer should spot-check first, to try to falsify this verdict:**

1. Run `tests/test_serve_harness_shutdown_reap.py` yourself and read its module docstring first —
   confirm the fake-`pi`-stub reasoning holds and that a real-`pi` substitution would indeed pass
   both before and after the fix (i.e., confirm the test is actually discriminating, not just
   green).
2. Run `tests/test_harness_claude_code_connector.py::test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream`
   and diff `claude_code_attach.py` against `3ce68d8` (`git diff 3ce68d8..1cc8522 --
   src/okto_nexus/adapters/outbound/harness/claude_code_attach.py`) to confirm the fix is the
   append-only-history-plus-lock pattern claimed, not something narrower that happens to pass this
   one test.
3. Confirm the send_only exactly-once claim yourself, including inbox notifications — the
   committed test only asserts persisted+published counts; the inbox-notification count in this
   report came from an independent scratch script, not a committed regression test, so a
   reviewer should not take my word for it without either running that script's equivalent or
   adding the assertion to the committed test.
4. Run `tests/test_serve_harness_sigkill_reap.py` and read `harness_orphan_watchdog.py`'s module
   docstring first — confirm the bracketed `os.getppid()` re-check (before AND after
   `_ps_snapshot()`) is really what closes the reparenting race, not something narrower. Then, if
   you want to stress it yourself: send a real `SIGKILL` to a `serve` process with a live harness
   session and the watchdog running, under CPU contention, and confirm the watchdog reaps the
   child — and separately, try to construct a case inside its disclosed one-poll-interval window
   to confirm the detection gap is real, not hedging.
5. Diff `relay_chain_id`/`relay_chain_started_at` handling in `harness_supervisor.py` against
   `ec6937b` (`git diff ec6937b..caae163 -- src/okto_nexus/application/harness_supervisor.py`) and
   confirm `relay_chain_started_at` is set once per chain, not re-stamped on every hop — the
   commit message notes the agent caught and fixed exactly that bug before shipping; verify it
   independently rather than trusting the note.
