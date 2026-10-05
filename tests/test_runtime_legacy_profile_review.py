"""Legacy profile absence needs a diagnostic, never a guessed restoration."""
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool

runtime = runtime_fixture


def legacy_session(connection, agent, sid):
    connection.execute("INSERT INTO harness_sessions(session_id,kind,owning_agent_id,status,capabilities,"
        "started_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (sid, "pi", agent, "RUNNING", "{}", "historical", "historical", "historical"))


def test_legacy_missing_profile_is_reported_without_inventing_damage_or_restoring(runtime):
    deps, client, _, peers, operator, caller = runtime
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET capabilities='{}',metadata=NULL WHERE agent_id='worker'")
        legacy_session(uow.connection, "worker", "old-one")
        legacy_session(uow.connection, "worker", "old-two")
        before = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='worker'").fetchone())
    reply = client.get("/api/v1/harness/diagnostics", headers={"x-api-key": operator})
    assert reply.status_code == 200, reply.text
    data = reply.json()["data"]
    # Behavioral assertion first: existing diagnostics have a generic recovery
    # sentence but no evidence about this missing canonical profile.
    assert data.get("legacy_profile_review", {}).get("agents"), data
    review = data["legacy_profile_review"]
    assert review["schema_version"] == 1 and not review["truncated"]
    assert review["agents"] == [{"agent_id": "worker", "capabilities": "empty",
        "metadata": "missing", "review_required": True}]
    assert review["damage_confirmed"] is False
    assert review["restoration_performed"] is False
    assert "trusted" in review["recovery"]
    assert tool(client, operator, "harness_list", {"view": "diagnostics"})["data"] == data
    assert client.get("/api/v1/harness/diagnostics", headers={"x-api-key": caller}).status_code == 403
    assert not tool(client, caller, "harness_list", {"view": "diagnostics"})["ok"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='worker'").fetchone()) == before
        assert uow.connection.execute("SELECT count(*) FROM harness_sessions WHERE status='RUNNING' AND ended_at IS NULL").fetchone()[0] == 2
    assert not peers


def test_legacy_review_does_not_expose_profile_content_or_mark_preserved_fields_missing(runtime):
    deps, client, _, _, operator, _ = runtime
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET metadata=? WHERE agent_id='worker'",
            (json.dumps({"private-note": "do-not-return-profile-value"}),))
        legacy_session(uow.connection, "worker", "old-preserved")
    data = client.get("/api/v1/harness/diagnostics", headers={"x-api-key": operator}).json()["data"]
    assert data.get("legacy_profile_review", {}).get("agents"), data
    assert data["legacy_profile_review"]["agents"] == [{"agent_id": "worker",
        "capabilities": "present", "metadata": "present", "review_required": False}]
    assert "do-not-return-profile-value" not in json.dumps(data)


@pytest.mark.parametrize("stored,state", [("  ", "empty"), ("null", "missing"),
    ("[", "invalid"), ('"private-value"', "invalid"), (b"invalid-blob", "invalid")])
def test_legacy_review_classifies_unusable_fields_without_exposing_or_repairing_them(runtime, stored, state):
    deps, client, _, _, operator, _ = runtime
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET metadata=? WHERE agent_id='worker'", (stored,))
        legacy_session(uow.connection, "worker", "old-invalid")
    response = client.get("/api/v1/harness/diagnostics", headers={"x-api-key": operator})
    assert response.status_code == 200, response.text
    review = response.json()["data"]["legacy_profile_review"]
    assert review["agents"][0]["metadata"] == state
    assert review["agents"][0]["review_required"]
    assert "private-value" not in response.text and "invalid-blob" not in response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT metadata FROM agents WHERE agent_id='worker'").fetchone()[0] == stored


def test_legacy_review_is_bounded_and_reports_truncation(runtime):
    deps, client, _, _, operator, _ = runtime
    with deps.connection_factory.unit_of_work() as uow:
        for index in range(101):
            agent = f"legacy-review-{index:03d}"
            deps.repos.agents.upsert(uow, agent_id=agent)
            legacy_session(uow.connection, agent, f"session-{index}")
    reply = client.get("/api/v1/harness/diagnostics", headers={"x-api-key": operator})
    assert reply.status_code == 200, reply.text
    review = reply.json()["data"]["legacy_profile_review"]
    assert review["truncated"] and len(review["agents"]) == 100
    assert review["agents"][0]["agent_id"] == "legacy-review-000"
    assert review["agents"][-1]["agent_id"] == "legacy-review-099"
    assert "offline" in review["recovery"]


def test_operator_restores_only_explicit_trusted_fixture_through_canonical_catalog(runtime, tmp_path):
    deps, client, _, peers, operator, caller = runtime
    # A disposable pre-damage export is explicitly selected by the fixture
    # operator. Diagnostics neither locates nor reads this source automatically.
    source = tmp_path / "reviewed-profile-export.json"
    source.write_text(json.dumps({"capabilities": ["restored-fixture-skill"],
        "metadata": {"origin": "reviewed-fixture-export"}, "role": "reviewer"}), encoding="utf-8")
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET capabilities='{}',metadata=NULL WHERE agent_id='worker'")
        legacy_session(uow.connection, "worker", "old-restore")
    headers = {"x-api-key": operator}
    assert client.get("/api/v1/harness/diagnostics", headers=headers).json()["data"][
        "legacy_profile_review"]["agents"][0]["review_required"]
    reviewed = json.loads(source.read_text(encoding="utf-8"))
    assert client.patch("/api/v1/agents/worker", headers={"x-api-key": caller}, json=reviewed).status_code == 403
    # Recovery does not bypass the canonical skill catalogue.
    assert client.patch("/api/v1/agents/worker", headers=headers, json=reviewed).status_code == 422
    assert client.post("/api/v1/capabilities", headers=headers,
        json={"name": "restored-fixture-skill"}).status_code == 200
    restored = client.patch("/api/v1/agents/worker", headers=headers, json=reviewed)
    assert restored.status_code == 200, restored.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        agent = deps.repos.agents.get(uow, "worker")
        assert agent.capabilities == {"restored-fixture-skill": True}
        assert agent.metadata == reviewed["metadata"] and agent.role == reviewed["role"]
        old = uow.connection.execute("SELECT * FROM harness_sessions WHERE session_id='old-restore'").fetchone()
        assert old["lifecycle_state"] == "legacy_unlinked" and old["ended_at"] is None
    review = client.get("/api/v1/harness/diagnostics", headers=headers).json()["data"]["legacy_profile_review"]
    assert not review["agents"][0]["review_required"]
    assert review["restoration_performed"] is False  # diagnostic remains read-only
    assert not peers
