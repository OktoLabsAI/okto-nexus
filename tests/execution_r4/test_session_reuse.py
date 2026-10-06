"""Automatic start selection preserves the original native opening."""
import pytest

from test_local_realization import local_setup
from test_embedded_dispatch import connect_local, wait_receipt


@pytest.fixture
def reuse_qualified():
    from okto_nexus.adapters.inbound.http import runtime_v1
    from okto_nexus.bootstrap import embedded_dispatch
    info = runtime_v1.protocol_info()
    assert info["remote_execution_ready"] is True
    assert embedded_dispatch.protocol_info() == info


@pytest.fixture
def reuse_connected(reuse_qualified, local_setup):
    return connect_local(local_setup)


def resolve(setup, binding, intent_id, **options):
    client, headers = setup[2], setup[3]
    return client.post("/v1/runtime/intents:resolve", headers=headers["subject"], json=dict(
        client_intent_id=intent_id, intent="runtime.start", binding_id=binding["binding_id"],
        workspace_binding_id=binding["workspace_binding_id"], **options))


def admit(setup, resolution, expected=202):
    response = setup[2].post("/v1/runtime/operations", headers=setup[3]["subject"],
        json={name: resolution[name] for name in
              ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")})
    assert response.status_code == expected, response.text
    return response.json()


def check_reuse_selection(reuse_connected):
    setup, binding, native = reuse_connected
    first = resolve(setup, binding, "first")
    assert first.status_code == 200, first.text
    first = first.json()
    assert not first["reuse"]
    admit(setup, first)
    wait_receipt(setup, first)
    second = resolve(setup, binding, "reuse")
    assert second.status_code == 200, second.text
    second = second.json()
    assert second["reuse"] and second["session_id"] == first["session_id"]
    assert second["operation_id"] == first["operation_id"] and second["intent_hash"] == first["intent_hash"]
    assert admit(setup, second, 200)["client_intent_id"] == "first"
    assert resolve(setup, binding, "reuse").json() == second
    admit(setup, second, 200)
    assert native.opens == 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT reuse_admitted_at FROM execution_client_intents WHERE client_intent_id='reuse'").fetchone()[0]
    explicit = resolve(setup, binding, "explicit", new_session=True)
    assert explicit.status_code == 200, explicit.text
    explicit = explicit.json()
    assert explicit["session_id"] != first["session_id"] and not explicit["reuse"]
    admit(setup, explicit)
    wait_receipt(setup, explicit)
    assert native.opens == 2
    assert resolve(setup, binding, "ambiguous").status_code == 409
    chosen = resolve(setup, binding, "selected", session_id=first["session_id"])
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["reuse"] and chosen.json()["operation_id"] == first["operation_id"]
    admit(setup, chosen.json(), 200)


def test_default_starts_cannot_admit_two_concurrent_claims(reuse_connected):
    setup, binding, native = reuse_connected
    first = resolve(setup, binding, "first").json()
    other = resolve(setup, binding, "concurrent").json()
    assert first["session_id"] != other["session_id"]
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    def submit(resolution):
        barrier.wait(timeout=5)
        return setup[2].post("/v1/runtime/operations", headers=setup[3]["subject"],
            json={name: resolution[name] for name in
                  ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")})
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(submit, (first, other)))
    assert sorted(response.status_code for response in responses) == [202, 409], [r.text for r in responses]
    winner = first if responses[0].status_code == 202 else other
    wait_receipt(setup, winner)
    assert native.opens == 1


def test_closing_one_explicit_session_preserves_its_sibling(reuse_connected):
    from test_embedded_dispatch import admit as action
    setup, binding, native = reuse_connected
    first = resolve(setup, binding, "sibling-first", new_session=True).json()
    admit(setup, first)
    wait_receipt(setup, first)
    first_peer = native.native
    second = resolve(setup, binding, "sibling-second", new_session=True).json()
    admit(setup, second)
    wait_receipt(setup, second)
    second_peer = native.native
    assert first_peer is not second_peer and native.opens == 2
    closed = action(setup, binding, "close-first", "runtime.close", session_id=first["session_id"])
    wait_receipt(setup, closed, ("SUCCEEDED",))
    assert first_peer.stopped and not second_peer.stopped
    sent = action(setup, binding, "send-second", "turn.submit",
                  session_id=second["session_id"], text="sibling survives")
    wait_receipt(setup, sent)
    assert [verb for verb, _ in second_peer.sent] == ["send_turn"]
    assert not first_peer.sent
    closed = action(setup, binding, "close-second", "runtime.close", session_id=second["session_id"])
    wait_receipt(setup, closed, ("SUCCEEDED",))
    assert first_peer.stopped and second_peer.stopped and native.opens == 2


def test_uncertain_opening_is_not_replaced(reuse_connected):
    setup, binding, native = reuse_connected
    first = resolve(setup, binding, "first").json()
    # Hold dispatch so the durable claim stays unresolved.
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    admit(setup, first)
    refused = resolve(setup, binding, "uncertain")
    assert refused.status_code == 409, refused.text
    assert native.opens == 0


@pytest.mark.parametrize("sql", [
    "UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'",
    "UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z'",
    "UPDATE execution_sessions SET owner_generation=owner_generation+1",
    "UPDATE execution_executors SET generation=generation+1",
    "UPDATE execution_realizations SET revision=revision+1",
])
@pytest.mark.parametrize("boundary", ["resolve", "admit"])
def test_reuse_revalidates_authority_at_both_boundaries(reuse_connected, sql, boundary):
    setup, binding, native = reuse_connected
    first = resolve(setup, binding, "first", new_session=True).json()
    admit(setup, first)
    wait_receipt(setup, first)
    if boundary == "admit":
        selected = resolve(setup, binding, "reuse")
        assert selected.status_code == 200, selected.text
        selected = selected.json()
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(sql)
    if boundary == "resolve":
        response = resolve(setup, binding, "reuse")
    else:
        response = setup[2].post("/v1/runtime/operations", headers=setup[3]["subject"],
            json={name: selected[name] for name in ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")})
    if boundary == 'resolve' and 'revoked_at' in sql and response.status_code == 200:
        # Revoked sessions are no longer automatic reuse candidates. A new
        # intent may be prepared, but cannot reuse the revoked opening.
        assert response.json()['reuse'] is False
        assert response.json()['session_id'] != first['session_id']
        assert native.opens == 1
    else:
        assert response.status_code in (403, 409), response.text
    assert native.opens == 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
        assert not uow.connection.execute("SELECT reuse_admitted_at FROM execution_client_intents WHERE client_intent_id='reuse' AND reuse_admitted_at IS NOT NULL").fetchall()


def test_confirmed_reuse_remains_recoverable_after_close(reuse_connected):
    setup, binding, native = reuse_connected
    first = resolve(setup, binding, "first").json()
    admit(setup, first)
    wait_receipt(setup, first)
    selected = resolve(setup, binding, "reuse").json()
    admitted = admit(setup, selected, 200)
    from test_embedded_dispatch import admit as action
    closed = action(setup, binding, "close", "runtime.close", session_id=first["session_id"])
    wait_receipt(setup, closed, ("SUCCEEDED",))
    assert admit(setup, selected, 200)["operation_id"] == admitted["operation_id"]
    assert native.opens == 1
