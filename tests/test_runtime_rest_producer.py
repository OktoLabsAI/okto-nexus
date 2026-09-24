"""REST steering uses canonical transactional inbox/outbox admission."""
import pytest

from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.errors import ErrorCode, OktoNexusError
from test_pr34_remediation import runtime as runtime_fixture, open_rest, wait_sent
from test_runtime_delivery_acceptance import counts

runtime = runtime_fixture


@pytest.mark.parametrize("rollback", [False, True])
def test_rest_steering_has_atomic_canonical_message_delivery_and_intent(runtime, monkeypatch, rollback):
    deps, client, _, peers, operator, _ = runtime
    opened = open_rest(runtime)
    assert opened.status_code == 200, opened.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute("SELECT workspace_id FROM harness_sessions").fetchone()[0]
        before = counts(uow)
    enqueue = SqliteRuntimeOutboxRepo.enqueue
    writes = []

    def observed(self, uow, **kwargs):
        enqueue(self, uow, **kwargs)
        writes.append(counts(uow))
        if rollback:
            raise OktoNexusError(ErrorCode.DB_ERROR, "Disposable fault after real intent write", {})

    with monkeypatch.context() as patch:
        patch.setattr(SqliteRuntimeOutboxRepo, "enqueue", observed)
        reply = client.post("/api/v1/steering/messages", headers={"x-api-key": operator}, json={
            "workspace": workspace, "to_agent_id": "worker", "body": "REST canonical producer", "subject": "fixture"})
    assert len(writes) == 1, reply.text
    for table in ("messages", "message_deliveries", "delivery_outbox"):
        assert writes[0][table] == before[table] + 1
    if rollback:
        assert reply.status_code >= 400, reply.text
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert counts(uow) == before
        assert peers[0].sent == []
        # Same public producer remains usable after the rolled-back write.
        reply = client.post("/api/v1/steering/messages", headers={"x-api-key": operator}, json={
            "workspace": workspace, "to_agent_id": "worker", "body": "REST canonical producer", "subject": "fixture"})
    assert reply.status_code == 200, reply.text
    admitted = reply.json()["data"]
    wait_sent(peers)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT o.operation_id,o.message_id,o.actor_agent_id,d.consumer_kind,m.from_agent_id "
            "FROM delivery_outbox o JOIN message_deliveries d USING(delivery_id) JOIN messages m ON m.message_id=o.message_id").fetchall()
        assert len(rows) == 1
        assert tuple(rows[0]) == (admitted["runtime_operations"][0], admitted["message_id"], "operator", "push", "operator")
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()
    assert len(peers[0].sent) == 1
