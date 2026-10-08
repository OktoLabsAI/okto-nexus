"""Production composition: canonical delivery, durable dispatch and exclusive consumption."""
import threading
import time
import json
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

import pytest

from okto_nexus.application.runtime_dispatcher import RuntimeDispatcher
from okto_nexus.domain.base import iso_plus
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, wait_sent, tool
from runtime_http_client import process_tool

runtime = runtime_fixture


def stop_dispatcher(runtime):
    deps = runtime[0]
    old = deps.runtime_dispatcher
    old.close()
    return old


def restart_dispatcher(runtime, old):
    deps = runtime[0]
    new = RuntimeDispatcher(connection_factory=deps.connection_factory, repo=old.repo,
        clock=deps.clock, validate=old.validate, dispatch=old.dispatch)
    deps.runtime_dispatcher = new
    assert new.start()
    return new


def operation(runtime, operation_id):
    deps = runtime[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return deps.runtime_dispatcher.repo.get(uow, operation_id)


def wait_status(runtime, operation_id, status):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        row = operation(runtime, operation_id)
        if row["status"] == status:
            return row
        time.sleep(0.01)
    pytest.fail(f"operation remained {row['status']}, expected {status}")










@pytest.mark.parametrize("previous_status", ["SENDING", "SENT_UNCONFIRMED", "ACCEPTED"])
def test_p06_takeover_never_replays_a_send_intent(runtime, previous_status):
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    old = stop_dispatcher(runtime)
    result = send_message(runtime)
    operation_id = result["runtime_operations"][0]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE delivery_outbox SET status=?,owner_epoch=?,attempt_id='old-attempt' WHERE operation_id=?",
                               (previous_status, old.epoch, operation_id))
    new = restart_dispatcher(runtime, old)
    assert operation(runtime, operation_id)["status"] == "OUTCOME_UNKNOWN"
    new.scan_once()
    assert peers[0].sent == []
    with deps.connection_factory.unit_of_work() as uow:
        assert not new.repo.observe(uow, operation_id=operation_id, epoch=old.epoch, attempt_id="old-attempt",
            expected="SENDING", status="ACCEPTED", now=deps.clock.now_iso())
