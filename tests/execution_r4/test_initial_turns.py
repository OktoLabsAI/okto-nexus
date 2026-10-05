"""A start prompt survives admission and waits for authenticated readiness."""
from test_session_reuse import reuse_qualified, reuse_connected, resolve, admit
from test_local_realization import local_setup
from test_embedded_dispatch import wait_receipt
from okto_nexus.application.execution_initial_turns import release_ready_initial_turns
import pytest


def test_start_prompt_waits_for_ready_and_replays_without_duplicate(reuse_connected):
    setup, binding, native = reuse_connected
    pump = setup[1].state.embedded_dispatch_owner.pump
    setup[2].portal.call(pump.send_lock.acquire)
    try:
        response = resolve(setup, binding, "initial", new_session=True, text="Initial request")
        assert response.status_code == 200, response.text
        resolved = response.json()
        assert "text" not in resolved["semantic_intent"]["payload"]
        view = admit(setup, resolved)
        child, = view["follow_up_operation_ids"]
        assert child != resolved["operation_id"]
        assert admit(setup, resolved, 200)["follow_up_operation_ids"] == [child]
        with setup[0].connection_factory.unit_of_work() as uow:
            release_ready_initial_turns(uow.connection, server_id=resolved["scope"]["server_id"],
                                       executor_id=resolved["scope"]["executor_id"])
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 2
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 1
            assert uow.connection.execute("SELECT parent_operation_id FROM execution_operations WHERE operation_id=?", (child,)).fetchone()[0] == resolved["operation_id"]
        assert native.opens == 0
    finally:
        setup[2].portal.call(pump.send_lock.release)
    wait_receipt(setup, resolved)
    wait_receipt(setup, {"operation_id": child})
    assert native.opens == 1
    assert [verb for verb, _ in native.native.sent] == ["send_turn"]


def test_child_revalidates_revoked_authority_before_send(reuse_connected):
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
    from okto_nexus.errors import OktoNexusError
    setup, binding, native = reuse_connected
    opened = resolve(setup, binding, "open", new_session=True).json()
    admit(setup, opened)
    wait_receipt(setup, opened)
    pump = setup[1].state.embedded_dispatch_owner.pump
    setup[2].portal.call(pump.stop)
    selected = resolve(setup, binding, "prompt", text="Must not execute").json()
    child, = admit(setup, selected, 200)["follow_up_operation_ids"]
    reservation = reserve_execution_dispatch(factory=pump.factory, server_id=pump.channel.server_id,
        executor_id=pump.channel.executor_id, remote_ready=True, channel=pump.channel)
    assert reservation.operation_id == child
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'")
    with pytest.raises(OktoNexusError):
        begin_execution_send(factory=pump.factory, reservation=reservation, remote_ready=True,
            fresh_publications=pump.fresh_publications, access=pump.access, channel=pump.channel)
    assert native.native.sent == []


def test_reused_start_prompt_creates_only_a_child_turn(reuse_connected):
    setup, binding, native = reuse_connected
    first = resolve(setup, binding, "first", new_session=True).json()
    admit(setup, first)
    wait_receipt(setup, first)
    second = resolve(setup, binding, "reuse-prompt", text="Continue").json()
    assert second["reuse"]
    child, = admit(setup, second, 200)["follow_up_operation_ids"]
    wait_receipt(setup, {"operation_id": child})
    assert admit(setup, second, 200)["follow_up_operation_ids"] == [child]
    assert native.opens == 1
    assert [verb for verb, _ in native.native.sent] == ["send_turn"]


def test_initial_prompt_resolution_is_stable_and_conflicting_text_is_refused(reuse_connected):
    setup, binding, native = reuse_connected
    original = resolve(setup, binding, "stable", new_session=True, text="Original")
    assert original.status_code == 200, original.text
    assert resolve(setup, binding, "stable", new_session=True, text="Original").json() == original.json()
    assert resolve(setup, binding, "stable", new_session=True, text="Different").status_code == 409
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
    assert native.opens == 0


def test_initial_prompt_obeys_encoded_payload_limit(reuse_connected):
    setup, binding, native = reuse_connected
    response = resolve(setup, binding, "large", new_session=True, text="界" * 30000)
    assert response.status_code == 200, response.text
    assert not response.json()["can_submit"]
    assert "operation_payload_too_large" in response.json()["blockers"]
    admit(setup, response.json(), 409)
    assert native.opens == 0
