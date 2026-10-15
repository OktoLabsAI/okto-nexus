"""Explicit structured work decisions through real native pipe and serve."""
import sys
import time
import threading

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_grants import issue
from test_runtime_handoff_dispatch import work

runtime = runtime_fixture


def native_work_peer(runtime, *, action="complete", mutation=""):
    from legacy_native_fixture.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    transform = '''
    envelope = json.loads(text.split("\\n", 1)[1])
    decision = {"schema_version": 1, "operation_id": envelope["operation_id"],
                "handoff_id": envelope["handoff_id"], "claim_epoch": envelope["claim_epoch"],
                "action": ACTION, VALUE_KEY: "fixture evidence"}
    MUTATION
    text = json.dumps({"nexus_work_result": decision})
'''.replace("ACTION", repr(action)).replace("VALUE_KEY", repr("result" if action == "complete" else "reason")).replace("MUTATION", mutation or "pass")
    source = _FAKE_SERVER_SOURCE.replace('    item_id = "item_" + turn_id', transform + '\n    item_id = "item_" + turn_id')
    deps, _, root, _, _, _ = runtime
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source], cwd=root, env=kwargs["backend"]["env"])


def dispatch(runtime, hid, *, structured=True):
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    response = tool(runtime[1], runtime[5], "handoff_claim", {
        "project_root": runtime[2], "handoff_id": hid, "agent_id": "worker",
        "runtime_endpoint_id": "endpoint-codex", "execution_grant_id": grant["grant_id"],
        "idempotency_key": "structured-work",
        **({"completion_mode": "structured_result_v1"} if structured else {})})
    assert response["ok"], response
    return response["data"]["runtime_operation"]["operation_id"], grant


def state(runtime, hid, expected):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            row = dict(uow.connection.execute("SELECT * FROM handoffs WHERE handoff_id=?", (hid,)).fetchone())
        if row["status"] == expected:
            return row
        time.sleep(.01)
    pytest.fail(f"Expected {expected}, observed {row['status']}")




def outcome(runtime, op):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_work_outcomes WHERE operation_id=?", (op,)).fetchone()
        if row:
            return dict(row)
        time.sleep(.01)
    pytest.fail("No durable work outcome")
