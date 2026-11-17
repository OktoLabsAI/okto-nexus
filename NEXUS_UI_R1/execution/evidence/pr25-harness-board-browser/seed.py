"""Small owned canonical relation facts; no extra native execution/admission."""
import json


def prepare_r3(s, identities):
    with s.factory.unit_of_work() as uow:
        c=uow.connection
        # This fixture's second session is CLOSED synthetic retained history.
        # No actual host resources exist: omit its synthetic containment request.
        c.execute("DELETE FROM execution_session_containment WHERE session_id='ui-session-2'")
        # A separate retained public handoff avoids inventing a native/session
        # association. Its actionability still comes from canonical policy.
        from tests.ui_simplification.test_fixtures import fixtures
        row=c.execute("SELECT * FROM handoffs WHERE handoff_id='ui-unassigned'").fetchone()
        fixtures._copy(c,'handoffs',row,handoff_id='r3-operator-handoff',visibility='public',status='VERIFYING',claimed_by='B',claim_epoch=1,
            verify_by=json.dumps({'kind':'agent','agent_id':'operator'}),result='Synthetic report for operator verification.')
    identities['r3_fixture']={'registered_bindings':['binding','ui-binding-2'],'initial_phase':'Canonical admitted pending blocking input plus closed synthetic history/result.','operator_handoff':'r3-operator-handoff; separate public retained handoff, another claimant, explicit operator verifier. Qualify only if actual HTTP exposes verify_handoff.','second_phase':'Explicit add_parallel marker adds a scoped RUNNING operation/session READ FACT on binding; not actual native execution.','unchanged_authority':'No operator permission, recipient, grant, ticket or native request TTL changed.'}


def add_parallel(s):
    from tests.ui_simplification.test_harness_board import add_parallel_running_read_fact
    add_parallel_running_read_fact(s)
