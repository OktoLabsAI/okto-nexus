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
