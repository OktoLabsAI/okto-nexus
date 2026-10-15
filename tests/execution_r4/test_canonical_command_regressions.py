"""Public command admission remains durable while Core native work is blocked."""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_canonical_grant_regressions import mcp_helpers, open_scoped, invoke_command


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_admission_and_interrupt_do_not_wait_for_blocked_native_turn(connected_local, monkeypatch, surface):
    from test_pr34_remediation import tool
    setup, _, native, _, sid = open_scoped(connected_local)
    _, _, client, headers, *_ = setup
    entered, release = threading.Event(), asyncio.Event()
    original = native.native.send
    async def blocked(verb, *args, **kwargs):
        if verb == "send_turn":
            entered.set()
            await release.wait()
        return await original(verb, *args, **kwargs)
    monkeypatch.setattr(native.native, "send", blocked)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(invoke_command, setup, monkeypatch, surface, sid,
                dict(payload=dict(text="Blocked native write"), idempotency_key="blocked-command"))
            assert entered.wait(5)
            admitted = response.result(timeout=1)
        assert admitted["ok"], admitted
        assert not release.is_set()
        key = headers["subject"]["Authorization"].removeprefix("Bearer ")
        body = dict(idempotency_key="interrupt-blocked")
        if surface == "mcp":
            control = tool(client, key, "harness_interrupt", dict(session_id=sid, **body))
        else:
            control = client.post(f"/api/v1/harness/sessions/{sid}/interrupt", headers=headers["subject"], json=body).json()
        assert control["ok"], control
        wait_receipt(setup, control["data"])
        assert [v for v, _ in native.native.sent] == ["interrupt"]
        assert not release.is_set()
    finally:
        client.portal.call(release.set)
    wait_receipt(setup, admitted["data"])
    assert [v for v, _ in native.native.sent] == ["interrupt", "send_turn"]


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_dispatch_enqueue_failure_rolls_back_operation_and_grant_spending(connected_local, monkeypatch, surface):
    setup, _, native, grant, sid = open_scoped(connected_local)
    deps = setup[0]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_command_dispatch BEFORE INSERT ON execution_dispatch_outbox "
            "BEGIN SELECT RAISE(ABORT, 'fixture enqueue failure'); END")
    body = dict(payload=dict(text="No effect before committed dispatch"), idempotency_key="enqueue-cut")
    failed = invoke_command(setup, monkeypatch, surface, sid, body)
    assert not failed["ok"], failed
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 0
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 0
        assert not native.native.sent
        uow.connection.execute("DROP TRIGGER reject_command_dispatch")
    retried = invoke_command(setup, monkeypatch, surface, sid, body)
    assert retried["ok"], retried
    wait_receipt(setup, retried["data"])
    assert len(native.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 1


@pytest.mark.parametrize("proof", ["valid", "missing", "possible_effect", "different_error", "different_session"])
def test_only_matching_durable_no_effect_receipt_preserves_healthy_session(connected_local, monkeypatch, proof):
    from dataclasses import replace
    from nexus_connector_core.models import EffectNotSent
    from test_agent_recovery_isolation import eventually
    setup, _, native, _, sid = open_scoped(connected_local)
    owner = setup[1].state.embedded_dispatch_owner
    original = native.native.send
    async def refuse(*args, **kwargs):
        raise EffectNotSent("Fixture pre-write refusal", code="STALE_TURN")
    read = owner.host.historical_receipt
    async def altered(**kwargs):
        receipt = await read(**kwargs)
        if receipt is None or receipt.error_code != "STALE_TURN":
            return receipt
        if proof == "missing":
            return None
        if proof == "possible_effect":
            return replace(receipt, possible_effect=True)
        if proof == "different_error":
            return replace(receipt, error_code="UNRELATED_FAILURE")
        if proof == "different_session":
            return replace(receipt, session_id="other-session")
        return receipt
    with monkeypatch.context() as patch:
        patch.setattr(native.native, "send", refuse)
        patch.setattr(owner.host, "historical_receipt", altered)
        result = invoke_command(setup, monkeypatch, "rest", sid,
            dict(idempotency_key="prewrite-refusal", payload=dict(text="Refused before write")))
        assert result["ok"], result
        if proof != "valid":
            eventually(lambda: "subject" in owner.agents.blocked)
            assert not native.native.sent
            return
        view = wait_receipt(setup, result["data"], stages=("FAILED",))
        assert view["retry_safe"] and not view["possible_effect"]
        assert "subject" not in owner.agents.blocked and sid in owner.sessions
        assert not native.native.stopped and not native.native.sent
    assert native.native.send == original
    next_turn = invoke_command(setup, monkeypatch, "rest", sid,
        dict(idempotency_key="healthy-after-refusal", payload=dict(text="Still available")))
    assert next_turn["ok"], next_turn
    wait_receipt(setup, next_turn["data"])
    assert len(native.native.sent) == 1 and native.opens == 1
