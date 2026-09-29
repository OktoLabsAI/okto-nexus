"""R4 resolve is a recoverable intent, not an operation admission."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.sqlite.execution_identity import (
    ensure_execution_installation,
)
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.application.execution_admission import submit_execution_operation
from okto_nexus.application.execution_intents import (
    read_execution_intent, resolve_execution_intent,
)


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
        refused = client.post("/v1/runtime/operations", json={
            "client_intent_id": body["client_intent_id"],
            "operation_id": resolution["operation_id"],
            "resolution_revision": resolution["resolution_revision"],
            "intent_hash": resolution["intent_hash"],
        }, headers={"Authorization": f"Bearer {key_a}"})
        assert refused.status_code == 409, refused.text
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


def test_ns06_02_atomic_admission_and_replay_with_synthetic_qualification(tmp_path):
    """The real protocol gate stays closed; this tests the isolated T2 writer."""
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    factory = deps.connection_factory
    server_id = ensure_execution_installation(factory).server_id
    now = "2026-09-29T00:00:00Z"
    candidate = "nexus-install-v1:" + "a" * 64
    inventory = "sha256:" + "b" * 64
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("INSERT INTO agents(agent_id,created_at) VALUES ('agent-a',?)",
                     (now,))
        conn.execute("INSERT INTO workspaces(workspace_id,created_at) "
                     "VALUES ('ws',?)", (now,))
        conn.execute(
            "INSERT INTO runtime_profiles(profile_id,adapter_id,config,enabled,"
            "created_at,updated_at) VALUES ('profile','codex_app_server','{}',1,?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO execution_executors(server_id,executor_id,connector_id,"
            "registered_by_agent_id,kind,control_state,generation) "
            "VALUES (?,'executor','connector','agent-a','remote','CONTROL_READY',1)",
            (server_id,),
        )
        conn.execute(
            "INSERT INTO execution_workspace_bindings(server_id,workspace_binding_id,"
            "executor_id,workspace_id,realization_handle,revision,status) "
            "VALUES (?,'wxb','executor','ws','local-root',1,'READY')",
            (server_id,),
        )
        conn.execute(
            "INSERT INTO execution_realizations(server_id,executor_id,"
            "realization_ref,local_realization_ref,subject_agent_id,"
            "workspace_binding_id,candidate_ref,inventory_revision,"
            "configuration_digest,local_root_proof_digest,revision,status) "
            "VALUES (?,'executor','real','local-root','agent-a','wxb',"
            "?,?,'sha256:1','sha256:2',1,'READY')",
            (server_id, candidate, inventory),
        )
        conn.execute(
            "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
            "adapter_id,protocol,profile_id,enabled,created_at,updated_at) "
            "VALUES ('ep','agent-a','ws','codex_app_server','nxl-r4',"
            "'profile',0,?,?)", (now, now),
        )
        conn.execute(
            "INSERT INTO execution_bindings(server_id,binding_id,executor_id,"
            "endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,"
            "realization_ref,realization_revision,binding_revision) "
            "VALUES (?,'binding','executor','ep','wxb',?,?,'real',1,1)",
            (server_id, candidate, inventory),
        )
        conn.execute(
            "INSERT INTO execution_inventory_snapshots(server_id,executor_id,"
            "publication_sequence,inventory_revision,catalog_format,"
            "availability_format,snapshot_format,core_version,canonical_projection,"
            "received_at,observation_age_ms,producer_instance_id) "
            "VALUES (?,'executor',1,?,1,1,1,'synthetic',?,?,0,'fixture')",
            (server_id, inventory, json.dumps({"evidence": [{
                "adapter_id": "codex_app_server", "candidate_ref": candidate}]}), now),
        )
        conn.execute(
            "INSERT INTO execution_inventory_current(server_id,executor_id,"
            "publication_sequence,inventory_revision) "
            "VALUES (?,'executor',1,?)", (server_id, inventory),
        )
    resolution = resolve_execution_intent(
        factory, actor_agent_id="agent-a", request={
            "client_intent_id": "start", "intent": "runtime.start",
            "binding_id": "binding", "workspace_binding_id": "wxb",
            "new_session": True,
        })
    assert resolution["blockers"] == ["remote_execution_unavailable"]
    # The fixture qualifies only this private writer call; the HTTP protocol
    # remains non-executable and never promotes this preview resolution.
    resolution["blockers"] = []
    resolution["can_submit"] = True
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_client_intents SET resolved_json=? "
            "WHERE client_intent_id='start'", (json.dumps(resolution),),
        )
    request = {key: resolution[key] for key in (
        "client_intent_id", "operation_id", "resolution_revision", "intent_hash")}
    freshness = {(server_id, "executor"): (1, time.monotonic(), 0)}
    # Interrupt the same transaction at its final write.
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "CREATE TRIGGER fail_r4_outbox_persistent BEFORE INSERT ON "
            "execution_dispatch_outbox BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
    try:
        with pytest.raises(Exception, match="synthetic failure"):
            submit_execution_operation(
                factory, actor_agent_id="agent-a", request=request,
                fresh_publications=freshness, remote_ready=True)
    finally:
        with factory.unit_of_work() as uow:
            uow.connection.execute("DROP TRIGGER fail_r4_outbox_persistent")
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
    first, reused = submit_execution_operation(
        factory, actor_agent_id="agent-a", request=request,
        fresh_publications=freshness, remote_ready=True)
    second, replay = submit_execution_operation(
        factory, actor_agent_id="agent-a", request=request,
        fresh_publications={}, remote_ready=False)
    assert not reused and replay and first == second
    assert first["admission_state"] == "ACCEPTED"
    assert first["receipt_revision"] == 0
    assert read_execution_intent(
        factory, actor_agent_id="agent-a", client_intent_id="start"
    )["operation"] == first
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 1
