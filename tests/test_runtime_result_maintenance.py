"""Operator recovery of private files never repeats native inference."""
from pathlib import Path

from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_artifact_durability import large_output_session
from test_runtime_result_publication import result
from test_governance import _attach, _rule

runtime = runtime_fixture


def request(runtime, **body):
    _, client, _, _, operator, _ = runtime
    return client.post("/api/v1/harness/artifacts", headers={"x-api-key": operator}, json=body)


def rejected_artifact(runtime):
    deps, client, _, _, operator, _ = runtime
    deps.config.feature_hitl = True
    large_output_session(runtime)
    _attach(deps, "worker", governance=[_rule("message_create", "require_approval")])
    source = send_message(runtime, body="unpublished artifact recovery fixture")
    op = source["runtime_operations"][0]
    pending = result(runtime, op, "PENDING_APPROVAL")
    response = client.post(f"/api/v1/approvals/{pending['publication_approval_id']}/decision",
        headers={"x-api-key": operator}, json={"decision": "reject"})
    assert response.status_code == 200, response.text
    deps.runtime_dispatcher.wake()
    return op, result(runtime, op, "BLOCKED")
