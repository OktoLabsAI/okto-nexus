"""Existing connection discovery/configuration follows public Core descriptors."""
from pathlib import Path
import pytest
import time

from okto_nexus.bootstrap import execution_compat
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt


def method(view):
    return next(row for row in view["methods"] if row["method"] == "codex_app_server")


def test_discovered_canonical_connect_call_opens_once(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    response = client.get("/api/v1/connections/available", headers=headers["subject"])
    assert response.status_code == 200, response.text
    assert str(root) not in response.text and "local_record" not in response.text
    found = method(response.json()["data"])
    assert found["available"] and found["protocol"] == "nxl-r4"
    row = found["endpoints"][0]
    assert row["endpoint_id"] == binding["endpoint_id"] and row["available"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_client_intents").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
    assert native.opens == 0
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers["host"] = "127.0.0.1:8000"
    key = headers["subject"]["Authorization"].removeprefix("Bearer ")
    call = row["connect"]
    rejected = tool(client, key, call["tool"], call["arguments"])
    assert not rejected["ok"] and native.opens == 0, rejected
    call["arguments"]["maintenance"]["idempotency_key"] = "discovered-open"
    opened = tool(client, key, call["tool"], call["arguments"])
    assert opened["ok"], opened
    wait_receipt(setup, opened["data"])
    replay = tool(client, key, call["tool"], call["arguments"])
    assert replay["ok"] and replay["data"]["reused"], replay
    assert native.opens == 1
    closed = tool(client, key, "harness_close", dict(session_id=opened["data"]["scope"]["session_id"], idempotency_key="discovered-close"))
    assert closed["ok"], closed
    wait_receipt(setup, closed["data"], stages=("SUCCEEDED",))


def test_operator_restricts_execution_without_issuing_connection_keys(connected_local):
    setup, binding, native = connected_local
    _, _, client, headers, *_ = setup
    path = "/api/v1/agents/subject/connections"
    view = client.get(path, headers=headers["operator"])
    assert view.status_code == 200, view.text
    assert method(view.json()["data"])["platform_authority"] == "executor"
    key = client.post("/api/v1/agents/subject/connection-keys", headers=headers["subject"],
                      json={"endpoint_id": binding["endpoint_id"]})
    assert key.status_code in (404, 405), key.text
    path = '/api/v1/agents/subject/execution-policy'
    change = dict(expected_revision=0, execution_location='remote')
    denied = client.put(path, headers=headers["subject"], json=change)
    assert denied.status_code == 403, denied.text
    response = client.put(path, headers=headers["operator"], json=change)
    assert response.status_code == 200, response.text
    assert response.json()['data']['execution_location'] == 'remote'
    available = client.get("/api/v1/connections/available", headers=headers["subject"])
    found = method(available.json()["data"])
    assert not found["available"] and "connect" not in found["endpoints"][0]
    assert client.put(path, headers=headers["operator"], json=change).status_code == 409
    assert native.opens == 0


@pytest.mark.parametrize("cause", ["grant", "stale", "offline", "readiness"])
def test_canonical_discovery_does_not_advertise_unready_binding(connected_local, monkeypatch, cause):
    setup, _, native = connected_local
    deps, _, client, headers, *_ = setup
    if cause == "stale":
        for key, value in list(deps.execution_fresh_publications.items()):
            deps.execution_fresh_publications[key] = (value[0], value[1] - 200, value[2])
    elif cause == "readiness":
        info = execution_compat.protocol_info()
        monkeypatch.setattr(execution_compat, "protocol_info", lambda: {**info, "remote_execution_ready": False})
    else:
        with deps.connection_factory.unit_of_work() as uow:
            if cause == "grant":
                uow.connection.execute("DELETE FROM runtime_execution_grants")
            else:
                uow.connection.execute("UPDATE execution_executors SET control_state='RECOVERING'")
    result = client.get("/api/v1/connections/available", headers=headers["subject"])
    assert result.status_code == 200, result.text
    found = method(result.json()["data"])
    assert not found["available"] and "connect" not in found["endpoints"][0]
    assert found["endpoints"][0]["unavailable_reasons"] and native.opens == 0


def test_binding_discovery_reads_canonical_history_without_native_registry(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    _, _, client, headers, *_ = setup
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers["host"] = "127.0.0.1:8000"
    key = headers["operator"]["Authorization"].removeprefix("Bearer ")
    opened = client.post("/api/v1/connections/connect", headers=headers["subject"],
                         json=dict(endpoint_id=binding["endpoint_id"], idempotency_key="binding-read-open"))
    assert opened.status_code == 200, opened.text
    operation = opened.json()["data"]
    wait_receipt(setup, operation)
    result = tool(client, key, "harness_list", dict(view="bindings", maintenance={"agent_id": "subject"}))
    assert result["ok"], result
    endpoint = result["data"]["agents"][0]["endpoints"][0]
    assert endpoint["adapter_id"] == "codex_app_server"
    session = endpoint["sessions"][0]
    assert session["session_id"] == operation["scope"]["session_id"]
    assert session["lifecycle_state"] == "READY"
    assert session["process_liveness"] == "not_probed" and not session["current_owner_ready_record"]
    assert endpoint["runtime_descriptor"]["native_kind"] == "codex"
    closed = client.post(f"/api/v1/harness/sessions/{session['session_id']}/close", headers=headers["subject"],
                         json={"idempotency_key": "binding-read-close"})
    assert closed.status_code == 200, closed.text
    wait_receipt(setup, closed.json()["data"], stages=("SUCCEEDED",))


def test_self_connect_refuses_foreign_identity_and_revoked_grant(connected_local, monkeypatch):
    from test_agent_recovery_isolation import create_agent
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    foreign = create_agent(setup, "foreign")[3]["subject"]
    available = client.get("/api/v1/connections/available", headers=foreign)
    assert available.status_code == 200, available.text
    assert all(not row["endpoints"] for row in available.json()["data"]["methods"])
    body = dict(endpoint_id=binding["endpoint_id"], idempotency_key="self-denied")
    assert client.post("/api/v1/connections/connect", headers=foreign, json=body).status_code == 403
    assert client.post("/api/v1/connections/connect", headers=headers["subject"],
        json=dict(body, agent_id="foreign")).status_code == 422
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers["host"] = "127.0.0.1:8000"
    spoofed = tool(client, headers["subject"]["Authorization"].removeprefix("Bearer "),
        "harness_list", dict(view="connections", maintenance=dict(action="available", agent_id="foreign")))
    assert not spoofed["ok"], spoofed
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at=?", (deps.clock.now_iso(),))
    assert client.post("/api/v1/connections/connect", headers=headers["subject"], json=body).status_code == 403
    assert native.opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0


def test_self_connect_keeps_authenticated_identity_despite_operator_environment(connected_local, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools import harness
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    monkeypatch.setenv("OKTO_NEXUS_API_KEY", headers["operator"]["Authorization"].removeprefix("Bearer "))
    # Canonical admission does not select an ambient credential for the old
    # Server-to-Server proxy, even when its legacy owner predicate is false.
    monkeypatch.setattr(harness, "is_local_runtime_owner", lambda deps: False)
    opened = client.post("/api/v1/connections/connect", headers=headers["subject"],
        json=dict(endpoint_id=binding["endpoint_id"], idempotency_key="self-original-principal"))
    assert opened.status_code == 200, opened.text
    wait_receipt(setup, opened.json()["data"])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT subject_agent_id,actor_agent_id FROM execution_operations").fetchone()[:] == ("subject", "subject")
        assert uow.connection.execute("SELECT COUNT(*) FROM agent_connection_keys").fetchone()[0] == 0
    assert native.opens == 1


@pytest.mark.parametrize('change', ['grant', 'permission'])
def test_self_connect_revalidates_grant_after_admission_before_native_open(connected_local, change):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        opened = client.post("/api/v1/connections/connect", headers=headers["subject"],
            json=dict(endpoint_id=binding["endpoint_id"], idempotency_key="self-revoke-before-write"))
        assert opened.status_code == 200, opened.text
        op = opened.json()["data"]["operation_id"]
        with deps.connection_factory.unit_of_work() as uow:
            if change == 'grant':
                uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at=?", (deps.clock.now_iso(),))
            else:
                uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'",
                    ('{"messages":{"send_direct":false}}',))
    finally:
        client.portal.call(lock.release)
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT dispatch_state,last_error FROM execution_dispatch_outbox WHERE operation_id=?", (op,)).fetchone()
        if row[0] == "RESOLVED_TERMINAL":
            assert ("CONFLICT" if change == 'permission' else "PERMISSION_DENIED") in row[1]
            break
        assert time.monotonic() < deadline, tuple(row)
        time.sleep(.02)
    assert native.opens == 0
