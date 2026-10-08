"""Known capture failure must stop new executable admission across writers."""
import errno
import os
import sqlite3

import pytest

from okto_nexus.domain.harness import HarnessEvent
from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool, send_message, wait_sent
from runtime_http_client import process_tool
from test_runtime_commands import wait_operation

runtime = runtime_fixture


@pytest.fixture
def capture_runtime(runtime):
    ingress = runtime[0].harness_supervisor.event_ingress
    quota = ingress.journal.quota
    try:
        yield runtime
    finally:
        # The deliberately damaged disposable journal must be reopened before
        # the common fixture requests normal lifecycle capture during cleanup.
        # This is test teardown only, never evidence of automatic recovery.
        with ingress._project_lock:
            ingress.journal.close()
            ingress.journal.quota = quota
            ingress.journal.start()
