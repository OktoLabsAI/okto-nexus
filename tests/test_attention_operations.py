"""Real SQLite metadata projection; no synthetic peer proves client acceptance."""
import json
from types import SimpleNamespace

import pytest

from fake_clock import FakeClock
from okto_nexus.adapters.outbound.sqlite.attention_operations import (
    SOURCE_SQL, SQL_FUNCTIONS, build_policy,
)
from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.application.attention_operations import operator_policy, project
from okto_nexus.application.attention_results import project as project_result
from okto_nexus.adapters.outbound.sqlite.attention_results import SOURCE_SQL as RESULT_SQL
from okto_nexus.application.database_reset import clear_operational_history
from okto_nexus.domain.attention import with_preferences
from okto_nexus.application.runtime_maintenance import RuntimeMaintenanceService
from okto_nexus.errors import OktoNexusError


NOW = "2026-11-06T12:00:00.000000Z"
LATER = "2026-11-06T13:00:00.000000Z"


@pytest.fixture
def db(migrated_factory):
    with migrated_factory.unit_of_work() as uow:
        c = uow.connection
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name='attention_operation_epochs'").fetchone()
        c.create_function("strftime", -1, lambda *args: NOW)
        seed(c)
        yield c


def seed(c):
    for name, arity, callback in SQL_FUNCTIONS:
        c.create_function(name, arity, callback, deterministic=True)
    c.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES('ws',?)", (NOW,))
    c.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES('other',?)", (NOW,))
    for actor in ("operator", "worker", "creator"):
        c.execute("INSERT INTO agents(agent_id,created_at) VALUES(?,?)", (actor, NOW))


def read(c, *, policy=None, now=NOW, workspace_id=None, agent_id=None):
    for name, arity, callback in SQL_FUNCTIONS:
        c.create_function(name, arity, callback, deterministic=True)
    rows = c.execute(SOURCE_SQL, dict(now=now, workspace_id=workspace_id, agent_id=agent_id)).fetchall()
    facts = [json.loads(row["facts"]) for row in rows]
    result = [item for row in facts for item in project(row, now, policy or operator_policy(None))]
    result_facts = [json.loads(row['facts']) for row in c.execute(
        RESULT_SQL, dict(now=now, workspace_id=workspace_id, agent_id=agent_id))]
    result.extend(item for row in result_facts for item in project_result(row, now, {}))
    facts.extend(result_facts)
    return result, facts


def delivery(c, identity="d", status="unread", workspace="ws"):
    c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES(?,?,'creator','SECRET BODY',?)",
              ("m-" + identity, workspace, NOW))
    c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES(?,?,'worker',?,?)",
              (identity, "m-" + identity, status, NOW))


def handoff(c, *, status="VERIFYING", creator="operator", claimant="worker", target=None, verifier=None):
    c.execute("INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,status,claimed_by,claim_epoch,created_at,updated_at,verify_by,result) "
              "VALUES('h','ws',?,?,'eligible',?,?,1,?,?,?,'SECRET RESULT')",
              (creator, json.dumps(target or {"strategy": "direct", "agent_id": "worker"}),
               status, claimant, NOW, NOW, json.dumps(verifier or {"kind": "creator"})))


def execution(c, identity="op", *, state="DISPATCHED", workspace="ws"):
    c.execute("INSERT OR IGNORE INTO execution_executors(server_id,executor_id,kind,control_state,generation) VALUES('s','e','embedded','CONTROL_READY',1)")
    c.execute("INSERT OR IGNORE INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,enabled,activation_state,created_at,updated_at) "
              "VALUES('ep','worker',?,'fixture','nxl-r4',1,'approved',?,?)", (workspace, NOW, NOW))
    c.execute("INSERT OR IGNORE INTO execution_workspace_bindings(server_id,workspace_binding_id,executor_id,workspace_id,realization_handle,revision,status) "
              "VALUES('s','wb','e',?,'local',1,'ACTIVE')", (workspace,))
    c.execute("INSERT OR IGNORE INTO execution_bindings(server_id,binding_id,executor_id,endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,realization_ref,realization_revision,binding_revision) "
              "VALUES('s','b','e','ep','wb','candidate','inventory','realization',1,1)")
    c.execute("INSERT INTO execution_operations(server_id,executor_id,operation_id,subject_agent_id,actor_agent_id,binding_id,workspace_id,workspace_binding_id,session_id,action,intent_hash,semantic_payload,expected_revisions_json,admission_state,created_at) "
              "VALUES('s','e',?,'worker','operator','b',?,'wb',?,'turn.submit','digest','{\"secret\":true}','{}',?,?)",
              (identity, workspace, "session-" + identity, state, NOW))
    c.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state) VALUES('s','e',?,?)", (identity, state))


def receipt(c, *, operation="op", revision=1, stage="OUTCOME_UNKNOWN"):
    c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) "
              "VALUES('s','e',?,?,'digest',?,1,0,?)", (operation, revision, stage, NOW))
    c.execute("UPDATE execution_dispatch_outbox SET dispatch_state=? WHERE operation_id=?",
              ("RECONCILING" if stage == "OUTCOME_UNKNOWN" else "RESOLVED_TERMINAL", operation))


def only(c, kind, **kwargs):
    return [item for item in read(c, **kwargs)[0] if item["kind"] == kind]


def test_read_is_metadata_only_and_changes_no_table(db):
    delivery(db, status="parked")
    handoff(db)
    before = list(db.iterdump())
    first, facts = read(db)
    second, _ = read(db, now=LATER)
    assert first == second
    assert list(db.iterdump()) == before
    assert "SECRET" not in json.dumps(facts) + json.dumps(first)


@pytest.mark.parametrize("creator,claimant,target,verifier,can_act", [
    ("operator", "worker", {"strategy": "direct", "agent_id": "worker"}, {"kind": "creator"}, True),
    ("operator", "operator", {"strategy": "broadcast"}, {"kind": "creator"}, False),
    ("creator", "worker", {"strategy": "direct", "agent_id": "worker"}, {"kind": "agent", "agent_id": "operator"}, False),
    ("creator", "worker", {"strategy": "broadcast"}, {"kind": "agent", "agent_id": "operator"}, True),
    ("creator", "worker", {"strategy": "broadcast"}, {"kind": "capability", "capability": "review"}, False),
])
def test_verification_uses_actual_verifier_visibility_and_anti_self(db, creator, claimant, target, verifier, can_act):
    handoff(db, creator=creator, claimant=claimant, target=target, verifier=verifier)
    item = only(db, "verification_pending")[0]
    assert ("verify_handoff" in item["allowed_actions"]) is can_act
    assert item["category"] == ("action_required" if can_act else "watch")


def test_operator_policy_revalidates_current_permissions_and_capabilities_once(db):
    handoff(db, creator="creator", target={"strategy": "broadcast"}, verifier={"kind": "capability", "capability": "review"})
    db.execute("UPDATE agents SET capabilities='[\"review\"]' WHERE agent_id='operator'")
    kwargs = dict(config=SimpleNamespace(), access=None, context=SimpleNamespace(actor_agent_id="operator"), now=NOW)
    policy = build_policy(SimpleNamespace(connection=db), **kwargs)
    assert "verify_handoff" in only(db, "verification_pending", policy=policy)[0]["allowed_actions"]
    db.execute("UPDATE agents SET permissions='{\"handoffs\":{\"work\":false}}' WHERE agent_id='operator'")
    policy = build_policy(SimpleNamespace(connection=db), **kwargs)
    assert "verify_handoff" not in only(db, "verification_pending", policy=policy)[0]["allowed_actions"]
    db.execute("UPDATE agents SET is_active=0,permissions=NULL WHERE agent_id='operator'")
    assert build_policy(SimpleNamespace(connection=db), **kwargs)["operator_can_verify"] is False


def test_verification_rework_has_new_episode_even_with_fixed_clock(db):
    handoff(db)
    first = only(db, "verification_pending")[0]
    repo = SqliteHandoffRepo(FakeClock(iso=NOW))
    uow = SimpleNamespace(connection=db)
    changed = repo.transition_verifying(uow, workspace_id="ws", handoff_id="h", status="CLAIMED", claim_epoch=1, updated_at=NOW)
    assert changed.claim_epoch == 2 and not only(db, "verification_pending")
    repo.transition_claimed(uow, workspace_id="ws", handoff_id="h", claimed_by="worker", status="VERIFYING", claim_epoch=2, updated_at=NOW)
    second = only(db, "verification_pending")[0]
    assert first["attention_id"] != second["attention_id"]
    assert first["first_detected_at"] == second["first_detected_at"]


def test_only_current_unknown_receipt_or_reconciliation_requires_attention(db):
    execution(db)
    assert not only(db, "execution_outcome_unknown")
    receipt(db)
    first = only(db, "execution_outcome_unknown")[0]
    assert first["allowed_actions"] == ["inspect_operation", "inspect_recovery"]
    receipt(db, revision=2, stage="SUCCEEDED")
    assert not only(db, "execution_outcome_unknown")
    # A stale outbox cannot resurrect an older unknown after canonical success.
    db.execute("UPDATE execution_dispatch_outbox SET dispatch_state='RECONCILING' WHERE operation_id='op'")
    assert not only(db, "execution_outcome_unknown")


def test_unknown_transition_rollback_and_reentry_are_durable(db):
    execution(db)
    db.execute("SAVEPOINT change")
    db.execute("UPDATE execution_dispatch_outbox SET dispatch_state='RECONCILING' WHERE operation_id='op'")
    aborted = only(db, "execution_outcome_unknown")[0]
    db.execute("ROLLBACK TO change")
    db.execute("RELEASE change")
    assert not only(db, "execution_outcome_unknown")
    db.execute("UPDATE execution_dispatch_outbox SET dispatch_state='RECONCILING' WHERE operation_id='op'")
    first = only(db, "execution_outcome_unknown")[0]
    assert first == aborted
    db.execute("UPDATE execution_dispatch_outbox SET dispatch_state='DISPATCHED' WHERE operation_id='op'")
    db.execute("UPDATE execution_dispatch_outbox SET dispatch_state='RECONCILING' WHERE operation_id='op'")
    assert only(db, "execution_outcome_unknown")[0]["attention_id"] != first["attention_id"]


def test_expired_delivery_and_attempt_count_do_not_create_parked_incident(db):
    delivery(db, status="delivered")
    db.execute("UPDATE message_deliveries SET attempts=99,lease_expires_at='2000-01-01T00:00:00Z'")
    assert not only(db, "delivery_parked")
    db.execute("UPDATE message_deliveries SET status='parked'")
    first = only(db, "delivery_parked")[0]
    db.execute("UPDATE message_deliveries SET attempts=attempts+1")
    assert only(db, "delivery_parked")[0] == first


def test_recovery_requires_current_attention_and_unclaimed_delivery(db):
    delivery(db)
    db.execute("INSERT INTO runtime_pending_deliveries(delivery_id,context_json,authorization_revision,created_at,status) VALUES('d','{\"secret\":true}','r',?,'waiting')", (NOW,))
    assert not only(db, "runtime_recovery_attention")
    db.execute("UPDATE runtime_pending_deliveries SET status='attention',reason='PERMISSION_DENIED'")
    first = only(db, "runtime_recovery_attention")[0]
    db.execute("UPDATE runtime_pending_deliveries SET attempts=attempts+1")
    assert only(db, "runtime_recovery_attention")[0] == first
    db.execute("UPDATE message_deliveries SET status='read'")
    assert not only(db, "runtime_recovery_attention")


def test_disconnected_idle_and_completed_executors_are_not_incidents(db):
    execution(db)
    db.execute("UPDATE execution_executors SET control_state='DISCONNECTED'")
    first = only(db, "executor_disconnected_with_work")[0]
    assert first["category"] == "watch"
    escalated = only(db, "executor_disconnected_with_work", now=LATER,
                     policy={"executor_disconnected_seconds": 60})[0]
    assert escalated["category"] == "action_required" and escalated["attention_id"] == first["attention_id"]
    assert escalated["source_revision"] != first["source_revision"]
    assert escalated == only(db, "executor_disconnected_with_work", now="2026-11-07T00:00:00+00:00",
                            policy={"executor_disconnected_seconds": 60})[0]
    db.execute("UPDATE execution_executors SET control_state='CONTROL_READY'")
    assert not only(db, "executor_disconnected_with_work")
    db.execute("UPDATE execution_executors SET control_state='DISCONNECTED'")
    second = only(db, "executor_disconnected_with_work")[0]
    assert first["attention_id"] != second["attention_id"]
    assert first["first_detected_at"] == second["first_detected_at"]
    receipt(db, stage="SUCCEEDED")
    assert not only(db, "executor_disconnected_with_work")


def test_source_filters_apply_to_every_returned_fact(db):
    delivery(db, status="parked")
    delivery(db, identity="elsewhere", status="parked", workspace="other")
    handoff(db)
    execution(db, state="RECONCILING")
    assert {row["workspace_id"] for row in read(db, workspace_id="other")[0]} == {"other"}
    assert not read(db, agent_id="absent")[0]


def test_normal_claim_cleanup_and_unproved_eligibility_are_not_incidents(db):
    handoff(db, status="CLAIMED")
    assert read(db)[0] == []
    for family in ("cleanup", "aged", "silence", "agent_recovering"):
        assert project({"family": family, "state": "CLOSING", "attempts": 999}, LATER, {}) == []


def test_result_seen_is_independent_of_canonical_success():
    facts = dict(source_type="execution_result", operation_id="op", server_id="s", executor_id="e",
        stream_epoch="stream", terminal_sequence=1, delivery_outcome="success", captured_at=NOW,
        agent_id="worker", workspace_id="ws", session_id="session")
    item = project_result(facts, NOW, {})[0]
    seen = with_preferences(item, now=LATER, seen_at=LATER)
    assert item["resolution"] == seen["resolution"] == "resolved"
    assert item["active"] is True and seen["active"] is False


def managed_operation(c):
    execution(c)
    handoff(c, status="CLAIMED")
    delivery(c)
    c.execute("INSERT INTO runtime_execution_grants(grant_id,issuer_agent_id,actor_agent_id,credential_binding,represented_agent_id,workspace_id,endpoint_id,actions,expires_at,max_executions,created_at) "
              "VALUES('g','operator','worker','SECRET CREDENTIAL','worker','ws','ep','[\"execute_work\"]','2030-01-01T00:00:00Z',100,?)", (NOW,))
    c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,status,created_at,updated_at) "
              "VALUES('domain-op','d','m-d','ws','worker','SECRET CREDENTIAL','worker','ep',1,'SECRET ENVELOPE','hash','revision','domain-op','PENDING',?,?)", (NOW, NOW))
    c.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,actor_agent_id,idempotency_key,request_hash,created_at) "
              "VALUES('h',1,'domain-op','g',1,'worker','key','hash',?)", (NOW,))


def revision_anchor_resources(db):
    """Synthetic resources for migration 161, not canonical admission proof.

    The authority family's command-equivalent predicates are exercised with
    actually admitted work in test_attention_authority.py.
    """
    managed_operation(db)
    db.execute("INSERT INTO runtime_profiles(profile_id,adapter_id,config,enabled,created_at,updated_at) "
               "VALUES('profile','fixture','{}',1,?,?)", (NOW, NOW))
    db.execute("UPDATE agent_endpoints SET profile_id='profile' WHERE endpoint_id='ep'")
    db.execute("UPDATE delivery_outbox SET profile_revision=1 WHERE operation_id='domain-op'")


REVISION_ANCHORS = {
    "grant": ("runtime_grant_revision", "g"),
    "endpoint": ("runtime_endpoint_revision", "ep"),
    "profile": ("runtime_profile_revision", "profile"),
}


def revision_anchor(db, resource):
    row = db.execute("SELECT * FROM attention_operation_epochs WHERE source_type=? AND source_id=?",
                     REVISION_ANCHORS[resource]).fetchone()
    assert row is not None
    return dict(row)


def revision_state(resource, revision):
    if resource == "grant":
        return str(revision)
    return json.dumps([revision, 1, "approved"] if resource == "endpoint" else [revision, 1],
                      separators=(",", ":"))


def change_authority_revision(db, resource, revision, at):
    db.create_function("strftime", -1, lambda *args: at)
    table, key, identity = {
        "grant": ("runtime_execution_grants", "grant_id", "g"),
        "endpoint": ("agent_endpoints", "endpoint_id", "ep"),
        "profile": ("runtime_profiles", "profile_id", "profile"),
    }[resource]
    db.execute(f"UPDATE {table} SET revision=? WHERE {key}=?", (revision, identity))


@pytest.mark.parametrize("resource", ["grant", "endpoint", "profile"])
def test_authority_revision_episode_survives_retry_and_observation_timestamps(db, resource):
    revision_anchor_resources(db)
    initial = revision_anchor(db, resource)
    assert initial["state"] == revision_state(resource, 1) and initial["episode"] == 1
    assert initial["first_detected_at"] == initial["last_changed_at"] == NOW
    changed_at = "2026-11-06T12:10:00.000000Z"
    change_authority_revision(db, resource, 2, changed_at)
    first = revision_anchor(db, resource)
    assert first["state"] == revision_state(resource, 2) and first["episode"] == 2
    assert first["first_detected_at"] == first["last_changed_at"] == changed_at

    db.create_function("strftime", -1, lambda *args: LATER)
    db.execute("UPDATE delivery_outbox SET attempt_count=attempt_count+1,status='RETRY_WAIT',updated_at=?", (LATER,))
    db.execute("UPDATE agent_endpoints SET health='healthy',last_observed_at=?,updated_at=?", (LATER, LATER))
    db.execute("UPDATE runtime_profiles SET updated_at=?", (LATER,))
    db.execute("UPDATE runtime_execution_grants SET used_executions=used_executions+1")
    before = list(db.iterdump())
    assert revision_anchor(db, resource) == first
    # The remaining operations/results projections are also passive observers
    # of these counters; they do not manufacture authority from this fixture.
    read(db, now=LATER)
    read(db, now="2026-11-07T00:00:00Z")
    assert revision_anchor(db, resource) == first
    assert list(db.iterdump()) == before


@pytest.mark.parametrize("resource", ["grant", "endpoint", "profile"])
def test_authority_revision_anchors_rollback_and_reenter_with_distinct_episode(db, resource):
    revision_anchor_resources(db)
    changed_at = "2026-11-06T12:10:00.000000Z"
    change_authority_revision(db, resource, 2, changed_at)
    first = revision_anchor(db, resource)
    assert first["state"] == revision_state(resource, 2) and first["episode"] == 2
    before = list(db.iterdump())
    db.execute("SAVEPOINT revision_change")
    change_authority_revision(db, resource, 3, LATER)
    aborted = revision_anchor(db, resource)
    assert aborted["episode"] == first["episode"] + 1 and aborted["state"] == revision_state(resource, 3)
    assert aborted["first_detected_at"] == aborted["last_changed_at"] == LATER
    db.execute("ROLLBACK TO revision_change")
    db.execute("RELEASE revision_change")
    assert list(db.iterdump()) == before
    assert revision_anchor(db, resource) == first
    change_authority_revision(db, resource, 3, LATER)
    assert revision_anchor(db, resource) == aborted
    # Returning to a previous value still records a material transition;
    # recurrence advances the counter even if the write clock repeats.
    change_authority_revision(db, resource, 1, LATER)
    restored = revision_anchor(db, resource)
    assert restored["state"] == revision_state(resource, 1)
    assert restored["episode"] == aborted["episode"] + 1
    change_authority_revision(db, resource, 2, LATER)
    repeated = revision_anchor(db, resource)
    assert repeated["state"] == first["state"]
    assert repeated["episode"] == restored["episode"] + 1
    assert repeated["first_detected_at"] == repeated["last_changed_at"] == LATER


def test_unused_authority_resource_deletion_removes_its_revision_anchor(db):
    db.execute("INSERT INTO runtime_profiles(profile_id,adapter_id,config,enabled,created_at,updated_at) "
               "VALUES('unused-profile','fixture','{}',1,?,?)", (NOW, NOW))
    db.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,profile_id,created_at,updated_at) "
               "VALUES('unused-endpoint','worker','ws','fixture','nxl-r4','unused-profile',?,?)", (NOW, NOW))
    db.execute("INSERT INTO runtime_execution_grants(grant_id,issuer_agent_id,actor_agent_id,credential_binding,represented_agent_id,workspace_id,endpoint_id,actions,expires_at,max_executions,created_at) "
               "VALUES('unused-grant','operator','worker','SECRET','worker','ws','unused-endpoint','[]','2030-01-01T00:00:00Z',1,?)", (NOW,))
    for table, key, identity, source_type in (
        ("runtime_execution_grants", "grant_id", "unused-grant", "runtime_grant_revision"),
        ("agent_endpoints", "endpoint_id", "unused-endpoint", "runtime_endpoint_revision"),
        ("runtime_profiles", "profile_id", "unused-profile", "runtime_profile_revision"),
    ):
        assert db.execute("SELECT 1 FROM attention_operation_epochs WHERE source_type=? AND source_id=?",
                          (source_type, identity)).fetchone()
        db.execute(f"DELETE FROM {table} WHERE {key}=?", (identity,))
        assert not db.execute("SELECT 1 FROM attention_operation_epochs WHERE source_type=? AND source_id=?",
                              (source_type, identity)).fetchone()


def test_real_agent_retirement_records_endpoint_gate_without_fabricating_revision(db):
    revision_anchor_resources(db)
    before = dict(db.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='ep'").fetchone())
    initial = revision_anchor(db, "endpoint")
    changed_at = "2026-11-06T12:10:00.000000Z"
    db.create_function("strftime", -1, lambda *args: changed_at)
    assert SqliteAgentRepo(FakeClock(iso=changed_at)).delete(SimpleNamespace(connection=db), agent_id="worker")
    current = dict(db.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='ep'").fetchone())
    assert current["enabled"] == 0
    assert current["revision"] == before["revision"] and current["updated_at"] == before["updated_at"]
    assert db.execute("SELECT status FROM handoffs WHERE handoff_id='h'").fetchone()[0] == "CLAIMED"
    first = revision_anchor(db, "endpoint")
    assert first["state"] == '[1,0,"approved"]' and first["episode"] == initial["episode"] + 1
    assert first["first_detected_at"] == first["last_changed_at"] == changed_at
    db.execute("UPDATE delivery_outbox SET attempt_count=attempt_count+1,updated_at=?", (LATER,))
    db.execute("UPDATE agent_endpoints SET health='healthy',updated_at=?", (LATER,))
    assert revision_anchor(db, "endpoint") == first


@pytest.mark.parametrize("resource,table,column,blocked,restored,blocked_state", [
    ("endpoint", "agent_endpoints", "activation_state", "pending_review", "approved", '[1,1,"pending_review"]'),
    ("profile", "runtime_profiles", "enabled", 0, 1, '[1,0]'),
])
def test_authority_gate_without_revision_has_material_anchor_state_and_episode(db, resource, table, column, blocked, restored, blocked_state):
    revision_anchor_resources(db)
    initial = revision_anchor(db, resource)
    changed_at = "2026-11-06T12:10:00.000000Z"
    db.create_function("strftime", -1, lambda *args: changed_at)
    db.execute(f"UPDATE {table} SET {column}=?", (blocked,))
    first = revision_anchor(db, resource)
    assert first["state"] == blocked_state and first["episode"] == initial["episode"] + 1
    assert first["first_detected_at"] == first["last_changed_at"] == changed_at
    assert db.execute(f"SELECT revision FROM {table}").fetchone()[0] == 1
    db.execute(f"UPDATE {table} SET {column}=?", (restored,))
    reopened = revision_anchor(db, resource)
    assert reopened["state"] == initial["state"] and reopened["episode"] == first["episode"] + 1
    db.execute(f"UPDATE {table} SET {column}=?", (blocked,))
    repeated = revision_anchor(db, resource)
    assert repeated["state"] == first["state"] and repeated["episode"] == reopened["episode"] + 1
    assert repeated["first_detected_at"] == repeated["last_changed_at"] == first["first_detected_at"]


@pytest.mark.parametrize("keep_agents", [True, False])
def test_reset_preserves_only_anchors_whose_canonical_resources_survive(db, keep_agents):
    revision_anchor_resources(db)
    for resource in ("grant", "endpoint", "profile"):
        change_authority_revision(db, resource, 2, NOW)
    db.execute("UPDATE runtime_execution_grants SET used_executions=7 WHERE grant_id='g'")
    before = {(row["source_type"], row["source_id"]): dict(row)
              for row in db.execute("SELECT * FROM attention_operation_epochs")}
    configuration_tables = ("agents", "agent_endpoints", "runtime_profiles", "runtime_execution_grants",
                            "execution_executors", "execution_bindings", "execution_workspace_bindings")
    configuration = {table: sorted((tuple(row) for row in db.execute(f"SELECT * FROM {table}")), key=repr)
                     for table in configuration_tables}
    # 162 keeps the authority counters of installation defaults independently
    # of identities. Its per-resource counters follow retained configuration.
    defaults = ("authority_runtime_policy_defaults", "[1]")
    clear_operational_history(db, keep_agents=keep_agents)
    remaining = {(row["source_type"], row["source_id"]): dict(row)
                 for row in db.execute("SELECT * FROM attention_operation_epochs")}
    if not keep_agents:
        assert remaining == {defaults: before[defaults]}
        assert remaining[defaults]["state"] == "present"
        for table in configuration_tables:
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        return
    retained_keys = {
        ("runtime_grant_revision", "g"), ("runtime_endpoint_revision", "ep"),
        ("runtime_profile_revision", "profile"), ("execution_executor", '["s","e"]'),
        defaults,
        ("authority_agents", '["operator"]'), ("authority_agents", '["worker"]'),
        ("authority_agents", '["creator"]'),
        ("authority_agent_endpoints", '["ep"]'),
        ("authority_runtime_profiles", '["profile"]'),
        ("authority_runtime_execution_grants", '["g"]'),
        ("authority_execution_executors", '["s","e"]'),
        ("authority_execution_bindings", '["s","e","b"]'),
        ("authority_execution_workspace_bindings", '["s","e","wb"]'),
    }
    assert remaining == {key: before[key] for key in retained_keys}
    assert {table: sorted((tuple(row) for row in db.execute(f"SELECT * FROM {table}")), key=repr)
            for table in configuration_tables} == configuration
    assert tuple(db.execute("SELECT used_executions,max_executions,revision FROM runtime_execution_grants "
                            "WHERE grant_id='g'").fetchone()) == (7, 100, 2)
    assert not read(db, now=LATER)[0]
    for resource, authority_type in (
        ("grant", "authority_runtime_execution_grants"),
        ("endpoint", "authority_agent_endpoints"),
        ("profile", "authority_runtime_profiles"),
    ):
        source_type, identity = REVISION_ANCHORS[resource]
        change_authority_revision(db, resource, 3, LATER)
        row = revision_anchor(db, resource)
        assert row["state"] == revision_state(resource, 3)
        assert row["episode"] == remaining[(source_type, identity)]["episode"] + 1
        assert row["first_detected_at"] == row["last_changed_at"] == LATER
        authority_key = (authority_type, json.dumps([identity], separators=(",", ":")))
        authority = dict(db.execute("SELECT * FROM attention_operation_epochs WHERE source_type=? AND source_id=?",
                                    authority_key).fetchone())
        assert authority["state"] == "present"
        assert authority["episode"] == remaining[authority_key]["episode"] + 1
        assert authority["first_detected_at"] == authority["last_changed_at"] == LATER


def canonical_result(c, *, terminal=None):
    c.execute("INSERT INTO execution_sessions(server_id,executor_id,session_id,binding_id,workspace_id,workspace_binding_id,open_operation_id,owner_generation,lifecycle_state,lease_state) "
               "VALUES('s','e','session-op','b','ws','wb','op',1,'READY','ACTIVE')")
    c.execute("INSERT INTO execution_event_ingress(server_id,executor_id,session_id,stream_epoch,sequence,event_hash,event_type,payload_json,received_at) "
               "VALUES('s','e','session-op','stream',1,'digest','turn_state','{}',?)", (NOW,))
    c.execute("INSERT INTO execution_results(server_id,executor_id,operation_id,session_id,stream_epoch,output_text,delivery_outcome,captured_at,terminal_sequence) "
               "VALUES('s','e','op','session-op','stream','SECRET OUTPUT','success',?,?)", (NOW, terminal))


def test_sql_result_requires_correlated_terminal_event_and_excludes_output(db):
    execution(db)
    canonical_result(db)
    assert not only(db, "result_unseen")
    db.execute("UPDATE execution_results SET terminal_sequence=1")
    first = only(db, "result_unseen")[0]
    assert first["resolution"] == "resolved" and first["active"] is True
    assert "SECRET" not in json.dumps(read(db)[1])
    assert only(db, "result_unseen", now=LATER)[0] == first


@pytest.mark.parametrize("target", [
    {"strategy": "direct", "agent_id": "worker"},
    {"strategy": "role", "role": "engineer"},
    {"strategy": "capability", "capability": "build"},
    {"strategy": "tag", "selector": {"team": ["code"]}},
    {"strategy": "mixed", "rules": [{"strategy": "role", "role": "engineer"}]},
    {"strategy": "broadcast"},
    {"strategy": "direct_with_fallback", "agent_id": "absent", "fallback_after_seconds": 60,
     "fallback": {"strategy": "role", "role": "engineer"}},
])
def test_aged_handoff_uses_all_canonical_routing_strategies_without_claiming(db, target):
    db.execute("UPDATE agents SET role='engineer',capabilities='[\"build\"]',tags='{\"team\":\"code\"}' WHERE agent_id='worker'")
    handoff(db, status="OPEN", claimant=None, target=target)
    policy = {"handoff_unclaimed_seconds": 300}
    assert not only(db, "handoff_unclaimed_aged", policy=policy)
    before = list(db.iterdump())
    first = only(db, "handoff_unclaimed_aged", now=LATER, policy=policy)[0]
    assert first["category"] == "watch" and first["first_detected_at"] == "2026-11-06T12:05:00.000000+00:00"
    assert list(db.iterdump()) == before
    assert only(db, "handoff_unclaimed_aged", now="2026-11-07T00:00:00Z", policy=policy)[0] == first


@pytest.mark.parametrize("change", [
    "UPDATE agents SET is_active=0 WHERE agent_id='worker'",
    "UPDATE agents SET permissions='{\"handoffs\":{\"work\":false}}' WHERE agent_id='worker'",
    "UPDATE agents SET comm_scope='{\"outbound\":{\"team\":[\"forbidden\"]}}' WHERE agent_id='operator'",
    "UPDATE agents SET comm_scope='{\"inbound\":{\"team\":[\"forbidden\"]}}' WHERE agent_id='worker'",
])
def test_no_aged_incident_without_current_eligible_claimant(db, change):
    handoff(db, status="OPEN", claimant=None)
    db.execute(change)
    assert not only(db, "handoff_unclaimed_aged", now=LATER, policy={"handoff_unclaimed_seconds": 60})


def test_dependency_wait_is_not_aged_claimable_work_and_unblock_starts_its_clock(db):
    handoff(db, status="OPEN", claimant=None)
    db.execute("INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,status,claim_epoch,created_at,updated_at) "
               "VALUES('dependency','ws','creator','{\"strategy\":\"direct\",\"agent_id\":\"worker\"}','eligible','CLAIMED',1,?,?)", (NOW, NOW))
    db.execute("INSERT INTO handoff_dependencies(handoff_id,depends_on_id,workspace_id,created_at) VALUES('h','dependency','ws',?)", (NOW,))
    policy = {"handoff_unclaimed_seconds": 60}
    assert not only(db, "handoff_unclaimed_aged", now=LATER, policy=policy)
    db.execute("UPDATE handoffs SET status='COMPLETED',updated_at=? WHERE handoff_id='dependency'", (LATER,))
    assert not only(db, "handoff_unclaimed_aged", now=LATER, policy=policy)
    item = only(db, "handoff_unclaimed_aged", now="2026-11-06T13:01:00+00:00", policy=policy)[0]
    assert item["first_detected_at"] == "2026-11-06T13:01:00.000000+00:00"


def test_timestamp_offsets_and_backfill_observation_do_not_invert_history(db):
    execution(db, state="RECONCILING")
    receipt(db)
    db.execute("UPDATE attention_operation_epochs SET first_detected_at='2026-11-06T13:00:00+00:00',last_changed_at='2026-11-06T13:00:00+00:00' WHERE source_type='execution_dispatch'")
    item = only(db, "execution_outcome_unknown", now=LATER)[0]
    assert item["first_detected_at"] == item["last_changed_at"] == "2026-11-06T13:00:00.000000+00:00"


@pytest.fixture
def cleanup_service(migrated_factory, monkeypatch):
    """Real maintenance/repository; authority is outside this focused failure test."""
    with migrated_factory.unit_of_work() as uow:
        c = uow.connection
        seed(c)
        managed_operation(c)
        canonical_result(c, terminal=1)
        c.execute("INSERT INTO runtime_results(result_id,payload,publication_state,captured_at,operation_id,output_text,artifact_reserved_bytes,delivery_outcome,canonical_server_id,canonical_executor_id,canonical_operation_id) "
                  "VALUES('result','{}','BLOCKED',?,'domain-op',?,4096,'success','s','e','op')", (NOW, 'x' * 60001))
    clock = FakeClock(iso=NOW)
    owner = SimpleNamespace(cf=migrated_factory, clock=clock)
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise OSError("fixture lost cleanup response")

    artifacts = SimpleNamespace(discard_unpublished=fail)
    service = RuntimeMaintenanceService(access=SimpleNamespace(authorize=lambda *args, **kwargs: None,
        authorize_maintenance=lambda *args, **kwargs: None, cf=migrated_factory),
                                        dispatcher=owner, artifact_store=artifacts)
    monkeypatch.setattr(service, "_authorize_owner", lambda context: owner)
    return service, migrated_factory, artifacts, calls, clock


def cleanup(service):
    return service.artifacts(SimpleNamespace(actor_agent_id="operator"), action="cleanup",
                             result_id="result", idempotency_key="cleanup", reason="Reconcile unpublished reservation")


def test_explicit_cleanup_failure_preserves_success_and_has_stable_episode_until_done(cleanup_service):
    service, factory, artifacts, calls, clock = cleanup_service
    with factory.unit_of_work(write=False) as uow:
        before = dict(uow.connection.execute("SELECT * FROM execution_results").fetchone())
        assert not only(uow.connection, "cleanup_attention")
    with pytest.raises(OktoNexusError) as first_error:
        cleanup(service)
    assert first_error.value.details["attention_recorded"] is True
    with factory.unit_of_work(write=False) as uow:
        first = only(uow.connection, "cleanup_attention")[0]
        assert dict(uow.connection.execute("SELECT * FROM execution_results").fetchone()) == before
    clock.set_iso(LATER)
    with pytest.raises(OktoNexusError) as second_error:
        cleanup(service)
    assert first_error.value.details["maintenance_id"] == second_error.value.details["maintenance_id"]
    assert len(calls) == 2
    with factory.unit_of_work(write=False) as uow:
        assert only(uow.connection, "cleanup_attention")[0] == first
    artifacts.discard_unpublished = lambda **kwargs: {"absent": True, "removed_directories": []}
    assert cleanup(service)["state"] == "DONE"
    with factory.unit_of_work(write=False) as uow:
        assert not only(uow.connection, "cleanup_attention")
        assert dict(uow.connection.execute("SELECT * FROM execution_results").fetchone()) == before
        assert uow.connection.execute("SELECT delivery_outcome FROM runtime_results").fetchone()[0] == "success"


def test_cleanup_diagnostic_write_failure_retains_receipt_without_repeating_effect(cleanup_service):
    service, factory, _, calls, _ = cleanup_service
    with factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_attention_marker BEFORE UPDATE OF attention_failure_at ON runtime_result_maintenance BEGIN SELECT RAISE(ABORT,'fixture marker failure'); END")
    with pytest.raises(OktoNexusError) as error:
        cleanup(service)
    assert error.value.details["attention_recorded"] is False
    assert error.value.details["cleanup_outcome"] == "unconfirmed" and len(calls) == 1
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM runtime_result_maintenance").fetchone()
        assert row["maintenance_id"] == error.value.details["maintenance_id"] and row["status"] == "PENDING"
        assert row["attention_failure_at"] is None
        assert not only(uow.connection, "cleanup_attention")
        assert uow.connection.execute("SELECT delivery_outcome FROM execution_results").fetchone()[0] == "success"


def test_idle_warm_preparation_is_not_disconnected_productive_work(db):
    execution(db, state="RESERVED")
    db.execute("UPDATE execution_executors SET control_state='DISCONNECTED'")
    assert only(db, "executor_disconnected_with_work")
    db.execute("INSERT INTO one_shot_slots(slot_id,executor_id,agent_id,configuration_digest,state,created_at,server_id,open_operation_id) "
               "VALUES('warm','e','worker','digest','STARTING',0,'s','op')")
    assert not only(db, "executor_disconnected_with_work")


def test_delivery_retention_removes_its_auxiliary_anchor(db):
    delivery(db, status="read")
    assert db.execute("SELECT 1 FROM attention_operation_epochs WHERE source_type='message_delivery' AND source_id='d'").fetchone()
    db.execute("DELETE FROM message_deliveries WHERE delivery_id='d'")
    assert not db.execute("SELECT 1 FROM attention_operation_epochs WHERE source_type='message_delivery' AND source_id='d'").fetchone()


def test_implicit_operator_uses_same_verifier_identity_and_permissions_as_endpoint(db):
    handoff(db)
    db.execute("UPDATE agents SET is_active=0 WHERE agent_id='operator'")
    kwargs = dict(config=SimpleNamespace(), access=None, context=SimpleNamespace(actor_agent_id=None), now=NOW)
    policy = build_policy(SimpleNamespace(connection=db), **kwargs)
    assert "verify_handoff" in only(db, "verification_pending", policy=policy)[0]["allowed_actions"]
    db.execute("UPDATE agents SET permissions='{\"handoffs\":{\"work\":false}}' WHERE agent_id='operator'")
    policy = build_policy(SimpleNamespace(connection=db), **kwargs)
    assert "verify_handoff" not in only(db, "verification_pending", policy=policy)[0]["allowed_actions"]


def test_disconnection_threshold_accepts_native_sqlite_timestamp_precision(db):
    execution(db)
    db.execute("UPDATE execution_executors SET control_state='DISCONNECTED'")
    db.execute("UPDATE attention_operation_epochs SET first_detected_at='2026-11-06T09:00:00.123-03:00',last_changed_at='2026-11-06T12:00:00.123Z' WHERE source_type='execution_executor'")
    item = only(db, "executor_disconnected_with_work", now=LATER, policy={"executor_disconnected_seconds": 60})[0]
    assert item["first_detected_at"] == "2026-11-06T12:00:00.123000+00:00"
    assert item["last_changed_at"] == "2026-11-06T12:01:00.123000+00:00"
