"""A pull competing with canonical push admission cannot see its payload."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork
from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, wait_sent
from test_runtime_consumption_acceptance import worker_key, pull

runtime = runtime_fixture


@pytest.mark.parametrize("cut", ["before_reservation", "after_reservation"])
def test_pull_contends_with_uncommitted_push_reservation(runtime, monkeypatch, cut):
    deps, _, _, peers, _, _ = runtime
    key = worker_key(runtime)
    assert open_rest(runtime).status_code == 200
    held, release, pull_begin = threading.Event(), threading.Event(), threading.Event()
    local = threading.local()
    enqueue = SqliteRuntimeOutboxRepo.enqueue
    inbox = build_service(deps)
    enter = SqliteUnitOfWork.__enter__
    seen = []

    def reserve(self, uow, **kwargs):
        envelope = kwargs["envelope"]
        if cut == "after_reservation":
            enqueue(self, uow, **kwargs)
        seen.append(envelope.delivery_id)
        assert uow.connection.execute("SELECT count(*) FROM message_deliveries WHERE delivery_id=?",
                                      (envelope.delivery_id,)).fetchone()[0] == 1
        held.set()
        assert release.wait(8)
        if cut == "before_reservation":
            enqueue(self, uow, **kwargs)

    def pulling():
        # Invoke the same wired canonical use case on an independent worker.
        # A blocking test barrier inside a synchronous MCP handler would block
        # its event loop and prevent the second request reaching the race.
        local.pulling = True
        try:
            return inbox.pull(agent_id="worker")["messages"]
        finally:
            local.pulling = False

    def entering(self):
        if self._write and getattr(local, "pulling", False):
            # Observe SQLite receiving the actual competing BEGIN IMMEDIATE,
            # before it waits for the message/intent transaction to commit.
            self.connection.set_trace_callback(
                lambda sql: pull_begin.set() if sql == "BEGIN IMMEDIATE" else None)
        return enter(self)

    monkeypatch.setattr(SqliteRuntimeOutboxRepo, "enqueue", reserve)
    monkeypatch.setattr(SqliteUnitOfWork, "__enter__", entering)
    with ThreadPoolExecutor(max_workers=2) as pool:
        send = pool.submit(send_message, runtime, body="one logical race payload")
        try:
            assert held.wait(5)
            receive = pool.submit(pulling)
            assert pull_begin.wait(5), "canonical pull did not reach SQLite contention"
            assert not receive.done(), "pull completed while admission held the writer lock"
            assert peers[0].sent == []
        finally:
            release.set()
        created = send.result(timeout=5)
        assert receive.result(timeout=5) == []
    wait_sent(peers)
    assert len(seen) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        delivery = uow.connection.execute(
            "SELECT consumer_kind,consumer_operation_id,attempts,lease_expires_at FROM message_deliveries WHERE delivery_id=?",
            (seen[0],)).fetchone()
        assert tuple(delivery) == ("push", created["runtime_operations"][0], 0, None)
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox WHERE delivery_id=?", (seen[0],)).fetchone()[0] == 1
    assert pull(runtime, key) == []
    assert len(peers[0].sent) == 1
