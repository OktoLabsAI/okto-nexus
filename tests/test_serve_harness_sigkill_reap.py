"""LIMITATION 1 (EV-OPS-001, SIGKILL gap): `harness_orphan_watchdog.py`.

`tests/test_serve_harness_shutdown_reap.py` closes EV-OPS-001 for clean
exit, SIGINT and SIGTERM - all three drive `serve.py`'s own `finally` block,
which reaps every live harness child directly. This file covers the one
path that CANNOT run any code in the killed process at all: `SIGKILL`. The
fix under test is a standalone watchdog process (`adapters/inbound/cli/
harness_orphan_watchdog.py`) `serve.py` spawns alongside itself; see that
module's own docstring for the full design rationale (why it cannot ask
`HarnessSupervisor` for child PIDs, why detection is a PPID walk rather
than a name grep, why `serve` is "gone" is detected via this watchdog's OWN
`os.getppid()` rather than polling the dead pid, and the bounded-lifetime
argument for why the watchdog itself does not become a second leak).

Helper functions below are DELIBERATELY duplicated from `tests/
test_serve_harness_shutdown_reap.py` rather than imported from it - this
task's files are `serve.py`, the one new module above, and this test file
alone; the sibling test file belongs to no one to edit for this task's
purpose, and importing test-private helpers across files is not a shape
this repo uses. Same reasoning, same fake `pi` stub (the REAL `pi` binary
self-exits on stdin EOF regardless of whether any fix exists - see the
sibling file's module docstring - so it cannot discriminate a real fix from
incidental death and is unusable as this file's fixture either).

## Why `_assert_eventually_reaped` is NOT the sibling file's
`_assert_no_orphan`

`_assert_no_orphan` (sibling file) fails IMMEDIATELY the instant it
observes the child alive with PPID 1 - correct for SIGINT/SIGTERM/clean,
where `serve`'s own reap runs BEFORE the child could ever be orphaned, so
any observed orphan there is already the defect. SIGKILL is structurally
different: the child WILL be alive with PPID 1 for a real, expected
stretch of wall-clock time between the kill landing and the independent
watchdog noticing, reaping and confirming it dead (bounded by the
watchdog's poll interval plus its SIGTERM-then-SIGKILL grace windows -
`harness_orphan_watchdog.py`'s own docstring states this explicitly as a
disclosed, non-zero bound, not something this design claims to close to
zero). Reusing `_assert_no_orphan` here would fail the test on that
EXPECTED transient window, so this file has its own helper that treats
"alive with PPID 1" as an allowed, in-progress state and only fails if the
child is STILL alive at the end of a timeout wide enough to cover the
watchdog's own bounded grace windows.

## Why this file also has a subprocess-free unit test

The root cause behind this fix's own failing-first flakiness (see the task
write-up) was `harness_orphan_watchdog.reap_orphans` including the
watchdog's OWN pid among its reap candidates - it would signal itself
(SIGTERM, delivered immediately) before ever reaching the real target,
dying silently with no traceback. The live-process tests above exercise
the fixed behaviour end-to-end, but they only catch a regression of that
specific defect probabilistically (candidate signalling order is a set
iteration, so a reintroduced self-inclusion bug fails roughly half of
these runs, not all of them - exactly what was observed before the real
cause was found). `test_reap_orphans_never_signals_itself` below is a
deterministic, in-process regression test for that one invariant:
`reap_orphans` must always exclude `os.getpid()`, every time, not "usually".
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from okto_nexus.adapters.inbound.cli import harness_orphan_watchdog

httpx = pytest.importorskip("httpx")

_WATCHDOG_MODULE = "okto_nexus.adapters.inbound.cli.harness_orphan_watchdog"

# Fast, test-only poll interval for the watchdog (production default is 1s -
# see harness_orphan_watchdog.DEFAULT_POLL_INTERVAL_S - a deliberate
# cost/latency trade-off documented there). This keeps the SIGKILL test's
# detection-latency bound small without changing the mechanism under test.
_TEST_POLL_INTERVAL_S = "0.15"

_FAKE_PI_SOURCE = '''#!/usr/bin/env python3
import json
import sys
import time

for line in iter(sys.stdin.readline, ""):
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    verb = msg.get("type")
    if verb:
        resp = {"type": "response", "command": verb, "success": True, "data": {}}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()

# Real EOF handling ends here (real `pi` self-exits at this point). Block
# until a signal kills us instead, so "the child is dead" is unambiguous
# evidence that a reap path (serve's own, or this file's watchdog) did it.
while True:
    time.sleep(3600)
'''


def _materialize_fake_pi(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "pi"
    script.write_text(_FAKE_PI_SOURCE, encoding="utf-8")
    script.chmod(0o755)
    return script


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _ps_snapshot() -> list[tuple[int, int, str]]:
    """`(pid, ppid, command)` for every process visible to this user."""
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,command="],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    rows = []
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        command = parts[2] if len(parts) > 2 else ""
        rows.append((pid, ppid, command))
    return rows


def _descendants(root_pid: int, snapshot: list[tuple[int, int, str]]) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, ppid, _ in snapshot:
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


def _ppid_of(pid: int, snapshot: list[tuple[int, int, str]]) -> int | None:
    for p, ppid, _ in snapshot:
        if p == pid:
            return ppid
    return None


@dataclass
class _Server:
    process: subprocess.Popen
    base_url: str
    home_dir: Path


def _spawn_server(tmp_path: Path) -> _Server:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    bin_dir = tmp_path / "bin"
    _materialize_fake_pi(bin_dir)
    port = _free_port()
    env = dict(os.environ)
    env["OKTO_NEXUS_HOME"] = str(home_dir)
    env["OKTO_NEXUS_DB_PATH"] = str(home_dir / "nexus.db")
    env["OKTO_NEXUS_PORT"] = str(port)
    env["OKTO_NEXUS_HOST"] = "127.0.0.1"
    env["OKTO_NEXUS_NO_BANNER"] = "1"
    env["OKTO_NEXUS_LOG_LEVEL"] = "warning"
    env["OKTO_NEXUS_HARNESS_WATCHDOG_POLL_INTERVAL_S"] = _TEST_POLL_INTERVAL_S
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    cmd = [sys.executable, "-m", "okto_nexus.adapters.inbound.mcp.server", "serve"]
    process = subprocess.Popen(
        cmd,
        cwd=str(home_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=(os.name == "posix"),
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30.0
    ready = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out, err = process.communicate(timeout=5)
            raise AssertionError(
                f"serve exited early (code {process.returncode})\n{out}\n{err}"
            )
        try:
            resp = httpx.get(f"{base_url}/api/v1/info", timeout=1.0)
            if resp.status_code == 200:
                ready = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    if not ready:
        _hard_kill(process)
        raise AssertionError(f"serve did not become ready on {base_url}")
    return _Server(process=process, base_url=base_url, home_dir=home_dir)


def _hard_kill(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, OSError, PermissionError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _open_pi_session(base_url: str, project_root: Path) -> str:
    resp = httpx.post(
        f"{base_url}/api/v1/harness/sessions",
        json={
            "agent_id": "ev_ops_001_sigkill_probe",
            "kind": "pi",
            "project_root": str(project_root),
            "backend": {"provider": "zai", "model": "glm-5.3"},
        },
        timeout=30.0,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["session_id"]


def _find_descendant_by_argv_token(
    server_pid: int, *, exact_token: str, timeout_s: float = 15.0
) -> int:
    """Poll for a descendant of `server_pid` whose command line has a token
    with the given exact basename. `exact_token` here is always a value
    that cannot collide with a real harness binary name (`"pi"` is never
    passed - see module docstring); this is a TEST convenience to locate
    which pid to watch, never the orphan-detection MECHANISM itself, which
    (both in `harness_orphan_watchdog.py` and in the assertions below) is
    PPID-based."""
    deadline = time.monotonic() + timeout_s
    last_descendants: set[int] = set()
    while time.monotonic() < deadline:
        snap = _ps_snapshot()
        descendants = _descendants(server_pid, snap)
        last_descendants = descendants
        for pid, ppid, command in snap:
            if pid not in descendants:
                continue
            tokens = command.strip().split()
            if any(tok.rsplit("/", 1)[-1] == exact_token for tok in tokens):
                return pid
        time.sleep(0.2)
    raise AssertionError(
        f"no descendant of {server_pid} with a {exact_token!r} argv token "
        f"found within {timeout_s}s (last descendants: {last_descendants})"
    )


def _find_pi_child(server_pid: int, timeout_s: float = 15.0) -> int:
    return _find_descendant_by_argv_token(server_pid, exact_token="pi", timeout_s=timeout_s)


def _find_watchdog_child(server_pid: int, timeout_s: float = 15.0) -> int:
    """The watchdog is invoked as `<python> -m <dotted module path>`, so its
    argv has no token whose basename is the module's own file name - match
    on the dotted module path token instead (still never `"pi"`)."""
    deadline = time.monotonic() + timeout_s
    last_descendants: set[int] = set()
    while time.monotonic() < deadline:
        snap = _ps_snapshot()
        descendants = _descendants(server_pid, snap)
        last_descendants = descendants
        for pid, ppid, command in snap:
            if pid not in descendants:
                continue
            if _WATCHDOG_MODULE in command:
                return pid
        time.sleep(0.2)
    raise AssertionError(
        f"no watchdog descendant ({_WATCHDOG_MODULE}) of {server_pid} found "
        f"within {timeout_s}s (last descendants: {last_descendants})"
    )


def _assert_eventually_reaped(pid: int, *, timeout_s: float) -> None:
    """Unlike the sibling file's `_assert_no_orphan`, being observed ALIVE
    with PPID 1 is an ALLOWED transient state here (see module docstring) -
    this only fails if `pid` is still alive once `timeout_s` elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.2)
    pytest.fail(
        f"pid={pid} still alive {timeout_s}s after the triggering shutdown; "
        f"the watchdog did not reap it in time"
    )


def _assert_eventually_gone(pid: int, *, timeout_s: float, what: str) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.2)
    pytest.fail(f"{what} pid={pid} is still alive {timeout_s}s after shutdown")


def _signal_serve_pid_only(server: _Server, sig: "signal.Signals") -> None:
    os.kill(server.process.pid, sig)


def test_sigkill_with_live_session_is_reaped_and_watchdog_self_terminates(tmp_path):
    """The core LIMITATION 1 case: `SIGKILL` on `serve` with a live harness
    session. Runs no code in the killed process by construction, so the
    ONLY thing that can reap the `pi` child is the independent watchdog.
    Also asserts the watchdog itself is gone afterwards (point: a watchdog
    that outlives its own job is a leak in its own right)."""
    server = _spawn_server(tmp_path)
    try:
        project = tmp_path / "project"
        project.mkdir()
        _open_pi_session(server.base_url, project)
        pi_pid = _find_pi_child(server.process.pid)
        watchdog_pid = _find_watchdog_child(server.process.pid)
        assert watchdog_pid != pi_pid

        os.kill(server.process.pid, signal.SIGKILL)
        server.process.wait(timeout=10)

        # Bound: poll-interval-to-notice + term_grace(3s) + kill_grace(2s) +
        # slack. Generous on purpose - this asserts eventual convergence,
        # not speed.
        _assert_eventually_reaped(pi_pid, timeout_s=20.0)
        _assert_eventually_gone(watchdog_pid, timeout_s=20.0, what="watchdog")
    finally:
        _hard_kill(server.process)


def test_clean_shutdown_stops_the_watchdog_promptly(tmp_path):
    """Companion to the SIGKILL case: on a path `serve` CAN run its own
    `finally` (explicit session close + SIGTERM here), `serve` itself is
    expected to stop the watchdog rather than leave it to self-detect - see
    `_stop_harness_orphan_watchdog` in `serve.py`. Confirms that happens
    promptly (well under the watchdog's own bounded reap window), i.e. the
    graceful paths do not regress into leaving an idle watchdog running."""
    server = _spawn_server(tmp_path)
    try:
        project = tmp_path / "project"
        project.mkdir()
        session_id = _open_pi_session(server.base_url, project)
        pi_pid = _find_pi_child(server.process.pid)
        watchdog_pid = _find_watchdog_child(server.process.pid)

        close = httpx.post(
            f"{server.base_url}/api/v1/harness/sessions/{session_id}/close",
            timeout=30.0,
        )
        assert close.status_code == 200, close.text

        _signal_serve_pid_only(server, signal.SIGTERM)
        server.process.wait(timeout=30)

        _assert_eventually_gone(pi_pid, timeout_s=15.0, what="pi child")
        # Explicit-stop path: this should be fast, not bounded by the
        # watchdog's own multi-second self-reap grace windows.
        _assert_eventually_gone(watchdog_pid, timeout_s=5.0, what="watchdog")
    finally:
        _hard_kill(server.process)


def test_sigterm_shutdown_stops_the_watchdog_promptly(tmp_path):
    """Same prompt-stop expectation as the clean-shutdown case above, on the
    SIGTERM path instead of an explicit close - the other path `serve`'s
    own `finally` runs on and therefore also explicitly stops the
    watchdog."""
    server = _spawn_server(tmp_path)
    try:
        project = tmp_path / "project"
        project.mkdir()
        _open_pi_session(server.base_url, project)
        pi_pid = _find_pi_child(server.process.pid)
        watchdog_pid = _find_watchdog_child(server.process.pid)

        _signal_serve_pid_only(server, signal.SIGTERM)
        server.process.wait(timeout=30)

        _assert_eventually_gone(pi_pid, timeout_s=15.0, what="pi child")
        _assert_eventually_gone(watchdog_pid, timeout_s=5.0, what="watchdog")
    finally:
        _hard_kill(server.process)


def test_reap_orphans_never_signals_itself(monkeypatch):
    """Deterministic, in-process regression test for this fix's confirmed
    root cause (see module docstring): `reap_orphans` must always exclude
    `os.getpid()` from its candidate set.

    Real signal delivery is monkeypatched to a recorder rather than left as
    the genuine `os.kill`/`os.killpg` calls. With the fix in place,
    `{os.getpid()}` is excluded before `reap_orphans` ever reaches the
    signalling code, so the recorder is never even invoked - but if this
    invariant regresses, `_signal_one` WOULD eventually be called with
    `os.getpid()` (the real, alive, non-orphaned pytest process, which
    `_wait_for_confirmed_orphans`'s own "still alive after the grace
    window is still ours" fallback would otherwise sweep in - see that
    function's docstring). Monkeypatching turns that regression into a
    normal, safe assertion failure instead of this test SIGTERM-ing the
    pytest process running it."""
    signalled: list[int] = []
    monkeypatch.setattr(
        harness_orphan_watchdog, "_signal_one", lambda pid, sig: signalled.append(pid)
    )

    result = harness_orphan_watchdog.reap_orphans(
        {os.getpid()},
        discovery_grace_s=0.2,
        term_grace_s=0.2,
        kill_grace_s=0.2,
    )

    assert result == []
    assert signalled == []


def test_run_watchdog_does_not_lose_candidates_to_snapshot_reparenting_race(
    monkeypatch,
):
    """Deterministic regression test for the traced defect: `_ps_snapshot()`
    can run AFTER the kernel has already reparented `serve`'s (SIGKILLed)
    descendants to init, even though the loop's OWN `os.getppid()` check
    just above it still saw `serve_pid` as the parent a moment earlier -
    `os.getppid()` flipping and the snapshot being taken are two separate
    events with no ordering guarantee between them once `serve` is gone.
    Pre-fix, that corrupted (empty) snapshot unconditionally overwrote
    `last_descendants`, so the real, still-alive target pid was silently
    dropped from the candidate set `reap_orphans` ever saw. This test makes
    that ordering deterministic (rather than relying on real CPU load to
    hit it ~10-13% of the time) by scripting `_ps_snapshot` to flip a fake
    `os.getppid()` as a SIDE EFFECT of the call that produces the
    already-reparented, empty-looking tree - i.e. the flip lands exactly
    between the loop's pre-snapshot check and the snapshot itself, which is
    the traced mechanism."""
    serve_pid = 424242
    target_pid = 555555
    real_getpid = os.getpid()

    state = {"ppid": serve_pid, "call": 0}

    def fake_getppid() -> int:
        return state["ppid"]

    def fake_snapshot() -> list[tuple[int, int]]:
        state["call"] += 1
        if state["call"] == 1:
            # Good snapshot: serve_pid -> target_pid, taken while `serve`
            # is still genuinely this process's parent.
            return [(serve_pid, 1), (target_pid, serve_pid), (real_getpid, serve_pid)]
        # Second call: the kernel reparenting race lands INSIDE this call -
        # `serve` (and this watchdog) have already been reparented to init
        # by the time `ps -A` actually runs, so `target_pid`'s edge under
        # `serve_pid` is gone from the tree even though `target_pid` is
        # still alive. Flipping `state["ppid"]` here, as a side effect of
        # the snapshot call, is what places the race exactly where the
        # trace says it happens - between the loop's leading `getppid()`
        # check and the moment `ps -A` output is actually produced.
        state["ppid"] = 1
        return [(target_pid, 1), (real_getpid, 1)]

    captured_candidates: list[set[int]] = []

    def fake_reap_orphans(candidates: set[int], **_kwargs) -> list[int]:
        captured_candidates.append(set(candidates))
        return []

    monkeypatch.setattr(harness_orphan_watchdog, "_ps_snapshot", fake_snapshot)
    monkeypatch.setattr(os, "getppid", fake_getppid)
    monkeypatch.setattr(harness_orphan_watchdog, "reap_orphans", fake_reap_orphans)

    harness_orphan_watchdog.run_watchdog(serve_pid, poll_interval_s=0.0)

    assert len(captured_candidates) == 1
    # The bracket must have discarded the second (corrupted, empty) call's
    # snapshot and kept the last snapshot proven to predate the flip - so
    # `target_pid` must still be in the candidate set `reap_orphans` sees.
    assert target_pid in captured_candidates[0]
    assert captured_candidates[0] == {target_pid}


def test_run_watchdog_legitimate_empty_snapshot_is_not_pinned_as_stale(monkeypatch):
    """Companion to the race-regression test above: proves the fix does NOT
    special-case "empty means keep the old set". When descendants exit
    normally WHILE `serve` is still alive (no reparenting race in play -
    `os.getppid()` reads the same value both before and after the
    snapshot), `last_descendants` must be allowed to correctly become
    empty rather than pinning a stale, possibly since-recycled pid set."""
    serve_pid = 424243
    target_pid = 555556
    real_getpid = os.getpid()

    state = {"call": 0}

    def fake_getppid() -> int:
        # Never flips in this scenario - `serve` stays alive throughout;
        # only its children exit.
        return serve_pid

    def fake_snapshot() -> list[tuple[int, int]]:
        state["call"] += 1
        if state["call"] == 1:
            return [(serve_pid, 1), (target_pid, serve_pid), (real_getpid, serve_pid)]
        if state["call"] == 2:
            # The child legitimately exited - no race, `serve` still alive.
            return [(serve_pid, 1), (real_getpid, serve_pid)]
        # Third call ends the loop via the module-level flip below.
        return [(serve_pid, 1), (real_getpid, serve_pid)]

    captured_candidates: list[set[int]] = []

    def fake_reap_orphans(candidates: set[int], **_kwargs) -> list[int]:
        captured_candidates.append(set(candidates))
        return []

    call_count = {"n": 0}
    real_fake_getppid = fake_getppid

    def limited_getppid() -> int:
        call_count["n"] += 1
        # Exit the loop after the third snapshot has been taken (the
        # SECOND pass already proved the legitimate-empty case; stop here
        # so the test terminates deterministically).
        if state["call"] >= 3:
            return 1
        return real_fake_getppid()

    monkeypatch.setattr(harness_orphan_watchdog, "_ps_snapshot", fake_snapshot)
    monkeypatch.setattr(os, "getppid", limited_getppid)
    monkeypatch.setattr(harness_orphan_watchdog, "reap_orphans", fake_reap_orphans)

    harness_orphan_watchdog.run_watchdog(serve_pid, poll_interval_s=0.0)

    assert len(captured_candidates) == 1
    # The legitimate empty set must be what reap_orphans sees - not the
    # stale first snapshot's target_pid.
    assert captured_candidates[0] == set()
