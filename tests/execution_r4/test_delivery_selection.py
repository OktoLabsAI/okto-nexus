"""Canonical readiness participates in the existing mixed delivery policy."""
import json
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send


def legacy(setup, binding, *, priority, group=None):
    deps = setup[0]
    with deps.connection_factory.unit_of_work() as uow:
        endpoint = dict(uow.connection.execute("SELECT * FROM agent_endpoints WHERE endpoint_id=?", (binding["endpoint_id"],)).fetchone())
        profile = dict(uow.connection.execute("SELECT * FROM runtime_profiles WHERE profile_id=?", (endpoint["profile_id"],)).fetchone())
        profile.update(profile_id="mixed-legacy-profile", adapter_id="pi", config=json.dumps({}), secret_refs=json.dumps({}))
        uow.connection.execute("INSERT INTO runtime_profiles (" + ",".join(profile) + ") VALUES (" + ",".join("?" for _ in profile) + ")", tuple(profile.values()))
        endpoint.update(endpoint_id="zz-legacy", adapter_id="pi", protocol="pi-rpc", profile_id=profile["profile_id"], priority=priority, selection_group=group)
        uow.connection.execute("INSERT INTO agent_endpoints (" + ",".join(endpoint) + ") VALUES (" + ",".join("?" for _ in endpoint) + ")", tuple(endpoint.values()))
        uow.connection.execute("UPDATE agent_endpoints SET priority=10,selection_group=? WHERE endpoint_id=?", (group, binding["endpoint_id"]))


@pytest.mark.parametrize("mode", ["ready", "priority", "group", "ambiguous"])
def test_mixed_endpoint_selection_before_native_effects(connected_local, monkeypatch, mode):
    setup, binding, native = connected_local
    enable(setup, binding)
    legacy(setup, binding, priority=99 if mode == "ready" else 1 if mode == "priority" else 10,
           group="approved-equivalence" if mode == "group" else None)
    opened = None
    if mode == "ready":
        opened = admit(setup, binding, "mixed-open", "runtime.start", new_session=True)
        wait_receipt(setup, opened)
    result = send(setup, monkeypatch)
    if mode == "ambiguous":
        assert not result["ok"] and "AMBIGUOUS_BINDING" in str(result), result
        assert native.opens == 0
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
        return
    assert result["ok"], result
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        delivery = uow.connection.execute("SELECT endpoint_id,runtime_session_id FROM delivery_outbox").fetchone()
        assert delivery[:] == (binding["endpoint_id"], None)
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        assert uow.connection.execute("SELECT COUNT(*) FROM harness_sessions").fetchone()[0] == 0
    wait_receipt(setup, turn)
    assert native.opens == 1 and len(native.native.sent) == 1
    if opened:
        assert turn["session_id"] == opened["scope"]["session_id"]
    closed = admit(setup, binding, "mixed-close", "runtime.close", session_id=turn["session_id"])
    wait_receipt(setup, closed, stages=("SUCCEEDED",))


def test_unresolved_canonical_session_does_not_fall_back(connected_local, monkeypatch):
    setup, binding, native = connected_local
    enable(setup, binding)
    legacy(setup, binding, priority=99, group="approved-equivalence")
    opened = admit(setup, binding, "unresolved-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lease_state='NONE' WHERE session_id=?", (opened["scope"]["session_id"],))
    result = send(setup, monkeypatch)
    assert not result["ok"] and "reconciliation" in str(result), result
    with setup[0].connection_factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 0
        uow.connection.execute("UPDATE execution_sessions SET lease_state='ACTIVE' WHERE session_id=?", (opened["scope"]["session_id"],))
    assert native.opens == 1 and not native.native.sent
    closed = admit(setup, binding, "unresolved-close", "runtime.close", session_id=opened["scope"]["session_id"])
    wait_receipt(setup, closed, stages=("SUCCEEDED",))
