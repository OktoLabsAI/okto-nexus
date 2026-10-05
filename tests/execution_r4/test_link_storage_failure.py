"""An accepted control link must close explicitly when heartbeat storage fails."""
from contextlib import contextmanager
import sqlite3

from fastapi.testclient import TestClient
from nexus_connector_core import R4_PREVIEW_REVISION, encode_r4_frame
import pytest
from starlette.websockets import WebSocketDisconnect

from okto_nexus.errors import OktoNexusError
from test_ns09 import setup_authority


@pytest.mark.parametrize("failure", ["normalized", "sqlite", "authority"])
def test_heartbeat_storage_failure_closes_link_and_releases_owner(tmp_path, monkeypatch, failure):
    deps, app, _, _, _, _, info, _, ticket, _, server, executor = setup_authority(tmp_path, monkeypatch)
    factory = deps.connection_factory
    original = factory.unit_of_work
    touches = []

    class Connection:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def execute(self, sql, *args):
            if sql.startswith("UPDATE execution_executors SET last_seen_at="):
                touches.append(sql)
                if failure == "normalized":
                    raise OktoNexusError("DB_ERROR", "fixture private storage diagnostic", retryable=True)
                if failure == "authority":
                    raise OktoNexusError("PERMISSION_DENIED", "fixture private authority diagnostic")
                raise sqlite3.OperationalError("fixture private storage diagnostic")
            return self.connection.execute(sql, *args)

    @contextmanager
    def faulty_uow(*args, **kwargs):
        with original(*args, **kwargs) as uow:
            connection = uow.connection
            uow.connection = Connection(connection)
            try:
                yield uow
            finally:
                uow.connection = connection

    monkeypatch.setattr(factory, "unit_of_work", faulty_uow)
    base = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION,
                server_id=server, executor_id=executor)
    with TestClient(app, base_url="https://127.0.0.1:8202") as client:
        with client.websocket_connect(f"wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link",
                headers={"Authorization": "Bearer " + ticket}, subprotocols=["nxl.v1"]) as ws:
            ws.send_text(encode_r4_frame(dict(**base, type="hello", link_attempt_id="attempt",
                core_version=info["core_version"], management_revision=info["management_revision"],
                supported_nxl=[R4_PREVIEW_REVISION], snapshot_formats=[info["executor_snapshot_format"]],
                control_capabilities=[])).decode())
            welcome = ws.receive_json()
            assert welcome["type"] == "welcome"
            assert ws.receive_json()["type"] == "reconcile.request"
            ws.send_text(encode_r4_frame(dict(**base, type="heartbeat",
                connection_id=welcome["connection_id"],
                connection_generation=welcome["connection_generation"])).decode())
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_text()
            assert closed.value.code == (4403 if failure == "authority" else 1011)
            assert "private" not in closed.value.reason
    assert len(touches) == 1
    with original(write=False) as uow:
        row = uow.connection.execute(
            "SELECT control_state,owner_instance_id,generation FROM execution_executors WHERE executor_id=?",
            (executor,)).fetchone()
        assert tuple(row) == ("DISCONNECTED", None, welcome["connection_generation"])
        assert uow.connection.execute("SELECT count(*) FROM execution_operations").fetchone()[0] == 0
