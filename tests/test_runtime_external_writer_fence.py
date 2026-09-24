"""An already-open writer-v1 cannot bypass external work proof after upgrade."""
import sqlite3

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_attach_work_channel import admitted, complete_fixture_work

runtime = runtime_fixture


@pytest.mark.parametrize("destination", ["COMPLETED", "VERIFYING", "REJECTED"])
def test_legacy_writer_cannot_complete_external_work_without_the_new_contract(runtime, destination):
    deps, _, _, _, _, _ = runtime
    admission = admitted(runtime)
    handoff, _, _, _, accepted, _ = admission
    # Match the v1 marker of a pre-064 connection and the old canonical
    # claimant/epoch-fenced transition. No new proof capability is registered.
    legacy = sqlite3.connect(deps.config.db_path, isolation_level=None)
    legacy.create_function("nexus_runtime_writer_v1", 0, lambda: 1)
    try:
        legacy.execute("PRAGMA foreign_keys=ON")
        legacy.execute("PRAGMA synchronous=FULL")
        with pytest.raises(sqlite3.IntegrityError, match="runtime_external_work_writer_incompatible"):
            legacy.execute("UPDATE handoffs SET status=?,result=?,updated_at=? "
                "WHERE handoff_id=? AND claimed_by=? AND claim_epoch=? AND status='CLAIMED'",
                (destination, "unproved old-writer completion", deps.clock.now_iso(), handoff, "worker", accepted["data"]["claim_epoch"]))
        # The store also fences consumption of this specific external work,
        # while its ordinary writer-v1 compatibility rules remain unchanged.
        with pytest.raises(sqlite3.IntegrityError, match="runtime_external_work_writer_incompatible"):
            legacy.execute("UPDATE message_deliveries SET status='read',read_at=? WHERE consumer_operation_id=?",
                (deps.clock.now_iso(), admission[-1]["operation_id"]))
    finally:
        legacy.close()
    complete_fixture_work(runtime, "complete", admission)


def test_external_work_session_is_retained_without_blocking_canonical_retention(runtime):
    from okto_nexus.domain.base import iso_plus
    deps, client, _, _, _, _ = runtime
    admission = admitted(runtime)
    complete_fixture_work(runtime, "complete", admission)
    _, worker_key, proof, _, _, operation = admission
    unrelated = tool(client, worker_key, "session_open", {"agent_id": "worker", "workspace_id": operation["workspace_id"]})
    assert unrelated["ok"], unrelated
    unrelated_id = unrelated["data"]["session_id"]
    for session_id in [proof["session_id"], unrelated_id]:
        closed = tool(client, worker_key, "session_close", {"session_id": session_id})
        assert closed["ok"], closed
    cutoff = iso_plus(deps.clock.now_iso(), 60)
    with deps.connection_factory.unit_of_work() as uow:
        # These are the same count/delete primitives used by RetentionService.
        before = deps.repos.sessions.count_closed_before(uow, cutoff=cutoff)
        assert deps.repos.sessions.prune_closed_before(uow, cutoff=cutoff, limit=100) == 1
        assert before == 1
        assert deps.repos.sessions.count_closed_before(uow, cutoff=cutoff) == 0
        assert deps.repos.sessions.get(uow, proof["session_id"]) is not None
        assert deps.repos.sessions.get(uow, unrelated_id) is None
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()


def test_recovered_external_claim_does_not_block_direct_rejection_of_open_work(runtime):
    from test_runtime_handoff_recovery import recovery
    deps, client, root, peers, operator, _ = runtime
    handoff, worker_key, _, _, accepted, operation = admitted(runtime)
    deps.harness_supervisor.close(operation["runtime_session_id"])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = dict(uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?", (operation["operation_id"],)).fetchone())
    recovered = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator},
        json=recovery(handoff, accepted["data"]["claim_epoch"], row))
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["data"]["handoff"]["status"] == "OPEN"
    rejected = tool(client, worker_key, "handoff_reject", {"project_root": root, "handoff_id": handoff,
        "agent_id": "worker", "reason": "Decline the reopened offer"})
    assert rejected["ok"], rejected
    assert sum(len(peer.sent) for peer in peers) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        prior = uow.connection.execute("SELECT external_completion_action FROM runtime_handoff_bindings WHERE operation_id=?", (operation["operation_id"],)).fetchone()
        assert prior[0] is None  # Rejection of the new OPEN offer is not an old-runtime response.
