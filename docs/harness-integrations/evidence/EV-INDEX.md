# EV-INDEX — final index at `1cc8522`

Captured: 2026-09-20. Commit under review: `1cc8522` (`feature/harness-integrations`), which
closed the three findings the prior index (corrected at `3ce68d8`) left open: RES-A2 (H-CA)'s
fan-out-partition defect, EV-OPS-001's orphaned-children defect, and a regression EV-OPS-001's own
fix exposed (send_only re-drain duplication in `HarnessSupervisor`). This supersedes the `3ce68d8`
index (preserved in git history), which showed 87 PASSED / 1 FAILED / 8 NOT-APPLICABLE / 0 UNRUN
with RES-A2 (H-CA) as the single FAILED row.

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

Also reproduced independently this session:

```
$ timeout 900 uv run python -m pytest -q
1861 passed, 4 skipped, 2 warnings in 154.27s (0:02:34)
$ timeout 200 uv run python -m pytest -q tests/test_http_parity.py tests/test_import_boundary.py
5 passed in 0.43s
$ uv run ruff check .
All checks passed!
```

This EXACTLY matches the task's own reference point ("1861 passed, 4 skipped, 0 failed at
`1cc8522`"). The one warning present (`PytestUnhandledThreadExceptionWarning` from
`test_res_b2_reader_exit_signals_shutdown_even_if_on_child_exit_itself_raises`) is the same
pre-existing, intentional one the `3ce68d8` index already disclosed — a test deliberately
triggering an exception-in-callback path and proving it's survived, not a failure.

Legend unchanged: **PASSED** = committed evidence (or, where noted, my own live reproduction this
session) proves the case. **FAILED** = proven not to hold. **NOT-APPLICABLE** = capability doesn't
exist on this connector, by design, reason stated. **UNRUN** = no evidence file exists — a case
with no evidence file is UNRUN even if the surrounding narrative implies otherwise.

H-PI = pi 0.85.1, H-CX = codex 0.144.6, H-CC = Claude Code stream-json (D7a),
H-CA = Claude Code cc-socks attach (D7b).

---

## Rows changed since `3ce68d8`

| Case ID | `3ce68d8` status | `1cc8522` status | Evidence | Note |
|---|---|---|---|---|
| RES-A2 (H-CA) | FAILED — measured partition | **PASSED** | `RES-claude-code-attach.md` (corrected, history preserved) + `tests/test_harness_claude_code_connector.py::test_res_a2_two_concurrent_events_consumers_each_receive_the_full_stream` | Append-only `_event_history` + lock-guarded snapshot replaces the shared-deque drain, mirroring the three sibling connectors' earlier fan-out fix. Re-verified live this session, not read off the commit message. |

No other of the 96 plan rows changed. `3ce68d8`'s 87 PASSED and 8 NOT-APPLICABLE rows are carried
forward unchanged — the `1cc8522` diff touches only `serve.py`, `claude_code_attach.py`,
`harness_supervisor.py`, and their three test files; nothing else in the application changed
(full suite re-run above confirms no regression elsewhere).

---

## Separately tracked items (outside the 96 plan rows) — both now resolved as far as they can be

These were never plan rows (found by process sweep / by a fix exposing a second defect, not by a
named test case), so they do not move any row in the Totals table below, but the task requires
reporting them honestly rather than letting a clean gate imply they're gone.

1. **EV-OPS-001 (orphaned harness children on unclean server exit)** — **CLOSED for clean exit,
   SIGINT, and SIGTERM** (re-verified live, see above). **NOT closed, and not closeable by this
   mechanism, for SIGKILL / OOM-kill / any signal a process cannot catch.** The PPID-based
   standalone-reaper recommendation from the original finding (a process independent of `serve`
   watching for orphaned descendants) was deliberately NOT built — what was built instead is
   signal handling that lets `serve`'s own existing (and already-correct, per SYS-10) teardown
   path run on SIGINT/SIGTERM instead of being skipped. A reader who wants SIGKILL-safety must
   still build that separate reaper; it remains an open, unclaimed recommendation.
2. **send_only drain duplication (regression the RES-A2 fix exposed, not present before it)** —
   **CLOSED**, per-session cursor added, re-verified live including the inbox-notification count
   the committed test itself does not assert (see above). Worth naming explicitly: this was a
   defect that did not exist until the RES-A2 fix changed `events()`'s contract from
   destructive-drain to broadcast-snapshot — a caution about assuming a fix is "purely additive"
   when it changes a shared contract three call sites depend on.

---

## Totals (`1cc8522`, final)

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

## Evidence quality spot-check (this pass — RES-A2/H-CA and EV-OPS-001 specifically)

- **`RES-claude-code-attach.md`** — the original file's RES-A2 verdict ("partition... is the
  documented, by-design behaviour") was itself the failure mode this project has repeatedly
  flagged: a conclusion presented as a design decision when it was an unexamined defect. That
  framing is exactly why the defect survived a six-agent Phase 5 pass whose explicit mandate was
  closing FAILED rows — nothing in the file told a reader it needed fixing. Corrected in place
  this session with a preserved-history annotation (not erased) per the task's explicit
  instruction; the correction states plainly that the prior verdict was wrong and why.
- **`EV-OPS-001-uat-orphan-children.md`** — the original file's "Required follow-up (OPEN)" list
  is now genuinely status-updated line by line rather than declared closed wholesale; the SIGKILL
  gap is stated as a structural limitation (not an oversight) directly beside the closed items, so
  a reader cannot come away thinking the finding is fully resolved.
- **`tests/test_serve_harness_shutdown_reap.py`** — read start-to-finish before trusting it. Its
  own module docstring pre-empts the exact false-pass risk this task's brief warned about (the
  real `pi` binary self-exiting on stdin EOF) and explains, with evidence, why the fake stub is
  necessary to prove anything. This is the honest-disclosure pattern the task's rule 6 asks for,
  reproduced correctly rather than papered over.

No new instance of the EV-REV-003/SYS-10/RES-claude-code-attach "conclusion exceeds the test"
pattern was found in this pass beyond the RES-claude-code-attach.md defect itself, which is now
corrected.

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
- **No-polling**: TRUE. Re-confirmed this session by grep across the entire harness adapter tree
  for `time.sleep` — the only hits are a readiness-banner poll in `serve.py` (waiting for uvicorn's
  own `started` flag before printing a ready message, unrelated to harness event delivery) and
  bounded lock/WAL-retry backoffs in the SQLite adapter, neither of which is "polling a harness for
  events." Every connector's event delivery is push-based (`Queue.get()` blocking waits or
  broadcast-snapshot reads), not a sleep-loop.
- **Native, non-polling communication with all four connectors**: TRUE, and now includes cc-socks'
  fan-out fix — previously the one connector with a real, uncorrected defect.
- **Evidences / full system / integration / regression / UAT test cases with undisputable
  evidence**: TRUE. 88 of 96 plan rows PASSED, 8 NOT-APPLICABLE with stated reasons, 0 FAILED,
  0 UNRUN. A fresh, reproduced 1861/4/0 full-suite run, `http_parity`/`import_boundary` green,
  ruff clean. Every one of this session's own claims above is backed by a command I ran and read
  the output of, not a commit message I trusted.

**Limitations a reader should know, stated plainly, not buried:**

1. **SIGKILL still orphans harness children.** No fix could close this — it's a property of Unix
   signal delivery, not a code gap. Anyone deploying `okto-nexus serve` under a supervisor that
   might SIGKILL it (rather than SIGTERM-then-wait-then-SIGKILL) should still expect orphaned
   harness processes on that path. A standalone PPID-based reaper, external to `serve` itself,
   is the only way to close this, and it was not built.
2. **cc-socks (H-CA) is an undocumented, reverse-engineered wire protocol** (recovered from a
   binary's own log strings, per `EV-CC-001-cc-socks-external-inject.md`), not a published API.
   Anthropic changing that protocol in a future Claude Code release would silently break this
   connector with no upstream compatibility guarantee — a risk inherent to the integration
   approach, not something any test in this suite can rule out for future releases.
3. **The harness-to-harness cascade guard blocks intentional relaying.** (Carried forward from
   prior evidence — not re-litigated this session, but still a real, load-bearing limitation an
   operator wiring one harness's output to trigger another harness should know about before
   assuming it "just works.")

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
4. Send a real `SIGKILL` (not `SIGTERM`/`SIGINT`) to a `serve` process with a live harness session
   and confirm it DOES still orphan — verifying the stated limitation is real, not hedging.
