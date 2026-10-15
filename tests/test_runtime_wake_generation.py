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
