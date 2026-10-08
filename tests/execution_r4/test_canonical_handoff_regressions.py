"""Managed handoff authorization and atomic claims over canonical execution."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import pytest
from okto_nexus.domain.base import iso_plus
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_agent_recovery_isolation import create_agent
from test_canonical_result_publication import current_turn, workspace


@pytest.fixture(autouse=True)
def trust_mode_before_tool_registration(request, monkeypatch):
    if getattr(request.node, "callspec", None) and request.node.callspec.params.get("strict"):
        import test_embedded_inventory
        original = test_embedded_inventory.build_app
        def strict_app(deps):
            deps.config.trust_mode = "strict"
            return original(deps)
        monkeypatch.setattr(test_embedded_inventory, "build_app", strict_app)


@pytest.fixture
def runtime(connected_local, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    setup, binding, _ = connected_local
    setup[3]["caller"] = create_agent(setup, "caller")[3]["subject"]
    setup[2].headers["host"] = "127.0.0.1:8000"
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='none' WHERE endpoint_id=?",
                               (binding["endpoint_id"],))
    return connected_local


def call(runtime, name, actor="caller", **kwargs):
    from test_pr34_remediation import tool
    setup = runtime[0]
    return tool(setup[2], setup[3][actor]["Authorization"].removeprefix("Bearer "), name,
                dict(workspace_id=workspace(setup), **kwargs))


def create(runtime):
    return call(runtime, "handoff_create", from_agent_id="caller", visibility="eligible",
                target=dict(strategy="direct", agent_id="subject"), payload="Review governed work")


def work(runtime):
    response = create(runtime)
    assert response["ok"], response
    return response["data"]["handoff_id"]


def grant(runtime, actions=("execute_work",)):
    setup, binding, _ = runtime
    response = setup[2].post("/api/v1/harness/grants", headers=setup[3]["operator"], json=dict(
        actor_agent_id="caller", endpoint_id=binding["endpoint_id"], actions=list(actions),
        max_executions=8, expires_at=iso_plus(setup[0].clock.now_iso(), 600)))
    assert response.status_code == 200, response.text
    return response.json()["data"]["grant_id"]


def claim(runtime, hid, gid, *, key="managed-claim", actor="caller"):
    return call(runtime, "handoff_claim", actor=actor, handoff_id=hid, agent_id="subject",
        runtime_endpoint_id=runtime[1]["endpoint_id"], execution_grant_id=gid, idempotency_key=key)


def assert_unclaimed(runtime, hid, gid=None):
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[:] == ("OPEN", 0)
        for table in ("delivery_outbox", "runtime_handoff_bindings", "execution_operations"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
        if gid:
            assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (gid,)).fetchone()[0] == 0
    assert runtime[2].opens == 0


@pytest.mark.parametrize("authorization", ["missing", "conversation"])
def test_managed_claim_requires_explicit_work_authority(runtime, authorization):
    hid = work(runtime)
    gid = grant(runtime, ("send",)) if authorization == "conversation" else None
    response = claim(runtime, hid, gid)
    assert response.get("error", {}).get("code") == "PERMISSION_DENIED", response
    assert_unclaimed(runtime, hid, gid)


def test_managed_claim_commit_cut_rolls_back_all_canonical_rows(runtime, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
    hid, gid = work(runtime), grant(runtime)
    enqueue = SqliteRuntimeOutboxRepo.enqueue
    def cut(self, uow, **kwargs):
        enqueue(self, uow, **kwargs)
        raise OSError("Injected claim commit failure")
    with monkeypatch.context() as patch:
        patch.setattr(SqliteRuntimeOutboxRepo, "enqueue", cut)
        assert not claim(runtime, hid, gid)["ok"]
    assert_unclaimed(runtime, hid, gid)
    assert claim(runtime, hid, gid)["ok"]
    wait_receipt(runtime[0], current_turn(runtime[0]))
    assert len(runtime[2].native.sent) == 1


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_managed_claims_have_one_effect(runtime, same_key):
    hid, gid = work(runtime), grant(runtime)
    barrier = threading.Barrier(4)
    def compete(index):
        barrier.wait(timeout=5)
        return claim(runtime, hid, gid, key="shared" if same_key else str(index))
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(pool.map(compete, range(4)))
    successful = [r["data"]["runtime_operation"]["operation_id"] for r in replies if r["ok"]]
    assert len(successful) == (4 if same_key else 1), replies
    assert len(set(successful)) == 1
    wait_receipt(runtime[0], current_turn(runtime[0]))
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (gid,)).fetchone()[0] == 1
    assert runtime[2].opens == 1 and len(runtime[2].native.sent) == 1


@pytest.mark.parametrize("strict", [False, True])
def test_delegated_managed_claim_has_rest_mcp_parity(runtime, strict):
    setup, binding, native = runtime
    deps, _, client, headers, *_ = setup
    deps.config.trust_mode = "strict" if strict else "cooperative"
    hid, gid = work(runtime), grant(runtime)
    body = dict(agent_id="subject", runtime_endpoint_id=binding["endpoint_id"],
                execution_grant_id=gid, idempotency_key="parity")
    route = f"/api/v1/workspaces/{workspace(setup)}/handoffs/{hid}/claim"
    assert client.post(route, headers=headers["subject"], json=body).status_code == 403
    first = client.post(route, headers=headers["caller"], json=body)
    assert first.status_code == 200, first.text
    retry = claim(runtime, hid, gid, key="parity")
    assert retry["ok"], retry
    assert retry["data"]["runtime_operation"]["operation_id"] == first.json()["data"]["runtime_operation"]["operation_id"]
    wait_receipt(setup, current_turn(setup))
    assert native.opens == 1 and len(native.native.sent) == 1


@pytest.mark.parametrize("rule", ["deny", "require_approval"])
def test_policy_change_after_creation_cannot_become_dispatch_authority(runtime, rule):
    from test_hitl import _attach, _rule
    deps = runtime[0][0]
    deps.config.feature_hitl = True
    hid = work(runtime)
    _attach(deps, "caller", governance=[_rule("handoff_create", rule)])
    gid = grant(runtime)
    assert not claim(runtime, hid, gid)["ok"]
    assert_unclaimed(runtime, hid, gid)


@pytest.mark.parametrize("change", ["missing_receipt", "enable_hitl"])
def test_creation_authority_is_never_invented(runtime, change):
    deps = runtime[0][0]
    hid = work(runtime)
    if change == "enable_hitl":
        deps.config.feature_hitl = True
    else:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("DELETE FROM handoff_authorization_receipts WHERE handoff_id=?", (hid,))
    gid = grant(runtime)
    assert not claim(runtime, hid, gid)["ok"]
    assert_unclaimed(runtime, hid, gid)


def test_human_approval_precedes_dispatch_authorization_receipt(runtime):
    from test_hitl import _attach, _rule
    setup = runtime[0]
    deps, _, client, headers, *_ = setup
    deps.config.feature_hitl = True
    _attach(deps, "caller", governance=[_rule("handoff_create", "require_approval")])
    pending = create(runtime)
    assert pending["ok"] and pending["data"]["status"] == "pending_approval", pending
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("handoff_authorization_receipts", "delivery_outbox", "execution_operations"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
    approved = client.post("/api/v1/approvals/" + pending["data"]["approval_id"] + "/decision",
        headers=headers["operator"], json=dict(decision="approve"))
    assert approved.status_code == 200, approved.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        hid = uow.connection.execute("SELECT handoff_id FROM handoffs").fetchone()[0]
        assert uow.connection.execute("SELECT COUNT(*) FROM handoff_authorization_receipts").fetchone()[0] == 1
    claimed = claim(runtime, hid, grant(runtime))
    assert claimed["ok"], claimed
    wait_receipt(setup, current_turn(setup))
    assert len(runtime[2].native.sent) == 1
