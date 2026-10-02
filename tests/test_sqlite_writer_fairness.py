"""Waiting writers progress without extending the SQLite admission budget."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading
import time

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.config import NexusConfig
from okto_nexus.errors import OktoNexusError


def factory_at(tmp_path, budget=1000):
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path, busy_timeout_ms=budget))
    with factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TABLE writes(value TEXT)")
    return factory


def queued(factory, count):
    deadline = time.monotonic() + 3
    while True:
        with factory._writer_gate._condition:
            if len(factory._writer_gate._waiting) == count:
                return
        assert time.monotonic() < deadline, "The expected writer never queued"
        time.sleep(.001)


def test_waiting_writers_precede_immediate_reacquisition(tmp_path):
    factory = factory_at(tmp_path)
    def write(value):
        with factory.unit_of_work() as uow:
            uow.connection.execute("INSERT INTO writes VALUES(?)", (value,))
    with ThreadPoolExecutor(max_workers=3) as pool:
        with factory.unit_of_work():
            futures = []
            for index in range(3):
                futures.append(pool.submit(write, str(index)))
                queued(factory, index + 1)
            # Snapshot readers remain independent of both holder and queue.
            with factory.unit_of_work(write=False) as reader:
                assert reader.connection.execute("SELECT COUNT(*) FROM writes").fetchone()[0] == 0
        write("greedy")
        for future in futures:
            future.result(timeout=3)
    with factory.unit_of_work(write=False) as uow:
        assert [row[0] for row in uow.connection.execute("SELECT value FROM writes ORDER BY rowid")] == [
            "0", "1", "2", "greedy"]


def test_expired_waiter_is_removed_without_writing_or_blocking_successor(tmp_path):
    factory = factory_at(tmp_path, budget=20)
    with factory.unit_of_work():
        with pytest.raises(OktoNexusError) as error:
            with factory.unit_of_work() as uow:
                uow.connection.execute("INSERT INTO writes VALUES('expired')")
        assert error.value.code == "DB_ERROR" and error.value.retryable
        queued(factory, 0)
    with factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM writes").fetchone()[0] == 0


@pytest.mark.parametrize("failure", ["hook", "body", "begin", "commit"])
def test_failed_transaction_releases_local_writer_admission(tmp_path, failure):
    factory = factory_at(tmp_path, budget=20)
    work = factory.unit_of_work()
    external = None
    def fail(*args):
        raise ValueError("injected failure")
    if failure == "hook":
        work._before_write = fail
    if failure == "begin":
        external = factory.get_connection()
        external.execute("BEGIN IMMEDIATE")
    if failure == "commit":
        work.commit = fail
    try:
        with pytest.raises((ValueError, OktoNexusError)):
            with work as uow:
                uow.connection.execute("INSERT INTO writes VALUES('rolled back')")
                if failure == "body":
                    fail()
    finally:
        if external:
            external.close()
    with pytest.raises(sqlite3.ProgrammingError):
        work.connection.execute("SELECT 1")
    with factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM writes").fetchone()[0] == 0


def test_queue_wait_reduces_sqlite_lock_wait_budget(tmp_path):
    factory = factory_at(tmp_path, budget=1000)
    remaining = []
    acquire = factory._writer_gate.acquire
    def measured(timeout):
        result = acquire(timeout)
        remaining.append(result)
        return result
    factory._writer_gate.acquire = measured
    def writer():
        work = factory.unit_of_work()
        statements = []
        work.connection.set_trace_callback(statements.append)
        with work:
            pass
        return statements
    with ThreadPoolExecutor(max_workers=1) as pool:
        with factory.unit_of_work():
            future = pool.submit(writer)
            queued(factory, 1)
            threading.Event().wait(.05)
        statements = future.result(timeout=3)
    budget = int(statements[0].split("=")[1])
    assert budget == int(remaining[-1] * 1000) and budget < 1000
    assert statements[1:3] == ["BEGIN IMMEDIATE", "PRAGMA busy_timeout=1000"]
