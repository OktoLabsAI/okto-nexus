"""Birth ownership replaces the historical scanner; retain its pure regressions."""
import os
from okto_nexus.adapters.inbound.cli import harness_orphan_watchdog
from runtime_serve_shutdown_fixture import ServeFixture


def test_sigkill_with_live_session_reaps_owned_tree_and_guardian(tmp_path):
    server = ServeFixture(tmp_path)
    try:
        server.open()
        server.stop("kill")
    finally:
        server.close()


def test_serve_does_not_launch_legacy_pid_scanner():
    from okto_nexus.adapters.inbound.cli.serve import _spawn_harness_orphan_watchdog
    assert _spawn_harness_orphan_watchdog({}) is None


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
