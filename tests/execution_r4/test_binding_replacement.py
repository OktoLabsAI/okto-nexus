"""Rebind is an explicit reviewed update, not a second or silently reused binding."""
import pytest
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from test_binding_operator import onboarding, prepare_operator
from test_binding_alias_scope import publish_candidate, apply
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions


def seed_claim(deps, binding, lifecycle):
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO execution_sessions(server_id,executor_id,session_id,binding_id,workspace_id,"
            "workspace_binding_id,open_operation_id,owner_generation,lifecycle_state,lease_state) "
            "VALUES (?,?,?,?,?,?,?,1,?,'ACTIVE')",
            (binding["server_id"], binding["executor_id"], "claim", binding["binding_id"], binding["workspace_id"],
             binding["workspace_binding_id"], "opening-claim", lifecycle))


def prepared_pair(onboarding, tmp_path):
    deps, client, headers, initial = onboarding
    first, registration = publish_candidate(client, headers, tmp_path, initial["workspace_id"],
        host="replacement-host", suffix="first", alias="assistant")
    other, _ = publish_candidate(client, headers, tmp_path, initial["workspace_id"],
        host="replacement-host", suffix="other", alias="reviewer", registration=registration)
    replacement, _ = publish_candidate(client, headers, tmp_path, initial["workspace_id"],
        host="replacement-host", suffix="replacement", alias="assistant", registration=registration)
    old = apply(client, headers, first, "old")
    independent = apply(client, headers, other, "independent")
    replacement["replace_binding_id"] = old["binding_id"]
    return deps, client, headers, old, independent, replacement


def test_replacement_changes_only_reviewed_binding_revision(onboarding, tmp_path):
    deps, client, headers, old, independent, request = prepared_pair(onboarding, tmp_path)
    seed_claim(deps, independent, "READY")
    contract = json.loads((Path(__file__).resolve().parents[2] / "plans/contratos/http-target.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator({"$defs": contract["$defs"], **contract["$defs"]["BindingPrepareRequest"]}).validate(request)
    before = current_agent_revisions(deps.connection_factory, agent_id="subject")[1]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        endpoints = [dict(row) for row in uow.connection.execute("SELECT * FROM agent_endpoints ORDER BY endpoint_id")]
        profiles = [dict(row) for row in uow.connection.execute("SELECT * FROM runtime_profiles ORDER BY profile_id")]
        other = dict(uow.connection.execute("SELECT * FROM execution_bindings WHERE binding_id=?", (independent["binding_id"],)).fetchone())
    proposal, body = prepare_operator(client, headers, request)
    Draft202012Validator({"$defs": contract["$defs"], **contract["$defs"]["BindingProposal"]}).validate(proposal)
    assert proposal["can_apply"] and proposal["binding_id"] == old["binding_id"]
    assert "Replace binding" in proposal["diff"]["summary"]
    assert "binding_revision" in proposal["diff"]["fields_changed"]
    body["client_intent_id"] = "replace-confirmed"
    response = client.post("/v1/connections/bindings:apply", headers=headers["operator"], json=body)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["binding_id"] == old["binding_id"] and updated["endpoint_id"] == old["endpoint_id"]
    assert updated["realization_ref"] == request["realization_ref"] != old["realization_ref"]
    assert updated["binding_revision"] == old["binding_revision"] + 1
    assert current_agent_revisions(deps.connection_factory, agent_id="subject")[1] == before
    assert client.post("/v1/connections/bindings:apply", headers=headers["operator"], json=body).json() == updated
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert [dict(row) for row in uow.connection.execute("SELECT * FROM agent_endpoints ORDER BY endpoint_id")] == endpoints
        assert [dict(row) for row in uow.connection.execute("SELECT * FROM runtime_profiles ORDER BY profile_id")] == profiles
        assert dict(uow.connection.execute("SELECT * FROM execution_bindings WHERE binding_id=?", (independent["binding_id"],)).fetchone()) == other
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0] == 2
        assert tuple(uow.connection.execute("SELECT binding_id,lifecycle_state,lease_state FROM execution_sessions").fetchone()) == (independent["binding_id"], "READY", "ACTIVE")


@pytest.mark.parametrize("fault", ["revision", "scope", "confirmation"])
def test_replacement_refuses_changed_target_or_unreviewed_diff(onboarding, tmp_path, fault):
    deps, client, headers, old, independent, request = prepared_pair(onboarding, tmp_path)
    if fault == "scope":
        request["replace_binding_id"] = independent["binding_id"]
        response = client.post("/v1/connections/bindings:prepare", headers=headers["operator"], json=request)
        assert response.status_code == 409, response.text
        return
    proposal, body = prepare_operator(client, headers, request)
    body["client_intent_id"] = "replacement"
    if fault == "revision":
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_bindings SET binding_revision=binding_revision+1 WHERE binding_id=?", (old["binding_id"],))
    else:
        body["approved_diff_hash"] = "sha256:" + "0" * 64
    response = client.post("/v1/connections/bindings:apply", headers=headers["operator"], json=body)
    assert response.status_code == 409, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT realization_ref FROM execution_bindings WHERE binding_id=?", (old["binding_id"],)).fetchone()[0] == old["realization_ref"]


@pytest.mark.parametrize("boundary", ["prepare", "apply"])
@pytest.mark.parametrize("lifecycle", ["READY", "OPEN_PENDING", "OUTCOME_UNKNOWN", "FAILED"])
def test_replacement_refuses_live_or_uncertain_target_claims(onboarding, tmp_path, boundary, lifecycle):
    deps, client, headers, old, independent, request = prepared_pair(onboarding, tmp_path)
    if boundary == "apply":
        _, body = prepare_operator(client, headers, request)
        body["client_intent_id"] = "replace"
    seed_claim(deps, old, lifecycle)
    if boundary == "prepare":
        response = client.post("/v1/connections/bindings:prepare", headers=headers["operator"], json=request)
    else:
        response = client.post("/v1/connections/bindings:apply", headers=headers["operator"], json=body)
    assert response.status_code == 409, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT realization_ref FROM execution_bindings WHERE binding_id=?", (old["binding_id"],)).fetchone()[0] == old["realization_ref"]


def test_replacement_allows_a_failed_open_after_durable_release(onboarding, tmp_path):
    deps, client, headers, old, _, request = prepared_pair(onboarding, tmp_path)
    seed_claim(deps, old, 'FAILED')
    with deps.connection_factory.unit_of_work() as uow:
        # FAILED alone is insufficient (covered above). CLOSED lease is the
        # canonical projection after the owner proves no remaining resources.
        uow.connection.execute("UPDATE execution_sessions SET lease_state='CLOSED' WHERE session_id='claim'")
    _, body = prepare_operator(client, headers, request)
    response = client.post('/v1/connections/bindings:apply', headers=headers['operator'], json=body)
    assert response.status_code == 200, response.text
    assert response.json()['binding_revision'] == old['binding_revision'] + 1
