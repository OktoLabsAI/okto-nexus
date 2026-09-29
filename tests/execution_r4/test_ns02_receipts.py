"""R4 receipts are durable facts only for an existing admitted operation."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from nexus_connector_core import R4_PREVIEW_REVISION

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.sqlite.execution_identity import (
    ensure_execution_installation, register_remote_executor,
)
from okto_nexus.adapters.outbound.sqlite.execution_receipts import (
    append_execution_receipt, read_execution_operation_history,
)
from okto_nexus.adapters.outbound.sqlite.execution_tickets import (
    VerifiedExecutionTicket, issue_execution_ticket,
)
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.errors import OktoNexusError


def _receipt(server_id: str, executor_id: str, **changes) -> dict:
    value = {
        "protocol_major": 1, "contract_revision": R4_PREVIEW_REVISION,
        "type": "operation.receipt", "server_id": server_id,
        "executor_id": executor_id, "binding_id": "binding",
        "agent_id": "agent", "session_id": "session",
        "connection_id": "control", "connection_generation": 1,
        "operation_id": "op", "intent_hash": "sha256:" + "a" * 64,
        "receipt_revision": 1, "stage": "RECEIVED_DURABLE",
        "possible_effect": False, "retry_safe": True,
    }
    value.update(changes)
    return value


def test_ns02_05_receipt_ingress_requires_admission_and_preserves_provenance(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    factory = deps.connection_factory
    installation = ensure_execution_installation(factory)
    server_id = installation.server_id
    app = build_app(deps)
    with factory.unit_of_work() as uow:
        conn = uow.connection
        now = "2026-09-29T00:00:00Z"
        conn.execute("INSERT INTO agents(agent_id,created_at) VALUES ('agent',?)", (now,))
        conn.execute("INSERT INTO agents(agent_id,created_at) VALUES ('foreign',?)", (now,))
        conn.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES ('ws',?)", (now,))
        conn.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
                     "adapter_id,protocol,enabled,created_at,updated_at) "
                     "VALUES ('endpoint','agent','ws','codex','native',0,?,?)",
                     (now, now))
        agent_key = app.state.auth.issue_key(uow, agent_id="agent")
        foreign_key = app.state.auth.issue_key(uow, agent_id="foreign")
    executor_id = register_remote_executor(
        factory, actor_agent_id="agent", connector_id="connector",
        client_intent_id="register",
    ).executor_id
    principal = VerifiedExecutionTicket(
        "ticket", server_id, executor_id, "binding", "agent",
        frozenset({"receipt:publish"}), 1, 1,
    )
    first = _receipt(server_id, executor_id)
    with pytest.raises(OktoNexusError):
        append_execution_receipt(factory, principal=principal, frame=first)
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("INSERT INTO execution_workspace_bindings(server_id,"
                     "workspace_binding_id,executor_id,workspace_id,realization_handle,"
                     "revision,status) VALUES (?,?,?,?,?,1,'READY')",
                     (server_id, "workspace-binding", executor_id, "ws", "root_1234567890123456"))
        conn.execute("INSERT INTO execution_bindings(server_id,binding_id,executor_id,"
                     "endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,"
                     "realization_ref,realization_revision,binding_revision) "
                     "VALUES (?,?,?,?,?,?,?,?,1,1)",
                     (server_id, "binding", executor_id, "endpoint", "workspace-binding",
                      "candidate", "sha256:" + "b" * 64, "realization"))
        conn.execute("INSERT INTO execution_operations(server_id,executor_id,operation_id,"
                     "subject_agent_id,actor_agent_id,binding_id,workspace_id,"
                     "workspace_binding_id,session_id,action,intent_hash,semantic_payload,"
                     "expected_revisions_json,admission_state,created_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (server_id, executor_id, "op", "agent", "agent", "binding", "ws",
                      "workspace-binding", "session", "runtime.open", first["intent_hash"],
                      "{}", "{}", "ACCEPTED", now))
        conn.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,"
                     "operation_id,dispatch_state) VALUES (?,?,?,'PENDING')",
                     (server_id, executor_id, "op"))
    admitted_view = read_execution_operation_history(
        factory, server_id=server_id, executor_id=None,
        operation_id="op", subject_agent_id="agent",
    ).public_view()
    assert admitted_view["admission_state"] == "ACCEPTED"
    assert admitted_view["executor_stage"] is None
    assert admitted_view["possible_effect"] is False
    assert append_execution_receipt(factory, principal=principal, frame=first).reused is False
    assert append_execution_receipt(factory, principal=principal, frame=first).reused is True
    with pytest.raises(OktoNexusError):
        append_execution_receipt(factory, principal=principal,
                                 frame={**first, "stage": "RUNNING"})
    with pytest.raises(OktoNexusError):
        append_execution_receipt(factory, principal=principal,
                                 frame={**first, "receipt_revision": 2,
                                        "agent_id": "foreign"})
    with pytest.raises(OktoNexusError):
        append_execution_receipt(factory, principal=replace(principal,
                                 scopes=frozenset()), frame=first)
    second = {**first, "receipt_revision": 2, "stage": "RUNNING",
              "possible_effect": True, "retry_safe": False}
    issued = issue_execution_ticket(
        factory, server_id=server_id, executor_id=executor_id, agent_id="agent",
        binding_id="binding", scopes=frozenset({"receipt:publish"}),
    )
    history_ticket = issue_execution_ticket(
        factory, server_id=server_id, executor_id=executor_id, agent_id="agent",
        binding_id="binding", scopes=frozenset({"history:read"}),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        path = "/v1/runtime/operations/op/receipts"
        assert client.get("/v1/runtime/operations/op").status_code == 401
        foreign_view = client.get(
            "/v1/runtime/operations/op",
            headers={"Authorization": f"Bearer {foreign_key}"})
        assert foreign_view.status_code == 404
        out_of_scope = client.get(
            "/v1/runtime/operations/op",
            headers={"Authorization": f"Bearer {issued.ticket}"})
        assert out_of_scope.status_code == 403
        assert client.post(path, json=second).status_code == 401
        response = client.post(path, json=second,
                               headers={"Authorization": f"Bearer {issued.ticket}"})
        assert response.status_code == 200, response.text
        assert response.json() == {"operation_id": "op", "receipt_revision": 2,
                                   "stage": "RUNNING", "accepted": True,
                                   "reused": False}
        view_response = client.get(
            "/v1/runtime/operations/op",
            headers={"Authorization": f"Bearer {agent_key}"})
        assert view_response.status_code == 200, view_response.text
        view = view_response.json()
        assert view["executor_stage"] == "RUNNING"
        assert view["receipt_revision"] == 2
        assert view["possible_effect"] is True
        assert view["retry_safe"] is False
        assert view["scope"]["agent_id"] == "agent"
        assert view["client_intent_id"] is None  # Legacy seeded operation.
        ticket_view = client.get(
            "/v1/runtime/operations/op",
            headers={"Authorization": f"Bearer {history_ticket.ticket}"})
        assert ticket_view.status_code == 200, ticket_view.text
        assert ticket_view.json() == view
    assert append_execution_receipt(factory, principal=principal,
                                    frame=second).reused is True
    with factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute(
            "SELECT receipt_revision,source_connection_id,"
            "source_connection_generation,frame_digest,canonical_frame "
            "FROM execution_receipts ORDER BY receipt_revision").fetchall()
        outbox = uow.connection.execute(
            "SELECT last_receipt_revision FROM execution_dispatch_outbox").fetchone()
    assert len(rows) == 2 and outbox[0] == 2
    assert rows[1]["source_connection_id"] == "control"
    assert rows[1]["source_connection_generation"] == 1
    assert rows[1]["frame_digest"].startswith("sha256:")
    assert '"stage":"RUNNING"' in rows[1]["canonical_frame"]
    restored = bootstrap({}, ["--home", str(tmp_path / "home")])
    history = read_execution_operation_history(
        restored.connection_factory, server_id=server_id,
        executor_id=executor_id, operation_id="op", subject_agent_id="agent",
    )
    assert [item["stage"] for item in history.receipts] == [
        "RECEIVED_DURABLE", "RUNNING"]
    assert history.public_view()["executor_stage"] == "RUNNING"
    with pytest.raises(OktoNexusError):
        read_execution_operation_history(
            restored.connection_factory, server_id=server_id,
            executor_id=executor_id, operation_id="op",
            subject_agent_id="foreign",
        )
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_receipts SET canonical_frame='{}' "
            "WHERE server_id=? AND executor_id=? AND operation_id=? "
            "AND receipt_revision=2", (server_id, executor_id, "op"),
        )
    with pytest.raises(OktoNexusError):
        read_execution_operation_history(
            restored.connection_factory, server_id=server_id,
            executor_id=executor_id, operation_id="op", subject_agent_id="agent",
        )
