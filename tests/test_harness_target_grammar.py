"""Canonical target routing through authenticated production serve.

Legacy callback/TTL relay assertions are covered by test_runtime_relay,
test_runtime_causality and test_runtime_relay_process_restart. See the explicit
migration map in P11_TARGET_GRAMMAR_MIGRATION.md; no implicit Agent registration.
"""
import json
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import wait_status

runtime = runtime_fixture




def test_failed_transport_preserves_durable_delivery_and_blocks_duplicate_lane(runtime, monkeypatch):
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    attempts = []
    def uncertain_write(session, command):
        attempts.append(command)
        raise OSError("fixture transport failed after potentially writing bytes")
    monkeypatch.setattr(peers[0], "send", uncertain_write)
    first = send_message(runtime)
    wait_status(runtime, first["runtime_operations"][0], "OUTCOME_UNKNOWN")
    second = send_message(runtime, body="independent logical delivery")
    wait_status(runtime, second["runtime_operations"][0], "PENDING")
    assert first["delivered_count"] == second["delivered_count"] == 1
    assert len(attempts) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT status,consumer_kind FROM message_deliveries ORDER BY created_at").fetchall()
        assert len(rows) == 2
        assert all(r["status"] == "unread" and r["consumer_kind"] == "push" for r in rows)
