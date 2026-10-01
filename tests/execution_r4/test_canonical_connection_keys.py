"""Limited bearer bootstrap remains bound through admission, dispatch and leases."""
import json
import time

import pytest

from okto_nexus.errors import OktoNexusError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt, admit


def issue(setup, binding, actor="subject"):
    _, _, client, headers, *_ = setup
    response = client.post("/api/v1/agents/subject/connection-keys", headers=headers[actor],
                           json={"endpoint_id": binding["endpoint_id"]})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def opening(setup, key):
    response = setup[2].post("/api/v1/connections/open",
        headers={"Authorization": "Bearer " + key["connection_key"]}, json={})
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.parametrize("issuer", ["subject", "operator"])
def test_limited_key_opens_core_once_and_cannot_control(connected_local, issuer):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    key = issue(setup, binding, issuer)
    opened = opening(setup, key)
    wait_receipt(setup, opened)
    replay = opening(setup, key)
    assert replay["reused"] and replay["operation_id"] == opened["operation_id"]
    session = opened["scope"]["session_id"]
    limited = {"Authorization": "Bearer " + key["connection_key"]}
    denied = client.post(f"/api/v1/harness/sessions/{session}/send", headers=limited,
                        json={"payload": {"text": "Forbidden"}, "idempotency_key": "key-send"})
    assert denied.status_code in (401, 403), denied.text
    assert native.opens == 1 and native.native.sent == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT connection_key_id FROM execution_operations WHERE operation_id=?",
                                      (opened["operation_id"],)).fetchone()[0] == key["key_id"]
        assert uow.connection.execute("SELECT COUNT(*) FROM harness_sessions").fetchone()[0] == 0
    close = client.post(f"/api/v1/harness/sessions/{session}/close", headers=headers["subject"],
                        json={"idempotency_key": "key-close"})
    assert close.status_code == 200, close.text
    wait_receipt(setup, close.json()["data"], stages=("SUCCEEDED",))


@pytest.mark.parametrize("migration", [92, 93])
def test_additive_open_authority_migrations_preserve_existing_r4_history(connected_local, tmp_path, migration):
    import sqlite3
    from okto_nexus.config import NexusConfig
    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
    setup, binding, _ = connected_local
    deps = setup[0]
    opened = admit(setup, binding, "pre-key-opening", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    closed = admit(setup, binding, "pre-key-close", "runtime.close", session_id=opened["scope"]["session_id"])
    wait_receipt(setup, closed, stages=("SUCCEEDED",))
    config = NexusConfig(home_dir=tmp_path / "upgrade-copy")
    factory = ConnectionFactory(config)
    # Reconstruct the exact prior schema on a consistent copy of real R4 rows.
    with sqlite3.connect(config.db_path) as target:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            uow.connection.backup(target)
        target.execute("ALTER TABLE execution_operations DROP COLUMN boot_authority_json")
        if migration == 92:
            target.execute("ALTER TABLE execution_operations DROP COLUMN connection_key_id")
        target.execute("DELETE FROM schema_migrations WHERE version>=?", (migration,))
        expected = target.execute("SELECT * FROM execution_operations ORDER BY operation_id").fetchall()
        receipts = target.execute("SELECT * FROM execution_receipts ORDER BY operation_id,receipt_revision").fetchall()
    assert MigrationRunner(factory).apply() == list(range(migration, 94))
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT * FROM execution_operations ORDER BY operation_id").fetchall()
        assert [tuple(row)[:-(94 - migration)] for row in rows] == expected
        assert all(row["connection_key_id"] is None for row in rows)
        assert all(row["boot_authority_json"] is None for row in rows)
        assert [tuple(row) for row in uow.connection.execute("SELECT * FROM execution_receipts ORDER BY operation_id,receipt_revision")] == receipts
        assert uow.connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("change", ["revoke", "expire", "source_grant"])
def test_key_change_after_admission_prevents_native_open(connected_local, change):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    key = issue(setup, binding)
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        opened = opening(setup, key)
        with deps.connection_factory.unit_of_work() as uow:
            if change == "revoke":
                uow.connection.execute("UPDATE agent_connection_keys SET revoked_at=? WHERE key_id=?",
                                       (deps.clock.now_iso(), key["key_id"]))
            elif change == "expire":
                uow.connection.execute("UPDATE agent_connection_keys SET expires_at='2000-01-01T00:00:00Z' WHERE key_id=?", (key["key_id"],))
            else:
                uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at=?", (deps.clock.now_iso(),))
    finally:
        client.portal.call(lock.release)
    until = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT dispatch_state,last_error FROM execution_dispatch_outbox WHERE operation_id=?",
                                           (opened["operation_id"],)).fetchone()
            state = row[0]
        if state == "RESOLVED_TERMINAL":
            assert "PERMISSION_DENIED" in row[1], row[1]
            break
        assert time.monotonic() < until, state
        time.sleep(.02)
    assert native.opens == 0
    replay = client.post("/api/v1/connections/open", headers={"Authorization": "Bearer " + key["connection_key"]}, json={})
    assert replay.status_code in (401, 403), replay.text


def test_revoked_bootstrap_key_cannot_renew_lease(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    key = issue(setup, binding)
    opened = opening(setup, key)
    wait_receipt(setup, opened)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        request = json.loads(uow.connection.execute("SELECT request_json FROM execution_leases ORDER BY lease_serial DESC LIMIT 1").fetchone()[0])
    revoke = client.delete("/api/v1/agents/subject/connection-keys/" + key["key_id"], headers=headers["operator"])
    assert revoke.status_code == 200, revoke.text
    request.update(request_id="renew-revoked-key", purpose="renew")
    owner = app.state.embedded_dispatch_owner
    with pytest.raises(OktoNexusError, match="connection credential"):
        owner.leases.issue(request, channel=owner.channel)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_leases").fetchone()[0] == 1
    # Revocation does not remove the authenticated subject's containment path.
    close = client.post(f"/api/v1/harness/sessions/{opened['scope']['session_id']}/close",
                        headers=headers["subject"], json={"idempotency_key": "revoked-key-close"})
    assert close.status_code == 200, close.text
    wait_receipt(setup, close.json()["data"], stages=("SUCCEEDED",))
