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
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import (
    current_agent_revisions,
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
            assert ws.receive_json()["type"] == "reconcile.request"
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


def test_ns08_02(tmp_path, monkeypatch):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    factory = deps.connection_factory
    installation = ensure_execution_installation(factory)
    stamp = "2026-09-29T00:00:00Z"
    with factory.unit_of_work() as uow:
        for agent in ("registrar", "agent-a", "agent-b"):
            uow.connection.execute(
                "INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
                (agent, stamp),
            )
            app.state.auth.issue_key(uow, agent_id=agent)
        uow.connection.execute(
            "INSERT INTO workspaces(workspace_id,created_at) VALUES ('ws',?)",
            (stamp,),
        )
        for agent in ("agent-a", "agent-b"):
            uow.connection.execute(
                "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
                "adapter_id,protocol,enabled,created_at,updated_at) "
                "VALUES (?,?,'ws','codex','native',0,?,?)",
                ("ep-" + agent, agent, stamp, stamp),
            )
    executor_id = register_remote_executor(
        factory, actor_agent_id="registrar", connector_id="connector",
        client_intent_id="register",
    ).executor_id
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO execution_workspace_bindings(server_id,"
            "workspace_binding_id,executor_id,workspace_id,realization_handle,"
            "revision,status) VALUES (?,?,?,?,?,1,'READY')",
            (installation.server_id, "workspace-binding", executor_id,
             "ws", "root_1234567890123456"),
        )
        for agent in ("agent-a", "agent-b"):
            uow.connection.execute(
                "INSERT INTO execution_bindings(server_id,binding_id,"
                "executor_id,endpoint_id,workspace_binding_id,candidate_ref,"
                "inventory_revision,realization_ref,realization_revision,"
                "binding_revision) VALUES (?,?,?,?,?,?,?,?,1,1)",
                (installation.server_id, "binding-" + agent, executor_id,
                 "ep-" + agent, "workspace-binding", "candidate",
                 "sha256:" + "a" * 64, "realization"),
            )
    bootstrap_ticket = issue_execution_ticket(
        factory, server_id=installation.server_id, executor_id=executor_id,
        agent_id="registrar", binding_id=None,
    ).ticket
    tickets = {}
    revisions = {}
    for agent in ("agent-a", "agent-b"):
        tickets[agent] = issue_execution_ticket(
            factory, server_id=installation.server_id,
            executor_id=executor_id, agent_id=agent,
            binding_id="binding-" + agent,
            scopes=frozenset({"lane:attach"}),
        )
        _, revisions[agent], _ = current_agent_revisions(
            factory, agent_id=agent)
    info = executor_link.protocol_info()
    monkeypatch.setattr(executor_link, "protocol_info", lambda: {
        **info, "remote_execution_ready": True,
        "nxl_accepted": [R4_PREVIEW_REVISION],
    })
    base = {"protocol_major": 1, "contract_revision": R4_PREVIEW_REVISION}
    path = f"wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link"
    hello = {
        **base, "type": "hello", "link_attempt_id": "attempt",
        "server_id": installation.server_id, "executor_id": executor_id,
        "core_version": CORE_VERSION,
        "management_revision": info["management_revision"],
        "supported_nxl": [R4_PREVIEW_REVISION],
        "snapshot_formats": [info["executor_snapshot_format"]],
        "control_capabilities": [],
    }
    with TestClient(app, base_url="https://127.0.0.1:8202") as client:
        with client.websocket_connect(
                path, headers={"Authorization": f"Bearer {bootstrap_ticket}"},
                subprotocols=["nxl.v1"]) as ws:
            ws.send_text(encode_r4_frame(hello).decode("utf-8"))
            welcome = ws.receive_json()
            assert ws.receive_json()["type"] == "reconcile.request"

            def attach(agent, ticket, request):
                revision = revisions[agent]
                frame = {
                    **base, "type": "binding.attach",
                    "attach_request_id": request,
                    "server_id": installation.server_id,
                    "executor_id": executor_id,
                    "binding_id": "binding-" + agent,
                    "agent_id": agent,
                    "connection_id": welcome["connection_id"],
                    "expected_connection_generation":
                    welcome["connection_generation"],
                    "credential_epoch": revision.credential_epoch,
                    "authorization_revision": revision.authorization,
                    "configuration_revision": revision.configuration,
                    "ticket": ticket,
                }
                ws.send_text(encode_r4_frame(frame).decode("utf-8"))
                return ws.receive_json()

            assert attach("agent-a", tickets["agent-b"].ticket,
                          "crossed")["code"] == "ATTACH_DENIED"
            assert attach("agent-b", tickets["agent-b"].ticket,
                          "b-first")["type"] == "binding.attached"
            assert attach("agent-a", tickets["agent-a"].ticket,
                          "a-first")["type"] == "binding.attached"
            with factory.unit_of_work() as uow:
                uow.connection.execute(
                    "UPDATE execution_link_tickets SET revoked_at=? "
                    "WHERE ticket_id=?",
                    (stamp, tickets["agent-a"].ticket_id),
                )
            assert attach("agent-a", tickets["agent-a"].ticket,
                          "a-old")["code"] == "ATTACH_DENIED"
            with factory.unit_of_work(write=False) as uow:
                lanes = uow.connection.execute(
                    "SELECT binding_id,state FROM execution_control_lanes "
                    "ORDER BY binding_id",
                ).fetchall()
                assert [tuple(row) for row in lanes] == [
                    ("binding-agent-a", "DISCONNECTED"),
                    ("binding-agent-b", "ADMITTED")]
            replacement = issue_execution_ticket(
                factory, server_id=installation.server_id,
                executor_id=executor_id, agent_id="agent-a",
                binding_id="binding-agent-a",
                scopes=frozenset({"lane:attach"}),
            )
            attached = attach("agent-a", replacement.ticket, "a-new")
            assert attached["type"] == "binding.attached"
            assert attached["attach_request_id"] == "a-new"
            assert attached["connection_generation"] == (
                welcome["connection_generation"])
            with factory.unit_of_work() as uow:
                uow.connection.execute(
                    "UPDATE agent_endpoints SET revision=revision+1 "
                    "WHERE endpoint_id='ep-agent-a'",
                )
            current_agent_revisions(factory, agent_id="agent-a")
            with factory.unit_of_work(write=False) as uow:
                lanes = uow.connection.execute(
                    "SELECT binding_id,state FROM execution_control_lanes "
                    "ORDER BY binding_id",
                ).fetchall()
                assert [tuple(row) for row in lanes] == [
                    ("binding-agent-a", "DISCONNECTED"),
                    ("binding-agent-b", "ADMITTED")]
    with factory.unit_of_work(write=False) as uow:
        lanes = uow.connection.execute(
            "SELECT state FROM execution_control_lanes ORDER BY binding_id",
        ).fetchall()
        assert [row["state"] for row in lanes] == [
            "DISCONNECTED", "DISCONNECTED"]


def test_ns08_03(tmp_path, monkeypatch):
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
    info = executor_link.protocol_info()
    monkeypatch.setattr(executor_link, "protocol_info", lambda: {
        **info, "remote_execution_ready": True,
        "nxl_accepted": [R4_PREVIEW_REVISION],
    })
    base = {"protocol_major": 1, "contract_revision": R4_PREVIEW_REVISION,
            "server_id": installation.server_id,
            "executor_id": registration.executor_id}
    path = ("wss://127.0.0.1:8202/v1/runtime/executors/"
            f"{registration.executor_id}/link")
    with TestClient(app, base_url="https://127.0.0.1:8202") as client:
        with client.websocket_connect(
                path, headers={"Authorization": f"Bearer {ticket}"},
                subprotocols=["nxl.v1"]) as ws:
            hello = {
                **base, "type": "hello", "link_attempt_id": "attempt",
                "core_version": CORE_VERSION,
                "management_revision": info["management_revision"],
                "supported_nxl": [R4_PREVIEW_REVISION],
                "snapshot_formats": [info["executor_snapshot_format"]],
                "control_capabilities": [],
            }
            ws.send_text(encode_r4_frame(hello).decode("utf-8"))
            welcome = ws.receive_json()
            first = ws.receive_json()
            assert first["type"] == "reconcile.request"
            scope = {
                **base, "connection_id": welcome["connection_id"],
                "connection_generation": welcome["connection_generation"],
            }
            unavailable = {
                **scope, "type": "error", "code": "JOURNAL_UNAVAILABLE",
                "stage": "reconcile.report", "possible_effect": False,
                "retry_safe": True,
            }
            ws.send_text(encode_r4_frame(unavailable).decode("utf-8"))
            with factory.unit_of_work(write=False) as uow:
                state = uow.connection.execute(
                    "SELECT control_state FROM execution_executors "
                    "WHERE executor_id=?", (registration.executor_id,),
                ).fetchone()[0]
                assert state == "RECOVERING"
            ws.send_text(encode_r4_frame({
                **scope, "type": "heartbeat",
            }).decode("utf-8"))
            retry = ws.receive_json()
            assert retry["type"] == "reconcile.request"
            assert retry["reconcile_id"] != first["reconcile_id"]
            report = {
                **scope, "type": "reconcile.report",
                "reconcile_id": retry["reconcile_id"],
                "cursor": retry["cursor"], "next_cursor": None,
                "complete": True, "receipts": [], "claims": [],
                "stream_watermarks": [], "ownership_facts": [],
            }
            ws.send_text(encode_r4_frame(report).decode("utf-8"))
            accepted = ws.receive_json()
            assert accepted["type"] == "reconcile.accepted"
            assert accepted["recovery_remaining"] is False
            assert accepted["ready_lane_ids"] == []
            with factory.unit_of_work(write=False) as uow:
                state = uow.connection.execute(
                    "SELECT control_state FROM execution_executors "
                    "WHERE executor_id=?", (registration.executor_id,),
                ).fetchone()[0]
                assert state == "CONTROL_READY"
