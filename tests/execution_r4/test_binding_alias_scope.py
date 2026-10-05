"""Independent executor/workspace aliases share an agent without replacing it."""
import pytest
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.discovery import fingerprint
from okto_nexus.adapters.outbound.execution.core_inventory import local_inventory_snapshot
from test_binding_operator import onboarding, prepare_operator


def publish_candidate(client, headers, tmp_path, workspace_id, *, host, suffix, alias, registration=None):
    if registration is None:
        registered = client.post("/v1/connections/executors:register", headers=headers["subject"], json={
            "client_intent_id": "register-" + host, "connector_id": host,
            "label": host, "control_capabilities": []})
        assert registered.status_code == 201, registered.text
        registration = registered.json()
    executor = registration["executor_id"]
    ticket = {"Authorization": "Bearer " + registration["bootstrap_ticket"]["ticket"]}
    if "_snapshot" not in registration:
        binary = tmp_path / (host + ".exe")
        binary.write_bytes(b"Synthetic installation for scoped alias tests")
        candidate = InstallationCandidate("codex_app_server", str(binary), fingerprint(binary), "explicit", host)
        snapshot = local_inventory_snapshot([candidate], server_id=registration["server_id"],
            executor_id=executor, producer_instance_id=host, publication_sequence=1)
        response = client.put(f"/v1/runtime/executors/{executor}/inventory", headers=ticket, json=snapshot)
        assert response.status_code == 200, response.text
        registration["_snapshot"] = snapshot
    snapshot = registration["_snapshot"]
    body = dict(client_intent_id="realization-" + suffix, agent_id="subject",
        local_realization_ref="root_" + suffix.ljust(20, "0"), realization_revision=1,
        workspace_id=workspace_id, workspace_label="Shared project", adapter_id="codex_app_server",
        candidate_ref=snapshot["evidence"][0]["candidate_ref"], inventory_revision=snapshot["inventory_revision"],
        local_root_proof_digest="sha256:" + "d" * 64, configuration_digest="sha256:" + "e" * 64,
        local_consent_id="consent-" + suffix)
    response = client.post(f"/v1/runtime/executors/{executor}/realizations", headers=ticket, json=body)
    assert response.status_code == 201, response.text
    realized = response.json()
    return dict(client_intent_id="prepare-" + suffix, agent_id_hint="subject", executor_id=executor,
        adapter_id=body["adapter_id"], candidate_ref=body["candidate_ref"], inventory_revision=body["inventory_revision"],
        realization_ref=realized["realization_ref"], workspace_id=workspace_id, alias=alias), registration


def apply(client, headers, prepare, suffix):
    proposal, body = prepare_operator(client, headers, prepare)
    assert proposal["can_apply"], proposal
    body["client_intent_id"] = "apply-" + suffix
    response = client.post("/v1/connections/bindings:apply", headers=headers["operator"], json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_same_alias_on_another_executor_preserves_both_bindings_and_agent(onboarding, tmp_path):
    deps, client, headers, first = onboarding
    left = apply(client, headers, first, "first")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        agent = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='subject'").fetchone())
        endpoint = dict(uow.connection.execute("SELECT * FROM agent_endpoints WHERE endpoint_id=?", (left["endpoint_id"],)).fetchone())
    second, registration = publish_candidate(client, headers, tmp_path, first["workspace_id"],
        host="second-host", suffix="second", alias=first["alias"])
    right = apply(client, headers, second, "second")
    assert left["binding_id"] != right["binding_id"] and left["executor_id"] != right["executor_id"]
    assert left["agent_id"] == right["agent_id"] == "subject"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        current_agent = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='subject'").fetchone())
        assert {k: v for k, v in current_agent.items() if k != "last_seen_at"} == {k: v for k, v in agent.items() if k != "last_seen_at"}
        assert dict(uow.connection.execute("SELECT * FROM agent_endpoints WHERE endpoint_id=?", (left["endpoint_id"],)).fetchone()) == endpoint
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0] == 2


@pytest.mark.parametrize("alias,allowed", [("assistant", False), ("reviewer", True)])
def test_alias_conflicts_are_scoped_within_the_selected_executor(onboarding, tmp_path, alias, allowed):
    deps, client, headers, first = onboarding
    prepare, registration = publish_candidate(client, headers, tmp_path, first["workspace_id"],
        host="same-host", suffix="first", alias="assistant")
    next_prepare, _ = publish_candidate(client, headers, tmp_path, first["workspace_id"],
        host="same-host", suffix="next", alias=alias, registration=registration)
    original = apply(client, headers, prepare, "original")
    proposal, body = prepare_operator(client, headers, next_prepare)
    assert proposal["can_apply"] is allowed
    body["client_intent_id"] = "apply-next"
    response = client.post("/v1/connections/bindings:apply", headers=headers["operator"], json=body)
    assert response.status_code == (200 if allowed else 409), response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0] == (2 if allowed else 1)
        assert uow.connection.execute("SELECT endpoint_id FROM execution_bindings WHERE binding_id=?", (original["binding_id"],)).fetchone()[0] == original["endpoint_id"]
