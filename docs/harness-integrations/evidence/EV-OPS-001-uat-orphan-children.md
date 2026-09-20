# EV-OPS-001 — Orphaned harness children survived the UAT stage

Found: 2026-09-20 16:51 -03, by the orchestrator's routine process sweep, NOT by any test case.
Severity: MAJOR (resource leak; contradicts a passing case's implied guarantee)
Status: orphans cleaned up; the underlying defect is OPEN.

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

## Required follow-up (OPEN)

- The supervisor must reap live children when the server shuts down, not only when a session is
  explicitly closed. Verify what `serve` does on SIGTERM/SIGINT and on an unclean exit.
- SYS-10 should be SPLIT into two cases: explicit-close teardown (currently proven), and
  server-exit-with-live-sessions (currently unproven, and empirically failing per this evidence).
- The orphan assertion in any future case should test PPID reparenting, not just a name grep.
