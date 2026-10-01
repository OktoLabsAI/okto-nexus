"""Existing harness callers share canonical admission and Core dispatch."""
import pytest
from pathlib import Path

from okto_nexus.bootstrap import execution_compat
from okto_nexus.adapters.inbound.mcp.tools import harness
from test_embedded_dispatch import (local_setup, connected_local, qualified_contract,
                                    admit, wait_receipt)


@pytest.fixture(autouse=True)
def qualified_bridge(monkeypatch, qualified_contract):
    info = execution_compat.protocol_info()
    monkeypatch.setattr(execution_compat, "protocol_info",
                        lambda: {**info, "remote_execution_ready": True})


def test_existing_rest_commands_use_core_once(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, "compat-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    session = opened["scope"]["session_id"]
    def forbidden(*args, **kwargs):
        raise AssertionError("Canonical caller reached the legacy control service")
    monkeypatch.setattr(harness.RuntimeControlService, "send", forbidden)
    monkeypatch.setattr(harness.RuntimeControlService, "close", forbidden)
    for action, extra in (
        ("send", {"payload": {"text": "Hello"}}),
        ("steer", {"payload": {"text": "Carefully"}, "expected_turn_id": "turn-from-native"}),
        ("interrupt", {}), ("close", {}),
    ):
        body = {"idempotency_key": "compat-" + action, **extra}
        path = f"/api/v1/harness/sessions/{session}/{action}"
        result = client.post(path, headers=headers["subject"], json=body)
        assert result.status_code == 200, result.text
        operation = result.json()["data"]
        replay = client.post(path, headers=headers["subject"], json=body)
        assert replay.status_code == 200, replay.text
        assert replay.json()["data"]["operation_id"] == operation["operation_id"]
        assert replay.json()["data"]["reused"]
        wait_receipt(setup, operation)
        history = client.get("/api/v1/harness/operations/" + operation["operation_id"], headers=headers["subject"])
        assert history.status_code == 200, history.text
        assert history.json()["data"]["scope"]["session_id"] == session
    read = client.get(f"/api/v1/harness/sessions/{session}", headers=headers["subject"])
    assert read.status_code == 200, read.text
    assert read.json()["data"]["lifecycle_state"] == "CLOSED"
    assert native.opens == 1 and native.native.stopped
    assert [verb for verb, _ in native.native.sent] == ["send_turn", "steer", "interrupt"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM harness_sessions").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 5


@pytest.mark.parametrize("extra", [
    {"idempotency_key": None}, {"expected_owner_epoch": 1},
    {"expected_operation_id": "old-op"}, {"expected_turn_id": "wrong-target"},
    {"payload": {"text": "hello", "model": "override"}},
])
def test_legacy_options_never_silently_change_canonical_command(connected_local, extra):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    opened = admit(setup, binding, "negative-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    result = client.post(f"/api/v1/harness/sessions/{opened['scope']['session_id']}/send",
        headers=headers["subject"], json={"idempotency_key": "invalid-command",
                                         "payload": {"text": "hello"}, **extra})
    assert result.status_code in (400, 422), result.text
    assert native.native.sent == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1


def test_mcp_uses_same_admission_and_history(connected_local, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    key = headers["subject"]["Authorization"].removeprefix("Bearer ")
    client.headers["host"] = "127.0.0.1:8000"
    opened = admit(setup, binding, "mcp-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    session = opened["scope"]["session_id"]
    body = dict(session_id=session, payload={"text": "MCP turn"}, idempotency_key="mcp-send")
    sent = tool(client, key, "harness_send", body)
    assert sent["ok"], sent
    wait_receipt(setup, sent["data"])
    replay = tool(client, key, "harness_send", body)
    assert replay["ok"] and replay["data"]["reused"], replay
    assert replay["data"]["operation_id"] == sent["data"]["operation_id"]
    read = tool(client, key, "harness_get", {"operation_id": sent["data"]["operation_id"]})
    assert read["ok"] and read["data"]["scope"]["session_id"] == session, read
    assert tool(client, key, "harness_get", {"session_id": session})["ok"]
    closed = tool(client, key, "harness_close", {"session_id": session, "idempotency_key": "mcp-close"})
    assert closed["ok"], closed
    wait_receipt(setup, closed["data"], stages=("SUCCEEDED",))
    assert len(native.native.sent) == 1 and native.native.stopped


@pytest.mark.parametrize("denial", ["grant", "endpoint_disabled", "readiness", "unauthorized"])
def test_canonical_callers_fail_closed(connected_local, monkeypatch, denial):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    opened = admit(setup, binding, "denied-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    caller = headers["subject"]
    if denial == "grant":
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("DELETE FROM runtime_execution_grants")
    elif denial == "endpoint_disabled":
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id=?", (binding["endpoint_id"],))
    elif denial == "readiness":
        info = execution_compat.protocol_info()
        monkeypatch.setattr(execution_compat, "protocol_info",
                            lambda: {**info, "remote_execution_ready": False})
    else:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("INSERT INTO agents(agent_id,created_at) VALUES (?,?)", ("outsider", deps.clock.now_iso()))
            key = setup[1].state.auth.issue_key(uow, agent_id="outsider")
        caller = {"Authorization": "Bearer " + key}
        for path in (f"sessions/{opened['scope']['session_id']}", f"operations/{opened['operation_id']}"):
            read = client.get("/api/v1/harness/" + path, headers=caller)
            assert read.status_code in (403, 404), read.text
    result = client.post(f"/api/v1/harness/sessions/{opened['scope']['session_id']}/send",
        headers=caller, json={"payload": {"text": "Forbidden"}, "idempotency_key": "denied-command"})
    assert result.status_code in (403, 404, 409), result.text
    assert native.native.sent == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
