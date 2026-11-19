"""SQLite acceptance only. Seeded scope rows carry no runtime grant or lease."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from nexus_connector_core import (
    CAPACITY_CONTRACT_REVISION,
    CapacityConsumption,
    CapacityRequest,
    CapacityReservation,
    CapacityScope,
)
from nexus_connector_core.protocol import canonical_json

from okto_nexus.adapters.outbound.sqlite.execution_session_release import SqliteSessionReleaseRepository
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.adapters.outbound.sqlite.session_interaction import (
    accept_input,
    prepare_dispatch_head,
    project_input_receipt,
    read_dispatch_capacity,
    record_input_delivery,
)
from okto_nexus.application.session_interaction_capacity import consume_input_capacity
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.execution.keys import SessionKey, SessionOwnerGeneration
from okto_nexus.domain.session_interaction import (
    InputAuthor,
    InputDeliveryState,
    InputScope,
)
from okto_nexus.errors import OktoNexusError

NOW = datetime(2026, 1, 1, tzinfo=UTC)
ALICE = InputAuthor("synthetic-auth-reference-a", "web")
BOB = InputAuthor("synthetic-auth-reference-b", "nexus_cli")


@pytest.fixture
def database(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home"), "--embedding-mode", "off", "--metrics-mode", "disabled"])
    factory = deps.connection_factory
    with factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO agents(agent_id,created_at) VALUES ('recipient','t')")
        scopes = []
        for suffix in ("a", "b"):
            executor, workspace, endpoint = (f"{prefix}-{suffix}" for prefix in ("executor", "workspace", "endpoint"))
            binding, workspace_binding = f"binding-{suffix}", f"wb-{suffix}"
            c.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES (?,'t')", (workspace,))
            c.execute("""
                INSERT INTO execution_executors(
                    server_id,executor_id,connector_id,registered_by_agent_id,kind,control_state,generation)
                VALUES('server',?,?,'recipient','remote','ACTIVE',1)
            """, (executor, f"connector-{suffix}"))
            c.execute("""
                INSERT INTO execution_workspace_bindings(
                    server_id,executor_id,workspace_id,workspace_binding_id,realization_handle,revision,status)
                VALUES('server',?,?,?,'realization',1,'ACTIVE')
            """, (executor, workspace, workspace_binding))
            c.execute("""
                INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,created_at,updated_at)
                VALUES(?,'recipient',?,'codex_app_server','nxl-r4','t','t')
            """, (endpoint, workspace))
            c.execute("""
                INSERT INTO execution_bindings(
                    server_id,executor_id,binding_id,endpoint_id,workspace_binding_id,candidate_ref,
                    inventory_revision,realization_ref,realization_revision,binding_revision)
                VALUES('server',?,?,?,?,'candidate','inventory','realization',1,1)
            """, (executor, binding, endpoint, workspace_binding))
            c.execute("""
                INSERT INTO execution_sessions(
                    server_id,executor_id,session_id,binding_id,workspace_id,workspace_binding_id,open_operation_id,
                    owner_generation,lifecycle_state,lease_state)
                VALUES('server',?,'same-short-id',?,?,?,'open-r4-id',1,'READY','CLOSED')
            """, (executor, binding, workspace, workspace_binding))
            scopes.append(InputScope(SessionKey("server", executor, "same-short-id"), SessionOwnerGeneration(1),
                                     binding, workspace, workspace_binding, "recipient"))
    return factory, scopes


def enqueue(uow, scope, *, intent="request", author=ALICE, text="Unmodified synthetic message.", now=NOW):
    return accept_input(uow, scope=scope, author=author, client_intent_id=intent,
                        capability_revision="capability-v1", text=text, now=now,
                        verify_new_authority=lambda: None)


def test_atomic_storage_and_retry_do_not_create_r4_operations(database):
    factory, (scope, sibling) = database
    with pytest.raises(RuntimeError), factory.unit_of_work() as uow:
        enqueue(uow, scope)
        raise RuntimeError("abort the write before sending acknowledgement")
    with factory.unit_of_work() as uow:
        first = enqueue(uow, scope)
        assert enqueue(uow, scope) == first
        with pytest.raises(OktoNexusError) as error:
            enqueue(uow, scope, text="Modified retry")
        assert error.value.code == "CONFLICT"
        assert first.sequence == 1 and first.status is InputDeliveryState.QUEUED
        assert first.operation_id is None and not first.possible_effect
        assert enqueue(uow, sibling).sequence == 1
    with factory.unit_of_work() as uow:
        assert enqueue(uow, scope) == first
    with factory.unit_of_work(write=False) as uow:
        c = uow.connection
        assert c.execute("SELECT count(*) FROM session_interaction_inputs").fetchone()[0] == 2
        assert c.execute("SELECT count(*) FROM execution_operations").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM execution_leases").fetchone()[0] == 0


def test_concurrent_authors_commit_distinct_fifo_sequences(database):
    factory, (scope, _) = database
    ready = Barrier(2, timeout=5)

    def send(author):
        ready.wait()
        with factory.unit_of_work() as uow:
            return enqueue(uow, scope, author=author)

    with ThreadPoolExecutor(max_workers=2) as workers:
        accepted = list(workers.map(send, (ALICE, BOB)))
    assert {item.sequence for item in accepted} == {1, 2}
    assert len({item.input_id for item in accepted}) == 2


def test_scope_or_generation_mismatch_refuses_without_creating_a_queue(database):
    factory, (scope, sibling) = database
    for selection in (replace(scope, workspace_id=sibling.workspace_id),
                      replace(scope, generation=SessionOwnerGeneration(2))):
        with pytest.raises(OktoNexusError), factory.unit_of_work() as uow:
            enqueue(uow, selection)
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM session_interaction_queues").fetchone()[0] == 0


def test_read_transaction_and_inconsistent_workspace_binding_are_refused(database):
    factory, (scope, sibling) = database
    with pytest.raises(RuntimeError, match="write unit of work"), factory.unit_of_work(write=False) as uow:
        enqueue(uow, scope)
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_workspace_bindings SET workspace_id=? WHERE workspace_binding_id=?",
                               (sibling.workspace_id, scope.workspace_binding_id))
    with pytest.raises(OktoNexusError), factory.unit_of_work() as uow:
        enqueue(uow, scope)


def test_pending_limit_rejects_new_intents_and_preserves_existing_receipts(database, monkeypatch):
    factory, (scope, _) = database
    monkeypatch.setattr("okto_nexus.adapters.outbound.sqlite.session_interaction.MAX_PENDING", 1)
    with factory.unit_of_work() as uow:
        accepted = enqueue(uow, scope)
    with pytest.raises(OktoNexusError) as error, factory.unit_of_work() as uow:
        enqueue(uow, scope, intent="second")
    assert error.value.details["reason"] == "INPUT_QUEUE_FULL"
    with factory.unit_of_work() as uow:
        assert enqueue(uow, scope) == accepted
        row = uow.connection.execute("SELECT expires_at FROM session_interaction_inputs").fetchone()
        assert row["expires_at"] == "2026-01-02T00:00:00+00:00"


def test_acceptance_enforces_encoded_runtime_bound(database):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        with pytest.raises(OktoNexusError) as error:
            enqueue(uow, scope, text='"' * (32 * 1024))
        assert error.value.details["reason"] == "INPUT_PAYLOAD_TOO_LARGE"
        assert enqueue(uow, scope, text="a" * (64 * 1024 - len('{"text":""}'))).sequence == 1


def test_preparation_expires_only_unsent_inputs_in_the_exact_session(database):
    factory, (scope, sibling) = database
    later = NOW + timedelta(hours=12)
    with factory.unit_of_work() as uow:
        first = enqueue(uow, scope, intent="first")
        second = enqueue(uow, scope, intent="second", now=later, text="Second input")
        enqueue(uow, sibling)
        assert prepare_dispatch_head(uow, scope=scope, now=NOW) is None
        uow.connection.execute("UPDATE execution_sessions SET lease_state='ACTIVE'")
        assert prepare_dispatch_head(uow, scope=scope, now=later).input_id == first.input_id
    with factory.unit_of_work() as uow:
        head = prepare_dispatch_head(uow, scope=scope, now=NOW + timedelta(hours=24))
        assert head.input_id == second.input_id and head.text == "Second input"
        first_retry = enqueue(uow, scope, intent="first")
        assert first_retry.status is InputDeliveryState.EXPIRED and first_retry.input_revision == 1
        assert first_retry.queue_revision == 3
        assert enqueue(uow, sibling).status is InputDeliveryState.QUEUED
        assert prepare_dispatch_head(uow, scope=scope, now=NOW + timedelta(hours=24)) == head
        assert enqueue(uow, scope, intent="first").queue_revision == 3


def test_preparation_keeps_blocked_head_ahead_of_later_input(database):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        first = enqueue(uow, scope, intent="first")
        enqueue(uow, scope, intent="second", now=NOW + timedelta(hours=12))
        uow.connection.execute("UPDATE execution_sessions SET lease_state='ACTIVE'")
        uow.connection.execute("UPDATE session_interaction_inputs SET status='BLOCKED_AUTH' WHERE input_id=?",
                               (first.input_id,))
        assert prepare_dispatch_head(uow, scope=scope, now=NOW + timedelta(hours=24)) is None
        assert enqueue(uow, scope, intent="first").status is InputDeliveryState.BLOCKED_AUTH
        uow.connection.execute("UPDATE session_interaction_inputs SET status='CANCELLED' WHERE input_id=?",
                               (first.input_id,))
        uow.connection.execute("UPDATE execution_sessions SET owner_generation=2")
        assert prepare_dispatch_head(uow, scope=scope, now=NOW) is None
        assert prepare_dispatch_head(uow, scope=replace(scope, generation=SessionOwnerGeneration(2)), now=NOW) is None


def test_canonical_release_blocks_only_unsent_inputs_in_the_closed_session(database):
    factory, (scope, sibling) = database
    key = (scope.session.server_id, scope.session.executor_id, scope.session.session_id)
    release = {
        "scope": {"server_id": key[0], "executor_id": key[1], "session_id": key[2],
                  "session_owner_generation": scope.generation.value},
        "opening_operation_id": "open-r4-id",
    }
    repo = SqliteSessionReleaseRepository()
    with factory.unit_of_work() as uow:
        conn = uow.connection
        enqueue(uow, scope)
        enqueue(uow, scope, intent="another-unsent")
        linked = enqueue(uow, scope, intent="uncertain")
        other = enqueue(uow, sibling)
        conn.execute("""
            INSERT INTO execution_operations(server_id,executor_id,session_id,operation_id,subject_agent_id,actor_agent_id,
                binding_id,workspace_id,workspace_binding_id,action,intent_hash,semantic_payload,expected_revisions_json,
                admission_state,created_at)
            VALUES(?,?,?,'uncertain-operation','recipient','recipient',?,?,?,'turn.submit','test','{}','{}','ACCEPTED','t')
        """, (*key, scope.binding_id, scope.workspace_id, scope.workspace_binding_id))
        conn.execute("UPDATE session_interaction_inputs SET status='DELIVERY_UNKNOWN',possible_effect=1,"
                     "operation_id='uncertain-operation' WHERE input_id=?", (linked.input_id,))
        queued = enqueue(uow, scope)
        second = enqueue(uow, scope, intent="another-unsent")
        uncertain = enqueue(uow, scope, intent="uncertain")
        conn.execute("UPDATE execution_sessions SET lease_state='SUPERSEDED' "
                     "WHERE server_id=? AND executor_id=? AND session_id=?", key)
        assert enqueue(uow, scope) == queued

    with pytest.raises(RuntimeError), factory.unit_of_work() as uow:
        repo.close(uow, release)
        raise RuntimeError("abort the closure transaction")

    with factory.unit_of_work() as uow:
        assert enqueue(uow, scope) == queued
        repo.close(uow, release)
        for intent, original in (("request", queued), ("another-unsent", second)):
            assert enqueue(uow, scope, intent=intent) == replace(
                original, status=InputDeliveryState.BLOCKED_SESSION, input_revision=original.input_revision + 1,
                queue_revision=queued.queue_revision + 1,
            )
        assert enqueue(uow, scope, intent="uncertain") == replace(uncertain, queue_revision=queued.queue_revision + 1)
        assert enqueue(uow, sibling) == other
        repo.close(uow, release)
        assert enqueue(uow, scope).queue_revision == queued.queue_revision + 1
        assert prepare_dispatch_head(uow, scope=scope, now=NOW) is None
        assert uow.connection.execute("SELECT count(*) FROM execution_operations").fetchone()[0] == 1


def test_retired_queue_backfill_preserves_receipts_and_is_idempotent(database):
    factory, (scope, sibling) = database
    with factory.unit_of_work() as uow:
        retired = enqueue(uow, scope)
        live = enqueue(uow, sibling)
        uow.connection.execute("DROP TRIGGER session_interaction_block_retired_inputs")
        uow.connection.execute("DELETE FROM schema_migrations WHERE version=187")
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='FAILED' WHERE executor_id=?",
                               (scope.session.executor_id,))
        assert enqueue(uow, scope) == retired

    assert MigrationRunner(factory).apply() == [187]
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work() as uow:
        assert enqueue(uow, scope) == replace(retired, status=InputDeliveryState.BLOCKED_SESSION,
                                              input_revision=retired.input_revision + 1,
                                              queue_revision=retired.queue_revision + 1)
        assert enqueue(uow, sibling) == live
        assert uow.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_receipt_projection_keeps_native_acceptance_and_exact_executor(database):
    factory, (scope, sibling) = database
    with factory.unit_of_work() as uow:
        conn = uow.connection
        for selection in (scope, sibling):
            pending = enqueue(uow, selection)
            conn.execute("""
                INSERT INTO execution_operations(server_id,executor_id,session_id,operation_id,subject_agent_id,actor_agent_id,
                    binding_id,workspace_id,workspace_binding_id,action,intent_hash,semantic_payload,expected_revisions_json,
                    admission_state,created_at)
                VALUES(?,?,?,'same-operation','recipient','recipient',?,?,?,'turn.submit','test','{}','{}','ACCEPTED','t')
            """, (selection.session.server_id, selection.session.executor_id, selection.session.session_id,
                  selection.binding_id, selection.workspace_id, selection.workspace_binding_id))
            conn.execute("UPDATE session_interaction_inputs SET status='DISPATCHING',operation_id='same-operation',"
                         "possible_effect=1 WHERE input_id=?", (pending.input_id,))
        key = (scope.session.server_id, scope.session.executor_id, 'same-operation')
        record_input_delivery(conn, operation_key=key, state=InputDeliveryState.REFUSED_BEFORE_SEND, require_unsent=True)
        project_input_receipt(conn, operation_key=key, stage='SUBMITTED', possible_effect=True, native_id='turn')
        assert enqueue(uow, scope).status is InputDeliveryState.DISPATCHING
        record_input_delivery(conn, operation_key=key, state=InputDeliveryState.DELIVERY_UNKNOWN)
        unknown = enqueue(uow, scope)
        assert unknown.status is InputDeliveryState.DELIVERY_UNKNOWN and unknown.possible_effect
        assert unknown.operation_id == 'same-operation'
        assert enqueue(uow, sibling).status is InputDeliveryState.DISPATCHING
        project_input_receipt(conn, operation_key=key, stage='ACCEPTED', possible_effect=True, native_id='turn')
        accepted = enqueue(uow, scope)
        assert accepted.status is InputDeliveryState.ACCEPTED_NATIVE and accepted.possible_effect
        project_input_receipt(conn, operation_key=key, stage='OUTCOME_UNKNOWN', possible_effect=True, native_id='turn')
        assert enqueue(uow, scope) == accepted


@pytest.mark.parametrize('expired', [False, True])
def test_capacity_outcome_recovers_same_operation_and_keeps_outbox_fenced(database, expired):
    factory, (scope, _) = database
    operation_id = 'fixture-operation'
    intent_hash = 'sha256:' + '0' * 64
    cap_scope = CapacityScope(server_id=scope.session.server_id, executor_id=scope.session.executor_id,
        session_id=scope.session.session_id, agent_id=scope.agent_id, binding_id=scope.binding_id,
        workspace_id=scope.workspace_id, workspace_binding_id=scope.workspace_binding_id,
        connection_generation=1, session_owner_generation=1, authorization_revision=1,
        configuration_revision=1, binding_revision=1, credential_epoch=1, boot_id='fixture-boot')
    with factory.unit_of_work() as uow:
        conn = uow.connection
        queued = enqueue(uow, scope)
        request = CapacityRequest(CAPACITY_CONTRACT_REVISION, f'{queued.input_id}:{queued.input_revision}',
                                  cap_scope, 'next_turn', intent_hash, 10000)
        held = CapacityReservation('fixture-held', request, 'HELD', 1, 9000, None)
        consumption = CapacityConsumption(operation_id, intent_hash, None, None)
        conn.execute("UPDATE execution_sessions SET lease_state='ACTIVE'")
        conn.execute("UPDATE execution_executors SET control_state='CONTROL_READY'")
        conn.execute("""
            INSERT INTO execution_operations(server_id,executor_id,session_id,operation_id,subject_agent_id,actor_agent_id,
                binding_id,workspace_id,workspace_binding_id,action,intent_hash,semantic_payload,expected_revisions_json,
                admission_state,created_at)
            VALUES(?,?,?,?,'recipient','recipient',?,?,?,'turn.submit',?,'{}','{}','ACCEPTED','t')
        """, (scope.session.server_id, scope.session.executor_id, scope.session.session_id, operation_id,
              scope.binding_id, scope.workspace_id, scope.workspace_binding_id, intent_hash))
        conn.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state) "
                     "VALUES(?,?,?,'WAITING_INTERACTION_CAPACITY')",
                     (scope.session.server_id, scope.session.executor_id, operation_id))
        conn.execute("UPDATE session_interaction_inputs SET operation_id=?,status='DISPATCHING', "
            "capacity_state='WAITING_CONSUMPTION',capacity_reservation_json=?,capacity_consumption_json=? WHERE input_id=?",
            (operation_id, canonical_json(held.to_dict()).decode(), canonical_json(consumption.to_dict()).decode(),
             queued.input_id))

    confirmed = replace(held, state='CONSUMED', capacity_revision=2, consumption=consumption)

    class Peer:
        observation = held
        consume_calls = 0

        async def get_capacity_reservation(self, supplied):
            assert supplied == request
            return self.observation

        async def consume_capacity(self, supplied, reservation_id, identity):
            assert (supplied, reservation_id, identity) == (request, held.reservation_id, consumption)
            self.consume_calls += 1
            self.observation = confirmed
            raise ConnectionError('fixture loses confirmation after host consumption')

    peer = Peer()
    lookup = {'scope': scope, 'operation_id': operation_id}
    arguments = {**lookup, 'factory': factory, 'capacity': peer}
    if expired:
        peer.observation = replace(held, state='EXPIRED_UNCONSUMED', capacity_revision=2, remaining_ms=0)
        assert asyncio.run(consume_input_capacity(**arguments)) == peer.observation
        assert asyncio.run(consume_input_capacity(**arguments)) == peer.observation
        assert peer.consume_calls == 0
        with factory.unit_of_work() as uow:
            assert read_dispatch_capacity(uow, **lookup).state == 'CANCELLED_NO_EFFECT'
            assert uow.connection.execute('SELECT dispatch_state FROM execution_dispatch_outbox').fetchone()[0] == (
                'RESOLVED_TERMINAL')
            refused = enqueue(uow, scope)
            assert refused.status is InputDeliveryState.REFUSED_BEFORE_SEND
            assert not refused.possible_effect and refused.operation_id == operation_id
        return
    with pytest.raises(ConnectionError, match='loses confirmation'):
        asyncio.run(consume_input_capacity(**arguments))
    with factory.unit_of_work(write=False) as uow:
        assert read_dispatch_capacity(uow, **lookup).state == 'NEEDS_RECONCILIATION'
        assert uow.connection.execute('SELECT dispatch_state FROM execution_dispatch_outbox').fetchone()[0] == (
            'WAITING_INTERACTION_CAPACITY')
    assert asyncio.run(consume_input_capacity(**arguments)) == confirmed
    assert asyncio.run(consume_input_capacity(**arguments)) == confirmed
    assert peer.consume_calls == 1
    with factory.unit_of_work(write=False) as uow:
        assert read_dispatch_capacity(uow, **lookup).state == 'CONSUMED'
        assert uow.connection.execute('SELECT dispatch_state FROM execution_dispatch_outbox').fetchone()[0] == 'PENDING'
