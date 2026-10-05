"""LIMITATION 1 (EV-OPS-001, SIGKILL gap): a lightweight, independent reaper
for harness children orphaned by an uncatchable signal to `serve`.

## Why this exists

`EV-OPS-001` is closed for clean exit, SIGINT and SIGTERM (see
`_reap_live_harness_sessions` in `serve.py` and
`tests/test_serve_harness_shutdown_reap.py`): all three drive `server.run()`
back to a normal Python return, so `serve`'s own `finally` block runs and
reaps every live harness child through `HarnessSupervisor.close()`.

SIGKILL cannot be intercepted by definition - no code in the killed process
runs in response to it, so `serve`'s own `finally` block NEVER executes on
that path. The only way to close this gap is a process OTHER than `serve`
that independently notices `serve` is gone and reaps whatever it left
behind. This module is that process.

## Why it cannot ask `HarnessSupervisor` which PIDs to watch

The natural-looking alternative - have `serve` hand this watchdog a list of
harness child PIDs up front - does not exist as an option within this
task's file boundaries. `HarnessSupervisor` (`application/harness_
supervisor.py`) and every per-harness connector (`adapters/outbound/
harness/*.py`) are owned by other agents on this branch and this task's
files are `serve.py`, this module, and this module's own test - nothing
else. Even setting that aside, the only place a child's real OS pid lives
today is a connector-private attribute (e.g. `PiRpcConnector._proc.pid`),
never exposed on the frozen `HarnessConnector` Protocol
(`application/ports.py`) - so there is no *stable, public* way to read it
even by reaching across files.

This module therefore never asks what a harness child IS. It only asks what
is a DESCENDANT of the `serve` process, discovered purely from the OS
process tree (`ps -A -o pid=,ppid=`), the same PPID-walk technique
`tests/test_serve_harness_shutdown_reap.py` already uses to PROVE the
SIGINT/SIGTERM fix, and for the identical reason stated in EV-OPS-001's own
postmortem: a name grep is exactly how the original orphans went unnoticed
for 90 minutes (a PATH shim's `python3` argv matched, the actual runaway
process's name did not). This module never inspects a command string at
all - not even to decide what counts as "a harness child". Everything that
was ever a descendant of `serve` is a candidate; nothing else is.

## The discovery race, stated plainly

The OS only lets you walk descendants of a PID that is still alive - once
`serve` is gone, its process-tree edges are gone too (surviving children are
already reparented to PID 1). So this module keeps a ROLLING snapshot of
`serve`'s descendants while `serve` is alive (`_poll_interval_s`, default
1s - see `run_watchdog`'s docstring for the cost/latency trade-off this
default encodes) and, the moment it detects `serve` is gone, treats the
LAST snapshot before that moment as the candidate set. A child spawned and
`serve` SIGKILLed inside one poll interval can be missed - this is a real,
disclosed bound on detection latency, not something this design closes to
zero. Lowering `--poll-interval-s` trades a busier poll loop for a tighter
window.

## How "serve is gone" is detected

By this process's OWN `os.getppid()`, not by polling `os.kill(serve_pid,
0)`. `serve.py` spawns this module as a direct child (`subprocess.Popen`,
no intermediate shell) with `start_new_session=True` - which gives it its
own process group/session (so a signal aimed at `serve` alone, or at
`serve`'s process group, never reaches it) while leaving its PPID as
`serve`'s pid until `serve` dies, at which point the kernel reparents it to
the nearest subreaper (PID 1 on the platforms this module runs on).
Watching a `serve_pid` argument to see if it "goes away" would be a
PID-reuse race (some unrelated process could eventually reuse that integer
while this loop is asleep); watching this process's OWN `getppid()` has no
such race - it is the kernel's own bookkeeping, updated atomically the
instant the parent exits, for exactly this process.

## Why only PID-alive-and-reparented-to-1 is the kill gate

A candidate pid from an earlier snapshot is only ever touched if, AT REAP
TIME, it is (a) still alive and (b) has PPID 1. (b) is what stops this from
ever touching a still-legitimately-parented process: a NEW `serve` started
after this one always spawns children whose PPID is the NEW `serve`'s pid,
never 1, so an old watchdog can never collide with a freshly restarted
server's own children even under PID reuse of the *watched* pid, because
the reused pid's current parent would not be 1 unless it too is orphaned
(and an orphan of anything is fair game for a reaper by definition). This
module does not go further and fingerprint process start time to rule out
the residual, much narrower case of a reused pid that ALSO happens to be
independently orphaned within the same handful of seconds - that risk is
judged negligible against the added parsing surface (BSD `ps` on macOS
does not reliably expose the GNU-only `etimes=` field this repo would
otherwise need); see the design report in the task write-up for the
explicit trade-off.

## Bounded lifetime - the watchdog must not itself become a leak

- Spawned detached (own session) so it can outlive `serve`, but every
  action it takes after detecting `serve`'s death is time-boxed
  (`--discovery-grace-s` absorbing the kernel reparenting race described
  above, then `--term-grace-s` + `--kill-grace-s` mirroring
  `PiRpcConnector.close`'s own SIGTERM-then-SIGKILL escalation - see
  `pi.py`). It ALWAYS exits after that window, whether or not every
  candidate died.
- On the three paths `serve` can run its own `finally` (clean exit,
  SIGINT, SIGTERM), `serve.py` explicitly terminates this process right
  after it finishes its own reap - see `_stop_harness_orphan_watchdog` in
  `serve.py` - so this module's self-governing loop is only ever the thing
  that actually matters on the SIGKILL path; on every other path it is a
  redundant backstop that gets told to stop rather than discovering it on
  its own.
- Holds no lock, no DB connection, no socket, no open file beyond `/dev/
  null` on its own stdio - nothing for it to leak besides the process
  entry itself, and that is what the bounded lifetime above closes.
- If THIS process dies first (its own crash, an operator `kill -9` aimed
  at it specifically, a whole-cgroup/OOM kill that takes `serve` and this
  process out together), the SIGKILL gap reopens exactly as before this
  module existed - a strict "no worse than today", never a claim that this
  makes SIGKILL-safety absolute. Supervising the supervisor is not
  attempted; that is an infinite regress, not a fix.

Stdlib-only by construction (no `sqlite3`/`mcp` import), matching every
other subprocess-managing module in this codebase's `adapters/outbound/
harness/` package, even though this module lives under `adapters/inbound/
cli/` (it is invoked exactly like `serve`/`tail`/`admin` - a standalone
`python -m` entry point - and needs nothing from the rest of the package,
deliberately, so it can never fail to start because of an unrelated
import).
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time

#: Default interval between process-tree polls while `serve` is alive. This
#: is a genuine cost/latency trade-off, not a magic number: a 1s poll on a
#: multi-day-running `serve` is roughly 86,400 `ps -A` forks a day (cheap
#: individually, non-zero in aggregate); a tighter interval shrinks the
#: "spawned and SIGKILLed within one poll" blind spot described in the
#: module docstring at the cost of more of those forks. Tests override this
#: via `--poll-interval-s` to stay fast without changing the mechanism.
DEFAULT_POLL_INTERVAL_S = 1.0

#: Bound on the discovery-retry loop that absorbs the kernel's own
#: parent-death reparenting race (see `_wait_for_confirmed_orphans`'s
#: docstring for the measured evidence this constant exists to fix, not
#: speculative hardening).
DEFAULT_DISCOVERY_GRACE_S = 3.0

#: Grace windows for the SIGTERM-then-SIGKILL escalation once `serve` is
#: confirmed gone, mirroring `PiRpcConnector.close`'s own 5s (3s + 2s)
#: shape in `adapters/outbound/harness/pi.py` so a harness child sees the
#: same bounded teardown whichever path reaped it.
DEFAULT_TERM_GRACE_S = 3.0
DEFAULT_KILL_GRACE_S = 2.0

#: PID a reparented-to-init process reports as its parent on every platform
#: this module runs on (POSIX only - see `run_watchdog`'s caller in
#: `serve.py`, which gates spawning this module on `os.name == "posix"`).
_INIT_PID = 1


def _ps_snapshot() -> list[tuple[int, int]]:
    """`(pid, ppid)` for every process visible to this user, via `ps -A`.

    Only pid/ppid are read - this module never inspects a command string
    (see the module docstring's discussion of why a name grep is exactly
    the mistake EV-OPS-001 already made once)."""
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid="],
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout
    rows: list[tuple[int, int]] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1])))
        except ValueError:
            continue
    return rows


def _descendants(root_pid: int, snapshot: list[tuple[int, int]]) -> set[int]:
    """Every pid transitively parented under `root_pid` in `snapshot`."""
    children: dict[int, list[int]] = {}
    for pid, ppid in snapshot:
        children.setdefault(ppid, []).append(pid)
    out: set[int] = set()
    frontier = [root_pid]
    while frontier:
        pid = frontier.pop()
        for child in children.get(pid, ()):
            if child not in out:
                out.add(child)
                frontier.append(child)
    return out


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _ppid_of(pid: int, snapshot: list[tuple[int, int]]) -> int | None:
    for p, ppid in snapshot:
        if p == pid:
            return ppid
    return None


def _is_group_leader(pid: int) -> bool:
    """True if `pid` is its own process-group leader (`getpgid(pid) ==
    pid`). Every harness connector in this codebase spawns its child with
    `start_new_session=True` specifically so its `close()` can `killpg` the
    whole tree (see `pi.py::_terminate_group`/`_kill_group`) - this mirrors
    that same escalation here. Guarded rather than assumed: `killpg`-ing a
    pid that is NOT a group leader would signal every OTHER member of
    whatever group it happens to belong to, which this module must never
    risk for a candidate it only knows via a PPID walk."""
    try:
        return os.getpgid(pid) == pid
    except OSError:
        return False


def _signal_one(pid: int, sig: "signal.Signals") -> None:
    if _is_group_leader(pid):
        try:
            os.killpg(pid, sig)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        os.kill(pid, sig)
    except OSError:
        pass


def _wait_for_confirmed_orphans(
    candidates: set[int], *, discovery_grace_s: float
) -> list[int]:
    """The subset of `candidates` that are alive AND reparented to PID 1 -
    the only pids this module will ever touch (see the module docstring's
    "why only PID-alive-and-reparented-to-1" note) - discovered by POLLING
    rather than a single snapshot.

    Honest provenance for this retry loop, so it is not oversold: repeated
    live-SIGKILL reproduction during this fix's own development DID show
    intermittent failures to reap (see the task's failing-first evidence).
    That flakiness was root-caused to a DIFFERENT, fully confirmed defect -
    this module briefly included ITS OWN pid among the reap candidates
    (fixed in `run_watchdog` below with an explicit `self_pid` exclusion,
    now also enforced here) - and once that was fixed, 30/30 repeated live
    reproductions passed with the single-shot version of this check still
    in place. The kernel-reparenting race this loop guards against was
    never itself directly observed (no captured run ever showed a
    candidate settle at a non-1, non-dead PPID); it remains a real,
    physically-possible window in principle - `os.getppid()` flipping in
    THIS process and the kernel finishing reparenting of a SIBLING process
    are two separate events with no ordering guarantee between them - but
    is retained here as cheap, bounded, defensive polling for an unproven
    edge case, not as a fix for a measured one. Do not cite this as
    empirically necessary; the self-exclusion fix is what the evidence
    actually supports.

    Every candidate here is, by construction, a former descendant of a
    `serve` process THIS function's caller has already confirmed is gone
    (`run_watchdog` only calls this after its own reparenting fires) - so a
    still-alive, not-yet-PPID-1 candidate can only be mid-reparent, never
    legitimately re-parented to something else (nothing in this system
    re-parents a live process to a NEW legitimate owner). Anything still
    alive and unsettled once `discovery_grace_s` elapses is therefore
    still treated as ours to reap rather than given up on."""
    pending = set(candidates)
    orphans: set[int] = set()
    deadline = time.monotonic() + discovery_grace_s
    while pending and time.monotonic() < deadline:
        snapshot = _ps_snapshot()
        settled = set()
        for pid in pending:
            if not _pid_alive(pid):
                settled.add(pid)  # gone on its own - nothing left to reap
                continue
            if _ppid_of(pid, snapshot) == _INIT_PID:
                orphans.add(pid)
                settled.add(pid)
        pending -= settled
        if pending:
            time.sleep(0.1)
    # See the docstring above: still-alive-and-unsettled after the grace
    # window is still ours, not "not an orphan after all".
    orphans.update(pid for pid in pending if _pid_alive(pid))
    return list(orphans)


def _wait_all_dead(pids: list[int], deadline: float) -> bool:
    while time.monotonic() < deadline:
        if not any(_pid_alive(p) for p in pids):
            return True
        time.sleep(0.1)
    return not any(_pid_alive(p) for p in pids)


def reap_orphans(
    candidates: set[int],
    *,
    discovery_grace_s: float = DEFAULT_DISCOVERY_GRACE_S,
    term_grace_s: float = DEFAULT_TERM_GRACE_S,
    kill_grace_s: float = DEFAULT_KILL_GRACE_S,
) -> list[int]:
    """Bounded discovery-then-SIGTERM-then-SIGKILL escalation against every
    confirmed orphan in `candidates`. Returns the pids actually reaped
    (dead by the end of this call). Never blocks past `discovery_grace_s +
    term_grace_s + kill_grace_s` regardless of outcome - see the module
    docstring's "bounded lifetime" section.

    ``os.getpid()`` (THIS process) is always excluded, defensively, even
    though `run_watchdog` (the only current caller) already excludes it
    from `last_descendants` before it ever reaches here. This is not
    redundant belt-and-suspenders for its own sake: a version of this
    module WITHOUT this exclusion is the confirmed root cause of the
    failing-first evidence's own flakiness (a watchdog signalling itself
    to death mid-escalation, before ever reaching the real target - see
    `run_watchdog`'s docstring). That defect had no deterministic
    regression test, only an integration test that failed ~50% of the
    time; enforcing the invariant HERE, at the one function that actually
    sends signals, and pairing it with a same-process unit test
    (`test_reap_orphans_never_signals_itself` in this module's own test
    file) closes that gap regardless of what any future caller's
    discovery logic does or forgets to do."""
    candidates = set(candidates) - {os.getpid()}
    if not candidates:
        return []
    orphans = _wait_for_confirmed_orphans(
        candidates, discovery_grace_s=discovery_grace_s
    )
    if not orphans:
        return []

    for pid in orphans:
        _signal_one(pid, signal.SIGTERM)
    _wait_all_dead(orphans, time.monotonic() + term_grace_s)

    still_alive = [p for p in orphans if _pid_alive(p)]
    if still_alive:
        for pid in still_alive:
            _signal_one(pid, signal.SIGKILL)
        _wait_all_dead(still_alive, time.monotonic() + kill_grace_s)

    return [p for p in orphans if not _pid_alive(p)]


def run_watchdog(
    serve_pid: int,
    *,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    discovery_grace_s: float = DEFAULT_DISCOVERY_GRACE_S,
    term_grace_s: float = DEFAULT_TERM_GRACE_S,
    kill_grace_s: float = DEFAULT_KILL_GRACE_S,
) -> list[int]:
    """Poll `serve_pid`'s descendant set while THIS process's own parent is
    still `serve_pid` (see the module docstring's "how serve is gone is
    detected" section for why `os.getppid()` and not `os.kill(serve_pid,
    0)`); once reparented, reap whatever was last seen. Returns the pids
    actually reaped, for the caller's own bookkeeping (tests read this
    directly; the `__main__` entry point below discards it - this process
    has no stdout to report to by construction, see `serve.py`'s spawn
    call)."""
    self_pid = os.getpid()
    last_descendants: set[int] = set()
    while True:
        if os.getppid() != serve_pid:
            break
        snapshot = _ps_snapshot()
        # THE DISCOVERY RACE THIS BRACKET CLOSES: `os.getppid()` can flip
        # to 1 (kernel reparenting `serve`'s dead children, including this
        # watchdog itself) at any point AROUND `_ps_snapshot()`'s `ps -A`
        # fork+exec - that call is not instantaneous. A snapshot taken
        # while (or after) that flip has already happened is not "empty
        # because the descendants really exited" - it is EMPTY (or
        # partially, silently truncated) because `ps -A` no longer sees
        # `serve_pid`'s subtree at all once `serve` is gone; the still-
        # alive `pi` process and its wrapper are simply no longer
        # discoverable BY WALKING FROM `serve_pid`, even though they are
        # very much alive, just already reparented to init. Checking
        # `os.getppid()` only BEFORE the snapshot (the old code) misses
        # exactly this: the loop condition can pass, then the flip lands
        # mid-`ps`, and the resulting corrupted snapshot is what
        # unconditionally overwrote `last_descendants` next.
        #
        # The fix re-reads `os.getppid()` again immediately AFTER the
        # snapshot and discards the snapshot (via `break`, keeping
        # whatever `last_descendants` already held) unless BOTH reads
        # agree `serve` was still this process's parent. That is a
        # bracket around the snapshot, not a check on its contents - and
        # deliberately not "treat an empty snapshot as untrustworthy":
        # children legitimately DO all exit sometimes while `serve` is
        # still alive, and in that case `last_descendants` MUST be
        # allowed to go empty (the bracket here passes correctly, both
        # `getppid()` reads see `serve_pid`, and the assignment below
        # takes effect - see `test_watchdog_bracket_accepts_legitimate_
        # empty_snapshot` in this module's test file). An "empty means
        # keep the old set" rule would get that legitimate case wrong
        # (pinning a stale, possibly since-recycled set of pids
        # indefinitely) while ALSO failing to catch the non-empty-but-
        # truncated variant of this same race (some descendants already
        # reparented out of the walk, others not yet). Bracketing the
        # read instead of inspecting the result catches both, and bounds
        # the staleness of a discarded snapshot to at most one
        # `poll_interval_s` - the same bound the pre-existing "spawned
        # and killed within one poll interval" blind spot already
        # discloses (module docstring), not a new or wider one.
        #
        # `_descendants` walks the WHOLE tree under `serve_pid`, which
        # includes THIS process (a direct child of `serve_pid` by
        # construction) and, transiently, `_ps_snapshot`'s own `ps -A`
        # child (which lists itself in its own output while it runs).
        # Both must never be reap candidates: once `serve` dies this
        # process is itself legitimately reparented to init and would
        # otherwise pass the exact same "alive + PPID 1" orphan test it
        # applies to everything else below - and having signalled itself
        # first in that loop (self-SIGTERM, delivered immediately) is
        # EXACTLY how an earlier version of this fix silently died before
        # ever reaching the real target. Measured empirically: roughly 1
        # run in 10-20 of repeated live SIGKILL reproduction during this
        # fix's own development, silently, with no traceback (a delivered
        # SIGTERM is not a Python exception) - this is not speculative.
        if os.getppid() != serve_pid:
            break
        last_descendants = _descendants(serve_pid, snapshot) - {self_pid}
        time.sleep(poll_interval_s)
    return reap_orphans(
        last_descendants,
        discovery_grace_s=discovery_grace_s,
        term_grace_s=term_grace_s,
        kill_grace_s=kill_grace_s,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="okto-nexus-harness-orphan-watchdog",
        description=(
            "Internal helper spawned by `okto-nexus serve` (EV-OPS-001 "
            "SIGKILL gap). Not a public CLI entry point."
        ),
    )
    parser.add_argument("--serve-pid", type=int, required=True)
    parser.add_argument(
        "--poll-interval-s", type=float, default=DEFAULT_POLL_INTERVAL_S
    )
    parser.add_argument(
        "--discovery-grace-s", type=float, default=DEFAULT_DISCOVERY_GRACE_S
    )
    parser.add_argument("--term-grace-s", type=float, default=DEFAULT_TERM_GRACE_S)
    parser.add_argument("--kill-grace-s", type=float, default=DEFAULT_KILL_GRACE_S)
    args = parser.parse_args(argv)

    run_watchdog(
        args.serve_pid,
        poll_interval_s=args.poll_interval_s,
        discovery_grace_s=args.discovery_grace_s,
        term_grace_s=args.term_grace_s,
        kill_grace_s=args.kill_grace_s,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
