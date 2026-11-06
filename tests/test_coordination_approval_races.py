"""Concurrent approval recovery must preserve a newer operator decision."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import sqlite3
from threading import Event, RLock
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.approvals_repo import SqliteApprovalRepo
from okto_nexus.application.approvals import ApprovalService
from okto_nexus.errors import ErrorCode, OktoNexusError


NOW = "2026-11-06T12:00:00.000Z"
WAIT_SECONDS = 10


class MemoryFactory:
    """Real SQLite transactions, serialized like the production writer gate."""

    def __init__(self):
        self.connection = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        self.connection.executescript("""
            CREATE TABLE approvals (
                approval_id TEXT PRIMARY KEY, workspace_id TEXT, agent_id TEXT,
                action TEXT, policy_id TEXT, request_payload TEXT, status TEXT,
                decided_by TEXT, justification TEXT, executed_result TEXT,
                trace_id TEXT, created_at TEXT, decided_at TEXT,
                archived_at TEXT, archived_by TEXT,
                decision_revision INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE effects (resource_id TEXT PRIMARY KEY);
            CREATE TABLE events (event_type TEXT);
        """)

    @contextmanager
    def unit_of_work(self, write=True):
        with self.lock:
            self.connection.execute("BEGIN")
            try:
                yield SimpleNamespace(connection=self.connection)
                self.connection.execute("COMMIT")
            except BaseException:
                self.connection.execute("ROLLBACK")
                raise


class DecisionEmitter:
    def emit(self, uow, **kwargs):
        uow.connection.execute("INSERT INTO events VALUES (?)", (kwargs["type"],))


@pytest.fixture
def approval_race():
    factory = MemoryFactory()
    repo = SqliteApprovalRepo()
    service = ApprovalService(
        connection_factory=factory, approvals=repo,
        clock=SimpleNamespace(now_iso=lambda: NOW), event_emitter=DecisionEmitter(),
    )
    metadata = {"revision": 1, "approval_id": "apr_race"}
    with factory.unit_of_work() as uow:
        repo.add(
            uow, approval_id="apr_race", workspace_id="workspace", agent_id="caller",
            action="handoff_create", policy_id="policy",
            request_payload=json.dumps({"kwargs": {"_coordination": metadata}}),
            trace_id=None, created_at=NOW,
        )
    yield SimpleNamespace(factory=factory, repo=repo, service=service)
    factory.connection.close()


def _decide(harness, decision="approve", justification=None):
    return harness.service.decide(
        approval_id="apr_race", decision=decision,
        decided_by="operator", justification=justification,
    )


def _row(harness):
    with harness.factory.unit_of_work(write=False) as uow:
        return harness.repo.get(uow, "apr_race")


def _stored(harness):
    with harness.factory.unit_of_work(write=False) as uow:
        return (
            [row[0] for row in uow.connection.execute("SELECT resource_id FROM effects")],
            [row[0] for row in uow.connection.execute("SELECT event_type FROM events")],
        )


class ControlledExecutor:
    def __init__(self, harness, *, stale_failure=False):
        self.harness = harness
        self.entered = [Event() for _ in range(3)]
        self.release = [Event() for _ in range(3)]
        self.calls = []
        self.stale_failure = stale_failure

    def __call__(self, kwargs):
        with self.harness.factory.lock:
            index = len(self.calls)
            self.calls.append(kwargs)
        self.entered[index].set()
        assert self.release[index].wait(WAIT_SECONDS), "Executor was not released"
        if index == 0 or (index == 1 and self.stale_failure):
            raise RuntimeError("Simulated failure before the canonical transaction")
        metadata = kwargs["_coordination"]
        revision = kwargs["_coordination_decision_revision"]
        with self.harness.factory.unit_of_work() as uow:
            self.harness.service.require_coordination_execution(
                uow, metadata=metadata, decision_revision=revision,
            )
            # Stand in for the canonical object in the SAME transaction as its result.
            uow.connection.execute("INSERT INTO effects VALUES ('hof_once')")
            result = {"status": "created", "handoff_id": "hof_once"}
            self.harness.service.complete_coordination(
                uow, metadata=metadata, result=result, decision_revision=revision,
            )
            return result

    def release_all(self):
        for event in self.release:
            event.set()


def test_failed_concurrent_resume_cannot_erase_later_rejection(approval_race):
    harness = approval_race
    executor = ControlledExecutor(harness)
    harness.service.register_executor("handoff_create", executor)
    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            first = pool.submit(_decide, harness)
            assert executor.entered[0].wait(WAIT_SECONDS)
            second = pool.submit(_decide, harness)
            assert executor.entered[1].wait(WAIT_SECONDS)
            executor.release[0].set()
            with pytest.raises(RuntimeError, match="Simulated failure"):
                first.result(timeout=WAIT_SECONDS)
            assert _row(harness).status == "pending"

            _decide(harness, "reject", "Do not execute")
            rejected = _row(harness)
            assert rejected.status == "rejected"
            executor.release[1].set()
            with pytest.raises(OktoNexusError) as error:
                second.result(timeout=WAIT_SECONDS)
            assert error.value.code == ErrorCode.CONFLICT

            assert _row(harness) == rejected
            assert _stored(harness) == ([], ["approval.denied"])
        finally:
            executor.release_all()


def test_failed_attempt_preserves_archived_decision(approval_race):
    """Repository defense; public archive already rejects in-flight approvals."""
    harness = approval_race
    executor = ControlledExecutor(harness)
    harness.service.register_executor("handoff_create", executor)
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            attempt = pool.submit(_decide, harness)
            assert executor.entered[0].wait(WAIT_SECONDS)
            # The public archive service rejects in-flight executions. Exercise
            # the repository invariant when another writer archives the row.
            with harness.factory.unit_of_work() as uow:
                harness.repo.archive(uow, approval_id="apr_race",
                    archived_by="operator", archived_at=NOW)
            archived = _row(harness)
            assert archived.status == "approved"
            assert archived.archived_at == NOW
            assert archived.archived_by == "operator"

            executor.release[0].set()
            with pytest.raises(RuntimeError, match="Simulated failure"):
                attempt.result(timeout=WAIT_SECONDS)

            assert _row(harness) == archived
            assert _stored(harness) == ([], [])
        finally:
            executor.release_all()


@pytest.mark.parametrize("stale_failure", [False, True], ids=["stale-execution", "stale-compensation"])
def test_old_attempt_cannot_execute_or_revert_new_identical_decision(approval_race, stale_failure):
    """Same actor, justification AND timestamp must still be a new decision."""
    harness = approval_race
    executor = ControlledExecutor(harness, stale_failure=stale_failure)
    harness.service.register_executor("handoff_create", executor)
    with ThreadPoolExecutor(max_workers=3) as pool:
        try:
            first = pool.submit(_decide, harness)
            assert executor.entered[0].wait(WAIT_SECONDS)
            second = pool.submit(_decide, harness)
            assert executor.entered[1].wait(WAIT_SECONDS)
            old_decision = _row(harness)
            executor.release[0].set()
            with pytest.raises(RuntimeError, match="Simulated failure"):
                first.result(timeout=WAIT_SECONDS)

            third = pool.submit(_decide, harness)
            assert executor.entered[2].wait(WAIT_SECONDS)
            new_decision = _row(harness)
            assert (new_decision.decided_by, new_decision.justification, new_decision.decided_at) == (
                old_decision.decided_by, old_decision.justification, old_decision.decided_at,
            )
            assert new_decision.status == "approved"

            executor.release[1].set()
            expected_error = RuntimeError if stale_failure else OktoNexusError
            with pytest.raises(expected_error) as error:
                second.result(timeout=WAIT_SECONDS)
            if not stale_failure:
                assert error.value.code == ErrorCode.CONFLICT
            assert _row(harness) == new_decision
            assert _stored(harness) == ([], [])

            executor.release[2].set()
            result = third.result(timeout=WAIT_SECONDS)
            assert result["executed_result"] == {"status": "created", "handoff_id": "hof_once"}
            assert _stored(harness) == (["hof_once"], ["approval.granted"])
            assert _row(harness).status == "approved"
        finally:
            executor.release_all()
