"""Exercise the scoped queue view against the real SQLite snapshot."""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.session_interaction_queue_controls import (
    set_input_queue_paused,
)
from okto_nexus.application.session_interaction_queue_view import (
    MAX_QUEUE_PAGE,
    InputQueueCursor,
    InputQueuePage,
    read_session_input_queue,
)
from okto_nexus.domain.execution.keys import SessionOwnerGeneration
from okto_nexus.domain.session_interaction import MAX_SQLITE_INTEGER, InputDeliveryState
from okto_nexus.errors import ErrorCode, OktoNexusError
from tests.session_interaction.test_queue_storage import database as queue_database
from tests.session_interaction.test_queue_storage import enqueue
from tests.session_interaction.test_receipt_lookup import (
    _store_operation,
)
from tests.session_interaction.test_receipt_lookup import (
    receipt_lookup as receipt_lookup_fixture,
)

database = queue_database
receipt_lookup = receipt_lookup_fixture


@pytest.fixture
def queue_view(receipt_lookup):
    fixture = receipt_lookup

    @contextmanager
    def readonly(*, write):
        assert write is False
        with fixture.factory.unit_of_work(write=False) as uow:
            uow.connection.execute("PRAGMA query_only=ON")
            try:
                yield uow
            finally:
                uow.connection.execute("PRAGMA query_only=OFF")

    factory = SimpleNamespace(unit_of_work=readonly)

    def read(**options):
        return read_session_input_queue(factory, **{
            "access": fixture.access, "resolve_human": fixture.auth.resolve_authority,
            "scope": fixture.scope, "author": fixture.author, **options,
        })

    fixture.read_queue = read
    return fixture


def test_fifo_pages_return_only_metadata_and_owned_cancellation_eligibility(queue_view):
    fixture = queue_view
    _, other_author = fixture.login()
    with fixture.factory.unit_of_work() as uow:
        foreign = enqueue(uow, fixture.scope, author=other_author, text="Private foreign content")
        paused = enqueue(uow, fixture.scope, author=fixture.author, intent="paused")
        unknown = enqueue(uow, fixture.scope, author=fixture.author, intent="unknown")
        _store_operation(uow, fixture.scope, "retained-turn", "turn.submit")
        uow.connection.execute("UPDATE session_interaction_inputs SET status='PAUSED',input_revision=1 WHERE input_id=?",
                               (paused.input_id,))
        uow.connection.execute("""
            UPDATE session_interaction_inputs SET status='DELIVERY_UNKNOWN',operation_id='retained-turn',
                possible_effect=1,input_revision=4 WHERE input_id=?
        """, (unknown.input_id,))

    first = fixture.read_queue(limit=2)
    assert first.queue_revision == 4 and not first.paused
    assert first.next_cursor == InputQueueCursor(fixture.scope, foreign.sequence)
    assert [item.input_id for item in first.items] == [fixture.original.input_id, foreign.input_id]
    assert [item.can_cancel for item in first.items] == [True, False]

    second = fixture.read_queue(limit=2, cursor=first.next_cursor)
    assert second.next_cursor is None and second.queue_revision == first.queue_revision
    assert [item.sequence for item in first.items + second.items] == [1, 2, 3, 4]
    assert [item.can_cancel for item in second.items] == [True, False]
    assert second.items[0].status is InputDeliveryState.PAUSED and second.items[0].input_revision == 1
    assert second.items[1].status is InputDeliveryState.DELIVERY_UNKNOWN
    assert second.items[1].possible_effect and second.items[1].operation_id == "retained-turn"
    assert not any(value in repr(first) + repr(second) for value in (
        fixture.author.authority_ref, other_author.authority_ref, "Private fixture content", "Private foreign content",
    ))

    assert [item.can_cancel for item in fixture.read_queue(author=other_author).items] == [False, True, False, False]
    swapped_surface = replace(fixture.author, surface="nexus_cli")
    assert not any(item.can_cancel for item in fixture.read_queue(author=swapped_surface).items)
    sibling = fixture.read_queue(scope=fixture.sibling)
    assert [item.input_id for item in sibling.items] == [fixture.other.input_id]
    assert fixture.read_queue(limit=2) == first
    with fixture.factory.unit_of_work(write=False) as uow:
        for table in ("runtime_execution_grants", "runtime_access_audit", "execution_dispatch_outbox", "execution_leases"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_empty_queue_and_pause_barrier_survive_owner_generation_change(queue_view):
    fixture = queue_view
    scope = fixture.scope
    with fixture.factory.unit_of_work() as uow:
        uow.connection.execute("DELETE FROM session_interaction_inputs WHERE executor_id=?", (scope.session.executor_id,))
        uow.connection.execute("DELETE FROM session_interaction_queues WHERE executor_id=?", (scope.session.executor_id,))
    assert fixture.read_queue() == InputQueuePage(0, False, (), None)
    with fixture.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM session_interaction_queues").fetchone()[0] == 1
    with fixture.factory.unit_of_work() as uow:
        set_input_queue_paused(uow, scope=scope, paused=True, expected_queue_revision=0,
                               capability_revision="test-pause", verify_authority=lambda: "test-pause")
        old_item = enqueue(uow, scope, author=fixture.author, intent="old")
    assert fixture.read_queue().paused
    assert fixture.read_queue().items[0].input_id == old_item.input_id

    current = replace(scope, generation=SessionOwnerGeneration(2))
    with fixture.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET owner_generation=2 WHERE executor_id=?",
                               (scope.session.executor_id,))
        new_item = enqueue(uow, current, author=fixture.author, intent="current")
    with pytest.raises(OktoNexusError) as error:
        fixture.read_queue()
    assert error.value.code == ErrorCode.NOT_FOUND
    page = fixture.read_queue(scope=current)
    assert page.queue_revision == 3 and page.paused
    assert [item.input_id for item in page.items] == [new_item.input_id]


def test_cursor_is_scope_bound_and_bounded_across_queue_changes(queue_view):
    fixture = queue_view
    with fixture.factory.unit_of_work() as uow:
        second = enqueue(uow, fixture.scope, author=fixture.author, intent="second")
    cursor = fixture.read_queue(limit=1).next_cursor
    with fixture.factory.unit_of_work() as uow:
        third = enqueue(uow, fixture.scope, author=fixture.author, intent="third")
    page = fixture.read_queue(limit=2, cursor=cursor)
    assert page.queue_revision == 3
    assert [item.input_id for item in page.items] == [second.input_id, third.input_id]

    with pytest.raises(OktoNexusError) as error:
        fixture.read_queue(scope=fixture.sibling, cursor=cursor)
    assert error.value.code == ErrorCode.VALIDATION_ERROR
    for position in (0, -1, True, MAX_SQLITE_INTEGER + 1):
        with pytest.raises(OktoNexusError) as error:
            fixture.read_queue(cursor=InputQueueCursor(fixture.scope, position))
        assert error.value.code == ErrorCode.VALIDATION_ERROR
    for limit in (0, True, MAX_QUEUE_PAGE + 1):
        with pytest.raises(OktoNexusError) as error:
            fixture.read_queue(limit=limit)
        assert error.value.code == ErrorCode.VALIDATION_ERROR


def test_requires_current_login_and_canonical_session_visibility(queue_view, monkeypatch):
    fixture = queue_view

    def deny(_context, *, uow, require_feature):
        assert require_feature is False
        assert uow.connection.execute("PRAGMA query_only").fetchone()[0] == 1
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Synthetic authorization denial.")

    with monkeypatch.context() as patch:
        patch.setattr(fixture.access, "authenticate", deny)
        with pytest.raises(OktoNexusError) as error:
            fixture.read_queue()
        assert error.value.code == ErrorCode.NOT_FOUND

    for field in ("binding_id", "workspace_id", "workspace_binding_id", "agent_id"):
        with pytest.raises(OktoNexusError) as error:
            fixture.read_queue(scope=replace(fixture.scope, **{field: "missing"}))
        assert error.value.code == ErrorCode.NOT_FOUND

    with fixture.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET workspace_id=? WHERE workspace_id=?",
                               (fixture.sibling.workspace_id, fixture.scope.workspace_id))
    with pytest.raises(OktoNexusError) as error:
        fixture.read_queue()
    assert error.value.code == ErrorCode.NOT_FOUND
    assert fixture.read_queue(scope=fixture.sibling).items
    fixture.auth.logout(fixture.token)
    with pytest.raises(OktoNexusError) as error:
        fixture.read_queue(scope=fixture.sibling)
    assert error.value.code == ErrorCode.NOT_FOUND
