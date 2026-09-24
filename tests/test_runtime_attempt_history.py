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


@pytest.mark.parametrize("interrupt_backfill", [False, True])
def test_upgrade_records_only_known_current_snapshot_and_is_repeatable(tmp_path, monkeypatch, interrupt_backfill):
    import shutil
    from okto_nexus.adapters.outbound.sqlite import migrations
    from test_migrations import make_factory
    old = tmp_path / "schema58"
    old.mkdir()
    for path in migrations._default_migrations_dir().glob("*.sql"):
        if int(path.name.split("_", 1)[0]) <= 58:
            shutil.copy(path, old)
    factory = make_factory(tmp_path)
    migrations.MigrationRunner(factory, migrations_dir=old).apply()
    # Persisted predecessor fixture only: current dispatcher code deliberately
    # requires its new schema and must not be run against an unmigrated store.
    with factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES('ws','2026-09-24T00:00:00Z')")
        c.execute("INSERT INTO agents(agent_id,created_at) VALUES('worker','2026-09-24T00:00:00Z')")
        c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,created_at) VALUES('msg','ws','worker','2026-09-24T00:00:00Z')")
        c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) "
            "VALUES('delivery','msg','worker','unread','2026-09-24T00:00:00Z')")
        c.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,created_at,updated_at) "
            "VALUES('endpoint','worker','ws','fixture','fixture','2026-09-24T00:00:00Z','2026-09-24T00:00:00Z')")
        c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,"
            "recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,"
            "created_at,updated_at,status,attempt_id,attempt_count,ack_level) "
            "VALUES('op','delivery','msg','ws','worker','fixture','worker','endpoint',1,'{}','fixture','fixture','root',"
            "'2026-09-24T00:00:00Z','2026-09-24T00:00:00Z','SENT_UNCONFIRMED','known-attempt',1,'TRANSPORT_WRITE')")
        before = dict(c.execute("SELECT * FROM delivery_outbox WHERE operation_id='op'").fetchone())
    if interrupt_backfill:
        from okto_nexus.errors import OktoNexusError
        connect = factory.get_connection
        observed = []

        class InterruptedBackfill:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, statement, *args):
                if statement.startswith("CREATE TRIGGER runtime_delivery_attempt_observed"):
                    # The real INSERT SELECT has already populated nonempty
                    # history in this transaction. Cut before migration commit.
                    observed.append(self.connection.execute(
                        "SELECT count(*) FROM runtime_delivery_attempt_events").fetchone()[0])
                    raise sqlite3.OperationalError("fixture cut after populated backfill")
                return self.connection.execute(statement, *args)

        with monkeypatch.context() as patch:
            patch.setattr(factory, "get_connection", lambda: InterruptedBackfill(connect()))
            with pytest.raises(OktoNexusError, match="migration"):
                migrations.MigrationRunner(factory).apply()
        assert observed == [1]
        with factory.unit_of_work(write=False) as uow:
            c = uow.connection
            assert c.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 58
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='runtime_delivery_attempt_events'").fetchone()
            assert dict(c.execute("SELECT * FROM delivery_outbox WHERE operation_id='op'").fetchone()) == before
            assert not c.execute("PRAGMA foreign_key_check").fetchall()
    assert migrations.MigrationRunner(factory).apply() == [59, 60, 61, 62, 63, 64, 65]
    assert migrations.MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        events = uow.connection.execute("SELECT * FROM runtime_delivery_attempt_events WHERE operation_id='op'").fetchall()
        assert len(events) == 1
        assert events[0]["provenance"] == "migration_snapshot"
        assert events[0]["attempt_id"] == before["attempt_id"]
        assert events[0]["state"] == before["status"]
        after = dict(uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id='op'").fetchone())
        assert all(after[key] == value for key, value in before.items())
        assert after["next_attempt_at"] is None and after["retry_basis"] is None
