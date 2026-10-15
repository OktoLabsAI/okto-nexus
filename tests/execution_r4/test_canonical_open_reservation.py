"""Opening needs an explicit key and durable admission before Core construction."""
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt


def test_open_requires_stable_key_and_reserves_before_native_factory(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    body = dict(agent_id="subject", kind="codex", endpoint_id=binding["endpoint_id"], project_root=str(root))
    response = client.post("/api/v1/harness/sessions", headers=headers["subject"], json=body)
    assert response.status_code == 422, response.text
    assert native.opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
    observed = []
    original = native.open
    async def checked(prepared, session_id, context, *, stream_epoch):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            rows = uow.connection.execute("SELECT o.operation_id,d.dispatch_state,p.session_id "
                "FROM execution_operations o JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id) "
                "JOIN execution_local_publications p USING(server_id,executor_id,operation_id) "
                "WHERE o.session_id=? AND o.action='runtime.open'", (session_id,)).fetchall()
            assert len(rows) == 1 and rows[0]["dispatch_state"] == "SENDING", [dict(r) for r in rows]
            observed.append(dict(rows[0]))
        return await original(prepared, session_id, context, stream_epoch=stream_epoch)
    monkeypatch.setattr(native, "open", checked)
    body["idempotency_key"] = "reserved-before-native"
    response = client.post("/api/v1/harness/sessions", headers=headers["subject"], json=body)
    assert response.status_code == 200, response.text
    operation = response.json()["data"]
    wait_receipt(setup, operation)
    replay = client.post("/api/v1/harness/sessions", headers=headers["subject"], json=body)
    assert replay.status_code == 200 and replay.json()["data"]["operation_id"] == operation["operation_id"]
    assert observed == [dict(operation_id=operation["operation_id"], dispatch_state="SENDING", session_id=operation["scope"]["session_id"])]
    assert native.opens == 1
