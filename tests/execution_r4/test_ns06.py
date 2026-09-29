"""R4 resolve is a recoverable intent, not an operation admission."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.sqlite.execution_identity import (
    ensure_execution_installation,
)
from okto_nexus.bootstrap.dependencies import bootstrap


def test_ns06_01(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    installation = ensure_execution_installation(deps.connection_factory)
    candidate_ref = "nexus-install-v1:" + "a" * 64
    inventory_revision = "sha256:" + "b" * 64
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        now = "2026-09-29T00:00:00Z"
        for agent_id in ("agent-a", "agent-b"):
            conn.execute("INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
                         (agent_id, now))
        conn.execute("INSERT INTO workspaces(workspace_id,created_at) "
                     "VALUES ('ws',?)", (now,))
        conn.execute(
            "INSERT INTO execution_executors(server_id,executor_id,connector_id,"
            "registered_by_agent_id,kind,control_state,generation) "
            "VALUES (?,?,'connector','agent-a','remote','DISCONNECTED',1)",
            (installation.server_id, "exe_remote"),
        )
        conn.execute(
            "INSERT INTO execution_workspace_bindings(server_id,workspace_binding_id,"
            "executor_id,workspace_id,realization_handle,revision,status) "
            "VALUES (?,'wxb','exe_remote','ws','root_1234567890123456',2,'READY')",
            (installation.server_id,),
        )
        conn.execute(
            "INSERT INTO execution_realizations(server_id,executor_id,"
            "realization_ref,local_realization_ref,subject_agent_id,"
            "workspace_binding_id,candidate_ref,inventory_revision,"
            "configuration_digest,local_root_proof_digest,revision,status) "
            "VALUES (?,'exe_remote','real','root_1234567890123456',"
            "'agent-a','wxb',?,?,?, ?,1,'READY')",
            (installation.server_id, candidate_ref, inventory_revision,
             "sha256:" + "c" * 64, "sha256:" + "d" * 64),
        )
        conn.execute(
            "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
            "adapter_id,protocol,enabled,created_at,updated_at) "
            "VALUES ('ep','agent-a','ws','codex_app_server','nxl-r4',0,?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO execution_bindings(server_id,binding_id,executor_id,"
            "endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,"
            "realization_ref,realization_revision,binding_revision) "
            "VALUES (?,'binding','exe_remote','ep','wxb',?,?, 'real',1,1)",
            (installation.server_id, candidate_ref, inventory_revision),
        )
    with deps.connection_factory.unit_of_work() as uow:
        key_a = app.state.auth.issue_key(uow, agent_id="agent-a")
        key_b = app.state.auth.issue_key(uow, agent_id="agent-b")
    body = {
        "client_intent_id": "start-one", "intent": "runtime.start",
        "binding_id": "binding", "workspace_binding_id": "wxb",
        "new_session": True,
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        route = "/v1/runtime/intents:resolve"
        created = client.post(route, json=body, headers={
            "Authorization": f"Bearer {key_a}"})
        assert created.status_code == 200, created.text
        resolution = created.json()
        contract = json.loads((Path(__file__).resolve().parents[2] /
                               "plans/contratos/http-target.schema.json").read_text(
                                   encoding="utf-8"))
        Draft202012Validator({"$defs": contract["$defs"],
                              **contract["$defs"]["IntentResolution"]}).validate(
                                  resolution)
        assert resolution["scope"]["binding_id"] == "binding"
        assert resolution["semantic_intent"]["action"] == "runtime.open"
        assert resolution["can_submit"] is False
        assert "remote_execution_unavailable" in resolution["blockers"]
        assert client.post(route, json=body, headers={
            "Authorization": f"Bearer {key_a}"}).json() == resolution
        assert client.post(route, json={**body, "binding_id": "different"},
                           headers={"Authorization": f"Bearer {key_a}"}).status_code == 409
        queried = client.get("/v1/runtime/intents/start-one", headers={
            "Authorization": f"Bearer {key_a}"})
        assert queried.status_code == 200
        assert queried.json() == {"resolution": resolution, "operation": None}
        assert client.get("/v1/runtime/intents/start-one", headers={
            "Authorization": f"Bearer {key_b}"}).status_code == 404
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute("SELECT COUNT(*) FROM execution_client_intents "
                            "WHERE client_intent_id='start-one'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
