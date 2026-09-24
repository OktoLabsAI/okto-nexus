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
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
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


def test_explicitly_authorized_structured_result_completes_canonical_handoff(runtime):
    native_work_peer(runtime)
    hid, _ = work(runtime)
    op, _ = dispatch(runtime, hid)
    assert state(runtime, hid, "COMPLETED")["result"] == "fixture evidence"
    observed = tool(runtime[1], runtime[4], "harness_get", {"operation_id": op})
    assert observed["ok"], observed
    assert observed["data"]["work_outcome"]["state"] == "APPLIED"
    assert observed["data"]["work_outcome"]["response"]["status"] == "COMPLETED"
    assert observed["data"]["result"]["publication_state"] == "WORK_APPLIED"
    assert not tool(runtime[1], runtime[5], "harness_get", {"operation_id": op})["ok"]


def outcome(runtime, op):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_work_outcomes WHERE operation_id=?", (op,)).fetchone()
        if row:
            return dict(row)
        time.sleep(.01)
    pytest.fail("No durable work outcome")


def test_structured_reject_uses_canonical_rejection(runtime):
    native_work_peer(runtime, action="reject")
    hid, _ = work(runtime)
    op, _ = dispatch(runtime, hid)
    assert state(runtime, hid, "REJECTED")["rejected_reason"] == "fixture evidence"
    assert outcome(runtime, op)["state"] == "APPLIED"


def test_structured_completion_cannot_self_verify(runtime):
    runtime[0].config.feature_verification = True
    native_work_peer(runtime)
    hid, _ = work(runtime, acceptance_criteria=["Operator reviews evidence"])
    op, _ = dispatch(runtime, hid)
    assert state(runtime, hid, "VERIFYING")["result"] == "fixture evidence"
    assert outcome(runtime, op)["state"] == "APPLIED"


@pytest.mark.parametrize("mutation", [
    'decision["operation_id"] = "forged"',
    'decision["handoff_id"] = "forged"',
    'decision["claim_epoch"] = 2',
    'decision["claim_epoch"] = True',
    'decision["action"] = "verify"',
    'decision["agent_id"] = "operator"',
    'decision["actor_agent_id"] = "operator"',
    'decision["from_agent_id"] = "operator"',
    'decision["execution_grant_id"] = "forged"',
    'decision["root_operation_id"] = "forged"',
])
def test_structured_result_cannot_replace_its_authority(runtime, mutation):
    native_work_peer(runtime, mutation=mutation)
    hid, _ = work(runtime)
    op, _ = dispatch(runtime, hid)
    assert outcome(runtime, op)["state"] == "BLOCKED"
    assert state(runtime, hid, "CLAIMED")["result"] is None


def test_structured_looking_output_without_admission_does_not_complete(runtime):
    from test_runtime_handoff_dispatch import wait_result
    native_work_peer(runtime)
    hid, _ = work(runtime)
    op, _ = dispatch(runtime, hid, structured=False)
    assert "nexus_work_result" in wait_result(runtime, op)["output_text"]
    runtime[0].runtime_dispatcher.publish_results()
    assert state(runtime, hid, "CLAIMED")["result"] is None
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM runtime_work_outcomes").fetchone()


def test_revoked_grant_blocks_structured_completion_and_retains_evidence(runtime, monkeypatch):
    from okto_nexus.application.handoff import HandoffService
    from test_runtime_handoff_dispatch import wait_result
    deps, client, _, _, operator, _ = runtime
    native_work_peer(runtime)
    hid, _ = work(runtime)
    entered, release = threading.Event(), threading.Event()
    complete = HandoffService.handoff_complete
    def held(self, **kwargs):
        if kwargs.get("_runtime_result_id"):
            entered.set()
            assert release.wait(10)
        return complete(self, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(HandoffService, "handoff_complete", held)
        try:
            op, grant = dispatch(runtime, hid)
            assert entered.wait(6)
            assert client.delete("/api/v1/harness/grants/" + grant["grant_id"], headers={"x-api-key": operator}).status_code == 200
        finally:
            release.set()
        assert outcome(runtime, op)["state"] == "BLOCKED"
    assert state(runtime, hid, "CLAIMED")["result"] is None
    assert "fixture evidence" in wait_result(runtime, op)["output_text"]


def test_completion_and_its_receipt_rollback_and_retry_together(runtime, monkeypatch):
    from okto_nexus.application.runtime_work import RuntimeWorkService
    deps = runtime[0]
    native_work_peer(runtime)
    hid, _ = work(runtime)
    record = RuntimeWorkService.record_result
    failed = threading.Event()
    def cut(self, uow, **kwargs):
        record(self, uow, **kwargs)
        if kwargs["state"] == "APPLIED":
            failed.set()
            raise OSError("fixture atomic completion cut")
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeWorkService, "record_result", cut)
        op, _ = dispatch(runtime, hid)
        assert failed.wait(6)
        assert state(runtime, hid, "CLAIMED")["result"] is None
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute("SELECT 1 FROM runtime_work_outcomes").fetchone()
    deps.runtime_dispatcher.wake()
    assert state(runtime, hid, "COMPLETED")["result"] == "fixture evidence"
    assert outcome(runtime, op)["state"] == "APPLIED"
    deps.runtime_dispatcher.publish_results()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_work_outcomes").fetchone()[0] == 1


def test_managed_revalidation_does_not_write_to_a_read_snapshot(runtime):
    from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service
    from test_runtime_handoff_dispatch import wait_result
    native_work_peer(runtime)
    hid, _ = work(runtime)
    op, _ = dispatch(runtime, hid, structured=False)
    wait_result(runtime, op)
    service = build_service(runtime[0]).runtime_work
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        before = uow.connection.total_changes
        operation = service.outbox.get(uow, op)
        service.revalidate(uow, operation=operation)
        assert uow.connection.total_changes == before


def test_rest_structured_contract_is_idempotent_with_mcp_and_cannot_be_changed(runtime):
    deps, client, root, _, _, caller = runtime
    native_work_peer(runtime)
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        ws = uow.connection.execute("SELECT workspace_id FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0]
    arguments = {"agent_id": "worker", "runtime_endpoint_id": "endpoint-codex",
        "execution_grant_id": grant["grant_id"], "idempotency_key": "rest-work",
        "completion_mode": "structured_result_v1"}
    response = client.post(f"/api/v1/workspaces/{ws}/handoffs/{hid}/claim", headers={"x-api-key": caller}, json=arguments)
    assert response.status_code == 200, response.text
    again = tool(client, caller, "handoff_claim", arguments | {"project_root": root, "handoff_id": hid})
    assert again["ok"], again
    assert again["data"]["runtime_operation"]["operation_id"] == response.json()["data"]["runtime_operation"]["operation_id"]
    assert again["data"]["runtime_operation"]["completion_mode"] == "structured_result_v1"
    changed = tool(client, caller, "handoff_claim", arguments | {
        "project_root": root, "handoff_id": hid, "completion_mode": "authenticated_nexus_call"})
    assert not changed["ok"], changed
    assert state(runtime, hid, "COMPLETED")["result"] == "fixture evidence"
