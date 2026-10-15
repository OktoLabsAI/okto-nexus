"""Core terminal output does not replace explicit governed handoff completion."""
import threading
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable
from test_canonical_handoff_regressions import runtime, call, grant, claim
from test_canonical_result_publication import current_turn, emit, wait_result, workspace


@pytest.fixture(autouse=True)
def configure_trust_before_tool_registration(request, monkeypatch):
    if "strict_unmanaged" in request.node.name:
        import test_embedded_inventory
        original = test_embedded_inventory.build_app
        def strict_app(deps):
            deps.config.trust_mode = "strict"
            return original(deps)
        monkeypatch.setattr(test_embedded_inventory, "build_app", strict_app)


def test_strict_unmanaged_claim_is_denied_with_rest_mcp_parity(runtime):
    setup, binding, native = runtime
    setup[0].config.trust_mode = "strict"
    created = call(runtime, "handoff_create", from_agent_id="caller", visibility="eligible",
        target=dict(strategy="direct", agent_id="subject"), payload="Strict managed work")
    assert created["ok"], created
    hid = created["data"]["handoff_id"]
    route = f"/api/v1/workspaces/{workspace(setup)}/handoffs/{hid}/claim"
    rest = setup[2].post(route, headers=setup[3]["subject"], json=dict(agent_id="subject"))
    mcp = call(runtime, "handoff_claim", actor="subject", handoff_id=hid, agent_id="subject")
    assert rest.status_code != 200 and not mcp["ok"]
    assert rest.json()["error"]["code"] == mcp["error"]["code"]
    gid = grant(runtime)
    body = dict(agent_id="subject", runtime_endpoint_id=binding["endpoint_id"], execution_grant_id=gid,
        idempotency_key="strict-managed")
    admitted = setup[2].post(route, headers=setup[3]["caller"], json=body)
    assert admitted.status_code == 200, admitted.text
    replay = claim(runtime, hid, gid, key="strict-managed")
    assert replay["ok"] and replay["data"]["runtime_operation"]["operation_id"] == admitted.json()["data"]["runtime_operation"]["operation_id"]
    wait_receipt(setup, current_turn(setup))
    assert native.opens == 1 and len(native.native.sent) == 1


def test_native_result_and_expired_lease_still_require_explicit_completion(runtime):
    setup, binding, native = runtime
    created = call(runtime, "handoff_create", from_agent_id="caller", visibility="eligible",
        target=dict(strategy="direct", agent_id="subject"), payload="Governed evidence")
    assert created["ok"], created
    hid, gid = created["data"]["handoff_id"], grant(runtime, ("execute_work", "read"))
    enable(setup, binding)
    first = claim(runtime, hid, gid)
    assert first["ok"], first
    op = first["data"]["runtime_operation"]["operation_id"]
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    pending = call(runtime, "harness_get", operation_id=op)
    assert pending["ok"] and not pending["data"]["result_durable"], pending
    assert pending["data"]["session_id"] == turn["session_id"]
    assert pending["data"]["external_acceptance"] == "observed"
    emit(setup, native, turn, "Retained governed evidence")
    published = wait_result(setup, "PUBLISHED")
    assert published["output_text"] == "Retained governed evidence"
    again = claim(runtime, hid, gid)
    assert again["ok"] and again["data"]["runtime_operation"]["operation_id"] == op
    with setup[0].connection_factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "CLAIMED"
        assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (gid,)).fetchone()[0] == 1
        uow.connection.execute("UPDATE handoffs SET lease_expires_at='2000-01-01T00:00:00Z' WHERE handoff_id=?", (hid,))
    current = call(runtime, "handoff_get", actor="subject", handoff_id=hid, agent_id="subject")
    assert current["ok"] and current["data"]["status"] == "CLAIMED", current
    assert current["data"]["managed_lease_protected"]
    observed = call(runtime, "harness_get", operation_id=op)
    assert observed["ok"] and observed["data"]["result_durable"], observed
    rest = setup[2].get("/api/v1/harness/operations/" + op, headers=setup[3]["caller"])
    assert rest.status_code == 200 and rest.json()["data"] == observed["data"], rest.text
    assert observed["data"]["handoff"] == dict(handoff_id=hid, claim_epoch=1)
    complete = call(runtime, "handoff_complete", actor="subject", handoff_id=hid, agent_id="subject", claim_epoch=1,
        result=dict(evidence="Explicitly reviewed"))
    assert complete["ok"] and complete["data"]["status"] == "COMPLETED", complete
    assert native.opens == 1 and len(native.native.sent) == 1


@pytest.mark.parametrize("change", ["revoke", "rework"])
def test_changed_work_authority_retains_late_output_without_publication(runtime, monkeypatch, change):
    from okto_nexus.application.runtime_results import RuntimeResultService
    setup, binding, native = runtime
    deps, _, client, headers, *_ = setup
    deps.config.feature_verification = True
    created = call(runtime, "handoff_create", from_agent_id="caller", visibility="eligible",
        target=dict(strategy="direct", agent_id="subject"), payload="Governed evidence",
        acceptance_criteria=["Review this evidence"])
    assert created["ok"], created
    # Creation notifications must not start an unrelated conversational turn
    # before this test admits the managed handoff whose output it will emit.
    enable(setup, binding)
    hid, gid = created["data"]["handoff_id"], grant(runtime)
    entered, release = threading.Event(), threading.Event()
    original = RuntimeResultService.prepare
    def held(self, result_id, **kwargs):
        entered.set()
        assert release.wait(15)
        return original(self, result_id, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeResultService, "prepare", held)
        try:
            admitted = claim(runtime, hid, gid)
            assert admitted["ok"], admitted
            op = admitted["data"]["runtime_operation"]["operation_id"]
            turn = current_turn(setup)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute(
                    "SELECT domain_operation_id FROM execution_domain_deliveries WHERE operation_id=?",
                    (turn["operation_id"],)).fetchone()[0] == op
            wait_receipt(setup, turn)
            emit(setup, native, turn, "Late governed evidence")
            assert entered.wait(5)
            if change == "revoke":
                assert client.delete("/api/v1/harness/grants/" + gid, headers=headers["operator"]).status_code == 200
            else:
                completed = call(runtime, "handoff_complete", actor="subject", handoff_id=hid, agent_id="subject",
                    claim_epoch=1, result="First explicit delivery")
                assert completed["ok"] and completed["data"]["status"] == "VERIFYING", completed
                verdict = call(runtime, "handoff_verify", handoff_id=hid, agent_id="caller", claim_epoch=1,
                    verdict="fail", feedback="Needs rework")
                assert verdict["ok"], verdict
                replay = claim(runtime, hid, gid)
                assert replay["ok"] and replay["data"]["claim_epoch"] == 1, replay
                assert replay["data"]["runtime_operation"]["operation_id"] == op
        finally:
            release.set()
        retained = wait_result(setup, "BLOCKED")
    assert retained["output_text"] == "Late governed evidence" and not retained["publication_message_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[:] == ("CLAIMED", 2 if change == "rework" else 1)
        assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 1
    assert native.opens == 1 and len(native.native.sent) == 1
