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



@pytest.fixture
def admitted(tmp_path):
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
                     "operation_id,dispatch_state,attempt_token,attempt_no,"
                     "reservation_class,reserved_bytes,reserved_at) "
                     "VALUES (?,?,?,'SENDING','attempt',1,'regular',100,?)",
                     (server_id, executor_id, "op", now))
    return factory, app, principal, first, agent_key, foreign_key


@pytest.mark.parametrize("code,expected", [
    ("PROVIDER_AUTH_REQUIRED", "Complete provider sign-in locally"),
    ("AGENT_AUTH_REQUIRED", "protected authentication references"),
    ("BINARY_NOT_FOUND", "Restore the approved installation"),
    ("NATIVE_VERSION_UNQUALIFIED", "Select a qualified build"),
    ("NEEDS_REDISCOVERY", "Rediscover the installation"),
    ("PROFILE_DRIFT", "Verify the installation, workspace and provider home"),
    ("UNKNOWN_EXECUTOR_FAILURE", "reconcile its outcome"),
])
@pytest.mark.parametrize("possible_effect", [False, True])
def test_scoped_operation_error_guides_local_recovery(admitted, code, expected, possible_effect):
    from jsonschema import Draft202012Validator
    import json
    from pathlib import Path
    factory, app, principal, first, key, foreign = admitted
    receipt = {**first, "stage": "FAILED", "error_code": code,
               "possible_effect": possible_effect, "retry_safe": not possible_effect}
    append_execution_receipt(factory, principal=principal, frame=receipt)
    with TestClient(app, raise_server_exceptions=False) as client:
        route = "/v1/runtime/operations/op"
        assert client.get(route).status_code == 401
        assert client.get(route, headers={"Authorization": "Bearer " + foreign}).status_code == 404
        response = client.get(route, headers={"Authorization": "Bearer " + key})
        assert response.status_code == 200, response.text
        view = response.json()
    error = view["error"]
    assert error["code"] == code and error["operation_id"] == "op"
    assert error["possible_effect"] is possible_effect
    assert error["retry_safe"] is (not possible_effect)
    assert principal.executor_id in error["action"] and "'binding'" in error["action"]
    assert expected in error["action"]
    if possible_effect:
        assert error["action"].startswith("Query this operation and reconcile")
    contract = json.loads((Path(__file__).resolve().parents[2] / "plans/contratos/http-target.schema.json").read_text())
    Draft202012Validator(contract["$defs"]["ErrorBody"]).validate(error)
    assert key not in json.dumps(view) and foreign not in json.dumps(view)
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_receipts").fetchone()[0] == 1
