"""Managed work uses the canonical handoff, inbox reservation and dispatcher."""
from test_pr34_remediation import runtime as runtime_fixture, tool
from okto_nexus.application.auth import AgentKeyAuthService
from test_runtime_grants import issue
from test_runtime_commands import codex_session
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest

runtime = runtime_fixture




def work(runtime, **options):
    deps, client, root, _, _, caller = runtime
    with deps.connection_factory.unit_of_work() as uow:
        key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker")
    created = tool(client, caller, "handoff_create", {
        "project_root": root, "from_agent_id": "caller", "visibility": "eligible",
        "target": {"strategy": "direct", "agent_id": "worker"}, "payload": "fixture managed work", **options,
    })
    assert created["ok"], created
    return created["data"]["handoff_id"], key




def claim(runtime, hid, grant, key, *, request_key="fixture-work", epoch=None):
    return tool(runtime[1], key, "handoff_claim", {
        "project_root": runtime[2], "handoff_id": hid, "agent_id": "worker",
        "runtime_endpoint_id": "endpoint-codex", "execution_grant_id": grant["grant_id"],
        "idempotency_key": request_key, **({"claim_epoch": epoch} if epoch else {}),
    })


def wait_result(runtime, op):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_results WHERE operation_id=?", (op,)).fetchone()
            if row:
                return dict(row)
        time.sleep(.01)
    raise AssertionError("No durable native result")
