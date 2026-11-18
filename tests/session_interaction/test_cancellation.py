"""Check cancellation and the capacity-attempt boundary with real SQLite writers."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.http.operator_auth import OperatorAuth
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.session_interaction_cancellation import (
    cancel_input,
)
from okto_nexus.adapters.outbound.sqlite.session_interaction_capacity_attempts import (
    fence_prepared_capacity_release,
    prepare_capacity_attempt,
    read_capacity_attempt,
    record_staged_capacity_attempt,
)
from okto_nexus.application.session_interaction_authority import cancel_human_input
from okto_nexus.domain.execution.keys import SessionOwnerGeneration
from okto_nexus.domain.session_interaction import InputAuthor, InputDeliveryState
from okto_nexus.errors import ErrorCode, OktoNexusError
from tests.session_interaction.test_capacity_attempts import (
    _enqueue,
    _head_and_request,
    _stage,
)
from tests.session_interaction.test_queue_storage import ALICE, BOB, NOW, enqueue
from tests.session_interaction.test_queue_storage import database as queue_database

database = queue_database


def _cancel(uow, scope, item, **changes):
    params = {
        "scope": scope, "author": ALICE, "input_id": item.input_id,
        "expected_queue_revision": item.queue_revision, "expected_input_revision": item.input_revision,
        "capability_revision": "fixture-capability", "verify_authority": lambda: "fixture-capability",
    }
    return cancel_input(uow, **(params | changes))


def test_human_cancellation_uses_the_existing_login_without_a_productive_grant(database, tmp_path):
    factory, (scope, _) = database
    auth = OperatorAuth(tmp_path)
    assert auth.configure('fixture-operator', 'fixture-password', local=True)
    active = auth.login('fixture-operator', 'fixture-password')
    other = auth.login('fixture-operator', 'fixture-password')
    author = InputAuthor(auth.authority_reference(active), 'web')
    another = InputAuthor(auth.authority_reference(other), 'web')
    with factory.unit_of_work() as uow:
        first = enqueue(uow, scope, intent='first', author=author)
        second = enqueue(uow, scope, intent='second', author=another)

    def authenticate(context, *, uow, require_feature):
        assert context.authentication_source == 'operator_session' and not require_feature
        return True

    args = {'factory': factory, 'access': SimpleNamespace(authenticate=authenticate), 'authority_fence': auth.authority_fence,
            'current_cancel_revision': lambda *_: 'fixture-capability', 'scope': scope,
            'capability_revision': 'fixture-capability', 'expected_queue_revision': second.queue_revision}
    with pytest.raises(OktoNexusError) as error:
        cancel_human_input(author=another, input_id=first.input_id, expected_input_revision=first.input_revision, **args)
    assert error.value.code == ErrorCode.NOT_FOUND
    auth.logout(other)
    with pytest.raises(OktoNexusError) as error:
        cancel_human_input(author=another, input_id=second.input_id, expected_input_revision=second.input_revision, **args)
    assert error.value.code == ErrorCode.PERMISSION_DENIED
    receipt = cancel_human_input(author=author, input_id=first.input_id, expected_input_revision=first.input_revision, **args)
    assert receipt.status is InputDeliveryState.CANCELLED and not receipt.possible_effect
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM runtime_execution_grants').fetchone()[0] == 0


@pytest.mark.parametrize("state", ["QUEUED", "PAUSED"])
def test_cancel_preserves_input_history_later_work_and_current_turn(database, state):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        first = enqueue(uow, scope, intent="first")
        last = enqueue(uow, scope, intent="last")
        conn = uow.connection
        conn.execute("UPDATE session_interaction_inputs SET status=? WHERE input_id=?", (state, first.input_id))
        conn.execute("""
            INSERT INTO execution_operations(
                server_id,executor_id,session_id,operation_id,subject_agent_id,actor_agent_id,
                binding_id,workspace_id,workspace_binding_id,action,intent_hash,semantic_payload,
                expected_revisions_json,admission_state,created_at)
            VALUES(?,?,?,'running-turn','recipient','recipient',?,?,?,'turn.submit','test','{}','{}','DISPATCHED','t')
        """, (scope.session.server_id, scope.session.executor_id, scope.session.session_id,
              scope.binding_id, scope.workspace_id, scope.workspace_binding_id))
        conn.execute("""
            INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,attempt_no)
            VALUES(?,?,'running-turn','SENDING',1)
        """, (scope.session.server_id, scope.session.executor_id))
        input_before = [dict(row) for row in conn.execute("SELECT * FROM session_interaction_inputs ORDER BY enqueue_sequence")]
        operation = dict(conn.execute("SELECT * FROM execution_operations").fetchone())
        outbox = dict(conn.execute("SELECT * FROM execution_dispatch_outbox").fetchone())

        cancelled = _cancel(uow, scope, first, expected_queue_revision=last.queue_revision)
        assert cancelled.status == InputDeliveryState.CANCELLED
        assert cancelled.sequence == first.sequence and cancelled.input_revision == first.input_revision + 1
        assert cancelled.queue_revision == last.queue_revision + 1
        assert cancelled.operation_id is None and not cancelled.possible_effect
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        rows = [dict(row) for row in conn.execute("SELECT * FROM session_interaction_inputs ORDER BY enqueue_sequence")]
        assert rows == [input_before[0] | {"status": "CANCELLED", "input_revision": 1}, input_before[1]]
        assert dict(conn.execute("SELECT * FROM execution_operations").fetchone()) == operation
        assert dict(conn.execute("SELECT * FROM execution_dispatch_outbox").fetchone()) == outbox


def test_cancel_requires_exact_author_scope_and_current_revisions(database):
    factory, (scope, other) = database
    with factory.unit_of_work() as uow:
        first = enqueue(uow, scope)
        last = enqueue(uow, scope, intent="later")
        for selection, author in (
            (scope, BOB),
            (scope, replace(ALICE, surface="nexus_cli")),
            (other, ALICE),
            (replace(scope, generation=SessionOwnerGeneration(2)), ALICE),
        ):
            with pytest.raises(OktoNexusError) as error:
                _cancel(uow, selection, first, author=author, expected_queue_revision=last.queue_revision)
            assert error.value.code == ErrorCode.NOT_FOUND
        for queue_revision, input_revision in ((first.queue_revision, 0), (last.queue_revision, 1)):
            with pytest.raises(OktoNexusError) as error:
                _cancel(uow, scope, first, expected_queue_revision=queue_revision, expected_input_revision=input_revision)
            assert error.value.details["reason"] == "INPUT_REVISION_CHANGED"
        with pytest.raises(OktoNexusError) as error:
            _cancel(uow, scope, first, expected_queue_revision=last.queue_revision,
                    verify_authority=lambda: "new-capability")
        assert error.value.details["reason"] == "INPUT_CAPABILITY_CHANGED"
        assert enqueue(uow, scope) == replace(first, queue_revision=last.queue_revision)


def test_cancel_stops_when_current_authority_is_denied(database):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        item = enqueue(uow, scope)

        def deny():
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Fixture authority was revoked.", {})

        with pytest.raises(OktoNexusError) as error:
            _cancel(uow, scope, item, verify_authority=deny)
        assert error.value.code == ErrorCode.PERMISSION_DENIED
        assert enqueue(uow, scope) == item


@pytest.mark.parametrize("state", ["DISPATCHING", "ACCEPTED_NATIVE", "DELIVERY_UNKNOWN", "BLOCKED_AUTH", "EXPIRED"])
def test_cancel_refuses_an_input_outside_the_unsent_cancellable_states(database, state):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        item = enqueue(uow, scope)
        conn = uow.connection
        linked = state in ("DISPATCHING", "ACCEPTED_NATIVE", "DELIVERY_UNKNOWN")
        if linked:
            conn.execute("""
                INSERT INTO execution_operations(
                    server_id,executor_id,session_id,operation_id,subject_agent_id,actor_agent_id,
                    binding_id,workspace_id,workspace_binding_id,action,intent_hash,semantic_payload,
                    expected_revisions_json,admission_state,created_at)
                VALUES(?,?,?,'linked-turn','recipient','recipient',?,?,?,'turn.submit','test','{}','{}','ACCEPTED','t')
            """, (scope.session.server_id, scope.session.executor_id, scope.session.session_id,
                  scope.binding_id, scope.workspace_id, scope.workspace_binding_id))
        conn.execute("UPDATE session_interaction_inputs SET status=?,operation_id=?,possible_effect=? WHERE input_id=?",
                     (state, "linked-turn" if linked else None, int(state == "DELIVERY_UNKNOWN"), item.input_id))
        with pytest.raises(OktoNexusError) as error:
            _cancel(uow, scope, item)
        assert error.value.details["reason"] == "INPUT_NOT_CANCELLABLE"
        assert enqueue(uow, scope).status == state


def test_cancel_retains_prepared_attempt_for_reconciliation(database):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        item = _enqueue(uow, scope, "first")
        head, request = _head_and_request(uow, scope)
        prepared = prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW)
        assert not fence_prepared_capacity_release(uow, scope=scope, request=request)
    with factory.unit_of_work() as uow:
        receipt = _cancel(uow, scope, item)
        assert receipt.status == InputDeliveryState.CANCELLED and receipt.operation_id is None
    with factory.unit_of_work(write=False) as uow:
        assert read_capacity_attempt(uow, session=scope.session) == prepared
        assert uow.connection.execute("SELECT count(*) FROM execution_operations").fetchone()[0] == 0
    with factory.unit_of_work() as uow:
        assert fence_prepared_capacity_release(uow, scope=scope, request=request)


@pytest.mark.parametrize("first_action", ["cancel", "stage"])
def test_cancel_and_capacity_staging_serialize_with_one_winner(database, first_action):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        item = _enqueue(uow, scope, "first")
        head, request = _head_and_request(uow, scope)
        prepare_capacity_attempt(uow, scope=scope, head=head, request=request, now=NOW)
    second = "stage" if first_action == "cancel" else "cancel"
    ready_to_commit, competitor_started = Event(), Event()
    competitor = ConnectionFactory(factory.config)

    def transact(database, action, *, hold):
        if not hold:
            assert ready_to_commit.wait(timeout=10)
        transaction = database.unit_of_work()
        if not hold:
            def before_statement(statement):
                if statement == "BEGIN IMMEDIATE":
                    competitor_started.set()
            transaction.connection.set_trace_callback(before_statement)
        try:
            with transaction as uow:
                if action == "cancel":
                    _cancel(uow, scope, item)
                else:
                    _stage(uow, scope, head, request)
                    record_staged_capacity_attempt(uow, scope=scope, request=request, operation_id="operation-a")
                if hold:
                    ready_to_commit.set()
                    assert competitor_started.wait(timeout=10)
            return "committed"
        except OktoNexusError as error:
            return error.details["reason"]

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            winner = workers.submit(transact, factory, first_action, hold=True)
            loser = workers.submit(transact, competitor, second, hold=False)
            assert winner.result(timeout=15) == "committed"
            assert loser.result(timeout=15) == (
                "INPUT_DISPATCH_CHANGED" if first_action == "cancel" else "INPUT_NOT_CANCELLABLE"
            )
        with competitor.unit_of_work(write=False) as uow:
            attempt = read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id)
            assert attempt.state == ("PREPARED" if first_action == "cancel" else "STAGED")
            count = int(first_action == "stage")
            assert uow.connection.execute("SELECT count(*) FROM execution_operations").fetchone()[0] == count
            assert uow.connection.execute("SELECT count(*) FROM execution_dispatch_outbox").fetchone()[0] == count
    finally:
        competitor.close()
