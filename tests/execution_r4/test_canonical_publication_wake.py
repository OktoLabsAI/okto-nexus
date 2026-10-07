"""A native commit wakes result publication even while a scan is in progress."""
import threading

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_result_publication import emit, wait_result, current_turn
from test_canonical_grant_regressions import mcp_helpers


def test_native_commit_during_active_publication_scan_is_not_lost(connected_local, monkeypatch):
    setup, binding, native = connected_local
    dispatcher = setup[0].runtime_dispatcher
    dispatcher.recovery_seconds = 60
    enable(setup, binding)
    entered, release = threading.Event(), threading.Event()
    original = dispatcher.publish_results
    calls = []
    def paused():
        calls.append(True)
        if len(calls) == 1:
            entered.set()
            assert release.wait(15)
            return 0
        return original()
    monkeypatch.setattr(dispatcher, "publish_results", paused)
    try:
        dispatcher.wake()
        assert entered.wait(3)
        assert send(setup, monkeypatch)["ok"]
        turn = current_turn(setup)
        wait_receipt(setup, turn)
        emit(setup, native, turn, "Result committed during the paused scan")
        row = wait_result(setup, "PENDING_AUTHORIZATION")
        assert row["publication_message_id"] is None
        # No manual wake after the native commit or release of this scan.
        release.set()
        published = wait_result(setup, "PUBLISHED")
        assert published["publication_message_id"] and len(calls) >= 2
        assert native.opens == 1 and len(native.native.sent) == 1
    finally:
        release.set()
