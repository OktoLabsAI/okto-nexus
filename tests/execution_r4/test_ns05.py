"""R4 realization claims are scoped evidence, never start authority."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from nexus_connector_core import InstallationCandidate

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.execution.core_inventory import (
    local_inventory_snapshot,
)
from okto_nexus.bootstrap.dependencies import bootstrap


def test_ns05_01(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with deps.connection_factory.unit_of_work() as uow:
        for agent_id in ("agent-a", "agent-b"):
            uow.connection.execute(
                "INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
                (agent_id, "2026-09-29T00:00:00Z"),
            )
    with deps.connection_factory.unit_of_work() as uow:
        key_a = app.state.auth.issue_key(uow, agent_id="agent-a")
        key_b = app.state.auth.issue_key(uow, agent_id="agent-b")
    with TestClient(app, raise_server_exceptions=False) as client:
        registered = client.post(
            "/v1/connections/executors:register",
            json={"client_intent_id": "register", "connector_id": "connector-a",
                  "label": "Remote host", "control_capabilities": []},
            headers={"Authorization": f"Bearer {key_a}"},
        )
        assert registered.status_code == 201, registered.text
        registration = registered.json()
        ticket = registration["bootstrap_ticket"]["ticket"]
        assert "realization:publish" in registration["bootstrap_ticket"]["scopes"]
        executor_id = registration["executor_id"]
        local_path = str(tmp_path / "secret-local-root" / "codex.exe")
        candidate = InstallationCandidate(
            "codex_app_server", local_path, "sha256:" + "a" * 64,
            "explicit", "selected",
        )
        snapshot = local_inventory_snapshot(
            [candidate], server_id=registration["server_id"],
            executor_id=executor_id, producer_instance_id="connector-process",
            publication_sequence=1,
        )
        published = client.put(
            f"/v1/runtime/executors/{executor_id}/inventory",
            json=snapshot, headers={"Authorization": f"Bearer {ticket}"},
        )
        assert published.status_code == 200, published.text
        body = {
            "client_intent_id": "realization-one", "agent_id": "agent-a",
            "local_realization_ref": "root_local_secret_1234567890123456",
            "realization_revision": 1, "workspace_id": None,
            "workspace_label": "Project Alpha",
            "adapter_id": "codex_app_server",
            "candidate_ref": snapshot["evidence"][0]["candidate_ref"],
            "inventory_revision": snapshot["inventory_revision"],
            "local_root_proof_digest": "sha256:" + "b" * 64,
            "configuration_digest": "sha256:" + "c" * 64,
            "local_consent_id": "consent-one",
        }
        route = f"/v1/runtime/executors/{executor_id}/realizations"
        assert client.post(route, json=body).status_code == 401
        assert client.post(route, json=body, headers={
            "Authorization": f"Bearer {key_a}"}).status_code == 403
        created = client.post(route, json=body, headers={
            "Authorization": f"Bearer {ticket}"})
        assert created.status_code == 201, created.text
        view = created.json()
        contract = json.loads((Path(__file__).resolve().parents[2] /
                               "plans/contratos/http-target.schema.json").read_text(
                                   encoding="utf-8"))
        Draft202012Validator(contract["$defs"]["RealizationView"]).validate(view)
        assert view["agent_id"] == "agent-a"
        assert view["executor_id"] == executor_id
        assert local_path not in created.text
        replay = client.post(route, json=body, headers={
            "Authorization": f"Bearer {ticket}"})
        assert replay.status_code == 200 and replay.json() == view
        changed = {**body, "configuration_digest": "sha256:" + "d" * 64}
        conflict = client.post(route, json=changed, headers={
            "Authorization": f"Bearer {ticket}"})
        assert conflict.status_code == 409
        wrong_agent = client.post(route, json={**body,
                                               "client_intent_id": "another",
                                               "agent_id": "agent-b"},
                                  headers={"Authorization": f"Bearer {ticket}"})
        assert wrong_agent.status_code in (400, 403)
        assert client.post(route.replace(executor_id, "another-executor"),
                           json=body, headers={
                               "Authorization": f"Bearer {ticket}"}).status_code == 403
        assert client.post(route, json={**body,
                                        "client_intent_id": "path-label",
                                        "workspace_label": local_path},
                           headers={"Authorization": f"Bearer {ticket}"}).status_code in (400, 422)
        assert client.post(route, json={**body,
                                        "client_intent_id": "path-ref",
                                        "local_realization_ref": local_path},
                           headers={"Authorization": f"Bearer {ticket}"}).status_code in (400, 422)
        assert client.post(route, json={**body,
                                        "client_intent_id": "other-candidate",
                                        "candidate_ref": "nexus-install-v1:" + "f" * 64},
                           headers={"Authorization": f"Bearer {ticket}"}).status_code == 409
        assert client.post(route, json={**body,
                                        "client_intent_id": "other-inventory",
                                        "inventory_revision": "sha256:" + "f" * 64},
                           headers={"Authorization": f"Bearer {ticket}"}).status_code == 409
        assert client.get("/v1/connections/me", headers={
            "Authorization": f"Bearer {key_b}"}).status_code == 200
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        row = conn.execute(
            "SELECT r.status,w.status,w.workspace_id,s.root_realpath,"
            "r.local_root_proof_digest,r.local_consent_id "
            "FROM execution_realizations r JOIN execution_workspace_bindings w "
            "ON w.workspace_binding_id=r.workspace_binding_id "
            "JOIN workspaces s ON s.workspace_id=w.workspace_id "
            "WHERE r.realization_ref=?", (view["realization_ref"],),
        ).fetchone()
        assert tuple(row) == (
            "PENDING_APPROVAL", "PENDING_APPROVAL", view["workspace_id"],
            None, body["local_root_proof_digest"], "consent-one",
        )
        assert conn.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
