"""Optional two-application HTTP inventory and receipt conformance.

Set OKTO_CONNECTOR_SRC to the Connector's src directory. This exercises the
real Nexus ASGI router and Connector HTTP client against the same Core wheel;
it is a contract test, not provider or two-host evidence.
"""

from __future__ import annotations

import os
import asyncio
from pathlib import Path

import httpx
import pytest
from nexus_connector_core import R4_PREVIEW_REVISION

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap


def test_connector_publishes_core_snapshot_to_nexus(tmp_path, monkeypatch):
    source = os.environ.get("OKTO_CONNECTOR_SRC")
    if not source or not Path(source).is_dir():
        pytest.skip("Set OKTO_CONNECTOR_SRC for the cross-repo contract run")
    monkeypatch.syspath_prepend(source)
    from okto_nexus_connector.services.discovery_service import (
        executor_inventory_snapshot,
    )
    from okto_nexus_connector.transport.https_client import NexusHTTPClient

    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
            ("agent-a", "2026-09-29T00:00:00Z"),
        )
    with deps.connection_factory.unit_of_work() as uow:
        key = app.state.auth.issue_key(uow, agent_id="agent-a")
    async def roundtrip():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport) as raw:
            async with NexusHTTPClient("http://127.0.0.1:8202", client=raw) as http:
                me = await http.me(key)
                assert me.agent_id == "agent-a"
                registered = await http.register_executor(
                    key, client_intent_id="register-a", connector_id="connector-a",
                    label="Remote host",
                )
                assert registered.server_id == me.server_id
                snapshot = executor_inventory_snapshot(
                    [], server_id=registered.server_id,
                    executor_id=registered.executor_id,
                    producer_instance_id="connector-process-a",
                    publication_sequence=1,
                )
                accepted = await http.publish_inventory(
                    registered.bootstrap_ticket,
                    executor_id=registered.executor_id, snapshot=snapshot,
                )
                assert accepted.inventory_revision == snapshot["inventory_revision"]
                with deps.connection_factory.unit_of_work() as uow:
                    conn = uow.connection
                    now = "2026-09-29T00:00:00Z"
                    conn.execute(
                        "INSERT INTO workspaces(workspace_id,created_at) VALUES ('ws',?)",
                        (now,),
                    )
                    conn.execute(
                        "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
                        "adapter_id,protocol,enabled,created_at,updated_at) "
                        "VALUES ('endpoint','agent-a','ws','codex','native',0,?,?)",
                        (now, now),
                    )
                    conn.execute(
                        "INSERT INTO execution_workspace_bindings(server_id,"
                        "workspace_binding_id,executor_id,workspace_id,realization_handle,"
                        "revision,status) VALUES (?,?,?,?,?,1,'READY')",
                        (me.server_id, "workspace-binding", registered.executor_id,
                         "ws", "root_1234567890123456"),
                    )
                    conn.execute(
                        "INSERT INTO execution_bindings(server_id,binding_id,executor_id,"
                        "endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,"
                        "realization_ref,realization_revision,binding_revision) "
                        "VALUES (?,?,?,?,?,?,?,?,1,1)",
                        (me.server_id, "binding", registered.executor_id,
                         "endpoint", "workspace-binding", "candidate",
                         snapshot["inventory_revision"], "realization"),
                    )
                    conn.execute(
                        "INSERT INTO execution_operations(server_id,executor_id,operation_id,"
                        "subject_agent_id,actor_agent_id,binding_id,workspace_id,"
                        "workspace_binding_id,session_id,action,intent_hash,semantic_payload,"
                        "expected_revisions_json,admission_state,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (me.server_id, registered.executor_id, "op", "agent-a",
                         "agent-a", "binding", "ws", "workspace-binding",
                         "session", "runtime.open", "sha256:" + "a" * 64,
                         "{}", "{}", "ACCEPTED", now),
                    )
                ticket = await http.request_r4_binding_ticket(
                    key, binding_id="binding", client_intent_id="ticket-intent",
                    credential_request_id="ticket-request",
                    scopes=("receipt:publish",),
                )
                receipt = {
                    "protocol_major": 1,
                    "contract_revision": R4_PREVIEW_REVISION,
                    "type": "operation.receipt", "server_id": me.server_id,
                    "executor_id": registered.executor_id,
                    "binding_id": "binding", "agent_id": "agent-a",
                    "session_id": "session", "connection_id": "control",
                    "connection_generation": 1, "operation_id": "op",
                    "intent_hash": "sha256:" + "a" * 64,
                    "receipt_revision": 1, "stage": "RECEIVED_DURABLE",
                    "possible_effect": False, "retry_safe": True,
                }
                receipt_ack = await http.publish_operation_receipt(
                    ticket.ticket, frame=receipt)
                assert receipt_ack.operation_id == "op"
                return registered, snapshot

    registered, snapshot = asyncio.run(roundtrip())
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT publication_sequence,inventory_revision FROM "
            "execution_inventory_current WHERE server_id=? AND executor_id=?",
            (registered.server_id, registered.executor_id),
        ).fetchone()
    assert tuple(row) == (1, snapshot["inventory_revision"])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        receipt = uow.connection.execute(
            "SELECT stage FROM execution_receipts WHERE server_id=? AND executor_id=? "
            "AND operation_id='op' AND receipt_revision=1",
            (registered.server_id, registered.executor_id),
        ).fetchone()
    assert receipt["stage"] == "RECEIVED_DURABLE"
