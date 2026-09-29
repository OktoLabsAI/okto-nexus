"""The R4 WebSocket upgrade has its own ticket and version fence."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nexus_connector_core import (
    R4_PREVIEW_REVISION, __version__ as CORE_VERSION, encode_r4_frame,
)

from okto_nexus.adapters.inbound.http import executor_link
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.sqlite.execution_identity import (
    ensure_execution_installation, register_remote_executor,
)
from okto_nexus.adapters.outbound.sqlite.execution_tickets import (
    issue_execution_ticket,
)
from okto_nexus.bootstrap.dependencies import bootstrap


def test_ns08_01(tmp_path, monkeypatch):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    factory = deps.connection_factory
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO agents(agent_id,created_at) VALUES ('agent',?)",
            ("2026-09-29T00:00:00Z",),
        )
        app.state.auth.issue_key(uow, agent_id="agent")
    registration = register_remote_executor(
        factory, actor_agent_id="agent", connector_id="connector",
        client_intent_id="registration",
    )
    installation = ensure_execution_installation(factory)
    ticket = issue_execution_ticket(
        factory, server_id=installation.server_id,
        executor_id=registration.executor_id, agent_id="agent",
        binding_id=None,
    ).ticket
    path = ("wss://127.0.0.1:8202/v1/runtime/executors/"
            f"{registration.executor_id}/link")
    with TestClient(app, base_url="https://127.0.0.1:8202") as client:
        with pytest.raises(WebSocketDisconnect) as missing:
            with client.websocket_connect(path, subprotocols=["nxl.v1"]):
                pass
        assert missing.value.code == 4401
        with pytest.raises(WebSocketDisconnect) as wrong_protocol:
            with client.websocket_connect(
                    path, headers={"Authorization": f"Bearer {ticket}"},
                    subprotocols=["unrelated"]):
                pass
        assert wrong_protocol.value.code == 4406
        with pytest.raises(WebSocketDisconnect) as wrong_origin:
            with client.websocket_connect(
                    path, headers={"Authorization": f"Bearer {ticket}",
                                   "Origin": "https://unrelated.example"},
                    subprotocols=["nxl.v1"]):
                pass
        assert wrong_origin.value.code == 4406
        with pytest.raises(WebSocketDisconnect) as wrong_target:
            with client.websocket_connect(
                    "wss://127.0.0.1:8202/v1/runtime/executors/other/link",
                    headers={"Authorization": f"Bearer {ticket}"},
                    subprotocols=["nxl.v1"]):
                pass
        assert wrong_target.value.code == 4401
        with pytest.raises(WebSocketDisconnect) as no_revision:
            with client.websocket_connect(
                    path, headers={"Authorization": f"Bearer {ticket}"},
                    subprotocols=["nxl.v1"]):
                pass
        assert no_revision.value.code == 4406
        with factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute(
                "SELECT generation,control_state FROM execution_executors "
                "WHERE executor_id=?", (registration.executor_id,),
            ).fetchone()
            assert tuple(row) == (1, "DISCONNECTED")
        info = executor_link.protocol_info()
        monkeypatch.setattr(executor_link, "protocol_info", lambda: {
            **info, "remote_execution_ready": True,
            "nxl_accepted": [R4_PREVIEW_REVISION],
        })
        hello = {
            "protocol_major": 1, "contract_revision": R4_PREVIEW_REVISION,
            "type": "hello", "link_attempt_id": "attempt",
            "server_id": installation.server_id,
            "executor_id": registration.executor_id,
            "core_version": CORE_VERSION,
            "management_revision": info["management_revision"],
            "supported_nxl": [R4_PREVIEW_REVISION],
            "snapshot_formats": [info["executor_snapshot_format"]],
            "control_capabilities": [],
        }
        with client.websocket_connect(
                path, headers={"Authorization": f"Bearer {ticket}"},
                subprotocols=["nxl.v1"]) as ws:
            ws.send_text(json.dumps({
                **hello, "management_revision": "obsolete",
            }))
            with pytest.raises(WebSocketDisconnect) as obsolete:
                ws.receive_text()
            assert obsolete.value.code == 4406
        with client.websocket_connect(
                path, headers={"Authorization": f"Bearer {ticket}"},
                subprotocols=["nxl.v1"]) as ws:
            ws.send_text(encode_r4_frame(hello).decode("utf-8"))
            welcome = ws.receive_json()
            assert welcome["type"] == "welcome"
            assert welcome["connection_generation"] == 2
            assert welcome["control_capabilities"] == []
            with factory.unit_of_work(write=False) as uow:
                row = uow.connection.execute(
                    "SELECT generation,control_state,owner_instance_id "
                    "FROM execution_executors WHERE executor_id=?",
                    (registration.executor_id,),
                ).fetchone()
                assert row["generation"] == 2
                assert row["control_state"] == "RECOVERING"
                assert row["owner_instance_id"] == welcome["connection_id"]
            heartbeat = {
                "protocol_major": 1, "contract_revision": R4_PREVIEW_REVISION,
                "type": "heartbeat", "server_id": installation.server_id,
                "executor_id": registration.executor_id,
                "connection_id": welcome["connection_id"],
                "connection_generation": welcome["connection_generation"],
            }
            ws.send_text(encode_r4_frame(heartbeat).decode("utf-8"))
            ws.send_text("{}")
            with pytest.raises(WebSocketDisconnect) as invalid:
                ws.receive_text()
            assert invalid.value.code == 4406
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT generation,control_state,owner_instance_id "
            "FROM execution_executors WHERE executor_id=?",
            (registration.executor_id,),
        ).fetchone()
        assert tuple(row) == (2, "DISCONNECTED", None)
