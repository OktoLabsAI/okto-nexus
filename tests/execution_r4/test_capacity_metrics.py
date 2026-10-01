"""Operator-only local gauges have fixed cardinality and retain unknown costs."""
import json

from fastapi.testclient import TestClient

from test_dispatch_pump import owner
from test_dispatch_capacity import backlog, reserve
from okto_nexus.application import execution_capacity


def read_metrics(state, actor="operator"):
    app = state[1]
    return TestClient(app).get("/api/v1/metrics/local/summary",
        headers={"Authorization": "Bearer " + app.state.test_agent_keys[actor]})


def test_operator_metrics_count_pending_and_uncertain_reservations_without_ids(owner):
    backlog(owner, "turn.interrupt", 3)
    held = reserve(owner)
    assert held.reservation_class == "control"
    with owner[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_dispatch_outbox SET dispatch_state='RECONCILING' "
                               "WHERE operation_id=?", (held.operation_id,))
        uow.connection.execute("UPDATE execution_operations SET admission_state='RECONCILING' "
                               "WHERE operation_id=?", (held.operation_id,))
    response = read_metrics(owner)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    gauges = data["runtime_capacity"]
    assert gauges["status"] == "available"
    assert set(gauges) == {"status", "pending_totals", "dispatch_totals", "pending_limits_per_executor"}
    assert gauges["pending_totals"]["regular"]["items"] == 1
    assert gauges["pending_totals"]["control"]["items"] == 3
    assert gauges["dispatch_totals"]["control"] == {"items": 1, "bytes": held.reserved_bytes}
    assert gauges["dispatch_totals"]["regular"] == {"items": 0, "bytes": 0}
    assert gauges["pending_limits_per_executor"]["regular"]["items"] == 32
    assert gauges["pending_limits_per_executor"]["control"]["items"] == 8
    assert set(data["authentication_cache"]) == {"entries", "capacity", "ttl_seconds"}
    assert 0 < data["authentication_cache"]["entries"] <= 4096
    raw = json.dumps({"capacity": gauges, "cache": data["authentication_cache"]})
    for identity in (held.server_id, held.executor_id, held.operation_id, held.owner_connection_id):
        assert identity not in raw
    for key in owner[1].state.test_agent_keys.values():
        assert key not in raw
    with owner[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' "
                               "WHERE operation_id=?", (held.operation_id,))
        uow.connection.execute("UPDATE execution_dispatch_outbox SET dispatch_state='RESOLVED_TERMINAL',"
                               "reserved_bytes=0,reservation_class=NULL WHERE operation_id=?", (held.operation_id,))
    current = read_metrics(owner).json()["data"]["runtime_capacity"]
    assert current["pending_totals"]["control"]["items"] == 2
    assert current["dispatch_totals"]["control"] == {"items": 0, "bytes": 0}


def test_nonoperator_keeps_existing_summary_without_global_runtime_gauges(owner):
    response = read_metrics(owner, "subject")
    assert response.status_code == 200
    assert "runtime_capacity" not in response.json()["data"]
    assert "authentication_cache" not in response.json()["data"]


def test_unavailable_storage_is_not_reported_as_zero_capacity(owner, monkeypatch):
    def unavailable(factory):
        raise OSError("Injected metrics storage failure")
    monkeypatch.setattr(execution_capacity, "execution_capacity_snapshot", unavailable)
    response = read_metrics(owner)
    assert response.status_code == 200
    assert response.json()["data"]["runtime_capacity"] == {"status": "unavailable"}
