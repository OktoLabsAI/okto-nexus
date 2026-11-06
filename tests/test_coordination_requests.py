"""Real SQLite receipt primitives, not end-to-end public retry certification.

The small submit driver deliberately composes existing canonical repositories
in one UoW. Public message/handoff/approval use-case integration and their
current authorization gates remain separate work and are not implied here.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest
import okto_nexus

from fake_clock import FakeClock
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.application.ports import CoordinationRequestRepo
from okto_nexus.application.retention import RetentionService
from okto_nexus.bootstrap.dependencies import build_repos
from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.coordination_requests import (
    RETENTION_SECONDS, CoordinationRequestKey, handoff_request_hash, message_request_hash,
)
from okto_nexus.errors import ErrorCode, OktoNexusError


NOW = "2026-11-06T12:00:00.000000Z"
MESSAGE = dict(subject="Review", body="Please review the design", target={"strategy": "direct", "agent_id": "worker"})
DIGEST = message_request_hash(**MESSAGE)


@pytest.fixture
def store(migrated_factory, tmp_config, tmp_path):
    factory = migrated_factory
    ensure_execution_installation(factory)
    clock = FakeClock(iso=NOW)
    repos, emitter = build_repos(clock, tmp_config)
    with factory.unit_of_work() as uow:
        for actor in ("sender", "worker"):
            repos.agents.upsert(uow, agent_id=actor)
        repos.workspaces.upsert(uow, workspace_id="workspace", root_realpath=str(tmp_path))
        repos.workspaces.upsert(uow, workspace_id="elsewhere", root_realpath=str(tmp_path / "elsewhere"))
        key = repos.coordination_requests.key(uow, actor_agent_id="sender", workspace_id="workspace",
            operation="message_create", client_request_id="request-1")
    return factory, repos, emitter, key, tmp_config


def effects(uow, repos, emitter, key, resource_id):
    """Canonical rows in the caller's transaction, no runtime/provider work."""
    if key.operation == "message_create":
        repos.messages.create(uow, message_id=resource_id, workspace_id=key.workspace_id,
            from_agent_id=key.actor_agent_id, subject=MESSAGE["subject"], body=MESSAGE["body"],
            target=json.dumps(MESSAGE["target"]), created_at=NOW)
        repos.deliveries.create(uow, delivery_id="delivery-" + resource_id, message_id=resource_id,
            recipient_agent_id="worker", status="unread", created_at=NOW)
    else:
        repos.handoffs.create(uow, handoff_id=resource_id, workspace_id=key.workspace_id,
            from_agent_id=key.actor_agent_id, target=json.dumps(MESSAGE["target"]), visibility="eligible",
            payload="Work description", status="OPEN", created_at=NOW)
    emitter.emit(uow, workspace_id=key.workspace_id, stream="workspace", type=key.operation,
        actor_agent_id=key.actor_agent_id, payload={"resource_id": resource_id})


def submit(store, *, key=None, digest=DIGEST, resource_id="message-1", fail=None, factory=None):
    original, repos, emitter, original_key, _ = store
    factory, key = factory or original, key or original_key
    receipt_repo = repos.coordination_requests
    with factory.unit_of_work() as uow:
        old = receipt_repo.lookup(uow, key, request_hash=digest, now=NOW)
        if old:
            return old
        effects(uow, repos, emitter, key, resource_id)
        if fail == "before_receipt":
            raise RuntimeError("injected before receipt")
        receipt = receipt_repo.record(uow, key, request_hash=digest, now=NOW, resource_id=resource_id)
        if fail == "after_receipt":
            raise RuntimeError("injected after receipt")
    return receipt


def counts(store):
    with store[0].unit_of_work(write=False) as uow:
        return {table: uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in ("messages", "handoffs", "message_deliveries", "events", "approvals", "coordination_requests")}


@contextmanager
def expect_conflict(reason):
    with pytest.raises(OktoNexusError, match="cannot be replayed") as caught:
        yield caught
    assert caught.value.code == ErrorCode.CONFLICT
    assert caught.value.details["reason"] == reason


@pytest.mark.parametrize("operation", ["message_create", "handoff_create"])
@pytest.mark.parametrize("cut", ["before_receipt", "after_receipt"])
def test_receipt_and_canonical_effects_rollback_together(store, operation, cut):
    key = replace(store[3], operation=operation)
    before = counts(store)
    with pytest.raises(RuntimeError, match="injected"):
        submit(store, key=key, fail=cut)
    assert counts(store) == before
    original = submit(store, key=key)
    after = counts(store)
    assert submit(store, key=key, resource_id="would-duplicate") == original
    assert counts(store) == after
    assert after["coordination_requests"] == 1 and after["events"] == 1


def test_competing_connections_and_lost_reply_keep_one_object(store):
    barrier = threading.Barrier(8)
    def worker(number):
        factory = ConnectionFactory(store[4])  # independent writer gates
        try:
            barrier.wait(timeout=10)
            return submit(store, resource_id=f"racer-{number}", factory=factory)
        finally:
            factory.close()
    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(worker, range(8)))
    assert len(set(receipts)) == 1
    assert counts(store) == dict(messages=1, handoffs=0, message_deliveries=1, events=1,
                                approvals=0, coordination_requests=1)
    restarted = ConnectionFactory(store[4])
    try:
        assert submit(store, factory=restarted, resource_id="after-restart") == receipts[0]
    finally:
        restarted.close()
    with expect_conflict("CLIENT_REQUEST_CONTENT_CONFLICT") as exc:
        submit(store, digest=message_request_hash(**{**MESSAGE, "body": "Changed work"}))
    assert exc.value.details["reason"] == "CLIENT_REQUEST_CONTENT_CONFLICT"
    assert counts(store)["messages"] == 1


@pytest.mark.parametrize("commit", [False, True])
def test_process_termination_at_commit_boundary(store, commit):
    factory, repos, _, key, config = store
    worker = r'''
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from okto_nexus.config import NexusConfig
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.coordination_requests import SqliteCoordinationRequestRepo
from okto_nexus.adapters.outbound.sqlite.messages_repo import SqliteMessageRepo
from okto_nexus.domain.coordination_requests import message_request_hash
cf = ConnectionFactory(NexusConfig(home_dir=Path(sys.argv[2])))
repo = SqliteCoordinationRequestRepo()
with cf.unit_of_work() as uow:
    key = repo.key(uow, actor_agent_id="sender", workspace_id="workspace", operation="message_create", client_request_id="request-1")
    SqliteMessageRepo().create(uow, message_id="crash-object", workspace_id="workspace", from_agent_id="sender")
    digest = message_request_hash(subject="Review", body="Please review the design", target={"strategy":"direct","agent_id":"worker"})
    repo.record(uow, key, request_hash=digest, now="2026-11-06T12:00:00.000000Z", resource_id="crash-object")
    if sys.argv[3] == "before":
        os._exit(73)
os._exit(74)
'''
    process = subprocess.run([sys.executable, "-I", "-c", worker,
        str(Path(okto_nexus.__file__).parents[1]), str(config.home_dir), "after" if commit else "before"],
        capture_output=True, text=True, timeout=30, cwd=config.home_dir)
    assert process.returncode == (74 if commit else 73), process.stderr
    with factory.unit_of_work(write=False) as uow:
        found = repos.coordination_requests.lookup(uow, key, request_hash=DIGEST, now=NOW)
        assert (found is not None) == commit
    result = submit(store)
    assert result.resource_id == ("crash-object" if commit else "message-1")
    assert counts(store)["messages"] == counts(store)["coordination_requests"] == 1


def pending(store, key=None, approval_id="approval-1"):
    factory, repos, _, original_key, _ = store
    key = key or original_key
    with factory.unit_of_work() as uow:
        repos.approvals.add(uow, approval_id=approval_id, workspace_id=key.workspace_id,
            agent_id=key.actor_agent_id, action=key.operation, policy_id="policy",
            request_payload=json.dumps({"kwargs": MESSAGE}), trace_id=None, created_at=NOW)
        return repos.coordination_requests.record(uow, key, request_hash=DIGEST, now=NOW, approval_id=approval_id)


@pytest.mark.parametrize("operation", ["message_create", "handoff_create"])
def test_pending_approval_transition_preserves_id_and_deadline(store, operation):
    factory, repos, emitter, original_key, _ = store
    key = replace(original_key, operation=operation)
    receipt = pending(store, key)
    after = counts(store)
    assert submit(store, key=key) == receipt
    assert counts(store) == after
    with factory.unit_of_work() as uow:
        repos.approvals.mark_decided(uow, approval_id=receipt.approval_id, status="approved",
            decided_by="operator", justification=None, decided_at=NOW)
    with factory.unit_of_work(write=False) as uow:
        assert repos.coordination_requests.reference(uow, receipt, now=NOW)["state"] == "approved_awaiting_execution"
    for fail in (True, False):
        try:
            with factory.unit_of_work() as uow:
                effects(uow, repos, emitter, key, "approved-object")
                resolved = repos.coordination_requests.resolve_approval(uow, key, request_hash=DIGEST,
                    approval_id=receipt.approval_id, resource_id="approved-object", now=iso_plus(NOW, 29 * 86400))
                if fail:
                    raise RuntimeError("injected approval cut")
        except RuntimeError:
            with factory.unit_of_work(write=False) as uow:
                assert repos.coordination_requests.get(uow, key) == receipt
            assert counts(store)["messages"] == counts(store)["handoffs"] == 0
    assert resolved.approval_id == receipt.approval_id
    assert resolved.expires_at == receipt.expires_at and resolved.created_at == receipt.created_at
    assert submit(store, key=key) == resolved
    assert counts(store)["approvals"] == 1


@pytest.mark.parametrize("state", ["pending", "rejected", "archived", "missing"])
def test_nonapproved_request_never_resolves(store, state):
    factory, repos, emitter, key, _ = store
    receipt = pending(store)
    with factory.unit_of_work() as uow:
        if state == "rejected":
            repos.approvals.mark_decided(uow, approval_id=receipt.approval_id, status="rejected",
                decided_by="operator", justification=None, decided_at=NOW)
        elif state == "archived":
            repos.approvals.archive(uow, approval_id=receipt.approval_id, archived_by="operator", archived_at=NOW)
        elif state == "missing":
            uow.connection.execute("DELETE FROM approvals")
    with expect_conflict("CLIENT_REQUEST_APPROVAL_NOT_APPROVED"):
        with factory.unit_of_work() as uow:
            effects(uow, repos, emitter, key, "unauthorized-object")
            repos.coordination_requests.resolve_approval(uow, key, request_hash=DIGEST,
                approval_id=receipt.approval_id, resource_id="unauthorized-object", now=NOW)
    assert counts(store)["messages"] == 0
    with factory.unit_of_work(write=False) as uow:
        expected = dict(pending="pending_approval", rejected="rejected", archived="approval_archived", missing="approval_removed")
        assert repos.coordination_requests.reference(uow, receipt, now=NOW)["state"] == expected[state]


def retention(store, now):
    factory, repos, _, _, config = store
    return RetentionService(connection_factory=factory, clock=FakeClock(iso=now), config=config,
        events=repos.events, deliveries=repos.deliveries, sessions=repos.sessions,
        messages=repos.messages, coordination_requests=repos.coordination_requests, batch_size=2)


def test_message_pruning_preserves_tombstone_and_refuses_replacement(store):
    factory, repos, emitter, key, _ = store
    receipt = submit(store)
    after_week = iso_plus(NOW, 8 * 86400)
    report = retention(store, after_week).prune(messages_keep_days=7)
    assert report["tables"]["messages"]["deleted"] == 1
    assert report["tables"]["coordination_requests"]["deleted"] == 0
    with factory.unit_of_work(write=False) as uow:
        assert repos.coordination_requests.lookup(uow, key, request_hash=DIGEST, now=after_week) == receipt
        assert repos.coordination_requests.reference(uow, receipt, now=after_week)["state"] == "resource_removed"
    with expect_conflict("CLIENT_REQUEST_REFERENCE_CONFLICT"):
        with factory.unit_of_work() as uow:
            effects(uow, repos, emitter, key, "replacement")
            repos.coordination_requests.record(uow, key, request_hash=DIGEST, now=after_week, resource_id="replacement")
    assert counts(store)["messages"] == 0 and counts(store)["coordination_requests"] == 1


def test_exact_expiry_readonly_dry_run_and_bounded_prune(store):
    factory, repos, _, key, _ = store
    receipt = submit(store)
    for number in range(4):
        pending(store, replace(key, client_request_id=f"pending-{number}"), approval_id=f"approval-{number}")
    deadline = iso_plus(NOW, RETENTION_SECONDS)
    with factory.unit_of_work(write=False) as uow:
        assert repos.coordination_requests.lookup(uow, key, request_hash=DIGEST, now=iso_plus(deadline, -0.000001)) == receipt
        with expect_conflict("CLIENT_REQUEST_WINDOW_EXPIRED") as exc:
            repos.coordination_requests.lookup(uow, key, request_hash=DIGEST, now=deadline)
        assert exc.value.details["reason"] == "CLIENT_REQUEST_WINDOW_EXPIRED"
        assert repos.coordination_requests.reference(uow, receipt, now=deadline)["state"] == "expired"
    before = counts(store)
    dry = retention(store, deadline).prune(dry_run=True, max_batches=1)
    assert dry["tables"]["coordination_requests"] == dict(deleted=5, complete=True)
    assert counts(store) == before
    actual = retention(store, deadline).prune(max_batches=1)
    assert actual["tables"]["coordination_requests"] == dict(deleted=2, complete=False)
    assert actual["cutoffs"]["coordination_requests_expires_at"] == deadline
    assert retention(store, deadline).prune()["tables"]["coordination_requests"] == dict(deleted=3, complete=True)
    assert counts(store)["approvals"] == 4  # pruning receipts never authorizes/deletes approvals
    with factory.unit_of_work() as uow:
        with expect_conflict("CLIENT_REQUEST_APPROVAL_REFERENCE_MISSING"):
            repos.coordination_requests.resolve_approval(uow, replace(key, client_request_id="pending-3"),
                request_hash=DIGEST, approval_id="approval-3", resource_id="must-not-create", now=deadline)


def test_key_scope_transaction_guards_and_minimal_storage(store):
    factory, repos, emitter, key, _ = store
    assert isinstance(repos.coordination_requests, CoordinationRequestRepo)
    receipt = submit(store)
    with factory.unit_of_work(write=False) as uow:
        for field, value in dict(server_id="another-installation", actor_agent_id="worker",
            workspace_id="elsewhere", operation="handoff_create", client_request_id="other-request").items():
            assert repos.coordination_requests.get(uow, replace(key, **{field: value})) is None
        row = dict(uow.connection.execute("SELECT * FROM coordination_requests").fetchone())
        assert set(row) == {"server_id", "actor_agent_id", "workspace_id", "operation", "client_request_id",
                           "request_hash", "state", "resource_id", "approval_id", "created_at", "expires_at"}
        assert MESSAGE["body"] not in json.dumps(row)
        with pytest.raises(OktoNexusError) as exc:
            repos.coordination_requests.record(uow, key, request_hash=DIGEST, resource_id=receipt.resource_id, now=NOW)
        assert exc.value.code == ErrorCode.INTERNAL_ERROR
    with expect_conflict("CLIENT_REQUEST_INSTALLATION_CONFLICT"):
        with factory.unit_of_work() as uow:
            repos.coordination_requests.record(uow, replace(key, server_id="another-installation"),
                request_hash=DIGEST, resource_id=receipt.resource_id, now=NOW)
    with expect_conflict("CLIENT_REQUEST_RESOURCE_SCOPE_CONFLICT"):
        with factory.unit_of_work() as uow:
            foreign_key = replace(key, actor_agent_id="worker")
            repos.coordination_requests.record(uow, foreign_key, request_hash=DIGEST, resource_id=receipt.resource_id, now=NOW)


def test_approval_reference_cannot_be_substituted_or_expired(store):
    factory, repos, emitter, key, _ = store
    receipt = pending(store)
    other_key = replace(key, client_request_id="another-request")
    other = pending(store, other_key, approval_id="another-approval")
    with factory.unit_of_work() as uow:
        for approval_id in (receipt.approval_id, other.approval_id):
            repos.approvals.mark_decided(uow, approval_id=approval_id, status="approved",
                decided_by="operator", justification=None, decided_at=NOW)
    for approval_id, now, reason in (
        (other.approval_id, NOW, "CLIENT_REQUEST_APPROVAL_REFERENCE_MISSING"),
        (receipt.approval_id, receipt.expires_at, "CLIENT_REQUEST_WINDOW_EXPIRED"),
        (receipt.approval_id, iso_plus(NOW, -1), "CLIENT_REQUEST_WINDOW_EXPIRED"),
    ):
        with expect_conflict(reason):
            with factory.unit_of_work() as uow:
                effects(uow, repos, emitter, key, "must-rollback")
                repos.coordination_requests.resolve_approval(uow, key, request_hash=DIGEST,
                    approval_id=approval_id, resource_id="must-rollback", now=now)
    assert counts(store)["messages"] == 0
    with factory.unit_of_work(write=False) as uow:
        assert repos.coordination_requests.get(uow, key) == receipt


def test_same_client_id_is_independent_for_actor_workspace_and_operation(store):
    keys = [store[3], replace(store[3], actor_agent_id="worker"),
            replace(store[3], workspace_id="elsewhere"), replace(store[3], operation="handoff_create")]
    for number, key in enumerate(keys):
        receipt = submit(store, key=key, resource_id=f"scoped-{number}")
        assert receipt.key == key and receipt.resource_id == f"scoped-{number}"
    assert counts(store)["coordination_requests"] == 4


def test_upgrade_from_158_preserves_canonical_rows(conn_factory, tmp_config, tmp_path):
    before_dir = tmp_path / "before159"
    before_dir.mkdir()
    for path in _default_migrations_dir().glob("*.sql"):
        if int(path.name.split("_", 1)[0]) <= 158:
            shutil.copyfile(path, before_dir / path.name)
    assert MigrationRunner(conn_factory, migrations_dir=before_dir).apply()[-1] == 158
    installation = ensure_execution_installation(conn_factory)
    repos, _ = build_repos(FakeClock(iso=NOW), tmp_config)
    with conn_factory.unit_of_work() as uow:
        repos.agents.upsert(uow, agent_id="sender")
        repos.workspaces.upsert(uow, workspace_id="workspace", root_realpath=str(tmp_path))
        repos.messages.create(uow, message_id="existing-message", workspace_id="workspace", from_agent_id="sender")
        repos.approvals.add(uow, approval_id="existing-approval", workspace_id="workspace", agent_id="sender",
            action="message_create", policy_id="policy", request_payload="{}", trace_id=None, created_at=NOW)
        before = {table: [dict(row) for row in uow.connection.execute("SELECT * FROM " + table)]
                  for table in ("messages", "approvals", "execution_installation")}
    assert MigrationRunner(conn_factory).apply() == [159]
    assert MigrationRunner(conn_factory).apply() == []
    with conn_factory.unit_of_work(write=False) as uow:
        for table, rows in before.items():
            assert [dict(row) for row in uow.connection.execute("SELECT * FROM " + table)] == rows
        assert uow.connection.execute("SELECT COUNT(*) FROM coordination_requests").fetchone()[0] == 0
        key = repos.coordination_requests.key(uow, actor_agent_id="sender", workspace_id="workspace",
            operation="message_create", client_request_id="new-request")
        assert key.server_id == installation.server_id


def test_semantic_hash_preserves_content_target_and_context():
    assert message_request_hash(**{**MESSAGE, "target": {"agent_id": "worker", "strategy": "direct"}}) == DIGEST
    for field, value in dict(body="changed", subject="changed", target={"strategy": "broadcast"},
        channel_id="channel", artifacts=["artifact"], parent_message_id="parent", trace_id="trace",
        session_id="session", source_session_key='["mcp","session"]', no_reply=True).items():
        assert message_request_hash(**{**MESSAGE, field: value}) != DIGEST
    handoff = dict(target=MESSAGE["target"], visibility="eligible", payload={"work": "review"})
    original = handoff_request_hash(**handoff)
    for field, value in dict(target={"strategy": "broadcast"}, visibility="public", payload={"work": "deploy"},
        trace_id="trace", acceptance_criteria=["reviewed"], verify_by={"kind": "creator"},
        depends_on=["dependency"], session_id="session", source_session_key='["mcp","session"]').items():
        assert handoff_request_hash(**{**handoff, field: value}) != original
    for name in ("session_secret", "api_key", "credential_binding"):
        with pytest.raises(TypeError):
            message_request_hash(**MESSAGE, **{name: "must-never-be-hashed"})
    for payload in (float("nan"), float("inf"), {1: "nonstring-key"}, object()):
        with pytest.raises(OktoNexusError):
            handoff_request_hash(**{**handoff, "payload": payload})


@pytest.mark.parametrize("request_id", [None, 1, True, "", " x", "x\n", "é", "x" * 129])
def test_invalid_request_id_is_rejected(request_id):
    with pytest.raises(OktoNexusError):
        CoordinationRequestKey("server", "actor", "workspace", "message_create", request_id)
