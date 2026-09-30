"""Public operator onboarding with synthetic inventory and no seeded binding."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from nexus_connector_core import InstallationCandidate
import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.execution.core_inventory import local_inventory_snapshot
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.base import iso_plus


@pytest.fixture
def onboarding(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home"),
                          "--feature-harness-integrations", "true"])
    app = build_app(deps)
    headers = {}
    with deps.connection_factory.unit_of_work() as uow:
        for agent in ("subject", "other", "operator"):
            uow.connection.execute(
                "INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)",
                (agent, deps.clock.now_iso()))
            key = app.state.auth.issue_key(uow, agent_id=agent)
            headers[agent] = {"Authorization": "Bearer " + key}
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/v1/connections/executors:register", json={
            "client_intent_id": "register", "connector_id": "connector",
            "label": "Remote host", "control_capabilities": [],
        }, headers=headers["subject"])
        assert response.status_code == 201, response.text
        registration = response.json()
        executor = registration["executor_id"]
        ticket = {"Authorization": "Bearer " + registration["bootstrap_ticket"]["ticket"]}
        candidate = InstallationCandidate(
            "codex_app_server", str(tmp_path / "remote-only" / "codex.exe"),
            "sha256:" + "a" * 64, "explicit", "selected")
        snapshot = local_inventory_snapshot(
            [candidate], server_id=registration["server_id"], executor_id=executor,
            producer_instance_id="peer", publication_sequence=1)
        response = client.put(f"/v1/runtime/executors/{executor}/inventory",
                              json=snapshot, headers=ticket)
        assert response.status_code == 200, response.text
        response = client.post(f"/v1/runtime/executors/{executor}/realizations", json={
            "client_intent_id": "realization", "agent_id": "subject",
            "local_realization_ref": "root_1234567890123456",
            "realization_revision": 1, "workspace_id": None,
            "workspace_label": "Project", "adapter_id": "codex_app_server",
            "candidate_ref": snapshot["evidence"][0]["candidate_ref"],
            "inventory_revision": snapshot["inventory_revision"],
            "local_root_proof_digest": "sha256:" + "b" * 64,
            "configuration_digest": "sha256:" + "c" * 64,
            "local_consent_id": "consent",
        }, headers=ticket)
        assert response.status_code == 201, response.text
        realization = response.json()
        prepare = {
            "client_intent_id": "prepare", "agent_id_hint": "subject",
            "executor_id": executor, "adapter_id": "codex_app_server",
            "candidate_ref": snapshot["evidence"][0]["candidate_ref"],
            "inventory_revision": snapshot["inventory_revision"],
            "realization_ref": realization["realization_ref"],
            "workspace_id": realization["workspace_id"], "alias": "assistant",
        }
        yield deps, client, headers, prepare


def prepare_operator(client, headers, prepare):
    response = client.post("/v1/connections/bindings:prepare", json=prepare,
                           headers=headers["operator"])
    assert response.status_code == 200, response.text
    proposal = response.json()
    return proposal, {
        "client_intent_id": "apply", "proposal_id": proposal["proposal_id"],
        "proposal_revision": proposal["proposal_revision"],
        "approved_diff_hash": proposal["diff"]["approved_diff_hash"],
    }


def assert_no_binding(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("agent_endpoints", "runtime_profiles", "execution_bindings",
                      "execution_sessions", "execution_dispatch_outbox"):
            assert uow.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_operator_binding_creates_profile_endpoint_and_scoped_grant(onboarding):
    deps, client, headers, prepare = onboarding
    # A payload subject never makes an ordinary agent an operator.
    denied = client.post("/v1/connections/bindings:prepare", json=prepare,
                         headers=headers["other"])
    assert denied.status_code == 403
    proposal, apply = prepare_operator(client, headers, prepare)
    assert proposal["agent_id"] == "subject"
    assert proposal["profile_id"]
    assert proposal["diff"]["requires_operator"] is True
    assert proposal["required_approvals"] == ["operator_confirmation"]
    assert_no_binding(deps)
    contract = json.loads((Path(__file__).resolve().parents[2] /
                           "plans/contratos/http-target.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator({"$defs": contract["$defs"],
                          **contract["$defs"]["BindingProposal"]}).validate(proposal)
    route = "/v1/connections/bindings:apply"
    assert client.post(route, json=apply, headers=headers["subject"]).status_code == 404
    assert client.post(route, json={**apply, "operator_proof_ref": "forged"},
                       headers=headers["operator"]).status_code == 409
    response = client.post(route, json=apply, headers=headers["operator"])
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["agent_id"] == "subject"
    assert client.post(route, json=apply, headers=headers["operator"]).json() == view
    assert client.post(route, json={**apply, "client_intent_id": "duplicate"},
                       headers=headers["operator"]).status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        endpoint = conn.execute("SELECT * FROM agent_endpoints").fetchone()
        profile = conn.execute("SELECT * FROM runtime_profiles").fetchone()
        assert endpoint["agent_id"] == "subject"
        assert endpoint["profile_id"] == profile["profile_id"] == proposal["profile_id"]
        assert endpoint["enabled"] == profile["enabled"] == 1
        assert endpoint["activation_state"] == "approved"
        assert profile["config"] == profile["secret_refs"] == "{}"
        assert profile["inherit_ambient"] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM runtime_execution_grants").fetchone()[0] == 0
        audit = conn.execute("SELECT actor_agent_id,resource_kind FROM runtime_access_audit "
                             "WHERE action LIKE 'config.%' ORDER BY audit_id").fetchall()
        assert [tuple(row) for row in audit] == [("operator", "profile"), ("operator", "endpoint")]
        stored = conn.execute("SELECT actor_agent_id,subject_agent_id FROM execution_proposals").fetchone()
        assert tuple(stored) == ("operator", "subject")
    me = client.get("/v1/connections/me", headers=headers["subject"]).json()
    assert me["revisions"]["authorization"] == view["authorization_revision"]
    assert me["revisions"]["configuration"] == view["configuration_revision"]
    # Delegation is an explicit authenticated command with an expiry and budget.
    grant = {
        "actor_agent_id": "subject", "endpoint_id": view["endpoint_id"],
        "actions": ["open", "send", "interrupt", "close"], "max_executions": 1,
        "expires_at": iso_plus(deps.clock.now_iso(), 600),
    }
    assert client.post("/api/v1/harness/grants", json=grant,
                       headers=headers["subject"]).status_code == 403
    issued = client.post("/api/v1/harness/grants", json=grant, headers=headers["operator"])
    assert issued.status_code == 200, issued.text
    assert issued.json()["data"]["profile_revision"] == 1


@pytest.mark.parametrize("change", ["subject_policy", "operator_key", "configuration", "expiry", "method"])
def test_operator_binding_revalidates_before_apply(onboarding, change):
    deps, client, headers, prepare = onboarding
    proposal, apply = prepare_operator(client, headers, prepare)
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        if change == "subject_policy":
            conn.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'",
                         (json.dumps({"messages": {"send_direct": False}}),))
        elif change == "operator_key":
            # A newly authenticated operator key cannot approve an old diff.
            key = client.app.state.auth.issue_key(uow, agent_id="operator")
            headers["operator"] = {"Authorization": "Bearer " + key}
        elif change == "configuration":
            conn.execute("UPDATE execution_realizations SET configuration_digest=?",
                         ("sha256:" + "d" * 64,))
        elif change == "expiry":
            conn.execute("UPDATE execution_proposals SET expires_at='2000-01-01T00:00:00Z'")
        else:
            conn.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) "
                         "VALUES ('subject','codex_app_server',0)")
    response = client.post("/v1/connections/bindings:apply", json=apply,
                           headers=headers["operator"])
    assert response.status_code in (403, 409), response.text
    assert_no_binding(deps)


def test_operator_binding_rolls_back_profile_with_binding(onboarding):
    deps, client, headers, prepare = onboarding
    _, apply = prepare_operator(client, headers, prepare)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_binding BEFORE INSERT ON execution_bindings "
                               "BEGIN SELECT RAISE(ABORT,'Injected binding write failure'); END")
    response = client.post("/v1/connections/bindings:apply", json=apply,
                           headers=headers["operator"])
    assert response.status_code == 500
    assert_no_binding(deps)
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT status FROM execution_proposals").fetchone()[0] == "PREPARED"
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_access_audit "
                                      "WHERE action LIKE 'config.%'").fetchone()[0] == 0
        uow.connection.execute("DROP TRIGGER reject_binding")
    assert client.post("/v1/connections/bindings:apply", json=apply,
                       headers=headers["operator"]).status_code == 200


def test_binding_does_not_turn_self_confirmation_into_execution_authority(onboarding):
    deps, client, headers, prepare = onboarding
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) "
                               "VALUES ('subject','codex_app_server',0)")
    denied = client.post("/v1/connections/bindings:prepare", json=prepare,
                         headers=headers["operator"])
    assert denied.status_code == 403
    response = client.post("/v1/connections/bindings:prepare", json=prepare,
                           headers=headers["subject"])
    assert response.status_code == 200, response.text
    proposal = response.json()
    apply = {"client_intent_id": "apply", "proposal_id": proposal["proposal_id"],
             "proposal_revision": proposal["proposal_revision"],
             "approved_diff_hash": proposal["diff"]["approved_diff_hash"]}
    response = client.post("/v1/connections/bindings:apply", json=apply,
                           headers=headers["subject"])
    assert response.status_code == 200, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        endpoint = conn.execute("SELECT enabled,profile_id FROM agent_endpoints").fetchone()
        assert tuple(endpoint) == (0, None)
        assert conn.execute("SELECT enabled FROM agent_connection_methods").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM runtime_execution_grants").fetchone()[0] == 0
