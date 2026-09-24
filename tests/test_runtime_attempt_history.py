"""A pre-send owner change must not erase the first transport attempt."""
import threading
import sqlite3

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import restart_dispatcher, wait_status

runtime = runtime_fixture


def test_prewrite_owner_change_preserves_both_attempts_in_operator_inspection(runtime, monkeypatch):
    deps, client, _, peers, operator, _ = runtime
    assert open_rest(runtime).status_code == 200
    old = deps.runtime_dispatcher
    entered, release = threading.Event(), threading.Event()
    execute = old._execute

    def hold_claim(operation, attempt):
        entered.set()
        assert release.wait(15)
        return execute(operation, attempt)

    monkeypatch.setattr(old, "_execute", hold_claim)
    try:
        sent = send_message(runtime)
        operation_id = sent["runtime_operations"][0]
        assert entered.wait(5)
        first = wait_status(runtime, operation_id, "CLAIMED")
        old.quiesce()
        old.close()
        new = restart_dispatcher(runtime, old)
        second = wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
        assert first["attempt_id"] != second["attempt_id"] and new.epoch != old.epoch
    finally:
        release.set()
    result = tool(client, operator, "harness_list", {"view": "outbox", "maintenance": {
        "action": "inspect", "operation_id": operation_id}})
    assert result["ok"], result
    item = result["data"]["items"][0]
    history = item.get("attempt_history", [])
    assert {entry["attempt_id"] for entry in history} == {first["attempt_id"], second["attempt_id"]}, item
    assert any(entry["attempt_id"] == first["attempt_id"] and entry["state"] == "CLAIMED" for entry in history)
    assert any(entry["attempt_id"] == first["attempt_id"] and entry["state"] == "PENDING" for entry in history)
    assert any(entry["attempt_id"] == second["attempt_id"] and entry["state"] == "SENT_UNCONFIRMED" for entry in history)
    assert sum(command.verb == "send_turn" for peer in peers for command in peer.sent) == 1


def test_attempt_observations_are_atomic_immutable_and_do_not_record_heartbeats(runtime):
    deps = runtime[0]
    assert open_rest(runtime).status_code == 200
    operation_id = send_message(runtime)["runtime_operations"][0]
    wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
    cf = deps.connection_factory
    with cf.unit_of_work(write=False) as uow:
        before = uow.connection.execute("SELECT count(*) FROM runtime_delivery_attempt_events WHERE operation_id=?",
            (operation_id,)).fetchone()[0]
    with cf.unit_of_work() as uow:
        uow.connection.execute("UPDATE delivery_outbox SET updated_at=? WHERE operation_id=?",
            (deps.clock.now_iso(), operation_id))
    with pytest.raises(RuntimeError, match="commit cut"):
        with cf.unit_of_work() as uow:
            uow.connection.execute("UPDATE delivery_outbox SET status='OUTCOME_UNKNOWN' WHERE operation_id=?", (operation_id,))
            raise RuntimeError("commit cut")
    for statement in ("UPDATE runtime_delivery_attempt_events SET reason='rewrite'",
                      "DELETE FROM runtime_delivery_attempt_events"):
        with pytest.raises(sqlite3.IntegrityError, match="runtime_attempt_history_is_immutable"):
            with cf.unit_of_work() as uow:
                uow.connection.execute(statement + " WHERE operation_id=?", (operation_id,))
    with cf.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_delivery_attempt_events WHERE operation_id=?",
            (operation_id,)).fetchone()[0] == before
        assert deps.runtime_dispatcher.repo.get(uow, operation_id)["status"] == "SENT_UNCONFIRMED"


@pytest.fixture
def runtime58(tmp_path, request, monkeypatch):
    import shutil
    from okto_nexus.adapters.outbound.sqlite import migrations
    original = migrations._default_migrations_dir
    old = tmp_path / "schema58"
    old.mkdir()
    for path in original().glob("*.sql"):
        if int(path.name.split("_", 1)[0]) <= 58:
            shutil.copy(path, old)
    # Reuse the actual HTTP/MCP fixture, with only its initial packaged schema
    # restricted to the predecessor. No reverse migration or personal database.
    with monkeypatch.context() as patch:
        patch.setattr(migrations, "_default_migrations_dir", lambda: old)
        fixture = runtime_fixture.__wrapped__(tmp_path, request)
        instance = next(fixture)
    try:
        yield instance
    finally:
        with pytest.raises(StopIteration):
            next(fixture)


def test_upgrade_records_only_known_current_snapshot_and_is_repeatable(runtime58):
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
    deps = runtime58[0]
    assert open_rest(runtime58).status_code == 200
    operation_id = send_message(runtime58)["runtime_operations"][0]
    before = wait_status(runtime58, operation_id, "SENT_UNCONFIRMED")
    assert MigrationRunner(deps.connection_factory).apply() == [59]
    assert MigrationRunner(deps.connection_factory).apply() == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        events = uow.connection.execute("SELECT * FROM runtime_delivery_attempt_events WHERE operation_id=?",
            (operation_id,)).fetchall()
        assert len(events) == 1
        assert events[0]["provenance"] == "migration_snapshot"
        assert events[0]["attempt_id"] == before["attempt_id"]
        assert events[0]["state"] == before["status"]
        assert deps.runtime_dispatcher.repo.get(uow, operation_id) == before
