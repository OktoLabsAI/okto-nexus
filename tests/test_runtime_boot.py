"""Retained endpoint reconciliation cannot revive removed native setup."""
import pytest
from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
def test_endpoint_reconciliation_requires_explicit_risk_and_is_idempotent(runtime):
    deps, client, _, peers, key, caller = runtime
    from test_runtime_production_multiplex import retained_profile, retained_endpoint, refused_open
    retained_profile(runtime)
    retained_endpoint(runtime, "endpoint-pi")
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET health='quarantined',health_reason='owner_lost' WHERE endpoint_id='endpoint-pi'")
    refused_open(runtime, "endpoint-pi")
    assert not peers
    body = {"expected_revision": 1, "idempotency_key": "fixture-reconciliation", "reason": "Reviewed disposable fixture owner"}
    url = "/api/v1/harness/endpoints/endpoint-pi/reconcile"
    assert client.post(url, headers={"x-api-key": key}, json=body).status_code == 422
    body["acknowledge_uncertain_effects"] = True
    assert client.post(url, headers={"x-api-key": caller}, json=body).status_code == 403
    response = client.post(url, headers={"x-api-key": key}, json=body)
    assert response.status_code == 200, response.text
    repeated = client.post(url, headers={"x-api-key": key}, json=body)
    assert repeated.json()["data"]["reconciliation_id"] == response.json()["data"]["reconciliation_id"]
    assert repeated.json()["data"]["replayed"]
    assert not peers, "reconciliation must not itself spawn or replay"
    # Reconciliation preserves history; it cannot restore removed native setup.
    refused_open(runtime, "endpoint-pi")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_endpoint_reconciliations").fetchone()[0] == 1
