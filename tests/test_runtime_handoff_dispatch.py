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


def test_managed_claim_cannot_silently_fall_back_to_unmanaged_claim(runtime):
    deps, client, root, _, _, _ = runtime
    hid, key = work(runtime)
    response = tool(client, key, "handoff_claim", {
        "project_root": root, "handoff_id": hid, "agent_id": "worker",
        "runtime_endpoint_id": "endpoint-codex",
    })
    assert response.get("error", {}).get("code") == "PERMISSION_DENIED", response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "OPEN"


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


def test_claim_dispatch_result_and_explicit_completion_are_one_canonical_flow(runtime):
    deps, client, root, _, _, caller = runtime
    codex_session(runtime)
    hid, worker = work(runtime)
    grant = issue(runtime, ["execute_work", "read"], endpoint_id="endpoint-codex")
    first = claim(runtime, hid, grant, caller)
    assert first["ok"], first
    data = first["data"]
    op = data["runtime_operation"]["operation_id"]
    assert data["claim_epoch"] == 1
    native = wait_result(runtime, op)
    assert "fixture managed work" in native["output_text"]
    again = claim(runtime, hid, grant, caller)
    assert again["ok"], again
    assert again["data"]["runtime_operation"]["operation_id"] == op
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "CLAIMED"
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 1
        uow.connection.execute("UPDATE handoffs SET lease_expires_at='2000-01-01T00:00:00.000000Z' WHERE handoff_id=?", (hid,))
    # Lease expiry and a terminal native event cannot reassign/complete work.
    current = tool(client, worker, "handoff_get", {"project_root": root, "handoff_id": hid, "agent_id": "worker"})
    assert current["data"]["status"] == "CLAIMED", current
    assert current["data"]["managed_lease_protected"]
    assert current["data"]["runtime_execution"]["operation_id"] == op
    observed = tool(client, caller, "harness_get", {"operation_id": op})
    assert observed["ok"] and observed["data"]["result_durable"], observed
    assert observed["data"]["handoff"] == {"handoff_id": hid, "claim_epoch": 1}
    complete = tool(client, worker, "handoff_complete", {
        "project_root": root, "handoff_id": hid, "agent_id": "worker", "claim_epoch": 1,
        "result": {"evidence": "fixture reviewed output"},
    })
    assert complete["ok"] and complete["data"]["status"] == "COMPLETED", complete


def test_managed_claim_commit_cut_rolls_back_claim_delivery_and_grant(runtime, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
    deps, _, _, _, _, caller = runtime
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    enqueue = SqliteRuntimeOutboxRepo.enqueue
    def cut(self, uow, **kwargs):
        enqueue(self, uow, **kwargs)
        raise OSError("fixture cut before claim/intention commit")
    with monkeypatch.context() as patch:
        patch.setattr(SqliteRuntimeOutboxRepo, "enqueue", cut)
        reply = claim(runtime, hid, grant, caller)
        assert not reply["ok"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[:] == ("OPEN", 0)
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 0
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject='Managed handoff execution'").fetchone()[0] == 0
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 0
    assert claim(runtime, hid, grant, caller)["ok"]


@pytest.mark.parametrize("same_key", [False, True])
def test_competing_admissions_create_only_one_execution(runtime, same_key):
    deps, _, _, _, _, caller = runtime
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex", max_executions=8)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(claim, runtime, hid, grant, caller, request_key="same" if same_key else str(i)) for i in range(4)]
        replies = [f.result() for f in futures]
    successful = [r["data"]["runtime_operation"]["operation_id"] for r in replies if r["ok"]]
    assert len(successful) == (4 if same_key else 1), replies
    assert len(set(successful)) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 1


def test_delegated_managed_claim_has_same_rest_and_mcp_admission(runtime):
    deps, client, root, _, _, caller = runtime
    hid, worker = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        ws = uow.connection.execute("SELECT workspace_id FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0]
    body = {"agent_id": "worker", "runtime_endpoint_id": "endpoint-codex", "execution_grant_id": grant["grant_id"], "idempotency_key": "parity"}
    url = f"/api/v1/workspaces/{ws}/handoffs/{hid}/claim"
    assert client.post(url, headers={"x-api-key": worker}, json=body).status_code == 403
    response = client.post(url, headers={"x-api-key": caller}, json=body)
    assert response.status_code == 200, response.text
    retry = claim(runtime, hid, grant, caller, request_key="parity")
    assert retry["ok"], retry
    assert retry["data"]["runtime_operation"]["operation_id"] == response.json()["data"]["runtime_operation"]["operation_id"]


def test_revocation_between_admission_and_write_prevents_native_effect(runtime):
    deps, client, _, peers, operator, caller = runtime
    # Use the actual owner's dispatch boundary, outside all writer UoWs.
    entered, release = threading.Event(), threading.Event()
    dispatch = deps.runtime_dispatcher.dispatch
    def held(operation):
        entered.set()
        assert release.wait(8)
        return dispatch(operation)
    deps.runtime_dispatcher.dispatch = held
    try:
        hid, _ = work(runtime)
        grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
        reply = claim(runtime, hid, grant, caller)
        assert reply["ok"], reply
        assert entered.wait(5)
        assert client.delete("/api/v1/harness/grants/" + grant["grant_id"], headers={"x-api-key": operator}).status_code == 200
    finally:
        release.set()
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT status FROM delivery_outbox").fetchone()
        if row[0] == "OUTCOME_UNKNOWN":
            break
        time.sleep(.01)
    assert row[0] == "OUTCOME_UNKNOWN"
    assert all(not peer.sent for peer in peers)


@pytest.mark.parametrize("runtime", ["strict"], indirect=True)
def test_strict_claim_credentials_have_rest_mcp_parity(runtime):
    deps, client, root, _, _, caller = runtime
    hid, worker = work(runtime)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        ws = uow.connection.execute("SELECT workspace_id FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0]
    url = f"/api/v1/workspaces/{ws}/handoffs/{hid}/claim"
    rest = client.post(url, headers={"x-api-key": worker}, json={"agent_id": "worker"})
    mcp = tool(client, worker, "handoff_claim", {
        "project_root": root, "handoff_id": hid, "agent_id": "worker"})
    assert not mcp["ok"], mcp
    assert rest.status_code != 200, rest.text
    assert rest.json()["error"]["code"] == mcp["error"]["code"]
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    response = client.post(url, headers={"x-api-key": caller}, json={
        "agent_id": "worker", "runtime_endpoint_id": "endpoint-codex",
        "execution_grant_id": grant["grant_id"], "idempotency_key": "strict-managed"})
    assert response.status_code == 200, response.text
    retry = claim(runtime, hid, grant, caller, request_key="strict-managed")
    assert retry["ok"], retry
    assert retry["data"]["runtime_operation"]["operation_id"] == response.json()["data"]["runtime_operation"]["operation_id"]


def test_conversation_grant_cannot_authorize_work(runtime):
    deps, _, _, peers, _, caller = runtime
    hid, _ = work(runtime)
    grant = issue(runtime, ["send"], endpoint_id="endpoint-codex")
    response = claim(runtime, hid, grant, caller)
    assert response.get("error", {}).get("code") == "PERMISSION_DENIED", response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "OPEN"
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 0
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 0
    assert not peers


@pytest.mark.parametrize("change", ["revoke", "rework"])
def test_late_managed_output_is_retained_without_unauthorized_publication(runtime, monkeypatch, change):
    from okto_nexus.application.runtime_results import RuntimeResultService
    from test_runtime_result_publication import result
    deps, client, root, _, operator, caller = runtime
    deps.config.feature_verification = True
    codex_session(runtime)
    hid, worker = work(runtime, acceptance_criteria=["Review the fixture evidence"])
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    prepare = RuntimeResultService.prepare
    entered, release = threading.Event(), threading.Event()
    def held(self, result_id, **kwargs):
        entered.set()
        assert release.wait(10)
        return prepare(self, result_id, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeResultService, "prepare", held)
        try:
            response = claim(runtime, hid, grant, caller)
            assert response["ok"], response
            op = response["data"]["runtime_operation"]["operation_id"]
            assert entered.wait(6)
            if change == "revoke":
                assert client.delete("/api/v1/harness/grants/" + grant["grant_id"], headers={"x-api-key": operator}).status_code == 200
            else:
                completed = tool(client, worker, "handoff_complete", {
                    "project_root": root, "handoff_id": hid, "agent_id": "worker", "claim_epoch": 1,
                    "result": "explicit first delivery"})
                assert completed["ok"] and completed["data"]["status"] == "VERIFYING", completed
                verdict = tool(client, caller, "handoff_verify", {
                    "project_root": root, "handoff_id": hid, "agent_id": "caller", "claim_epoch": 1,
                    "verdict": "fail", "feedback": "fixture rework"})
                assert verdict["ok"], verdict
                retry = claim(runtime, hid, grant, caller)
                assert retry["ok"], retry
                assert retry["data"]["claim_epoch"] == 1
                assert retry["data"]["runtime_operation"]["operation_id"] == op
        finally:
            release.set()
        retained = result(runtime, op, "BLOCKED")
    assert "fixture managed work" in retained["output_text"]
    assert not retained["publication_message_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        current = uow.connection.execute("SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()
        assert current[:] == ("CLAIMED", 2 if change == "rework" else 1)
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
