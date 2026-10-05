"""Commit wakes remain outstanding across waits and bounded dispatch scans."""
import threading
import time

from okto_nexus.application.runtime_dispatcher import RuntimeDispatcher
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message
from test_runtime_outbox import wait_status

runtime = runtime_fixture


def test_generation_keeps_wakes_before_wait_and_during_processing():
    dispatcher = RuntimeDispatcher(connection_factory=None, repo=None, clock=None,
                                   validate=None, dispatch=None)
    observed = 0
    for _ in range(1000):
        dispatcher.wake()
    observed = dispatcher._wait_for_wake(observed, timeout=0)
    assert observed == 1000
    # This signal arrives after the consumer's snapshot but before its next wait.
    dispatcher.wake()
    assert dispatcher._wait_for_wake(observed, timeout=0) == 1001
    assert dispatcher._wait_for_wake(1001, timeout=0) == 1001


def test_wake_during_scan_drains_without_waiting_for_recovery(runtime):
    deps = runtime[0]
    assert open_rest(runtime).status_code == 200
    scanned, release, scanned_again = threading.Event(), threading.Event(), threading.Event()
    # A wake raised during the owner's scan must trigger another scan immediately.
    new = deps.runtime_dispatcher
    new.recovery_seconds = 3600
    original_scan = new.scan_once
    first = True

    def paused_scan():
        nonlocal first
        original_scan()
        if first:
            first = False
            scanned.set()
            assert release.wait(3)
        else:
            scanned_again.set()

    new.scan_once = paused_scan
    try:
        new.wake()
        assert scanned.wait(3)
        result = send_message(runtime)
        started = time.monotonic()
        new.wake()
        release.set()
        assert scanned_again.wait(3), "committed wake waited for periodic recovery"
        wait_status(runtime, result["runtime_operations"][0], "SENT_UNCONFIRMED")
        assert time.monotonic() - started < 3
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
    finally:
        release.set()
