"""Closed-session settlement never mistakes a transport attempt for unsent work."""
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


@pytest.mark.parametrize("guard", ["unsent", "live", "sending", "prior_attempt", "other_subject"])
def test_only_never_dispatched_work_on_a_closed_session_is_settled(connected_local, guard):
    from okto_nexus.application.execution_initial_turns import settle_unsent_closed_session_operations
    setup, binding, _ = connected_local
    opened = admit(setup, binding, "queued-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    sid = opened["scope"]["session_id"]
    active = admit(setup, binding, "active-turn", "turn.submit", session_id=sid, text="Active")
    wait_receipt(setup, active)
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    queued = admit(setup, binding, "queued-turn", "turn.submit", session_id=sid, text="Queued")
    class Rollback(Exception):
        pass
    # Exercise the storage predicate in a rolled-back transaction. Actual
    # process-release proof and automatic restoration use a real Codex peer in
    # test_canonical_result_correlation.
    with pytest.raises(Rollback):
        with setup[0].connection_factory.unit_of_work() as uow:
            conn = uow.connection
            row = dict(conn.execute("SELECT * FROM execution_dispatch_outbox WHERE operation_id=?", (queued["operation_id"],)).fetchone())
            assert row["dispatch_state"] == "PENDING" and row["attempt_no"] == 0
            if guard != "live":
                conn.execute("UPDATE execution_sessions SET lifecycle_state='CLOSED',lease_state='CLOSED' WHERE session_id=?", (sid,))
            if guard == "sending":
                conn.execute("UPDATE execution_dispatch_outbox SET dispatch_state='SENDING' WHERE operation_id=?", (queued["operation_id"],))
            if guard == "prior_attempt":
                conn.execute("UPDATE execution_dispatch_outbox SET attempt_no=1 WHERE operation_id=?", (queued["operation_id"],))
            before = dict(conn.execute("SELECT * FROM execution_dispatch_outbox WHERE operation_id=?", (queued["operation_id"],)).fetchone())
            settle_unsent_closed_session_operations(conn, server_id=row["server_id"], executor_id=row["executor_id"],
                agent_id="other" if guard == "other_subject" else "subject")
            after = dict(conn.execute("SELECT * FROM execution_dispatch_outbox WHERE operation_id=?", (queued["operation_id"],)).fetchone())
            if guard == "unsent":
                assert after["dispatch_state"] == "RESOLVED_TERMINAL"
                assert '"possible_effect": false' in after["last_error"]
                assert conn.execute("SELECT admission_state FROM execution_operations WHERE operation_id=?", (queued["operation_id"],)).fetchone()[0] == "RESOLVED_TERMINAL"
            else:
                assert after == before
            assert conn.execute("SELECT COUNT(*) FROM execution_receipts WHERE operation_id=?", (queued["operation_id"],)).fetchone()[0] == 0
            assert conn.execute("SELECT admission_state FROM execution_operations WHERE operation_id=?", (active["operation_id"],)).fetchone()[0] != "RESOLVED_TERMINAL"
            raise Rollback()
