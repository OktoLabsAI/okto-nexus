"""A thread reuses one SQLite connection for its units of work."""
import sqlite3
import threading

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.config import NexusConfig


@pytest.fixture
def factory(tmp_path):
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path, busy_timeout_ms=1234))
    with factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TABLE items(value TEXT)")
    yield factory
    factory.close()


def connection_of(factory, write=True):
    with factory.unit_of_work(write=write) as uow:
        return uow.connection


def test_one_thread_reuses_its_connection(factory):
    first = connection_of(factory)
    assert connection_of(factory) is first
    assert connection_of(factory, write=False) is first


def test_reused_connection_keeps_pragmas_and_functions(factory):
    connection_of(factory)
    with factory.unit_of_work() as uow:
        conn = uow.connection
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 1234
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.row_factory is sqlite3.Row
        assert conn.execute("SELECT nexus_runtime_writer_v1()").fetchone()[0] == 1
        assert conn.execute("SELECT nexus_runtime_owner_id()").fetchone()[0] is None


def test_query_only_set_by_a_unit_of_work_does_not_reach_the_next_one(factory):
    with factory.unit_of_work(write=False) as uow:
        uow.connection.execute("PRAGMA query_only=ON")
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO items VALUES('written')")
        assert uow.connection.execute("PRAGMA query_only").fetchone()[0] == 0


def test_every_unit_of_work_keeps_its_transaction_boundary(factory):
    with pytest.raises(ValueError):
        with factory.unit_of_work() as uow:
            uow.connection.execute("INSERT INTO items VALUES('rolled back')")
            raise ValueError("fail")
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO items VALUES('kept')")
    with factory.unit_of_work(write=False) as uow:
        assert [row[0] for row in uow.connection.execute("SELECT value FROM items")] == ["kept"]
        assert uow.connection.in_transaction
    assert not connection_of(factory).in_transaction


def test_failed_unit_of_work_closes_its_connection(factory):
    used = connection_of(factory)
    with pytest.raises(ValueError):
        with factory.unit_of_work() as uow:
            failed = uow.connection
            raise ValueError("fail")
    assert failed is used
    with pytest.raises(sqlite3.ProgrammingError):
        failed.execute("SELECT 1")
    assert connection_of(factory) is not used


def test_nested_unit_of_work_gets_a_separate_connection(factory):
    with factory.unit_of_work(write=False) as outer:
        with factory.unit_of_work(write=False) as inner:
            assert inner.connection is not outer.connection
            inner.connection.execute("SELECT 1").fetchone()
        outer.connection.execute("SELECT 1").fetchone()
    assert connection_of(factory) is outer.connection


def test_each_thread_has_its_own_connection(factory):
    main = connection_of(factory)
    seen = []
    def work():
        seen.append(connection_of(factory))
        seen.append(connection_of(factory))
    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert seen[0] is seen[1] and seen[0] is not main


def test_get_connection_returns_a_new_connection_to_close(factory):
    first, second = factory.get_connection(), factory.get_connection()
    try:
        assert first is not second and first is not connection_of(factory)
    finally:
        first.close()
        second.close()


def test_close_releases_idle_connections_and_the_factory_stays_usable(factory):
    used = connection_of(factory)
    seen = []
    thread = threading.Thread(target=lambda: seen.append(connection_of(factory)))
    thread.start()
    thread.join()
    factory.close()
    for closed in (used, seen[0]):
        with pytest.raises(sqlite3.ProgrammingError):
            closed.execute("SELECT 1")
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection is not used
        assert uow.connection.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0


def test_close_during_a_unit_of_work_closes_its_connection_when_it_ends(factory):
    with factory.unit_of_work() as uow:
        factory.close()
        uow.connection.execute("INSERT INTO items VALUES('inside')")
    with pytest.raises(sqlite3.ProgrammingError):
        uow.connection.execute("SELECT 1")
    with factory.unit_of_work(write=False) as reader:
        assert reader.connection.execute("SELECT value FROM items").fetchone()[0] == "inside"


def test_replaced_database_file_is_not_served_by_the_old_connection(tmp_path):
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path))
    with factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TABLE items(value TEXT)")
        uow.connection.execute("INSERT INTO items VALUES('old')")
    used = connection_of(factory)
    path = factory.config.db_path
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    with factory.unit_of_work() as uow:
        assert uow.connection is not used
        assert uow.connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='items'").fetchone()[0] == 0
    factory.close()


def test_changed_busy_timeout_opens_a_new_connection(factory):
    used = connection_of(factory)
    factory.config.busy_timeout_ms = 777
    with factory.unit_of_work() as uow:
        assert uow.connection is not used
        assert uow.connection.execute("PRAGMA busy_timeout").fetchone()[0] == 777
