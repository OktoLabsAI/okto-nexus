"""Results enter the canonical message policy path, never native fan-out."""
import time
import threading

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_commands import codex_session

runtime = runtime_fixture


def result(runtime, operation_id, state):
    deps = runtime[0]
    deadline = time.monotonic() + 5
    row = None
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            found = uow.connection.execute("SELECT * FROM runtime_results WHERE operation_id=?", (operation_id,)).fetchone()
            row = dict(found) if found else None
        if row and row["publication_state"] == state:
            return row
        time.sleep(.01)
    pytest.fail(str(row))
