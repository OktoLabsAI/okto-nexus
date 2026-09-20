# EV-OPS-001 — Orphaned harness children survived the UAT stage

Found: 2026-09-20 16:51 -03, by the orchestrator's routine process sweep, NOT by any test case.
Severity: MAJOR (resource leak; contradicts a passing case's implied guarantee)

> **STATUS UPDATE — 2026-09-20, post-`1cc8522`: CLOSED for the paths tested below;
> NOT closed for SIGKILL (never claimed).**
>
> `serve.py` previously had **no signal handling at all** — `signal.signal(SIGTERM, ...)`
> was never called, so uvicorn's own `capture_signals()` re-raised SIGTERM against the
> process's default disposition (`SIG_DFL`), which terminates the process immediately
> and means none of `serve`'s own `finally:` teardown blocks ever ran on that path. That
> was the actual root cause of the orphan this file documents, not merely "no reaping
> logic exists."
>
> `1cc8522` adds explicit signal handling in `serve.py` (~line 393 onward: installs a
> no-op `SIGTERM` handler so the re-raise converges on the same code path as `SIGINT`/
> clean exit, then runs the harness-child reap in a `finally` block reached by all
> three).
>
> **Covered by this fix, and independently re-verified in this session** (not just by
> reading `tests/test_serve_harness_shutdown_reap.py` — I ran it: 3 passed):
> - **Clean exit** (`test_clean_shutdown_after_explicit_close_leaves_no_orphan`) — a live
>   session explicitly closed, then SIGTERM to the serve PID. No orphan.
> - **SIGINT** (`test_sigint_with_live_session_reaps_the_harness_child`) — a live
>   session, SIGINT sent to the serve PID ONLY (never the process group). No orphan.
> - **SIGTERM** (`test_sigterm_with_live_session_reaps_the_harness_child`) — same, with
>   SIGTERM. No orphan.
>
>   All three tests use a fake `pi` stub that blocks forever on stdin instead of the
>   real `pi` binary specifically because the real binary self-exits on stdin EOF,
>   which would make the test pass whether or not `okto-nexus`'s own reap logic works —
>   exactly the "incidental self-cleanup, not a deliberate reap" confound this file's own
>   `EV-INDEX.md`-linked history flagged as unresolved. The fake stub removes that
>   confound: a still-alive, PPID=1-reparented fake `pi` after the signal is
>   unambiguous evidence of a real orphan, and its death is unambiguous evidence of our
>   own reap path, not luck.
>
> **NOT covered, by definition, not oversight: `SIGKILL`.** `SIGKILL` cannot be caught,
> blocked, or handled by any process — no `finally` block, no signal handler, no
> `atexit` hook can run in response to it. A `SIGKILL` (or an OOM-kill, a segfault, or
> `launchd`/`systemd` escalating straight past SIGTERM) against `okto-nexus serve` will
> still orphan any live harness children. This is a structural limitation of Unix
> signal delivery, not something this fix could have closed, and it was not claimed to
> be closed.
>
> **The PPID-based reaper recommendation below ("Required follow-up") was deliberately
> NOT built as a separate mechanism.** What was built instead is signal handling that
> lets the EXISTING teardown path (already correct for the explicit-close case, per
> SYS-10) also run on SIGINT/SIGTERM. A standalone PPID-walking reaper (e.g., a
> supervisor process watching for orphaned descendants independent of `serve`'s own
> shutdown code path) would additionally cover the SIGKILL case and is still a
> legitimate, unclaimed piece of future work — see the verdict in `EV-INDEX.md`.
>
> Status, precisely: **clean exit / SIGINT / SIGTERM — CLOSED, re-verified live.
> SIGKILL / OOM-kill / hard signals — OPEN, structurally unfixable by this
> mechanism, not attempted.**

Original status at discovery: orphans cleaned up; the underlying defect was OPEN.

## What was found

Two `pi --mode rpc` children from the Phase 4 UAT stage were still alive 1.5 hours after that
stage finished, reparented to `launchd`:

    PID    PPID  ELAPSED     COMMAND
    80514  1     01:33:38    .../scratchpad/uat/bin/pi --mode rpc --session-id hsess_b6d14a766ee84d
    84235  1     01:30:25    .../scratchpad/uat/bin/pi --mode rpc --session-id hsess_a496301772b74a

`PPID=1` is the tell: the `okto-nexus serve` process that spawned them exited WITHOUT reaping
them. They held no sockets or ports, so they were idle, but they were real `pi` sessions holding
process slots indefinitely.

Cleaned up with SIGTERM (both exited; no SIGKILL needed). A follow-up sweep for any harness
process reparented to `launchd` returned nothing.

## Why this matters more than the leak itself

**SYS-10 ("clean shutdown: hub stop terminates every child, leaving no orphans") PASSED.**

That pass was not wrong — it verified the SYS stage's own teardown path, where sessions were
closed explicitly before the server stopped. What it did not cover is the path UAT actually took:
a server exiting (or being torn down) while sessions were still live.

So the guarantee a reader would reasonably infer from SYS-10 — "harness children never outlive
the hub" — is broader than what SYS-10 actually proved. This is the second time in this project
that an evidence file's implied scope exceeded its literal test (the first being EV-REV-003's
downgrade of pi's unbounded `proc.wait()`, later superseded by RES-B1).

## How it was found

Not by a test. By the orchestrator's per-tick process sweep, which had to be WIDENED to catch it:
earlier sweeps grepped for `okto_nexus|pi --mode rpc|codex app-server` against full command lines,
and these processes matched only as `python3 /private/tmp/.../scratchpad/uat/bin/pi` — the PATH
shim the UAT stage had to build because `harness_open` lacked backend selection (see
EV-SYS-002-boot-and-registration.md). The shim's argv put `python3` first, so the pattern missed.

Two lessons, both recorded rather than fixed here:
1. An orphan check that greps for the expected binary name misses children launched through a
   wrapper. Check for PPID=1 reparenting as well as by name.
2. The PATH-shim workaround, itself a consequence of the missing backend-selection parameter,
   directly caused the monitoring blind spot.

## Required follow-up — status as of `1cc8522`

- ~~The supervisor must reap live children when the server shuts down, not only when a
  session is explicitly closed. Verify what `serve` does on SIGTERM/SIGINT and on an
  unclean exit.~~ **DONE for SIGTERM/SIGINT/clean exit** (see status update above).
  `serve` previously had no `signal.signal()` call at all; it now installs a SIGTERM
  handler so uvicorn's re-raise converges on the same reap-bearing `finally` path as
  SIGINT and a clean return.
- ~~SYS-10 should be SPLIT into two cases: explicit-close teardown (currently proven),
  and server-exit-with-live-sessions (currently unproven, and empirically failing per
  this evidence).~~ **Effectively done via `tests/test_serve_harness_shutdown_reap.py`**,
  a dedicated module covering all three server-exit-with-live-session paths
  (clean/SIGINT/SIGTERM) separately from SYS-10's explicit-close case, using a real
  `serve` subprocess and PPID-based assertions per the point below. SYS-10 itself was
  not literally split into two named plan rows, but the gap it left is now covered.
- ~~The orphan assertion in any future case should test PPID reparenting, not just a
  name grep.~~ **DONE** — `tests/test_serve_harness_shutdown_reap.py`'s
  `_assert_no_orphan` walks `ps -A` output by PPID; the fake `pi` stub is located among
  the server's descendants by name only to pick which PID to watch, never to decide
  pass/fail.
- **Still genuinely open, not attempted:** a standalone PPID-based reaper (e.g., a
  process independent of `serve` itself, watching for orphaned descendants) that would
  additionally cover `SIGKILL`/OOM-kill/hard-signal termination, where no code inside
  the killed process can run at all. This remains a recommendation only.
