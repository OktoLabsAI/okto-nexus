"""Public admission budgets include children and native decisions atomically."""
import pytest

from test_session_reuse import reuse_qualified, reuse_connected, resolve, admit
from test_local_realization import local_setup
from test_embedded_dispatch import wait_receipt
from test_native_decisions import decision_state, opening, post, snapshot
from okto_nexus.application import execution_capacity


def submit(setup, resolved):
    return setup[2].post("/v1/runtime/operations", headers=setup[3]["subject"],
        json={name: resolved[name] for name in
              ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")})


def intent(setup, binding, session, identifier, action="turn.submit"):
    body = dict(client_intent_id=identifier, intent=action, binding_id=binding["binding_id"],
                workspace_binding_id=binding["workspace_binding_id"], session_id=session)
    if action == "turn.submit":
        body["text"] = "Queued work"
    response = setup[2].post("/v1/runtime/intents:resolve", headers=setup[3]["subject"], json=body)
    assert response.status_code == 200, response.text
    return response.json()


def seed_pending(conn, *, action, count):
    source = dict(conn.execute("SELECT * FROM execution_operations LIMIT 1").fetchone())
    for index in range(count):
        row = dict(source, operation_id=f"quota-{action}-{index}", action=action,
                   admission_state="ACCEPTED", parent_operation_id=None)
        conn.execute("INSERT INTO execution_operations (" + ",".join(row) + ") VALUES (" +
                     ",".join("?" for _ in row) + ")", tuple(row.values()))


def test_productive_flood_keeps_control_reserve_and_replay(reuse_connected):
    setup, binding, native = reuse_connected
    opened = resolve(setup, binding, "capacity-open", new_session=True).json()
    admit(setup, opened)
    wait_receipt(setup, opened)
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    session = opened["scope"]["session_id"]
    accepted = []
    for index in range(32):
        planned = intent(setup, binding, session, f"pending-{index}")
        assert submit(setup, planned).status_code == 202
        accepted.append(planned)
    refused = submit(setup, intent(setup, binding, session, "overflow"))
    assert refused.status_code == 429 and refused.headers["retry-after"] == "1"
    assert refused.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert not refused.json()["error"]["possible_effect"]
    assert submit(setup, accepted[0]).status_code == 200
    for index in range(8):
        assert submit(setup, intent(setup, binding, session, f"close-{index}", "runtime.close")).status_code == 202
    assert submit(setup, intent(setup, binding, session, "control-overflow", "runtime.close")).status_code == 429
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE admission_state='ACCEPTED'").fetchone()[0] == 40
        assert uow.connection.execute("SELECT min(admission_bytes) FROM execution_operations").fetchone()[0] > 0
    assert native.native.sent == [] and native.opens == 1


def test_initial_child_overflow_rolls_back_parent_and_session(reuse_connected):
    setup, binding, native = reuse_connected
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    seed = resolve(setup, binding, "seed", new_session=True).json()
    admit(setup, seed)
    with setup[0].connection_factory.unit_of_work() as uow:
        seed_pending(uow.connection, action="turn.submit", count=30)
    planned = resolve(setup, binding, "parent-and-child", new_session=True, text="Initial work").json()
    response = submit(setup, planned)
    assert response.status_code == 429
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 31
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 1
    assert native.opens == 0


def test_byte_budget_refuses_before_operation_creation(reuse_connected, monkeypatch):
    setup, binding, native = reuse_connected
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    monkeypatch.setattr(execution_capacity, "REGULAR_BYTES", 1)
    planned = resolve(setup, binding, "byte-limit", new_session=True).json()
    assert submit(setup, planned).status_code == 429
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
    assert native.opens == 0


@pytest.mark.parametrize("decision_state", [None, "input"], indirect=True)
def test_native_decision_capacity_refusal_is_atomic(decision_state):
    with decision_state[0].connection_factory.unit_of_work() as uow:
        seed_pending(uow.connection, action="approval.decide", count=8)
    before = snapshot(decision_state)
    response = post(decision_state)
    assert response.status_code == 429 and response.headers["retry-after"] == "1"
    assert snapshot(decision_state) == before


def test_two_requests_race_for_last_pending_slot(reuse_connected):
    from concurrent.futures import ThreadPoolExecutor
    setup, binding, _ = reuse_connected
    opened = resolve(setup, binding, "race-open", new_session=True).json()
    admit(setup, opened)
    wait_receipt(setup, opened)
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    with setup[0].connection_factory.unit_of_work() as uow:
        seed_pending(uow.connection, action="turn.submit", count=31)
    plans = [intent(setup, binding, opened["scope"]["session_id"], f"last-slot-{i}") for i in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda planned: submit(setup, planned), plans))
    assert sorted(response.status_code for response in responses) == [202, 429]
    winner = plans[next(i for i, response in enumerate(responses) if response.status_code == 202)]
    assert submit(setup, winner).status_code == 200
    with setup[0].connection_factory.unit_of_work() as uow:
        # Durable acknowledgement, not elapsed time, returns pending capacity.
        uow.connection.execute("UPDATE execution_operations SET admission_state='DISPATCHED' WHERE operation_id=?",
                               (winner["operation_id"],))
    loser = plans[next(i for i, response in enumerate(responses) if response.status_code == 429)]
    assert submit(setup, loser).status_code == 202


def test_capacity_migration_backfills_utf8_and_protects_historical_input():
    import sqlite3
    from importlib.resources import files
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE execution_operations(server_id TEXT,executor_id TEXT,operation_id TEXT,"
                     "action TEXT,semantic_payload TEXT,admission_state TEXT)")
        conn.executemany("INSERT INTO execution_operations VALUES('s','e',?,?,?,'ACCEPTED')", [
            ("plain", "turn.submit", '"é"'), ("input", "input.provide", '{"response_ref":"retained"}')])
        sql = files("okto_nexus").joinpath("migrations/091_execution_admission_capacity.sql").read_text()
        conn.executescript(sql)
        rows = conn.execute("SELECT operation_id,admission_bytes FROM execution_operations ORDER BY operation_id").fetchall()
        assert rows == [("input", len('{"response_ref":"retained"}'.encode()) + 16384), ("plain", 4)]
        plan = conn.execute("EXPLAIN QUERY PLAN SELECT admission_bytes FROM execution_operations "
                            "WHERE server_id='s' AND executor_id='e' AND action='turn.submit' "
                            "AND admission_state IN ('ACCEPTED','DISPATCH_PENDING','RECONCILING') LIMIT 32").fetchall()
        assert any("idx_execution_pending_admission" in row[3] for row in plan)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE execution_operations SET admission_bytes=-1")
    finally:
        conn.close()
