"""Test receipt recovery against the canonical session reader and real SQLite."""

from contextlib import contextmanager
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest
from nexus_connector_core.protocol import canonical_json

from okto_nexus.adapters.inbound.http.operator_auth import OperatorAuth
from okto_nexus.application.runtime_access import RuntimeAccessService
from okto_nexus.application.session_interaction_receipts import (
    read_session_input_receipt,
)
from okto_nexus.domain.execution.keys import SessionOwnerGeneration
from okto_nexus.domain.session_interaction import InputAuthor, InputDeliveryState
from okto_nexus.errors import ErrorCode, OktoNexusError
from tests.session_interaction.test_queue_storage import database as queue_database
from tests.session_interaction.test_queue_storage import enqueue

database = queue_database


def _store_operation(uow, scope, operation_id, action):
    fields = {
        **asdict(scope.session), "binding_id": scope.binding_id, "workspace_id": scope.workspace_id,
        "workspace_binding_id": scope.workspace_binding_id, "agent_id": scope.agent_id,
        "session_owner_generation": scope.generation.value, "authorization_revision": 1,
        "configuration_revision": 1, "binding_revision": 1, "credential_epoch": 1,
    }
    uow.connection.execute("""
        INSERT INTO execution_operations (
            server_id,executor_id,session_id,operation_id,subject_agent_id,actor_agent_id,binding_id,workspace_id,
            workspace_binding_id,action,intent_hash,semantic_payload,expected_revisions_json,admission_state,created_at
        ) VALUES (
            :server_id,:executor_id,:session_id,:operation_id,:agent_id,:agent_id,:binding_id,:workspace_id,
            :workspace_binding_id,:action,'fixture-hash','{}',:scope,'ACCEPTED','t'
        )
    """, {**fields, "operation_id": operation_id, "action": action, "scope": canonical_json(fields).decode()})


@pytest.fixture
def receipt_lookup(database, tmp_path):
    factory, (scope, sibling) = database
    auth = OperatorAuth(tmp_path / "auth")
    assert auth.configure("test-operator", "test-password", local=True)

    def login():
        token = auth.login("test-operator", "test-password")
        reference = auth.authority_reference(token)
        assert token and reference
        return token, InputAuthor(reference, "web")

    token, author = login()
    with factory.unit_of_work() as uow:
        for selection in (scope, sibling):
            _store_operation(uow, selection, "open-r4-id", "runtime.open")
        original = enqueue(uow, scope, author=author, text="Private fixture content")
        other = enqueue(uow, sibling, author=author)

    @contextmanager
    def read_only(*, write):
        assert write is False
        with factory.unit_of_work(write=False) as uow:
            uow.connection.execute("PRAGMA query_only = ON")
            try:
                yield uow
            finally:
                uow.connection.execute("PRAGMA query_only = OFF")

    access = RuntimeAccessService(
        connection_factory=factory, agents=SimpleNamespace(get=lambda *_: None), endpoints=None, grants=None,
        config=SimpleNamespace(feature_harness_integrations=False), clock=None,
    )
    read_factory = SimpleNamespace(unit_of_work=read_only)

    def read(**overrides):
        return read_session_input_receipt(read_factory, **{
            "access": access, "resolve_human": auth.resolve_authority, "scope": scope, "author": author,
            "client_intent_id": "request", **overrides,
        })

    return SimpleNamespace(factory=factory, scope=scope, sibling=sibling, auth=auth, token=token, author=author,
                           login=login, access=access, read=read, original=original, other=other)


def _check_absent(read, **options):
    with pytest.raises(OktoNexusError) as error:
        read(**options)
    assert error.value.code == ErrorCode.NOT_FOUND
    assert error.value.message == "The input receipt was not found in this scope."
    assert error.value.details is None


def test_reads_owned_receipt_in_exact_namespace_without_mutating_store(receipt_lookup):
    fixture = receipt_lookup
    assert fixture.read() == fixture.original
    assert fixture.read(scope=fixture.sibling) == fixture.other
    assert fixture.read() == fixture.original
    assert fixture.original.input_id != fixture.other.input_id
    assert "Private fixture content" not in repr(fixture.read())
    assert fixture.author.authority_ref not in repr(fixture.read())
    with fixture.factory.unit_of_work(write=False) as uow:
        for table in ("runtime_execution_grants", "runtime_access_audit", "execution_dispatch_outbox", "execution_leases"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_recovers_old_generation_and_current_status_without_replaying_input(receipt_lookup):
    fixture = receipt_lookup
    scope = fixture.scope
    with fixture.factory.unit_of_work() as uow:
        _store_operation(uow, scope, "retained-turn", "turn.submit")
        uow.connection.execute("""
            UPDATE session_interaction_inputs SET status='DELIVERY_UNKNOWN',operation_id='retained-turn',
                possible_effect=1,input_revision=4 WHERE input_id=?
        """, (fixture.original.input_id,))
        uow.connection.execute("UPDATE session_interaction_queues SET revision=5 WHERE executor_id=?",
                               (scope.session.executor_id,))
        uow.connection.execute("UPDATE execution_sessions SET owner_generation=2,lifecycle_state='CLOSED' WHERE executor_id=?",
                               (scope.session.executor_id,))

    receipt = fixture.read()
    assert receipt == replace(fixture.original, input_revision=4, queue_revision=5,
                              status=InputDeliveryState.DELIVERY_UNKNOWN, operation_id="retained-turn", possible_effect=True)
    _check_absent(fixture.read, scope=replace(scope, generation=SessionOwnerGeneration(2)))


def test_mismatches_share_one_not_found_result(receipt_lookup):
    fixture = receipt_lookup
    scope = fixture.scope
    _, other_author = fixture.login()
    _check_absent(fixture.read, client_intent_id="unretained")
    _check_absent(fixture.read, author=other_author)
    _check_absent(fixture.read, author=replace(fixture.author, surface="nexus_cli"))
    for key in ("server_id", "executor_id", "session_id"):
        _check_absent(fixture.read, scope=replace(scope, session=replace(scope.session, **{key: "missing"})))
    for key in ("binding_id", "workspace_id", "workspace_binding_id", "agent_id"):
        _check_absent(fixture.read, scope=replace(scope, **{key: "missing"}))

    fixture.auth.logout(fixture.token)
    _check_absent(fixture.read)


def test_requires_current_session_visibility(receipt_lookup, monkeypatch):
    fixture = receipt_lookup

    def deny(_context, *, uow, require_feature):
        assert require_feature is False
        assert uow.connection.execute("PRAGMA query_only").fetchone()[0] == 1
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Synthetic authorization denial.", {})

    with monkeypatch.context() as patch:
        patch.setattr(fixture.access, "authenticate", deny)
        _check_absent(fixture.read)

    with fixture.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET workspace_id=? WHERE workspace_id=?",
                               (fixture.sibling.workspace_id, fixture.scope.workspace_id))
    _check_absent(fixture.read)
