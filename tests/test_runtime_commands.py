"""Durable administrative command admission through production surfaces."""
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool

runtime = runtime_fixture






def wait_operation(runtime, operation_id, predicate):
    _, client, _, _, operator, _ = runtime
    return wait_command(client, operator, operation_id, predicate)


def wait_command(client, operator, operation_id, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/harness/operations/{operation_id}", headers={"x-api-key": operator})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        if predicate(data):
            return data
        time.sleep(.01)
    assert predicate(data), data


def wait_close_result(client, operator, response):
    data = response.json()["data"] if hasattr(response, "json") else response["data"]
    operation = wait_command(client, operator, data["operation_id"],
        lambda row: row["state"] in {"DONE", "OUTCOME_UNKNOWN", "REJECTED"})
    assert operation["result"], operation
    return operation["result"]


def codex_session(runtime, *, outcome="completed"):
    from legacy_native_fixture.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, _, operator, _ = runtime
    source = _FAKE_SERVER_SOURCE.replace('"status": "completed"', '"status": "' + outcome + '"')
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source.replace('"result": {"userAgent": "okto-nexus/0.156.1"}',
            '\"result\": {\"userAgent\": \"okto-nexus/0.156.1 fixture\"}', 1)], cwd=root, env=kwargs["backend"]["env"])
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator},
        json={"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert response.status_code == 200, response.text
    return response.json()["data"]["session_id"]
