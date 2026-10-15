"""Retry only an observed transient pre-write failure, on the same logical intent."""
import time
import pytest

from okto_nexus.domain.base import iso_plus, iso_to_epoch
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import operation, wait_status
from test_runtime_operation_reconciliation import recovery

runtime = runtime_fixture


def busy_lane(runtime, monkeypatch):
    deps, _, _, peers, _, _ = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    peer = peers[0]
    peer.delivery_event_phase = lambda event: {"turn_started": "started", "turn_completed": "terminal"}.get(event.kind)
    # A trusted legacy/internal turn is active in the adapter, but has no
    # canonical outbox operation. This exercises the real adapter's final fence.
    deps.harness_supervisor.send(session, "send_turn", {"text": "existing internal turn"})
    peer.push_event(kind="turn_started")
    clock = [deps.clock.now_iso()]
    monkeypatch.setattr(deps.clock, "now_iso", lambda: clock[0])
    return peer, clock
