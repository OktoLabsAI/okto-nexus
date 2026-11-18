"""SQLite proofs of attempt identity and staging, independent of any host."""

import asyncio
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

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
from okto_nexus.adapters.outbound.sqlite.execution_dispatch_ownership import (
    reject_unsent_dispatch,
    release_dispatch_owner,
)
from okto_nexus.adapters.outbound.sqlite.session_interaction import (
    accept_input,
    confirm_dispatch_capacity,
    prepare_dispatch_head,
    read_dispatch_capacity,
    stage_dispatch,
)
from okto_nexus.adapters.outbound.sqlite.session_interaction_capacity_attempts import (
    prepare_capacity_attempt,
    read_capacity_attempt,
    record_staged_capacity_attempt,
)
from okto_nexus.application import session_interaction_capacity
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch
from okto_nexus.application.execution_leases import ExecutionChannel
from okto_nexus.application.execution_semantics import execution_intent_hash
from okto_nexus.application.runtime_availability import CapacityHost
from okto_nexus.domain.session_interaction import InputDeliveryState
from okto_nexus.errors import ErrorCode, OktoNexusError
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


@pytest.mark.parametrize('expired', [False, True])
def test_capacity_step_commits_request_before_host_and_uses_the_same_attempt(database, monkeypatch, expired):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        queued = _enqueue(uow, scope, 'first')
        head, request = _head_and_request(uow, scope)
    held = CapacityReservation(capacity_reservation_id(request), request, 'HELD', 1, 5000, None)
    result = replace(held, state='EXPIRED_UNCONSUMED', capacity_revision=2, remaining_ms=0) if expired else held

    def prepare(uow, **_options):
        current = prepare_dispatch_head(uow, scope=scope, now=NOW)
        return prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW) if current else None

    def stage(uow, *, reservation, **_options):
        assert reservation == held
        _, consumption = _stage(uow, scope, head, request)
        record_staged_capacity_attempt(uow, scope=scope, request=request, operation_id=consumption.turn_operation_id)
        return consumption

    monkeypatch.setattr(session_interaction_capacity, 'prepare_input_capacity', prepare)
    monkeypatch.setattr(session_interaction_capacity, 'admit_held_input', stage)

    class Peer:
        observed = None
        reserve_calls = consume_calls = 0

        async def get_capacity_reservation(self, supplied):
            assert supplied == request
            return self.observed

        async def try_reserve_capacity(self, supplied):
            assert supplied == request
            with factory.unit_of_work(write=False) as uow:
                assert read_capacity_attempt(uow, session=scope.session).request == request
                assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 0
            self.reserve_calls += 1
            self.observed = result
            return self.observed

        async def consume_capacity(self, supplied, reservation_id, consumption):
            assert (supplied, reservation_id) == (request, held.reservation_id)
            self.consume_calls += 1
            with factory.unit_of_work(write=False) as uow:
                prior = read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id)
                assert prior.state == 'STAGED' and prior.consumption == consumption
            self.observed = replace(held, state='CONSUMED', capacity_revision=2, consumption=consumption)
            return self.observed

    peer = Peer()
    access = SimpleNamespace(clock=SimpleNamespace(now_iso=lambda: NOW.isoformat()))
    host = CapacityHost(ExecutionChannel(scope.session.server_id, scope.session.executor_id, 'fixture-connection', 1),
                        peer, request.scope.boot_id)
    args = {'factory': factory, 'access': access, 'host': host, 'scope': scope,
            'authority_fence': lambda: nullcontext(lambda _: True), 'current_capability_revision': lambda *_: None,
            'fresh_publications': {}, 'remote_ready': True}
    observed = asyncio.run(session_interaction_capacity.advance_input_capacity(**args))
    assert observed.state == ('EXPIRED_UNCONSUMED' if expired else 'CONSUMED')
    assert asyncio.run(session_interaction_capacity.advance_input_capacity(**args)) is None
    assert peer.reserve_calls == 1 and peer.consume_calls == int(not expired)
    with factory.unit_of_work() as uow:
        prior = read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id)
        if expired:
            assert prior.resolution == observed and prior.operation_id is None
            current = _enqueue(uow, scope, 'first')
            assert current.input_id == queued.input_id and current.status is InputDeliveryState.REFUSED_BEFORE_SEND
        else:
            assert prior.state == 'STAGED' and prior.operation_id == observed.consumption.turn_operation_id


@pytest.mark.parametrize('staged', [False, True])
def test_replacement_host_only_observes_the_original_attempt(database, monkeypatch, staged):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        first = _enqueue(uow, scope, 'first')
        second = _enqueue(uow, scope, 'second')
        head, request = _head_and_request(uow, scope)
        prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW)
        if staged:
            held, consumption = _stage(uow, scope, head, request)
            record_staged_capacity_attempt(uow, scope=scope, request=request, operation_id=consumption.turn_operation_id)
        else:
            uow.connection.execute("UPDATE session_interaction_inputs SET status='CANCELLED' WHERE input_id=?",
                                   (first.input_id,))
        uow.connection.execute('UPDATE execution_executors SET generation=2')

    historical = held if staged else CapacityReservation(capacity_reservation_id(request), request,
        'EXPIRED_UNCONSUMED', 2, 0, None)

    class ReconnectedPeer:
        async def get_capacity_reservation(self, supplied):
            assert supplied == request
            return historical

    def unexpected_prepare(*args, **kwargs):
        pytest.fail('A historical lookup cannot prepare work on the replacement host.')

    monkeypatch.setattr(session_interaction_capacity, 'prepare_input_capacity', unexpected_prepare)
    access = SimpleNamespace(clock=SimpleNamespace(now_iso=lambda: NOW.isoformat()))
    host = CapacityHost(ExecutionChannel(scope.session.server_id, scope.session.executor_id, 'new-connection', 2),
                        ReconnectedPeer(), 'new-boot')
    assert asyncio.run(session_interaction_capacity.advance_input_capacity(factory=factory, access=access,
        host=host, scope=scope, authority_fence=lambda: nullcontext(lambda _: True),
        current_capability_revision=lambda *_: None, fresh_publications={}, remote_ready=True)) == historical
    with factory.unit_of_work() as uow:
        old = read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id)
        if staged:
            assert old.state == 'STAGED'
            assert uow.connection.execute('SELECT dispatch_state FROM execution_dispatch_outbox').fetchone()[0] == (
                'WAITING_INTERACTION_CAPACITY')
        else:
            assert old.resolution == historical
            assert read_capacity_attempt(uow, session=scope.session) is None
            following = _enqueue(uow, scope, 'second')
            assert following.input_id == second.input_id and following.status is InputDeliveryState.QUEUED
            assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 0


@pytest.mark.parametrize('revoked', [False, True])
def test_release_tombstone_recovers_abandoned_prepared_attempt(database, monkeypatch, revoked):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        _enqueue(uow, scope, 'first')
        head, request = _head_and_request(uow, scope)
        original = prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW)
        if not revoked:
            uow.connection.execute("UPDATE session_interaction_inputs SET status='EXPIRED' WHERE input_id=?", (head.input_id,))

    released = CapacityReservation(capacity_reservation_id(request), request, 'RELEASED', 2, 0, None)

    class Peer:
        observation = None
        calls = 0

        async def get_capacity_reservation(self, supplied):
            assert supplied == request
            return self.observation

        async def release_capacity(self, supplied, reservation_id, reason):
            assert (supplied, reservation_id, reason) == (request, released.reservation_id,
                                                         'REVOKED' if revoked else 'CANCELLED')
            with factory.unit_of_work() as uow:
                expected = InputDeliveryState.BLOCKED_AUTH if revoked else InputDeliveryState.EXPIRED
                assert _enqueue(uow, scope, 'first').status is expected
                assert read_capacity_attempt(uow, session=scope.session) == original
            self.calls += 1
            self.observation = released
            raise ConnectionError('fixture reply lost after tombstone')

    def prepare(*args, **kwargs):
        if revoked:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Fixture author expired.')

    monkeypatch.setattr(session_interaction_capacity, 'prepare_input_capacity', prepare)
    peer = Peer()
    host = CapacityHost(ExecutionChannel(scope.session.server_id, scope.session.executor_id, 'fixture-connection', 1),
                        peer, request.scope.boot_id)
    access = SimpleNamespace(clock=SimpleNamespace(now_iso=lambda: NOW.isoformat()))
    args = {'factory': factory, 'access': access, 'host': host, 'scope': scope,
            'authority_fence': lambda: nullcontext(lambda _: True), 'current_capability_revision': lambda *_: None,
            'fresh_publications': {}, 'remote_ready': True}
    with pytest.raises(ConnectionError, match='reply lost'):
        asyncio.run(session_interaction_capacity.advance_input_capacity(**args))
    with factory.unit_of_work(write=False) as uow:
        assert read_capacity_attempt(uow, session=scope.session) == original
    assert asyncio.run(session_interaction_capacity.advance_input_capacity(**args)) == released
    assert peer.calls == 1
    with factory.unit_of_work(write=False) as uow:
        assert read_capacity_attempt(uow, session=scope.session) is None
        assert read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id).resolution == released
        assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 0


@pytest.mark.parametrize('crossed_send_cut', [False, True])
def test_recovery_releases_consumed_slot_only_for_exact_unsent_refusal(database, crossed_send_cut):
    factory, (scope, _) = database
    channel = ExecutionChannel(scope.session.server_id, scope.session.executor_id, 'fixture-connection', 1)
    with factory.unit_of_work() as uow:
        queued = _enqueue(uow, scope, 'first')
        uow.connection.execute('UPDATE execution_executors SET owner_instance_id=? WHERE executor_id=?',
                               (channel.connection_id, channel.executor_id))
        head, request = _head_and_request(uow, scope)
        prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW)
        held, consumption = _stage(uow, scope, head, request)
        operation_id = consumption.turn_operation_id
        record_staged_capacity_attempt(uow, scope=scope, request=request, operation_id=operation_id)
        consumed = replace(held, state='CONSUMED', capacity_revision=2, consumption=consumption)
        confirm_dispatch_capacity(uow, scope=scope, operation_id=operation_id, observed=consumed)
    reservation = reserve_execution_dispatch(factory, server_id=channel.server_id, executor_id=channel.executor_id,
                                             remote_ready=True, channel=channel)
    assert reservation is not None and reservation.operation_id == operation_id
    if crossed_send_cut:
        with factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_dispatch_outbox SET dispatch_state='SENDING' WHERE operation_id=?",
                                   (operation_id,))
            uow.connection.execute('UPDATE session_interaction_inputs SET possible_effect=1 WHERE input_id=?',
                                   (queued.input_id,))
        release_dispatch_owner(factory, channel=channel)
    else:
        reject_unsent_dispatch(factory, reservation=reservation,
            error=OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Fixture authority was revoked.'))

    released = replace(consumed, state='RELEASED', capacity_revision=3, remaining_ms=0)

    class Peer:
        calls = 0

        async def release_capacity(self, supplied, reservation_id, reason):
            assert (supplied, reservation_id, reason) == (request, held.reservation_id, 'REVOKED')
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError('fixture reply lost after release')
            return released

    peer = Peer()
    args = {'factory': factory, 'scope': scope, 'operation_id': operation_id, 'capacity': peer}
    if crossed_send_cut:
        assert asyncio.run(session_interaction_capacity.consume_input_capacity(**args)) == consumed
        assert peer.calls == 0
    else:
        with pytest.raises(ConnectionError, match='reply lost'):
            asyncio.run(session_interaction_capacity.consume_input_capacity(**args))
        with factory.unit_of_work(write=False) as uow:
            assert read_dispatch_capacity(uow, scope=scope, operation_id=operation_id).state == 'CONSUMED'
        assert asyncio.run(session_interaction_capacity.consume_input_capacity(**args)) == released
        assert asyncio.run(session_interaction_capacity.consume_input_capacity(**args)) == released
        assert peer.calls == 2
    with factory.unit_of_work() as uow:
        receipt = _enqueue(uow, scope, 'first')
        assert receipt.input_id == queued.input_id and receipt.operation_id == operation_id
        assert receipt.status is (InputDeliveryState.DELIVERY_UNKNOWN if crossed_send_cut
                                  else InputDeliveryState.REFUSED_BEFORE_SEND)
        assert receipt.possible_effect == crossed_send_cut
        assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM runtime_execution_grants').fetchone()[0] == 0
