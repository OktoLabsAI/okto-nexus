"""Lease timer, expiry and silence notices, handoff_get fields (#92)."""
import json
import sqlite3

import pytest

from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service as build_handoff_service
from okto_nexus.adapters.outbound.sqlite.handoff_runtime_schedule import SqliteHandoffScheduleRepository
from okto_nexus.application.execution_release_notifications import notify_contained_claimant
from okto_nexus.application.handoff_runtime_scheduler import HandoffRuntimeScheduler
from okto_nexus.application.settings import _coerce, _SPEC_BY_KEY
from okto_nexus.config import NexusConfig, load_config
from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError
from test_handoff_outcome_push import claim, env, pushed, runtime_for, build_service as build_message_service
from test_handoff_dependencies import _ok

__all__ = ["env"]


def set_lease(deps, hid, seconds_from_now):
    now = deps.clock.now_iso()
    conn = deps.connection_factory.get_connection()
    try:
        conn.execute("UPDATE handoffs SET lease_expires_at=? WHERE handoff_id=?", (iso_plus(now, seconds_from_now), hid))
    finally:
        conn.close()


def watch(deps):
    service = build_handoff_service(deps)
    with deps.connection_factory.unit_of_work() as uow:
        return service.watch_leases(uow)


def rows(deps, sql, *args):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [dict(r) for r in uow.connection.execute(sql, args)]


def say(deps, workspace, sender, recipient, text="working", kind=None, tag="a"):
    """Send a plain message from ``sender`` to ``recipient``."""
    service = build_message_service(deps)
    now = deps.clock.now_iso()
    body = json.dumps({"kind": kind}) if kind else text
    with deps.connection_factory.unit_of_work() as uow:
        mid = f"msg_say_{sender}_{tag}"
        service._messages.create(uow, message_id=mid, workspace_id=workspace, from_agent_id=sender, channel_id=None,
            from_session_id=None, target=json.dumps(dict(strategy="direct", agent_id=recipient)), subject="s", body=body,
            artifacts=[], parent_message_id=None, trace_id=None, created_at=now)
        service._deliveries.create(uow, delivery_id="del_" + mid, message_id=mid, recipient_agent_id=recipient,
            status="unread", created_at=now)


def test_expiry_runs_in_the_scheduler_sweep_and_pushes_to_creator_and_claimant(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha", "beta")
    hid = claim(tools, root)
    set_lease(deps, hid, -5)
    service = build_handoff_service(deps)
    scheduler = HandoffRuntimeScheduler(factory=deps.connection_factory, repository=SqliteHandoffScheduleRepository(),
        processor=None, lease_watch=service.watch_leases)
    scheduler._reserve_page(False, True, (), 0)  # the sweep, with no caller of handoff_list/get
    assert rows(deps, "SELECT status,claimed_by FROM handoffs WHERE handoff_id=?", hid) == [{"status": "OPEN", "claimed_by": None}]
    got = pushed(deps, hid)
    assert [(r["recipient_agent_id"], r["event_type"], r["runtime_route"], r["status"]) for r in got] == [
        ("alpha", "handoff.lease_expired:1", "conversation", "waiting"),
        ("beta", "handoff.lease_expired:1", "conversation", "waiting")]
    senders = rows(deps, "SELECT n.recipient_agent_id r,m.from_agent_id f,m.body b FROM runtime_handoff_notifications n "
                         "JOIN messages m USING(message_id) WHERE n.handoff_id=? AND n.event_type LIKE '%:%' ORDER BY 1", hid)
    assert [(r["r"], r["f"]) for r in senders] == [("alpha", "beta"), ("beta", "alpha")]
    assert json.loads(senders[1]["b"])["previous_claimed_by"] == "beta"
    assert watch(deps) == 0  # a second sweep finds nothing and sends nothing
    assert len(pushed(deps, hid)) == 2


def test_notify_expiry_off_reopens_without_a_notice(env):
    deps, tools, root, workspace = env
    deps.config.handoff_notify_expiry = False
    runtime_for(deps, workspace, "alpha", "beta")
    hid = claim(tools, root)
    set_lease(deps, hid, -5)
    assert watch(deps) == 1
    assert pushed(deps, hid) == []


def test_sweep_with_no_claimed_handoff_is_one_indexed_probe(env):
    deps, tools, root, workspace = env
    statements = []
    conn = deps.connection_factory.get_connection()
    try:
        service = build_handoff_service(deps)
        conn.set_trace_callback(statements.append)
        class Uow:
            connection = conn
        assert service.watch_leases(Uow()) == 0
        conn.set_trace_callback(None)
        plan = conn.execute("EXPLAIN QUERY PLAN SELECT MIN(lease_expires_at) FROM handoffs WHERE status='CLAIMED'").fetchall()
    finally:
        conn.close()
    assert [s for s in statements if s.startswith("SELECT")] == ["SELECT MIN(lease_expires_at) FROM handoffs WHERE status='CLAIMED'"]
    assert any("idx_handoffs_claimed_lease" in str(r[-1]) for r in plan), plan


def test_not_yet_due_claim_costs_nothing_more(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha", "beta")
    hid = claim(tools, root)  # lease is the full 3600 s
    assert watch(deps) == 0
    assert rows(deps, "SELECT count(*) c FROM handoff_silence_notices") == [{"c": 0}]
    assert pushed(deps, hid) == []


def test_silence_notice_once_per_epoch_with_details(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha", "beta")
    hid = claim(tools, root)
    set_lease(deps, hid, 1000)  # 2600 s of the 3600 s lease passed
    watch(deps)
    watch(deps)
    got = pushed(deps, hid)
    assert [(r["recipient_agent_id"], r["event_type"]) for r in got] == [("alpha", "handoff.claimant_silent:1")]
    body = json.loads(rows(deps, "SELECT m.body b FROM runtime_handoff_notifications n JOIN messages m USING(message_id) "
                                 "WHERE n.handoff_id=?", hid)[0]["b"])
    assert body["claimed_by"] == "beta" and 43 <= body["minutes_silent"] <= 44
    assert body["lease_expires_at"] and len(body["options"]) == 3 and "claimant_session" in body
    assert rows(deps, "SELECT count(*) c FROM messages WHERE body LIKE '%claimant_silent%'") == [{"c": 1}]
    # The handoff stays CLAIMED: the notice does not touch the claim.
    assert rows(deps, "SELECT status FROM handoffs WHERE handoff_id=?", hid) == [{"status": "CLAIMED"}]


def test_a_new_claim_epoch_gets_its_own_silence_notice(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha", "beta")
    hid = claim(tools, root)
    set_lease(deps, hid, 1000)
    watch(deps)
    set_lease(deps, hid, -5)
    watch(deps)  # expiry
    _ok(tools["handoff_claim"](project_root=root, handoff_id=hid, agent_id="beta"))
    set_lease(deps, hid, 1000)
    watch(deps)
    kinds = sorted(r["event_type"] for r in pushed(deps, hid) if r["recipient_agent_id"] == "alpha")
    assert kinds == ["handoff.claimant_silent:1", "handoff.claimant_silent:2", "handoff.lease_expired:1"]


def test_progress_message_suppresses_the_warning_and_system_notices_do_not_count(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha", "beta")
    hid = claim(tools, root)
    set_lease(deps, hid, 1000)
    say(deps, workspace, "beta", "alpha", "still on it")
    watch(deps)
    assert pushed(deps, hid) == []
    assert rows(deps, "SELECT count(*) c FROM handoff_silence_notices") == [{"c": 0}]  # checked again next sweep


def test_a_system_notice_from_the_claimant_is_not_progress(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha", "beta")
    hid = claim(tools, root)
    set_lease(deps, hid, 1000)
    say(deps, workspace, "beta", "alpha", kind="handoff.lease_expired", tag="sys")
    watch(deps)
    assert [r["event_type"] for r in pushed(deps, hid)] == ["handoff.claimant_silent:1"]


def test_silence_warning_is_skipped_after_a_containment_notice(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha")
    hid = claim(tools, root)
    notify_contained_claimant(deps, build_message_service(deps), server_id="server", executor_id="executor",
        session_id="session-1", agent_id="beta", reason="EVENT_OPERATION_MISMATCH")
    set_lease(deps, hid, 1000)
    watch(deps)
    assert [r["event_type"].split(":")[0] for r in pushed(deps, hid)] == ["handoff.claimant_contained"]
    assert rows(deps, "SELECT count(*) c FROM messages WHERE body LIKE '%claimant_silent%'") == [{"c": 0}]


def test_fraction_zero_turns_the_warning_off(env):
    deps, tools, root, workspace = env
    deps.config.handoff_silence_warn_fraction = 0.0
    runtime_for(deps, workspace, "alpha", "beta")
    hid = claim(tools, root)
    set_lease(deps, hid, 100)
    watch(deps)
    assert pushed(deps, hid) == []


def add_session(deps, workspace, agent, state="OPEN", error=None):
    conn = deps.connection_factory.get_connection()
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO execution_operations(server_id,executor_id,operation_id,subject_agent_id,actor_agent_id,binding_id,"
                     "workspace_id,workspace_binding_id,session_id,action,intent_hash,semantic_payload,expected_revisions_json,"
                     "admission_state,created_at) VALUES('s','e','op1',?,?,'b',?,'wb','sess','turn.submit','h','{}','{}','ADMITTED','2026-01-01T00:00:00Z')",
                     (agent, agent, workspace))
        conn.execute("INSERT INTO execution_sessions(server_id,executor_id,session_id,binding_id,workspace_id,workspace_binding_id,"
                     "open_operation_id,owner_generation,lifecycle_state,lease_state) VALUES('s','e','sess','b',?,'wb','op0',1,?,'HELD')",
                     (workspace, state))
        conn.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,"
                     "possible_effect,retry_safe,error_code,received_at) VALUES('s','e','op1',1,'h','FAILED',0,0,?,'2026-01-01T00:05:00Z')", (error,))
    finally:
        conn.close()


def test_handoff_get_shows_progress_and_session_to_creator_and_claimant_only(env):
    deps, tools, root, workspace = env
    hid = claim(tools, root)
    say(deps, workspace, "beta", "alpha", "halfway")
    try:
        add_session(deps, workspace, "beta", "OPEN", "TURN_TIMEOUT")
    except sqlite3.Error as exc:  # pragma: no cover - schema drift guard
        pytest.fail(str(exc))
    for agent in ("alpha", "beta"):
        got = _ok(tools["handoff_get"](project_root=root, handoff_id=hid, agent_id=agent))
        assert got["claimant_session"] == {"state": "OPEN", "last_turn_end_at": "2026-01-01T00:05:00Z",
                                           "last_error_code": "TURN_TIMEOUT"}
    progress = rows(deps, "SELECT created_at c FROM messages WHERE message_id='msg_say_beta_a'")[0]["c"]
    assert _ok(tools["handoff_get"](project_root=root, handoff_id=hid, agent_id="alpha"))["last_progress_at"] == progress
    third = _ok(tools["handoff_get"](project_root=root, handoff_id=hid, agent_id="gamma"))
    assert "last_progress_at" not in third and "claimant_session" not in third


def test_handoff_get_of_an_unclaimed_handoff_is_unchanged(env):
    deps, tools, root, workspace = env
    hid = _ok(tools["handoff_create"](project_root=root, from_agent_id="alpha",
        target={"strategy": "direct", "agent_id": "beta"}, visibility="public"))["handoff_id"]
    got = _ok(tools["handoff_get"](project_root=root, handoff_id=hid, agent_id="alpha"))
    # Golden key set of an OPEN handoff before #92. Only a claimed handoff gets new keys.
    assert sorted(got) == sorted(["handoff_id", "workspace_id", "status", "from_agent_id", "target", "visibility",
        "claimed_by", "claim_epoch", "lease_expires_at", "result", "rejected_reason", "created_at", "updated_at"])
    assert got["status"] == "OPEN" and got["claimed_by"] is None


def test_settings_defaults_bounds_and_env():
    config = NexusConfig()
    assert config.handoff_notify_expiry is True and config.handoff_silence_warn_fraction == 0.5
    spec = _SPEC_BY_KEY["handoff_silence_warn_fraction"]
    assert _coerce(spec, "0.25") == 0.25 and _coerce(spec, 0) == 0.0
    for bad in (-0.1, 1.5, "x", float("nan"), True):
        with pytest.raises(OktoNexusError):
            _coerce(spec, bad)
    assert _coerce(_SPEC_BY_KEY["handoff_notify_expiry"], "false") is False
    resolved = load_config({"OKTO_NEXUS_HANDOFF_SILENCE_WARN_FRACTION": "0.75", "OKTO_NEXUS_HANDOFF_NOTIFY_EXPIRY": "false"}, [])
    assert (resolved.handoff_silence_warn_fraction, resolved.handoff_notify_expiry) == (0.75, False)
    with pytest.raises(OktoNexusError):
        load_config({}, ["--handoff-silence-warn-fraction", "2"])
