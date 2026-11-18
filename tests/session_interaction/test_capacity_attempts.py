"""SQLite proofs of attempt identity and staging, independent of any host."""

from dataclasses import replace

import pytest
from nexus_connector_core import (
    CAPACITY_CONTRACT_REVISION,
    CapacityRequest,
    CapacityReservation,
    CapacityScope,
    capacity_reservation_id,
)
from nexus_connector_core.protocol import canonical_json

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.session_interaction import (
    accept_input,
    prepare_dispatch_head,
    stage_dispatch,
)
from okto_nexus.adapters.outbound.sqlite.session_interaction_capacity_attempts import (
    prepare_capacity_attempt,
    read_capacity_attempt,
    record_staged_capacity_attempt,
)
from okto_nexus.application.execution_semantics import execution_intent_hash
from okto_nexus.errors import OktoNexusError
from tests.session_interaction.test_queue_storage import ALICE, NOW
from tests.session_interaction.test_queue_storage import database as queue_database

database = queue_database


def _enqueue(uow, scope, intent):
    return accept_input(uow, scope=scope, author=ALICE, client_intent_id=intent,
                        capability_revision="fixture-capability", text=intent, now=NOW,
                        verify_new_authority=lambda: ("fixture-grant", 1))


def _head_and_request(uow, scope):
    uow.connection.execute("UPDATE execution_sessions SET lease_state='ACTIVE'")
    uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY'")
    head = prepare_dispatch_head(uow, scope=scope, now=NOW)
    request = CapacityRequest(CAPACITY_CONTRACT_REVISION, f"{head.input_id}:{head.input_revision}",
        CapacityScope(scope.session.server_id, scope.session.executor_id, scope.agent_id, scope.binding_id,
            scope.workspace_id, scope.workspace_binding_id, scope.session.session_id,
            1, scope.generation.value, 1, 1, 1, 1, "fixture-boot"),
        "next_turn", "sha256:" + "e" * 64, 5000)
    return head, request


def _stage(uow, scope, head, request):
    scope_data = request.scope.to_dict()
    operation_scope = {name: value for name, value in scope_data.items() if name not in {"boot_id", "connection_generation"}}
    semantic = {name: scope_data[name] for name in (
        "server_id", "executor_id", "binding_id", "agent_id", "workspace_id", "workspace_binding_id", "session_id",
        "configuration_revision",
    )}
    semantic.update(action="turn.submit", target={"kind": "none", "expected_turn_id": None}, payload={"text": head.text})
    uow.connection.execute("INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES ('operator','t')")
    uow.connection.execute("""
        INSERT INTO execution_operations(
            server_id,executor_id,session_id,operation_id,subject_agent_id,actor_agent_id,binding_id,workspace_id,
            workspace_binding_id,action,intent_hash,semantic_payload,expected_revisions_json,admission_state,created_at)
        VALUES(:server_id,:executor_id,:session_id,'operation-a',:agent_id,'operator',:binding_id,:workspace_id,
            :workspace_binding_id,'turn.submit',:intent_hash,:semantic,:scope,'ACCEPTED','t')
    """, {**scope_data, "intent_hash": execution_intent_hash(semantic), "semantic": canonical_json(semantic).decode(),
           "scope": canonical_json(operation_scope).decode()})
    uow.connection.execute("""
        INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state)
        VALUES(:server_id,:executor_id,'operation-a','PENDING')
    """, scope_data)
    reservation = CapacityReservation(capacity_reservation_id(request), request, "HELD", 1, 5000, None)
    return reservation, stage_dispatch(uow, scope=scope, head=head, operation_id="operation-a",
                                       reservation=reservation, now=NOW)


def test_prepared_request_survives_reopen_and_concurrent_input_has_no_early_operation(database):
    factory, (scope, other) = database
    with factory.unit_of_work() as uow:
        first = _enqueue(uow, scope, "first")
        second = _enqueue(uow, scope, "second")
        _enqueue(uow, other, "other")
        head, request = _head_and_request(uow, scope)
        assert head.input_id == first.input_id
        stale_head = replace(head, input_id=second.input_id)
        stale_request = replace(request, attempt_id=f"{second.input_id}:0")
        with pytest.raises(OktoNexusError) as error:
            prepare_capacity_attempt(uow, scope=scope, head=stale_head, request=stale_request, now=NOW)
        assert error.value.details["reason"] == "INPUT_CAPACITY_HEAD_CHANGED"
        prepared = prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW)
    assert prepared.state == "PREPARED" and prepared.operation_id is None and prepared.reservation is None

    reopened = ConnectionFactory(factory.config)
    try:
        with reopened.unit_of_work(write=False) as uow:
            assert read_capacity_attempt(uow, session=scope.session) == prepared
            assert read_capacity_attempt(uow, session=other.session) is None
            assert uow.connection.execute("SELECT count(*) FROM execution_operations").fetchone()[0] == 0
            assert uow.connection.execute("SELECT count(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
        with reopened.unit_of_work() as uow:
            assert prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW) == prepared
            with pytest.raises(OktoNexusError) as error:
                prepare_capacity_attempt(uow, scope=scope, head=head, request=replace(request, ttl_ms=4999), now=NOW)
            assert error.value.details["reason"] == "INPUT_CAPACITY_REQUEST_CHANGED"
            uow.connection.execute("UPDATE session_interaction_inputs SET status='CANCELLED' WHERE input_id=?",
                                   (head.input_id,))
            second_head = prepare_dispatch_head(uow, scope=scope, now=NOW)
            assert second_head.input_id == second.input_id
            with pytest.raises(OktoNexusError) as error:
                prepare_capacity_attempt(uow, scope=scope, head=second_head, request=stale_request, now=NOW)
            assert error.value.details["reason"] == "INPUT_CAPACITY_ATTEMPT_PENDING"
            assert read_capacity_attempt(uow, session=scope.session) == prepared
    finally:
        reopened.close()


def test_preparation_refuses_stale_session_and_connection_generations(database):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        _enqueue(uow, scope, "first")
        head, request = _head_and_request(uow, scope)
        old_owner = replace(request, scope=replace(request.scope, session_owner_generation=2))
        with pytest.raises(OktoNexusError) as error:
            prepare_capacity_attempt(uow, scope=scope, head=head, request=old_owner, now=NOW)
        assert error.value.details["reason"] == "INPUT_CAPACITY_REQUEST_CHANGED"
        uow.connection.execute("UPDATE execution_executors SET generation=2")
        with pytest.raises(OktoNexusError) as error:
            prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW)
        assert error.value.details["reason"] == "INPUT_CAPACITY_OWNER_CHANGED"
        assert read_capacity_attempt(uow, session=scope.session) is None


def test_staging_requires_prepared_request_and_preserves_proof_after_link(database):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        _enqueue(uow, scope, "first")
        head, request = _head_and_request(uow, scope)
        prepared = prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW)
    altered = replace(request, scope=replace(request.scope, boot_id="other-boot"))
    with pytest.raises(OktoNexusError) as error, factory.unit_of_work() as uow:
        _stage(uow, scope, head, altered)
        record_staged_capacity_attempt(uow, scope=scope, request=request, operation_id="operation-a")
    assert error.value.details["reason"] == "INPUT_CAPACITY_OPERATION_CHANGED"
    with factory.unit_of_work() as uow:
        assert read_capacity_attempt(uow, session=scope.session) == prepared
        assert uow.connection.execute("SELECT count(*) FROM execution_operations").fetchone()[0] == 0
        held, consumption = _stage(uow, scope, head, request)
        staged = record_staged_capacity_attempt(uow, scope=scope, request=request, operation_id="operation-a")
        assert staged.state == "STAGED"
        assert staged.request == request and staged.reservation == held and staged.consumption == consumption
        assert read_capacity_attempt(uow, session=scope.session) is None
        assert prepare_dispatch_head(uow, scope=scope, now=NOW) is None
    with factory.unit_of_work() as uow:
        assert read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id) == staged
        assert record_staged_capacity_attempt(uow, scope=scope, request=request, operation_id="operation-a") == staged
        with pytest.raises(OktoNexusError) as error:
            record_staged_capacity_attempt(uow, scope=scope, request=request, operation_id="operation-b")
        assert error.value.details["reason"] == "INPUT_CAPACITY_OPERATION_CHANGED"
